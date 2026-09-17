from __future__ import annotations

import math

from app.domain.exceptions import GeometryError
from app.domain.models import CeilingSurface, FloorSurface, Patch, Room, Wall, WallSurface
from app.services.vector_math import (
    EPS,
    en12464_spacing,
    inset_rings,
    norm,
    perimeter_border,
    point_in_polygon,
    signed_area,
)

Vec2 = tuple[float, float]


def _close(vertices: list[Vec2]) -> list[Vec2]:
    if len(vertices) >= 2 and vertices[0] == vertices[-1]:
        return vertices[:-1]
    return list(vertices)


def _segments(start: float, end: float, size: float) -> list[tuple[float, float]]:
    span = end - start
    if span <= EPS or size <= EPS:
        return []
    n = max(1, math.ceil(span / size - EPS))
    actual = span / n
    return [(start + i * actual, start + (i + 1) * actual) for i in range(n)]


def define_room(vertices: list[Vec2], height: float, step: float = 1.0) -> Room:
    polygon = _close(vertices)
    if len(polygon) < 3 or abs(signed_area(polygon)) <= EPS:
        raise GeometryError("Room polygon must have non-zero area.")
    walls: list[Wall] = []
    for i, start in enumerate(polygon):
        end = polygon[(i + 1) % len(polygon)]
        length = norm((end[0] - start[0], end[1] - start[1]))
        wall_id = f"W{i + 1}"
        if length < EPS:
            raise GeometryError(f"Wall {wall_id} has zero length.")
        dx, dy = (end[0] - start[0]) / length, (end[1] - start[1]) / length
        # CCW polygon: rotate edge 90° left for inward; CW: opposite.
        if signed_area(polygon) > 0:
            normal = (-dy, dx)
        else:
            normal = (dy, -dx)
        walls.append(Wall(id=wall_id, start=start, end=end, length=length, normal=normal, height=height))
    return Room(polygon=polygon, height=height, walls=walls, step=step)


def generate_patches(
    surface: FloorSurface | CeilingSurface | WallSurface,
    patch_size: float | None = None,
    *,
    plane_z: float,
    border: float = 0.0,
) -> list[Patch]:
    if isinstance(surface, FloorSurface):
        return _floor_patches(surface, plane_z, border)
    if isinstance(surface, CeilingSurface):
        return _ceiling_patches(surface, plane_z, border)
    size = 1.0 if patch_size is None else patch_size
    return _wall_patches(surface, size)


def _floor_patches(surface: FloorSurface, plane_z: float, border: float) -> list[Patch]:
    patches, _ = generate_floor_evaluation_grid(surface.polygon, plane_z, border)
    return patches


def generate_ceiling_evaluation_grid(
    polygon: list[Vec2], plane_z: float, border: float
) -> tuple[list[Patch], dict[str, float]]:
    patches, meta = generate_floor_evaluation_grid(polygon, plane_z, border)
    ceiling: list[Patch] = []
    for i, p in enumerate(patches):
        ceiling.append(
            Patch(
                id=f"ceiling-{i}",
                surface_type="ceiling",
                parent_id="ceiling",
                center=(p.center[0], p.center[1], plane_z),
                normal=(0.0, 0.0, -1.0),
                area=p.area,
                size=p.size,
            )
        )
    return ceiling, meta


def _ceiling_patches(surface: CeilingSurface, plane_z: float, border: float) -> list[Patch]:
    patches, _ = generate_ceiling_evaluation_grid(surface.polygon, plane_z, border)
    return patches


def resolve_horizontal_border(polygon: list[Vec2], override: float | None) -> float:
    """Floor/ceiling inset: fixed 0.5 m default; explicit override wins."""
    from app.app_settings import FLOOR_BORDER

    if override is not None:
        return max(0.0, override)
    return FLOOR_BORDER


def resolve_wall_border(length: float, height: float, override: float | None) -> float:
    """Wall inset: 15% of shortest wall side capped at 0.5 m; override wins."""
    if override is not None:
        return max(0.0, override)
    return perimeter_border(min(length, height))


