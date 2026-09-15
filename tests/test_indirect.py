import math
import random

import pytest

from app.domain.models import Patch
from app.services.indirect_illuminance_service import (
    _segment_fraction,
    compute_indirect_floor_per_origin,
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
    for _ in range(200):
        a = (rng.uniform(-1, 5), rng.uniform(-1, 4))
        b = (rng.uniform(-1, 5), rng.uniform(-1, 4))
        frac = _segment_fraction(a, b, room)
        assert frac in (0.0, 0.5, 1.0)
        assert frac >= float(segment_inside_room(a, b, room))
