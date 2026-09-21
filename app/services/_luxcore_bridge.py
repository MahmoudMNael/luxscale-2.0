"""OOP bridge between the Python services and the C++ ``luxcore`` extension.

Architecture (Hybrid plan):
- Python/Shapely keeps boolean geometry (inset rings, buffered visibility
  polygon, convexity). C++ owns hot numeric loops over already-prepared
  vertex rings (Strategy: transparent vs buffered-ring policy in C++).
- Services keep their public signatures; they ask this bridge first and
  fall back to the pure-Python implementation on any failure, so
  ``LUXCORE_ENABLED=0`` or a missing build never breaks the API.
- All NumPy exchange is struct-of-arrays (centres/normals/areas), GIL is
  released inside C++ (nanobind ``gil_scoped_release`` + OpenMP).

Classes:
- ``LuxCoreConfig`` — env-driven settings (enabled flag, thread count).
- ``LuxCoreRuntime`` — lazy ``import luxcore`` + thread control (Singleton).
- ``PatchSoAConverter`` — ``Patch`` lists <-> SoA NumPy views.
- ``VisibilityContext`` / ``VisibilityContextBuilder`` — Shapely -> (convex, ring).
- ``IesHandleCache`` — ``IESProfile`` -> ``luxcore.IesProfile`` (per-id cache).
- ``LuxCoreDirectEngine`` / ``LuxCoreRadiositySolver`` / ``LuxCoreGeometry`` /
  ``LuxCoreMatrix`` — thin OOP facades over the extension functions.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Any

import numpy as np

_log = logging.getLogger(__name__)

_SURFACE_TO_INT = {"wall": 0, "floor": 1, "ceiling": 2}


class LuxCoreConfig:
    """Environment-driven settings (value object)."""

    def __init__(
        self,
        enabled: bool | None = None,
        threads: int | None = None,
    ) -> None:
        if enabled is None:
            enabled = os.environ.get("LUXCORE_ENABLED", "1") != "0"
        if threads is None:
            raw = os.environ.get("LUXCORE_THREADS", os.environ.get("OMP_NUM_THREADS", "0"))
            try:
                threads = int(raw)
            except ValueError:
                threads = 0
        self.enabled = enabled
        self.threads = threads or 0

    def __repr__(self) -> str:  # pragma: no cover
        return f"LuxCoreConfig(enabled={self.enabled}, threads={self.threads})"


class LuxCoreRuntime:
    """Singleton managing the optional ``luxcore`` extension import."""

    _instance: LuxCoreRuntime | None = None
    _module: Any | None = None
    _tried_import = False

    def __new__(cls, config: LuxCoreConfig | None = None) -> LuxCoreRuntime:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance.config = config or LuxCoreConfig()
        elif config is not None:
            cls._instance.config = config
        return cls._instance

    @property
    def module(self) -> Any | None:
        if not self.config.enabled:
            return None
        if not self._tried_import:
            self._tried_import = True
            try:
                import luxcore as _mod  # type: ignore[import-not-found]

                self._module = _mod
                try:
                    _mod.set_threads(self.config.threads)
                except Exception:  # pragma: no cover
                    pass
                _log.info(
                    "luxcore backend active (%s, openmp=%s)",
                    getattr(_mod, "__version__", "?"),
                    getattr(_mod, "has_openmp", "?"),
                )
            except Exception as exc:
                _log.info("luxcore unavailable, using Python fallback (%s)", exc)
                self._module = None
        return self._module

    def is_available(self) -> bool:
        return self.module is not None

    def set_threads(self, n: int) -> int:
        mod = self.module
        if mod is None:
            return 0
        return int(mod.set_threads(n))

    def backend_name(self) -> str:
        mod = self.module
        if mod is None:
            return "python"
        try:
            return str(mod.backend())
        except Exception:  # pragma: no cover
            return "luxcore"


@dataclass(frozen=True)
class PatchSoA:
    centers: np.ndarray  # (N,3) float64
    normals: np.ndarray  # (N,3) float64
    areas: np.ndarray  # (N,) float64
    sizes: np.ndarray  # (N,) float64
    surfaces: np.ndarray  # (N,) int32


class PatchSoAConverter:
    """Converts domain ``Patch`` lists to SoA NumPy (zero-copy friendly)."""

    @staticmethod
    def from_patches(patches: list[Any]) -> PatchSoA:
        n = len(patches)
        centers = np.empty((n, 3), dtype=np.float64)
        normals = np.empty((n, 3), dtype=np.float64)
        areas = np.empty(n, dtype=np.float64)
        sizes = np.empty(n, dtype=np.float64)
        surfaces = np.empty(n, dtype=np.int32)
        for i, p in enumerate(patches):
            c = p.center
            nn = p.normal
            centers[i, 0] = c[0]
            centers[i, 1] = c[1]
            centers[i, 2] = c[2]
            normals[i, 0] = nn[0]
            normals[i, 1] = nn[1]
            normals[i, 2] = nn[2]
            areas[i] = p.area
            sizes[i] = p.size
            surfaces[i] = _SURFACE_TO_INT.get(getattr(p, "surface_type", "wall"), 0)
        return PatchSoA(centers, normals, areas, sizes, surfaces)

    @staticmethod
    def centers_normals(patches: list[Any]) -> tuple[np.ndarray, np.ndarray]:
        soa = PatchSoAConverter.from_patches(patches)
        return soa.centers, soa.normals


@dataclass(frozen=True)
class VisibilityContext:
    convex: bool
    ring: np.ndarray  # (K,2) float64 buffered exterior (empty when convex)


class VisibilityContextBuilder:
    """Builds the Hybrid visibility input from a room polygon.

    Convex rooms skip occlusion entirely (matches Python fast path).
    Concave rooms pass the Shapely-buffered exterior ring vertices to C++,
    which runs the per-segment predicate without per-pair Python objects.
    """

    _cache: dict[tuple, VisibilityContext] = {}

    @classmethod
    def build(cls, room_polygon: list[tuple[float, float]] | Any | None) -> VisibilityContext:
        if room_polygon is None:
            return VisibilityContext(True, np.zeros((0, 2), dtype=np.float64))
        if not isinstance(room_polygon, list):
            # Shapely/prepared polygons: keep exact Python semantics.
            raise _UsePythonFallback
        key = tuple((round(float(x), 9), round(float(y), 9)) for x, y in room_polygon)
        hit = cls._cache.get(key)
        if hit is not None:
            return hit
        from app.services.vector_math import (  # noqa: PLC0415
            is_convex_polygon,
            visibility_polygon,
        )

        if is_convex_polygon(list(room_polygon)):
            ctx = VisibilityContext(True, np.zeros((0, 2), dtype=np.float64))
        else:
            poly = visibility_polygon(list(room_polygon))
            try:
                coords = list(poly.exterior.coords)
            except Exception:
                coords = list(room_polygon)
            ring = np.asarray([(float(x), float(y)) for x, y, *_ in coords], dtype=np.float64)
            ctx = VisibilityContext(False, np.ascontiguousarray(ring))
        if len(cls._cache) < 64:
            cls._cache[key] = ctx
        return ctx


class _UsePythonFallback(Exception):
    pass


class IesHandleCache:
    """Caches ``luxcore.IesProfile`` per Python profile id (fixtures share one)."""

    _cache: dict[int, Any] = {}

    @classmethod
    def get(cls, profile: Any) -> Any:
        mod = LuxCoreRuntime().module
        if mod is None:
            raise _UsePythonFallback
        key = id(profile)
        hit = cls._cache.get(key)
        if hit is not None:
            return hit
        table = profile.candela_table
        nv = len(profile.vertical_angles)
        nh = len(profile.horizontal_angles)
        flat = np.asarray(table, dtype=np.float64).reshape(nv, nh).ravel()
        handle = mod.IesProfile(
            np.asarray(profile.vertical_angles, dtype=np.float64),
            np.asarray(profile.horizontal_angles, dtype=np.float64),
            np.ascontiguousarray(flat),
            nv,
            nh,
            float(profile.multiplier),
            float(profile.ballast_factor),
            float(profile.ballast_lamp_factor),
            float(profile.flux_scale),
            float(profile.width),
            float(profile.length),
            float(profile.height),
        )
        if len(cls._cache) < 32:
            cls._cache[key] = handle
        return handle

    @classmethod
    def clear(cls) -> None:
        cls._cache.clear()


class LuxCoreDirectEngine:
    """Direct I/N-sum via C++ (OpenMP over patches, GIL released)."""

    def __init__(self, runtime: LuxCoreRuntime | None = None) -> None:
        self._rt = runtime or LuxCoreRuntime()

    def compute_values(
        self,
        fixture: Any,
        patches: list[Any],
        *,
        c0_offset_deg: float = 0.0,
        room_polygon: list[tuple[float, float]] | Any | None = None,
    ) -> list[float]:
        mod = self._rt.module
        if mod is None or not patches:
            raise _UsePythonFallback
        if room_polygon is not None and not isinstance(room_polygon, list):
            raise _UsePythonFallback
        soa = PatchSoAConverter.from_patches(patches)
        ies = IesHandleCache.get(fixture.ies_profile)
        pos = np.asarray(fixture.position, dtype=np.float64)
        aim = np.asarray(fixture.aim_direction, dtype=np.float64)
        # Luminous element sample points (mirrors fixture_service, in C++).
        origins = np.asarray(
            mod.luminous_elements(
                [float(pos[0]), float(pos[1]), float(pos[2])],
                float(fixture.rotation),
                float(fixture.ies_profile.length),
                float(fixture.ies_profile.width),
            ),
            dtype=np.float64,
        )
        ctx = VisibilityContextBuilder.build(room_polygon)
        out = mod.direct_compute(
            np.ascontiguousarray(pos),
            np.ascontiguousarray(aim),
            float(fixture.rotation),
            float(c0_offset_deg),
            ies,
            np.ascontiguousarray(soa.centers),
            np.ascontiguousarray(soa.normals),
            np.ascontiguousarray(origins),
            np.ascontiguousarray(ctx.ring),
            bool(ctx.convex),
            int(self._rt.config.threads),
        )
        return [float(v) for v in np.asarray(out).ravel().tolist()]


class LuxCoreRadiositySolver:
    """Interreflection Neumann-series solver via C++."""

    def __init__(self, runtime: LuxCoreRuntime | None = None) -> None:
        self._rt = runtime or LuxCoreRuntime()

    def solve(
        self,
        sources: list[Any],
        seeds: dict[str, list[float]],
        targets: dict[str, list[Any]],
        *,
        wall_reflectance: float,
        num_bounces: int,
        room_polygon: list[tuple[float, float]] | None,
        floor_reflectance: float = 0.0,
        ceiling_reflectance: float = 0.0,
    ) -> dict[str, dict[str, list[float]]]:
        mod = self._rt.module
        if mod is None:
            raise _UsePythonFallback
        if room_polygon is not None and not isinstance(room_polygon, list):
            raise _UsePythonFallback
        src = PatchSoAConverter.from_patches(sources)
        order = sorted(seeds)
        seed_mat = np.empty((len(order), len(sources)), dtype=np.float64)
        for k, oid in enumerate(order):
            seed_mat[k, :] = np.asarray(seeds[oid], dtype=np.float64)
        tids = list(targets.keys())
        t_centers, t_normals, t_areas, t_surf = [], [], [], []
        for tid in tids:
            soa = PatchSoAConverter.from_patches(targets[tid])
            t_centers.append(np.ascontiguousarray(soa.centers))
            t_normals.append(np.ascontiguousarray(soa.normals))
            t_areas.append(np.ascontiguousarray(soa.areas))
            surf = 0
            if targets[tid]:
                surf = int(soa.surfaces[0]) if len(soa.surfaces) else 0
            t_surf.append(surf)
        ctx = VisibilityContextBuilder.build(room_polygon)
        solver = mod.RadiositySolver(
            float(wall_reflectance),
            float(floor_reflectance),
            float(ceiling_reflectance),
            int(num_bounces),
            int(self._rt.config.threads),
        )
        res = solver.solve(
            np.ascontiguousarray(src.centers),
            np.ascontiguousarray(src.normals),
            np.ascontiguousarray(src.areas),
            np.ascontiguousarray(src.surfaces),
            order,
            np.ascontiguousarray(seed_mat),
            tids,
            t_centers,
            t_normals,
            t_areas,
            t_surf,
            np.ascontiguousarray(ctx.ring),
            bool(ctx.convex),
        )
        out: dict[str, dict[str, list[float]]] = {}
        for tid in tids:
            per: dict[str, list[float]] = {}
            for oid in order:
                per[oid] = [float(v) for v in np.asarray(res[tid][oid]).ravel().tolist()]
            out[tid] = per
        return out

    def bounce_values(
        self,
        sources: list[Any],
        source_values: list[float] | np.ndarray,
        targets: list[Any],
        reflectance: float,
        room_polygon: list[tuple[float, float]] | None = None,
    ) -> list[float]:
        mod = self._rt.module
        if mod is None:
            raise _UsePythonFallback
        if room_polygon is not None and not isinstance(room_polygon, list):
            raise _UsePythonFallback
        src = PatchSoAConverter.from_patches(sources)
        tgt = PatchSoAConverter.from_patches(targets)
        # bounce_values needs a solver instance for rho config; reflectances unused here.
        solver = mod.RadiositySolver(0.5, 0.0, 0.0, 1, int(self._rt.config.threads))
        ctx = VisibilityContextBuilder.build(room_polygon)
        out = solver.bounce_values(
            np.ascontiguousarray(src.centers),
            np.ascontiguousarray(src.normals),
            np.ascontiguousarray(src.areas),
            np.ascontiguousarray(np.asarray(source_values, dtype=np.float64)),
            np.ascontiguousarray(tgt.centers),
            np.ascontiguousarray(tgt.normals),
            float(reflectance),
            np.ascontiguousarray(ctx.ring),
            bool(ctx.convex),
        )
        return [float(v) for v in np.asarray(out).ravel().tolist()]


class LuxCoreGeometry:
    """Mesh + CSR interpolation weights via C++ (stateless)."""

    def __init__(self, runtime: LuxCoreRuntime | None = None) -> None:
        self._rt = runtime or LuxCoreRuntime()

    def apply_weights(self, values: list[float], weights: tuple) -> list[float]:
        mod = self._rt.module
        if mod is None:
            raise _UsePythonFallback
        indptr, indices, data, n_eval, _n_full = weights
        out = mod.apply_weights(
            np.ascontiguousarray(np.asarray(values, dtype=np.float64)),
            np.ascontiguousarray(np.asarray(indptr, dtype=np.float64)),
            np.ascontiguousarray(np.asarray(indices, dtype=np.float64)),
            np.ascontiguousarray(np.asarray(data, dtype=np.float64)),
            int(n_eval),
            int(_n_full),
        )
        return [float(v) for v in np.asarray(out).ravel().tolist()]


class LuxCorePhotometry:
    @staticmethod
    def candela(profile: Any, theta: float, phi: float) -> float:
        ies = IesHandleCache.get(profile)
        return float(ies.sample(float(theta), float(phi)))