def _empty_meta() -> dict[str, float]:
    return {"spacing": 0.0, "spacingX": 0.0, "spacingY": 0.0, "nx": 0, "ny": 0, "dx": 0.0, "dy": 0.0,
            "xmin": 0.0, "xmax": 0.0, "ymin": 0.0, "ymax": 0.0, "border": 0.0}


def generate_floor_evaluation_grid(
    polygon: list[Vec2], plane_z: float, border: float
) -> tuple[list[Patch], dict[str, float]]:
    """EN 12464 standard grid for horizontal surfaces (Relux-style per-axis).

    Effective region = polygon inset by ``border``; single spacing per
    EN 12464-1 (d = longer side of the calculation area)
    ``p = en12464_spacing(max(width, height))``,
    ``nx = ceil(width / p)``, ``ny = ceil(height / p)``, cell centres
    kept when inside the inset region. A surface that cannot keep
    ``border`` on both sides yields [].
    """
    domains = inset_rings(polygon, border)
    if not domains:
        m = _empty_meta()
        m["border"] = border
        return [], m
    xs = [p[0] for ring in domains for p in ring]
    ys = [p[1] for ring in domains for p in ring]
    width, height = max(xs) - min(xs), max(ys) - min(ys)
    if width <= EPS or height <= EPS:
        m = _empty_meta()
        m.update({"xmin": min(xs), "xmax": max(xs), "ymin": min(ys), "ymax": max(ys), "border": border})
        return [], m
    spacing = en12464_spacing(max(width, height))
    if spacing <= EPS:
        m = _empty_meta()
        m.update({"xmin": min(xs), "xmax": max(xs), "ymin": min(ys), "ymax": max(ys), "border": border})
        return [], m
    spacing_x = spacing
    spacing_y = spacing
    xmin, xmax, ymin, ymax = min(xs), max(xs), min(ys), max(ys)
    nx = max(1, math.ceil(width / spacing - EPS))
    ny = max(1, math.ceil(height / spacing - EPS))
    dx, dy = width / nx, height / ny
    area = dx * dy
    size = max(dx, dy)
    patches: list[Patch] = []
    n = 0
    for j in range(ny):
        cy = ymin + (j + 0.5) * dy
        for i in range(nx):
            cx = xmin + (i + 0.5) * dx
            if not any(point_in_polygon((cx, cy), domain) for domain in domains):
                continue
            patches.append(
                Patch(
                    id=f"floor-{n}",
                    surface_type="floor",
                    parent_id="floor",
                    center=(cx, cy, plane_z),
                    normal=(0.0, 0.0, 1.0),
                    area=area,
                    size=size,
                )
            )
            n += 1
    meta = {"spacing": spacing, "spacingX": spacing_x, "spacingY": spacing_y,
            "nx": float(nx), "ny": float(ny), "dx": dx, "dy": dy,
            "xmin": xmin, "xmax": xmax, "ymin": ymin, "ymax": ymax, "border": border}
    return patches, meta


def generate_wall_evaluation_grid(
    wall: Wall, border: float
) -> tuple[list[Patch], dict[str, float]]:
    """EN 12464 evaluation grid for a vertical wall rectangle (Relux parity).

    Effective region = [border, L-border] x [border, H-border];
    single spacing per EN 12464-1 (d = longer side of the wall
    calculation area) ``p = en12464_spacing(max(eff_L, eff_H))``,
    ``ns = ceil(eff_L / p)``, ``nz = ceil(eff_H / p)``.
    Neglected ([]) when ``min(L, H) <= 1.0 m`` or the wall cannot keep
    ``border`` on both sides.
    """
    from app.app_settings import WALL_MIN_DIMENSION

    return _wall_grid(wall, border, apply_neglect=True)


def generate_wall_radiosity_grid(wall: Wall) -> tuple[list[Patch], dict[str, float]]:
    """Full-coverage wall mesh for radiosity (border 0, no 1 m neglect).

    Covers the whole wall so border strips reflect; results are later
    sampled onto the standard evaluation grid.
    """
    return _wall_grid(wall, 0.0, apply_neglect=False)


