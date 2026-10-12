from __future__ import annotations

import pytest
from app.modules.calculation.grid_generator import generate_calculation_grid


def test_en12464_grid_generation_rectangular() -> None:
    # 8m x 6m room
    room_polygon = [(0.0, 0.0), (8.0, 0.0), (8.0, 6.0), (0.0, 6.0)]
    grid = generate_calculation_grid(room_polygon, workplane_height=0.85, wall_margin=0.5)

    assert grid.nx > 0
    assert grid.ny > 0
    assert grid.wall_zone == 0.5
    assert grid.work_plane_height == 0.85
    assert len(grid.points) == grid.nx * grid.ny

    # Check bounds of points
    for x, y, z in grid.points:
        assert 0.5 <= x <= 7.5
        assert 0.5 <= y <= 5.5
        assert z == 0.85


def test_custom_pitch_grid_generation() -> None:
    # 8m x 6m room with fixed pitch 0.5m
    room_polygon = [(0.0, 0.0), (8.0, 0.0), (8.0, 6.0), (0.0, 6.0)]
    grid = generate_calculation_grid(
        room_polygon, workplane_height=0.85, wall_margin=0.5, pitch=0.5
    )

    # Inset span X = 7m -> 7 / 0.5 = 14 cells
    assert grid.nx == 14
    # Inset span Y = 5m -> 5 / 0.5 = 10 cells
    assert grid.ny == 10
    assert len(grid.points) == 140


def test_l_shaped_polygon_filtering() -> None:
    # L-shaped room: 8x6 with top-right 4x3 cut out
    l_polygon = [
        (0.0, 0.0),
        (8.0, 0.0),
        (8.0, 3.0),
        (4.0, 3.0),
        (4.0, 6.0),
        (0.0, 6.0),
    ]
    grid = generate_calculation_grid(l_polygon, workplane_height=0.85, wall_margin=0.2, pitch=0.5)

    assert len(grid.points) > 0
    # Ensure no points fall in the excluded cutout area (x > 4 and y > 3)
    for x, y, _ in grid.points:
        assert not (x > 4.0 and y > 3.0)
