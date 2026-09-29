"""Two-stage best-grid search over free placements. Framework-free.

Stage A (bounces=0, direct only, shared solver cache): rank all candidates.
Stage B (full bounces): verify top-N, keep compliant, return diverse Top-K.
Catalog mode = outer loop per fixture key; single mode = one key.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field, replace

from app.domain.exceptions import NoFixturesError
from app.domain.models import FixtureGeometry, FixturePlacement, IESProfile
from app.engine import (
    EvalGrids,
    PhysicsOptions,
    RoomInput,
    build_eval_grids,
    build_room,
    build_solver_cache,
    resolve_fixtures,
    run,
)
from app.automate.layouts import LayoutSpec, enumerate_layouts, placements_for_layout
from app.automate.lumen import passes_lumen_gate, room_uf
from app.providers import StandardTarget
from app.services.fixture_service import fixture_geometries
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
    variant_key: str
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
    miss_reason: str | None = None  # None = compliant; else under_target|over_cap|uniformity
    fixtures: list[FixtureGeometry] = field(default_factory=list)  # attached post-selection only
    floor_values: list[float] = field(default_factory=list)  # maintained total-floor lux, eval-grid order


@dataclass(frozen=True)
class Outcome:
    solutions: list[Solution] = field(default_factory=list)
    overcap: list[Solution] = field(default_factory=list)
    evaluated_a: int = 0
    evaluated_b: int = 0
    pruned: dict[str, int] = field(default_factory=dict)
    closest_miss: Solution | None = None
    grids: EvalGrids | None = None  # shared eval grids (one room per search)


def is_compliant(avg: float, u0: float, target: StandardTarget) -> bool:
    return (
        avg >= target.avg_lux
        and u0 >= target.uniformity
        and avg <= target.avg_lux * (1.0 + target.max_overdesign)
    )


def classify_miss(avg: float, u0: float, target: StandardTarget) -> str | None:
    """First failing compliance check (target order): under_target | over_cap | uniformity.

    Returns None for compliant values. Powers Solution.miss_reason and the
    demo's miss badge — EDIT HERE if compliance gains more criteria.
    """
    if avg < target.avg_lux:
        return "under_target"
    if avg > target.avg_lux * (1.0 + target.max_overdesign):
        return "over_cap"
    if u0 < target.uniformity:
        return "uniformity"
    return None


def _miss_key(avg: float, u0: float, target: StandardTarget) -> tuple[float, float]:
    """Distance of a miss to the compliant window (then higher uniformity wins)."""
    cap = target.avg_lux * (1.0 + target.max_overdesign)
    if avg < target.avg_lux:
        return (target.avg_lux - avg, -u0)
    if avg > cap:
        return (avg - cap, -u0)
    return (0.0, target.uniformity - u0)  # in-window avg, only uniformity fails


@dataclass
class _Row:
    """One Stage-A ranked candidate (fixture x layout). Module-level for testability."""

    key: str
    spec: LayoutSpec
    placements: list[FixturePlacement]
    count: int
    avg: float
    u0: float


def best_per_variant(rows: list, key_of, rank_of) -> list:
    """One grid per variant: keep each variant's best row by rank_of order.

    Used so results compare variants (best grid each) instead of showing
    several grids of one variant. First-seen order kept for stability.
    """
    best: dict = {}
    for row in rows:
        key = key_of(row)
        if key not in best or rank_of(row) < rank_of(best[key]):
            best[key] = row
    return list(best.values())


def shortlist_for_key(
    feas: list[_Row],
    rest: list[_Row],
    fallback: list[_Row],
    stage_b_n: int,
    target: StandardTarget | None = None,
) -> list[_Row]:
    """Round-robin across fixture counts (feas entries first within each count).

    Without this, one count band hogs all stage_b_n slots.
    When target is provided, count buckets are ordered by proximity to the
    compliant window (_miss_key) so vast spaces don't waste slots on dim layouts.
    """
    buckets: dict[int, list[_Row]] = {}
    for row in feas:
        buckets.setdefault(row.count, []).append(row)
    for row in rest:
        buckets.setdefault(row.count, []).append(row)

    if target is not None:
        for count in buckets:
            buckets[count].sort(key=lambda r: _miss_key(r.avg, r.u0, target))
        ordered_counts = sorted(
            buckets,
            key=lambda c: (min(_miss_key(r.avg, r.u0, target) for r in buckets[c]), c),
        )
    else:
        ordered_counts = sorted(buckets)

    ranked: list[_Row] = []
    depth = 0
    while len(ranked) < stage_b_n:
        progressed = False
        for count in ordered_counts:
            if depth < len(buckets[count]):
                ranked.append(buckets[count][depth])
                progressed = True
                if len(ranked) >= stage_b_n:
                    break
        if not progressed:
            break
        depth += 1
    return ranked or sorted(fallback, key=lambda r: -r.avg)[:3]


def automate(
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
    direct_opts = replace(opts, bounces=0, include_wall_ceiling=False)
    stage_b_opts = replace(opts, include_wall_ceiling=False)

    # Stage A: cheap rank over (fixture x layout).
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
    # Per-fixture shortlist budgets (count-diverse: see shortlist_for_key).
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
        shortlist.extend(
            shortlist_for_key(
                feas, rest, [r for r in rows_a if r.key == key], stage_b_n, target
            )
        )

    # Stage B: full-physics verify.
    verified: list[Solution] = []
    for row in shortlist:
        fixtures = resolve_fixtures(room, row.placements, {row.key: catalog[row.key]}, mount_h, row.key)
        result = run(fixtures, room, evaluation, cache, stage_b_opts)
        ev = result.evaluation
        power = len(fixtures) * watts[row.key] if row.key in watts else None
        verified.append(
            Solution(
                variant_key=row.key, spec=row.spec, placements=row.placements,
                count=len(fixtures), average=ev.average, minimum=ev.minimum,
                maximum=ev.maximum, uniformity=ev.uniformity,
                overdesign=ev.average / target.avg_lux - 1.0,
                power_w=power,
                power_density=(power / area if power is not None and area > 0 else None),
                miss_reason=classify_miss(ev.average, ev.uniformity, target),
                floor_values=list(result.total_floor.values),
            )
        )
    feasible = [s for s in verified if is_compliant(s.average, s.uniformity, target)]
    misses = [s for s in verified if not is_compliant(s.average, s.uniformity, target)]
    # One grid per variant across the whole response: a variant shown once
    # (compliant or flagged) never reappears as over-cap pick or miss.
    solutions = pick_diverse(
        best_per_variant(
            feasible,
            lambda s: s.variant_key,
            lambda s: (s.count, s.overdesign, -s.uniformity),
        ),
        top_k,
    )
    shown_variants = {s.variant_key for s in solutions}
    overcap = pick_overcap(
        [m for m in misses if m.variant_key not in shown_variants],
        target, max(0, top_k - len(solutions)),
    )
    shown_variants |= {s.variant_key for s in overcap}
    rest_misses = [s for s in misses if s.variant_key not in shown_variants]
    miss = (min(rest_misses, key=lambda s: _miss_key(s.average, s.uniformity, target))
            if rest_misses else None)
    # Engine fixture geometry for returned entries only: re-resolve their
    # placements (cheap, no physics) and attach opening corners/elements for
    # visualization. Verified losers stay lightweight.
    def _with_geometry(sol: Solution) -> Solution:
        fixtures = resolve_fixtures(
            room, sol.placements, {sol.variant_key: catalog[sol.variant_key]},
            mount_h, sol.variant_key,
        )
        return replace(sol, fixtures=fixture_geometries(fixtures))

    solutions = [_with_geometry(s) for s in solutions]
    overcap = [_with_geometry(s) for s in overcap]
    miss = _with_geometry(miss) if miss is not None else None
    _log.info(
        "automate candidates=%s feasible_a=%s verified=%s feasible=%s overcap=%s unshown_variants=%s",
        len(rows_a), len(feasible_a), len(verified), len(feasible), len(overcap),
        len({m.variant_key for m in rest_misses}),
    )
    return Outcome(
        solutions=solutions,
        overcap=overcap,
        evaluated_a=len(rows_a),
        evaluated_b=len(verified),
        pruned=pruned,
        closest_miss=miss,
        grids=evaluation,
    )


def pick_overcap(misses: list[Solution], target: StandardTarget, limit: int) -> list[Solution]:
    """Flagged over-cap picks: pure over-lighting only (uniformity must pass).

    Nearest to the cap first, then most compact. Under-target and
    non-uniform layouts stay misses — a layout that is both dim in corners
    and over-bright on average helps nobody. `limit` is the leftover
    top-K budget, so plentiful runs show zero flagged entries.
    """
    if limit <= 0:
        return []
    pool = [s for s in misses
            if s.miss_reason == "over_cap" and s.uniformity >= target.uniformity]
    best = best_per_variant(
        pool, lambda s: s.variant_key, lambda s: (s.overdesign, s.count, -s.uniformity)
    )
    return sorted(best, key=lambda s: (s.overdesign, s.count, -s.uniformity))[:limit]


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
        key = (sol.variant_key, sol.spec)
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