def _wall_grid(wall: Wall, border: float, *, apply_neglect: bool) -> tuple[list[Patch], dict[str, float]]:
    from app.app_settings import WALL_MIN_DIMENSION

    length = wall.length
    height = wall.height
    if apply_neglect and min(length, height) <= WALL_MIN_DIMENSION + EPS:
        m = _empty_meta()
        m["border"] = border
        return [], m
    eff_l = length - 2.0 * border
    eff_h = height - 2.0 * border
    if eff_l <= EPS or eff_h <= EPS:
        m = _empty_meta()
        m["border"] = border
        return [], m
    spacing = en12464_spacing(max(eff_l, eff_h))
    if spacing <= EPS:
        m = _empty_meta()
        m["border"] = border
        return [], m
    spacing_x = spacing
    spacing_y = spacing
    ns = max(1, math.ceil(eff_l / spacing - EPS))
    nz = max(1, math.ceil(eff_h / spacing - EPS))
    ds, dz = eff_l / ns, eff_h / nz
    dx = wall.end[0] - wall.start[0]
    dy = wall.end[1] - wall.start[1]
    ux, uy = dx / length, dy / length
    patches: list[Patch] = []
    n = 0
    for k in range(nz):
        z_mid = border + (k + 0.5) * dz
        for i in range(ns):
            s_mid = border + (i + 0.5) * ds
            patches.append(
                Patch(
                    id=f"{wall.id}-{n}",
                    surface_type="wall",
                    parent_id=wall.id,
                    center=(wall.start[0] + ux * s_mid, wall.start[1] + uy * s_mid, z_mid),
                    normal=(wall.normal[0], wall.normal[1], 0.0),
                    area=ds * dz,
                    size=max(ds, dz),
                )
            )
            n += 1
    meta = {"spacing": spacing, "spacingX": spacing_x, "spacingY": spacing_y,
            "nx": float(ns), "ny": float(nz), "dx": ds, "dy": dz,
            "xmin": border, "xmax": border + eff_l, "ymin": border, "ymax": border + eff_h,
            "border": border}
    return patches, meta


def _lattice_map(patches: list[Patch], xs: list[float], ys: list[float]) -> dict[tuple[int, int], int]:
    return {(round(x), round(y)): n for n, (x, y) in enumerate(zip(xs, ys))}


def generate_solver_plan_grid(
    polygon: list[Vec2],
    plane_z: float,
    surface_type: str,
    parent_id: str,
    cell: float,
    *,
    normal: tuple[float, float, float],
) -> tuple[list[Patch], dict[str, float]]:
    """Relux-like independent solver mesh: fixed raster, full coverage.

    ``nx = ceil(W / cell)``, ``ny = ceil(H / cell)`` over the room bbox,
    cell centres kept when inside the polygon. No border inset, no neglect.
    """
    xs = [p[0] for p in polygon]
    ys = [p[1] for p in polygon]
    xmin, xmax, ymin, ymax = min(xs), max(xs), min(ys), max(ys)
    width, height = xmax - xmin, ymax - ymin
    if width <= EPS or height <= EPS or cell <= EPS:
        m = _empty_meta()
        return [], m
    nx = max(1, math.ceil(width / cell - EPS))
    ny = max(1, math.ceil(height / cell - EPS))
    dx, dy = width / nx, height / ny
    area = dx * dy
    size = max(dx, dy)
    patches: list[Patch] = []
    n = 0
    for j in range(ny):
        cy = ymin + (j + 0.5) * dy
        for i in range(nx):
            cx = xmin + (i + 0.5) * dx
            if not point_in_polygon((cx, cy), polygon):
                continue
            patches.append(
                Patch(
                    id=f"{parent_id}-{n}",
                    surface_type=surface_type,  # type: ignore[arg-type]
                    parent_id=parent_id,
                    center=(cx, cy, plane_z),
                    normal=normal,
                    area=area,
                    size=size,
                )
            )
            n += 1
    meta = {"spacing": cell, "spacingX": cell, "spacingY": cell,
            "nx": float(nx), "ny": float(ny), "dx": dx, "dy": dy,
            "xmin": xmin, "xmax": xmax, "ymin": ymin, "ymax": ymax, "border": 0.0}
    return patches, meta


