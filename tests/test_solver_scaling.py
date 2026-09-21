"""Solver-mesh scaling: full 0.3 m resolution up to 10x10 m rooms,
adaptive coarsening beyond MAX_SOLVER_PATCHES (large halls).

Helper tests run on every backend (pure math, no physics). The 100x60 m
end-to-end study needs the C++ extension (the Python fallback would take
far too long at ~6k solver sources) and is skipped without it.
"""

import math

import pytest

from app.app_settings import MAX_SOLVER_PATCHES, SOLVER_CELL
from app.schemas.calculate import CalculateRequest
from app.schemas.geometry import Point2D
from app.schemas.grid import AxisGrid, GridInput
from app.services.calculate_service import calculate
from app.services.geometry_service import (
    define_room,
    estimate_solver_patches,
    resolve_solver_cell,
)
from app.services.vector_math import EPS
from tests.ies_sample import SAMPLE_IES

from app.services._luxcore_bridge import LuxCoreRuntime

needs_luxcore = pytest.mark.skipif(
    not LuxCoreRuntime().is_available(), reason="luxcore extension not built")


def _room_10x10():
    return define_room([(0, 0), (10, 0), (10, 10), (0, 10)], 3.0)


def test_estimate_matches_hand_count_for_reference_room():
    room = _room_10x10()
    # Floor+ceiling: ceil(10/0.3)=34 -> 2*34*34=2312; walls: 4*(34*10)=1360.
    assert estimate_solver_patches(room.polygon, room.walls, SOLVER_CELL) == 3672


def test_resolve_keeps_full_resolution_up_to_10x10():
    room = _room_10x10()
    cell, estimate, degraded = resolve_solver_cell(room.polygon, room.walls)
    assert cell == pytest.approx(SOLVER_CELL)
    assert degraded is False
    assert estimate <= MAX_SOLVER_PATCHES


def test_resolve_coarsens_100x60_within_cap():
    room = define_room([(0, 0), (100, 0), (100, 60), (0, 60)], 8.0)
    raw = estimate_solver_patches(room.polygon, room.walls, SOLVER_CELL)
    assert raw > MAX_SOLVER_PATCHES  # would need raw**2*8 bytes for F
    cell, estimate, degraded = resolve_solver_cell(room.polygon, room.walls)
    assert degraded is True
    assert cell > SOLVER_CELL
    assert estimate <= MAX_SOLVER_PATCHES
    # Dense F matrix bound: n^2 x 8 bytes.
    assert estimate**2 * 8 <= MAX_SOLVER_PATCHES**2 * 8


def test_resolve_degenerate_polygon_never_blows_up():
    cell, estimate, degraded = resolve_solver_cell([(0, 0), (1, 0)], [])
    assert (cell, estimate, degraded) == (SOLVER_CELL, 0, False)


def _payload(poly, height, spacing, offset) -> CalculateRequest:
    return CalculateRequest(
        polygon=[Point2D(x=x, y=y) for x, y in poly],
        height=height,
        grid=GridInput(
            x=AxisGrid(spacing=spacing, offsetBeginning=offset, offsetEnding=offset),
            y=AxisGrid(spacing=spacing, offsetBeginning=offset, offsetEnding=offset),
        ),
    )


def test_small_room_reports_full_resolution_solver():
    result = calculate(_payload([(0, 0), (4, 0), (4, 4), (0, 4)], 3.0, 2.0, 1.0), SAMPLE_IES)
    assert result.solverCell == pytest.approx(SOLVER_CELL)
    assert result.solverDegraded is False
    assert result.evaluation.average > 0


@needs_luxcore
def test_100x60_study_completes_degraded():
    result = calculate(
        _payload([(0, 0), (100, 0), (100, 60), (0, 60)], 8.0, 10.0, 5.0), SAMPLE_IES
    )
    assert result.solverDegraded is True
    assert result.solverCell > SOLVER_CELL
    assert len(result.fixtures) == 60
    assert result.evaluation.average > 0
    assert max(result.totalFloorIlluminance.values) > 0
