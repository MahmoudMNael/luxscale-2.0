import math
import random

import numpy as np
import pytest

from app.domain.models import Patch
from app.services.indirect_illuminance_service import (
    _segment_fraction,
    build_transfer_matrix,
    compute_indirect_floor_per_origin,
    form_factor,
    solve_source_exitance,
)
from app.services.vector_math import segment_inside_room, visibility_polygon


def _patch(pid, surface, parent, center, normal) -> Patch:
    return Patch(
        id=pid, surface_type=surface, parent_id=parent,
        center=center, normal=normal, area=1.0, size=1.0,
    )


def test_single_wall_seed_matches_analytic_form_factor():
    src = [_patch("w0", "wall", "W1", (0.0, 0.0, 1.0), (1.0, 0.0, 0.0))]
    floor = [_patch("f0", "floor", "floor", (1.0, 0.0, 0.0), (0.0, 0.0, 1.0))]
    out = compute_indirect_floor_per_origin(
        src, {"W1": [1000.0]}, floor, 0.5, 1, None, floor_reflectance=0.0, ceiling_reflectance=0.0
    )
    assert out["W1"] == pytest.approx([1000.0 * 0.5 / (4.0 * math.pi)])


def test_facing_walls_boost_floor_indirect():
    a = _patch("w0", "wall", "W1", (0.0, 0.0, 1.0), (1.0, 0.0, 0.0))
    b = _patch("w1", "wall", "W2", (1.0, 0.0, 1.0), (-1.0, 0.0, 0.0))
    floor = [_patch("f0", "floor", "floor", (0.5, 2.0, 0.0), (0.0, 0.0, 1.0))]
    one = compute_indirect_floor_per_origin(
        [a], {"W1": [1000.0]}, floor, 0.5, 1, None, floor_reflectance=0.0, ceiling_reflectance=0.0
    )
    two = compute_indirect_floor_per_origin(
        [a, b], {"W1": [1000.0, 0.0]}, floor, 0.5, 1, None, floor_reflectance=0.0, ceiling_reflectance=0.0
    )
    assert two["W1"][0] > one["W1"][0] > 0.0


def test_segment_fraction_bounds_and_dominance():
    poly = [(0, 0), (4, 0), (4, 1), (1, 1), (1, 3), (0, 3)]
    room = visibility_polygon(poly)
    rng = random.Random(7)
    assert _segment_fraction((0.5, 0.5), (0.5, 2.5), room) == 1.0
    assert _segment_fraction((2.0, 2.0), (3.0, 2.5), room) == 0.0
    # Notch crossing: x=2 vertical from y=0.5 (inside) to y=2.5 (outside
    # above y=1) → exactly 0.5 / 2.0 visible; the old {0, 0.5, 1} bucket
    # could only guess here.
    assert _segment_fraction((2.0, 0.5), (2.0, 2.5), room) == pytest.approx(0.25, abs=5e-3)
    for _ in range(200):
        a = (rng.uniform(-1, 5), rng.uniform(-1, 4))
        b = (rng.uniform(-1, 5), rng.uniform(-1, 4))
        frac = _segment_fraction(a, b, room)
        assert 0.0 <= frac <= 1.0
        assert frac >= float(segment_inside_room(a, b, room))


def _mixed_patches() -> list[Patch]:
    return [
        _patch("w0", "wall", "W1", (0.0, 0.0, 1.0), (1.0, 0.0, 0.0)),
        _patch("w1", "wall", "W2", (2.0, 0.0, 1.0), (-1.0, 0.0, 0.0)),
        _patch("f0", "floor", "floor", (0.5, 0.0, 0.0), (0.0, 0.0, 1.0)),
        _patch("f1", "floor", "floor", (1.5, 0.0, 0.0), (0.0, 0.0, 1.0)),
        _patch("c0", "ceiling", "ceiling", (0.5, 0.0, 3.0), (0.0, 0.0, -1.0)),
        _patch("c1", "ceiling", "ceiling", (1.5, 0.0, 3.0), (0.0, 0.0, -1.0)),
    ]


def test_transfer_matrix_matches_point_form_factor():
    patches = _mixed_patches()
    F = build_transfer_matrix(patches, block_size=2).astype(np.float64)
    for t, tgt in enumerate(patches):
        for i, src in enumerate(patches):
            assert F[i, t] == pytest.approx(form_factor(src, tgt), abs=1e-6)


def test_transfer_matrix_gates_occluded_pairs_in_concave_room():
    poly = [(0, 0), (4, 0), (4, 1), (1, 1), (1, 3), (0, 3)]
    a = _patch("w0", "wall", "W1", (0.0, 2.0, 1.0), (1.0, 0.0, 0.0))
    b = _patch("w1", "wall", "W2", (4.0, 0.5, 1.0), (-1.0, 0.0, 0.0))
    open_f = build_transfer_matrix([a, b]).astype(np.float64)
    assert open_f[0, 1] > 0.0 and open_f[1, 0] > 0.0
    gated = build_transfer_matrix([a, b], room_polygon=poly).astype(np.float64)
    assert gated[0, 1] == 0.0 and gated[1, 0] == 0.0


def test_transfer_matrix_convex_room_keeps_all_pairs():
    poly = [(0, 0), (4, 0), (4, 3), (0, 3)]
    a = _patch("w0", "wall", "W1", (0.0, 2.0, 1.0), (1.0, 0.0, 0.0))
    b = _patch("w1", "wall", "W2", (4.0, 0.5, 1.0), (-1.0, 0.0, 0.0))
    open_f = build_transfer_matrix([a, b]).astype(np.float64)
    gated = build_transfer_matrix([a, b], room_polygon=poly).astype(np.float64)
    assert gated == pytest.approx(open_f)


def test_transfer_matrix_coplanar_blocks_exactly_zero():
    patches = _mixed_patches()
    F = build_transfer_matrix(patches, block_size=4).astype(np.float64)
    floor = [i for i, p in enumerate(patches) if p.surface_type == "floor"]
    ceil = [i for i, p in enumerate(patches) if p.surface_type == "ceiling"]
    assert (F[np.ix_(floor, floor)] == 0.0).all()
    assert (F[np.ix_(ceil, ceil)] == 0.0).all()


def test_exact_solver_agrees_with_converged_neumann():
    patches = _mixed_patches()
    F = build_transfer_matrix(patches)
    seeds = np.array([[1000.0, 0.0, 500.0, 0.0, 0.0, 200.0]])
    rho = np.array([0.5, 0.5, 0.2, 0.2, 0.7, 0.7])
    exact, _ = solve_source_exitance(seeds, F, rho, method="exact")
    conv, used = solve_source_exitance(
        seeds, F, rho, method="neumann", num_bounces=None, tol_lux=1e-9, max_iters=1000
    )
    assert used > 5
    assert conv == pytest.approx(exact, rel=1e-4, abs=1e-3)


def test_converged_mode_reports_bounces_used():
    patches = _mixed_patches()
    floor = [_patch("f0", "floor", "floor", (1.0, 0.0, 0.0), (0.0, 0.0, 1.0))]
    meta: dict = {}
    out = compute_indirect_floor_per_origin(
        patches, {"W1": [1000.0, 0.0, 0.0, 0.0, 0.0, 0.0]}, floor, 0.5, None,
        None, floor_reflectance=0.2, ceiling_reflectance=0.7, out_meta=meta,
    )
    assert out["W1"][0] > 0.0
    assert meta["bounces_used"] >= 1
    assert meta["f_build_ms"] >= 0.0