def generate_solver_wall_grid(wall: Wall, cell: float) -> tuple[list[Patch], dict[str, float]]:
    """Relux-like independent solver mesh for one wall: fixed raster.

    ``ns = ceil(L / cell)``, ``nz = ceil(H / cell)``, full coverage from
    ``(s=0, z=0)``. No border inset, no 1 m neglect: every wall reflects.
    """
    length, height = wall.length, wall.height
    if length <= EPS or height <= EPS or cell <= EPS:
        m = _empty_meta()
        return [], m
    ns = max(1, math.ceil(length / cell - EPS))
    nz = max(1, math.ceil(height / cell - EPS))
    ds, dz = length / ns, height / nz
    dx = wall.end[0] - wall.start[0]
    dy = wall.end[1] - wall.start[1]
    ux, uy = dx / length, dy / length
    patches: list[Patch] = []
    n = 0
    for k in range(nz):
        z_mid = (k + 0.5) * dz
        for i in range(ns):
            s_mid = (i + 0.5) * ds
            patches.append(
                Patch(
                    id=f"{wall.id}-s{n}",
                    surface_type="wall",
                    parent_id=wall.id,
                    center=(wall.start[0] + ux * s_mid, wall.start[1] + uy * s_mid, z_mid),
                    normal=(wall.normal[0], wall.normal[1], 0.0),
                    area=ds * dz,
                    size=max(ds, dz),
                )
            )
            n += 1
    meta = {"spacing": cell, "spacingX": cell, "spacingY": cell,
            "nx": float(ns), "ny": float(nz), "dx": ds, "dy": dz,
            "xmin": 0.0, "xmax": length, "ymin": 0.0, "ymax": height, "border": 0.0}
    return patches, meta


def build_plan_interp_weights(
    full_patches: list[Patch],
    full_meta: dict[str, float],
    eval_patches: list[Patch],
    *,
    eval_dx: float = 0.0,
    eval_dy: float = 0.0,
) -> tuple[list[int], list[int], list[float], int, int]:
    """CSR weights from solver plan mesh to eval centres (Relux measuring).

    Area-average over solver cells whose centres fall inside the eval cell
    footprint (Relux cell-average semantics, smooths fine-solver peaks);
    falls back to bilinear at the centre when the footprint holds no solver
    centre (eval finer than solver), then nearest centre. Rows sum to 1.
    """
    import math as _math

    n_eval, n_full = len(eval_patches), len(full_patches)
    indptr = [0]
    indices: list[int] = []
    data: list[float] = []
    nx = int(full_meta.get("nx", 0))
    ny = int(full_meta.get("ny", 0))
    dx = float(full_meta.get("dx", 0.0))
    dy = float(full_meta.get("dy", 0.0))
    xmin = float(full_meta.get("xmin", 0.0))
    ymin = float(full_meta.get("ymin", 0.0))
    if not full_patches or nx <= 0 or ny <= 0 or dx <= EPS or dy <= EPS or n_eval == 0:
        return [0] * (n_eval + 1), [], [], n_eval, n_full
    lattice = _lattice_map(
        full_patches,
        [round((p.center[0] - xmin) / dx - 0.5) for p in full_patches],
        [round((p.center[1] - ymin) / dy - 0.5) for p in full_patches],
    )
    for e in eval_patches:
        taps = _footprint_taps_plan(
            e.center[0], e.center[1], eval_dx, eval_dy,
            xmin, ymin, dx, dy, nx, ny, lattice,
        )
        if taps is None:
            fx = (e.center[0] - xmin) / dx - 0.5
            fy = (e.center[1] - ymin) / dy - 0.5
            i0, j0 = _math.floor(fx), _math.floor(fy)
            tx, ty = fx - i0, fy - j0
            cands = ((i0, j0, (1.0 - tx) * (1.0 - ty)), ((i0 + 1), j0, tx * (1.0 - ty)),
                     (i0, j0 + 1, (1.0 - tx) * ty), (i0 + 1, j0 + 1, tx * ty))
            taps = []
            for ci, cj, w in cands:
                if w <= 0.0:
                    continue
                hit = lattice.get((ci, cj))
                if hit is not None:
                    taps.append((hit, w))
            if not taps:
                taps = [(_nearest(full_patches, *e.center), 1.0)]
            else:
                s = sum(w for _, w in taps)
                taps = [(h, w / s) for h, w in taps]
        for h, w in taps:
            indices.append(h)
            data.append(w)
        indptr.append(len(indices))
    return indptr, indices, data, n_eval, n_full


