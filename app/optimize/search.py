"""Two-stage best-grid search over free placements. Framework-free.

Stage A (bounces=0, direct only, shared solver cache): rank all candidates.
Stage B (full bounces): verify top-N, keep compliant, return diverse Top-K.
Catalog mode = outer loop per fixture key; single mode = one key.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field, replace

from app.domain.exceptions import NoFixturesError
from app.domain.models import FixturePlacement, IESProfile
from app.engine import (
    PhysicsOptions,
    RoomInput,
    build_eval_grids,
    build_room,
    build_solver_cache,
    resolve_fixtures,
    run,
)
from app.optimize.layouts import LayoutSpec, enumerate_layouts, placements_for_layout
from app.optimize.lumen import passes_lumen_gate, room_uf
from app.providers import StandardTarget
from app.services.ies_service import installed_flux
from app.services.vector_math import polygon_area

_log = logging.getLogger(__name__)

# Stage-A gate is relaxed on purpose: direct-only lux runs ~30% below the
# full-physics value (no interreflection yet), so strict gating here would
# kill viable candidates. Stage B decides real compliance.
_A_MIN_AVG_RATIO = 0.5
_A_MIN_U0_RATIO = 0.5
_A_MAX_CAP_RATIO = 2.0


@dataclass(frozen=True)
class Solution:
    fixture_key: str
    spec: LayoutSpec
    placements: list[FixturePlacement]
    count: int
    average: float
    minimum: float
    maximum: float
    uniformity: float
    overdesign: float  # average/target - 1
    power_w: float | None = None
    power_density: float | None = None


@dataclass(frozen=True)
class Outcome:
    solutions: list[Solution] = field(default_factory=list)
    evaluated_a: int = 0
    evaluated_b: int = 0
    pruned: dict[str, int] = field(default_factory=dict)
    closest_miss: Solution | None = None


def is_compliant(avg: float, u0: float, target: StandardTarget) -> bool:
    return (
        avg >= target.avg_lux
        and u0 >= target.uniformity
        and avg <= target.avg_lux * (1.0 + target.max_overdesign)
    )


def optimize(
    room_input: RoomInput,
    catalog: dict[str, IESProfile],
    target: StandardTarget,
    sx_vals: list[float],
    sy_vals: list[float],
    offset_fractions: list[float],
    rotations: list[float],
    *,
    wattages: dict[str, float] | None = None,
    lumens: dict[str, float] | None = None,
    max_fixtures: int = 64,
    min_wall_clearance: float = 0.0,
    shr_max: float = 1.5,
    top_k: int = 5,
    stage_b_n: int = 12,
    options: PhysicsOptions | None = None,
) -> Outcome:
    """Run the search. Room/solver cache built once, shared by all candidates."""
    opts = options or PhysicsOptions()
    room, _ceiling_h, mount_h, work_z = build_room(room_input)
    evaluation = build_eval_grids(room, work_z, room_input.floor_zone, room_input.wall_zone)
    cache = build_solver_cache(room, evaluation, room.height, opts)
    area = polygon_area(room.polygon)
    watts = wattages or {}
    flux = {key: (lumens or {}).get(key, installed_flux(profile))
            for key, profile in catalog.items()}
    uf = room_uf(room.polygon, mount_h, work_z, opts.wall_reflectance)

    specs, pruned = enumerate_layouts(
        room.polygon, mount_h, sx_vals, sy_vals, offset_fractions,
        rotations, min_wall_clearance, shr_max,
    )
    pruned = dict(pruned)
    pruned.setdefault("outside", 0)
    pruned.setdefault("count", 0)
    pruned.setdefault("lumen", 0)
    direct_opts = replace(opts, bounces=0)

    # Stage A: cheap rank over (fixture x layout).
    @dataclass
    class _Row:
        key: str
        spec: LayoutSpec
        placements: list[FixturePlacement]
        count: int
        avg: float
        u0: float

    rows_a: list[_Row] = []
    for key, profile in catalog.items():
        for spec in specs:
            placements = placements_for_layout(room.polygon, spec)
            if not placements:
                pruned["outside"] += 1
                continue
            if len(placements) > max_fixtures:
                pruned["count"] += 1
                continue
            if not passes_lumen_gate(len(placements) * flux[key], target, area, uf,
                                     opts.maintenance_factor):
                pruned["lumen"] += 1
                continue
            try:
                fixtures = resolve_fixtures(room, placements, {key: profile}, mount_h, key)
            except NoFixturesError:
                pruned["outside"] += 1
                continue
            result = run(fixtures, room, evaluation, cache, direct_opts)
            rows_a.append(
                _Row(key, spec, placements, len(fixtures),
                      result.evaluation.average, result.evaluation.uniformity)
            )
    feasible_a = [r for r in rows_a if is_compliant(r.avg, r.u0, target)]
    feasible_a.sort(key=lambda r: (r.count, r.avg / target.avg_lux, -r.u0))
    feas_ids = {id(r) for r in feasible_a}
    cap = target.avg_lux * (1.0 + target.max_overdesign)
    relaxed = [
        r for r in rows_a
        if id(r) not in feas_ids
        and r.avg >= target.avg_lux * _A_MIN_AVG_RATIO
        and r.u0 >= target.uniformity * _A_MIN_U0_RATIO
        and r.avg <= cap * _A_MAX_CAP_RATIO
    ]
    # Per-fixture shortlist budgets: guarantees every catalog entry is
    # verified (catalog-compare mode) instead of one fixture hogging stage B.
    shortlist: list[_Row] = []
    for key in catalog:
        feas = sorted(
            (r for r in feasible_a if r.key == key),
            key=lambda r: (r.count, r.avg / target.avg_lux, -r.u0),
        )
        rest = sorted(
            (r for r in relaxed if r.key == key),
            key=lambda r: (r.count, -r.avg, -r.u0),
        )
        pool = feas + rest
        shortlist.extend(pool[:stage_b_n] or sorted(
            (r for r in rows_a if r.key == key), key=lambda r: -r.avg
        )[:3])

    # Stage B: full-physics verify.
    verified: list[Solution] = []
    for row in shortlist:
        fixtures = resolve_fixtures(room, row.placements, {row.key: catalog[row.key]}, mount_h, row.key)
        result = run(fixtures, room, evaluation, cache, opts)
        ev = result.evaluation
        power = len(fixtures) * watts[row.key] if row.key in watts else None
        verified.append(
            Solution(
                fixture_key=row.key, spec=row.spec, placements=row.placements,
                count=len(fixtures), average=ev.average, minimum=ev.minimum,
                maximum=ev.maximum, uniformity=ev.uniformity,
                overdesign=ev.average / target.avg_lux - 1.0,
                power_w=power,
                power_density=(power / area if power is not None and area > 0 else None),
            )
        )
    feasible = [s for s in verified if is_compliant(s.average, s.uniformity, target)]
    misses = [s for s in verified if not is_compliant(s.average, s.uniformity, target)]
    _log.info(
        "optimize candidates=%s feasible_a=%s verified=%s feasible=%s",
        len(rows_a), len(feasible_a), len(verified), len(feasible),
    )
    return Outcome(
        solutions=pick_diverse(feasible, top_k),
        evaluated_a=len(rows_a),
        evaluated_b=len(verified),
        pruned=pruned,
        closest_miss=(sorted(misses, key=lambda s: -s.average)[0] if misses else None),
    )


def pick_diverse(feasible: list[Solution], top_k: int) -> list[Solution]:
    """Diverse Top-K: compact, most uniform, least overdesign, then rank order.

    ponytail: O(n log n) sorts, n = verified survivors (<= stage_b_n);
    no heap needed at this scale.
    """
    if not feasible:
        return []
    ranked = sorted(feasible, key=lambda s: (s.count, s.overdesign, -s.uniformity))
    picks: list[Solution] = []
    seen: set[tuple] = set()

    def _take(sol: Solution | None) -> None:
        if sol is None:
            return
        key = (sol.fixture_key, sol.spec)
        if key not in seen:
            seen.add(key)
            picks.append(sol)

    _take(min(feasible, key=lambda s: (s.count, s.overdesign)))  # compact
    _take(max(feasible, key=lambda s: s.uniformity))  # most uniform
    _take(min(feasible, key=lambda s: s.overdesign))  # least overdesign
    for sol in ranked:  # fill
        if len(picks) >= top_k:
            break
        _take(sol)
    return picks[: max(top_k, 1)]