def _footprint_taps_plan(
    cx: float, cy: float, ex: float, ey: float,
    xmin: float, ymin: float, dx: float, dy: float,
    nx: int, ny: int, lattice: dict[tuple[int, int], int],
) -> list[tuple[int, float]] | None:
    """Mean over solver cells with centres inside the eval footprint."""
    import math as _math

    if ex <= EPS or ey <= EPS:
        return None
    i_lo = max(0, int(_math.ceil((cx - ex / 2.0 - xmin) / dx - 0.5 - EPS)))
    i_hi = min(nx - 1, int(_math.floor((cx + ex / 2.0 - xmin) / dx - 0.5 + EPS)))
    j_lo = max(0, int(_math.ceil((cy - ey / 2.0 - ymin) / dy - 0.5 - EPS)))
    j_hi = min(ny - 1, int(_math.floor((cy + ey / 2.0 - ymin) / dy - 0.5 + EPS)))
    if i_hi < i_lo or j_hi < j_lo:
        return None
    hits = [lattice[(i, j)] for j in range(j_lo, j_hi + 1) for i in range(i_lo, i_hi + 1) if (i, j) in lattice]
    if not hits:
        return None
    w = 1.0 / len(hits)
    return [(h, w) for h in hits]


def build_wall_interp_weights(
    wall: Wall,
    full_patches: list[Patch],
    full_meta: dict[str, float],
    eval_patches: list[Patch],
    *,
    eval_ds: float = 0.0,
    eval_dz: float = 0.0,
) -> tuple[list[int], list[int], list[float], int, int]:
    """CSR weights from solver wall mesh to eval centres (Relux measuring).

    Area-average over solver cells in the eval footprint; bilinear fallback
    when the footprint holds none (eval finer than solver). Rows sum to 1.
    """
    import math as _math

    n_eval, n_full = len(eval_patches), len(full_patches)
    indptr = [0]
    indices: list[int] = []
    data: list[float] = []
    length = wall.length
    dx = wall.end[0] - wall.start[0]
    dy = wall.end[1] - wall.start[1]
    if length <= EPS or not full_patches or n_eval == 0:
        return [0] * (n_eval + 1), [], [], n_eval, n_full
    ux, uy = dx / length, dy / length
    ns = int(full_meta.get("nx", 0))
    nz = int(full_meta.get("ny", 0))
    ds = float(full_meta.get("dx", 0.0))
    dz = float(full_meta.get("dy", 0.0))
    if ns <= 0 or nz <= 0 or ds <= EPS or dz <= EPS:
        return [0] * (n_eval + 1), [], [], n_eval, n_full
    lattice = _lattice_map(
        full_patches,
        [round(((p.center[0] - wall.start[0]) * ux + (p.center[1] - wall.start[1]) * uy) / ds - 0.5) for p in full_patches],
        [round(p.center[2] / dz - 0.5) for p in full_patches],
    )
    for e in eval_patches:
        s = (e.center[0] - wall.start[0]) * ux + (e.center[1] - wall.start[1]) * uy
        taps = _footprint_taps_wall(s, e.center[2], eval_ds, eval_dz, ds, dz, ns, nz, lattice)
        if taps is None:
            fs = s / ds - 0.5
            fz = e.center[2] / dz - 0.5
            i0, k0 = _math.floor(fs), _math.floor(fz)
            ts, tz = fs - i0, fz - k0
            cands = ((i0, k0, (1.0 - ts) * (1.0 - tz)), ((i0 + 1), k0, ts * (1.0 - tz)),
                     (i0, k0 + 1, (1.0 - ts) * tz), (i0 + 1, k0 + 1, ts * tz))
            taps = []
            for ci, ck, w in cands:
                if w <= 0.0:
                    continue
                hit = lattice.get((ci, ck))
                if hit is not None:
                    taps.append((hit, w))
            if not taps:
                taps = [(_nearest(full_patches, *e.center), 1.0)]
            else:
                tot = sum(w for _, w in taps)
                taps = [(h, w / tot) for h, w in taps]
        for h, w in taps:
            indices.append(h)
            data.append(w)
        indptr.append(len(indices))
    return indptr, indices, data, n_eval, n_full


def _footprint_taps_wall(
    s: float, z: float, es: float, ez: float,
    ds: float, dz: float, ns: int, nz: int,
    lattice: dict[tuple[int, int], int],
) -> list[tuple[int, float]] | None:
    """Mean over solver wall cells with centres inside the eval footprint."""
    import math as _math

    if es <= EPS or ez <= EPS:
        return None
    i_lo = max(0, int(_math.ceil((s - es / 2.0) / ds - 0.5 - EPS)))
    i_hi = min(ns - 1, int(_math.floor((s + es / 2.0) / ds - 0.5 + EPS)))
    k_lo = max(0, int(_math.ceil((z - ez / 2.0) / dz - 0.5 - EPS)))
    k_hi = min(nz - 1, int(_math.floor((z + ez / 2.0) / dz - 0.5 + EPS)))
    if i_hi < i_lo or k_hi < k_lo:
        return None
    hits = [lattice[(i, k)] for k in range(k_lo, k_hi + 1) for i in range(i_lo, i_hi + 1) if (i, k) in lattice]
    if not hits:
        return None
    w = 1.0 / len(hits)
    return [(h, w) for h in hits]


def apply_interp_weights(
    values: list[float] | tuple[float, ...],
    weights: tuple[list[int], list[int], list[float], int, int],
) -> list[float]:
    """Apply CSR interpolation weights to a solver-mesh value vector."""
    indptr, indices, data, n_eval, _ = weights
    if n_eval == 0:
        return []
    out: list[float] = []
    for r in range(n_eval):
        acc = 0.0
        for t in range(indptr[r], indptr[r + 1]):
            acc += data[t] * values[indices[t]]
        out.append(acc)
    return out


def _nearest(values: list[Patch], cx: float, cy: float, cz: float) -> int:
    best, best_d2 = 0, float("inf")
    for n, p in enumerate(values):
        d2 = (p.center[0] - cx) ** 2 + (p.center[1] - cy) ** 2 + (p.center[2] - cz) ** 2
        if d2 < best_d2:
            best, best_d2 = n, d2
    return best


def sample_plan_to_eval(
    full_patches: list[Patch], full_meta: dict[str, float], eval_patches: list[Patch]
) -> list[int]:
    """Map each eval centre onto a full-mesh patch index (same surface).

    Index lookup on the full lattice, falling back to nearest centre for
    cells dropped by polygon clipping (e.g. L-notch edges).
    """
    import math as _math

    nx, ny = int(full_meta.get("nx", 0)), int(full_meta.get("ny", 0))
    dx, dy = float(full_meta.get("dx", 0.0)), float(full_meta.get("dy", 0.0))
    xmin, ymin = float(full_meta.get("xmin", 0.0)), float(full_meta.get("ymin", 0.0))
    if not full_patches or nx <= 0 or ny <= 0 or dx <= EPS or dy <= EPS:
        return []
    lattice = _lattice_map(
        full_patches,
        [round((p.center[0] - xmin) / dx - 0.5) for p in full_patches],
        [round((p.center[1] - ymin) / dy - 0.5) for p in full_patches],
    )
    out: list[int] = []
    for e in eval_patches:
        i = min(max(int(_math.floor((e.center[0] - xmin) / dx)), 0), nx - 1)
        j = min(max(int(_math.floor((e.center[1] - ymin) / dy)), 0), ny - 1)
        hit = lattice.get((i, j))
        out.append(hit if hit is not None else _nearest(full_patches, *e.center))
    return out


def sample_wall_to_eval(
    wall: Wall, full_patches: list[Patch], full_meta: dict[str, float], eval_patches: list[Patch]
) -> list[int]:
    """Map each eval wall centre onto a full-mesh wall patch index."""
    import math as _math

    length = wall.length
    dx = wall.end[0] - wall.start[0]
    dy = wall.end[1] - wall.start[1]
    ux, uy = dx / length, dy / length
    ns, nz = int(full_meta.get("nx", 0)), int(full_meta.get("ny", 0))
    ds, dz = float(full_meta.get("dx", 0.0)), float(full_meta.get("dy", 0.0))
    if not full_patches or ns <= 0 or nz <= 0 or ds <= EPS or dz <= EPS:
        return []
    lattice = _lattice_map(
        full_patches,
        [round(((p.center[0] - wall.start[0]) * ux + (p.center[1] - wall.start[1]) * uy) / ds - 0.5) for p in full_patches],
        [round(p.center[2] / dz - 0.5) for p in full_patches],
    )
    out: list[int] = []
    for e in eval_patches:
        s = (e.center[0] - wall.start[0]) * ux + (e.center[1] - wall.start[1]) * uy
        i = min(max(int(_math.floor(s / ds)), 0), ns - 1)
        k = min(max(int(_math.floor(e.center[2] / dz)), 0), nz - 1)
        hit = lattice.get((i, k))
        out.append(hit if hit is not None else _nearest(full_patches, *e.center))
    return out


def _wall_patches(surface: WallSurface, size: float) -> list[Patch]:
    dx = surface.end[0] - surface.start[0]
    dy = surface.end[1] - surface.start[1]
    length = norm((dx, dy))
    if length < EPS:
        raise GeometryError(f"Wall {surface.wall_id} has zero length.")
    ux, uy = dx / length, dy / length
    patches: list[Patch] = []
    n = 0
    for z0, z1 in _segments(0.0, surface.height, size):
        for s0, s1 in _segments(0.0, length, size):
            s_mid, z_mid = (s0 + s1) / 2.0, (z0 + z1) / 2.0
            patches.append(
                Patch(
                    id=f"{surface.wall_id}-{n}",
                    surface_type="wall",
                    parent_id=surface.wall_id,
                    center=(surface.start[0] + ux * s_mid, surface.start[1] + uy * s_mid, z_mid),
                    normal=(surface.normal[0], surface.normal[1], 0.0),
                    area=(s1 - s0) * (z1 - z0),
                    size=max(s1 - s0, z1 - z0),
                )
            )
            n += 1
    return patches


def subdivide_wall_patches(
    coarse: list[Patch],
    surface: WallSurface,
    factor: int = 2,
) -> tuple[list[Patch], list[int]]:
    """Split each coarse wall cell into factor×factor sub-cells.

    Returns the fine patches plus the coarse index of each fine patch, so
    fine direct values area-average exactly back onto the radiosity layout.
    """
    if factor < 2 or not coarse:
        return list(coarse), list(range(len(coarse)))
    dx = surface.end[0] - surface.start[0]
    dy = surface.end[1] - surface.start[1]
    length = norm((dx, dy))
    if length < EPS:
        raise GeometryError(f"Wall {surface.wall_id} has zero length.")
    ux, uy = dx / length, dy / length
    zs = sorted({round(p.center[2], 9) for p in coarse})
    nz = len(zs)
    ns = len(coarse) // nz if nz else len(coarse)
    if ns <= 0 or nz <= 0 or ns * nz != len(coarse):
        return list(coarse), list(range(len(coarse)))
    ds, dz = length / ns, surface.height / nz
    fine: list[Patch] = []
    coarse_idx: list[int] = []
    n = 0
    for ci in range(len(coarse)):
        iz, is_ = divmod(ci, ns)
        for fz in range(factor):
            for fs in range(factor):
                s_mid = (is_ + (fs + 0.5) / factor) * ds
                z_mid = (iz + (fz + 0.5) / factor) * dz
                fine.append(
                    Patch(
                        id=f"{surface.wall_id}-{ci}-{n}",
                        surface_type="wall",
                        parent_id=surface.wall_id,
                        center=(surface.start[0] + ux * s_mid, surface.start[1] + uy * s_mid, z_mid),
                        normal=(surface.normal[0], surface.normal[1], 0.0),
                        area=ds * dz / (factor * factor),
                        size=max(ds, dz) / factor,
                    )
                )
                coarse_idx.append(ci)
                n += 1
    return fine, coarse_idx
