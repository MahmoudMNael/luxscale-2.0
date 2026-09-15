import math

import pytest

from app.domain.exceptions import GeometryError
from app.domain.models import FloorSurface, WallSurface
from app.services.geometry_service import define_room, generate_patches
from app.services.vector_math import (
    EPS,
    clip_rect_to_polygon,
    en12464_spacing,
    inset_rings,
    point_in_polygon,
    signed_area,
)


def _fit_count(span: float, spacing: float) -> int:
    return max(1, math.ceil(span / spacing - EPS))


def test_en12464_spacing_ten_metres():
    assert en12464_spacing(10.0) == pytest.approx(1.0)


def test_ccw_room_has_inward_normals():
    room = define_room([(0, 0), (4, 0), (4, 3), (0, 3)], height=2.5)
    assert len(room.walls) == 4
    south = next(w for w in room.walls if w.id == "W1")
    assert south.normal[1] > 0


def test_floor_patches_l_shape_keeps_centres_inside():
    l_poly = [(0, 0), (4, 0), (4, 1), (1, 1), (1, 3), (0, 3)]
    patches = generate_patches(FloorSurface(l_poly), plane_z=0.0)
    assert patches
    assert all(p.center[2] == 0.0 for p in patches)
    assert all(point_in_polygon((p.center[0], p.center[1]), l_poly) for p in patches)


def test_floor_patches_inset_rect_symmetric_centres():
    border = 0.5
    patches = generate_patches(
        FloorSurface([(0, 0), (4, 0), (4, 3), (0, 3)]),
        plane_z=0.0,
        border=border,
    )
    width, height = 3.0, 2.0
    nx = _fit_count(width, en12464_spacing(width))
    ny = _fit_count(height, en12464_spacing(height))
    dx, dy = width / nx, height / ny
    xs = [p.center[0] for p in patches]
    ys = [p.center[1] for p in patches]
    assert len(patches) == nx * ny
    assert min(xs) == pytest.approx(border + dx / 2)
    assert max(xs) == pytest.approx(4 - border - dx / 2)
    assert min(ys) == pytest.approx(border + dy / 2)
    assert max(ys) == pytest.approx(3 - border - dy / 2)
    assert abs((min(xs) - border) - ((4 - border) - max(xs))) < 1e-6


def test_floor_patches_leftover_room_has_no_sliver_centroid():
    poly = [(0, 0), (4.85, 0), (4.85, 5.26), (0, 5.26)]
    border = 0.25
    patches = generate_patches(FloorSurface(poly), plane_z=0.0, border=border)
    assert patches
    assert not any(abs(p.center[0] - 4.42) < 0.02 and abs(p.center[1] - 4.88) < 0.02 for p in patches)
    xs = [p.center[0] for p in patches]
    ys = [p.center[1] for p in patches]
    assert abs((min(xs) - border) - ((4.85 - border) - max(xs))) < 1e-6
    assert abs((min(ys) - border) - ((5.26 - border) - max(ys))) < 1e-6


def test_floor_patches_inset_skips_l_inner_edge():
    l_poly = [(0, 0), (8, 0), (8, 3), (3, 3), (3, 8), (0, 8)]
    border = 0.5
    patches = generate_patches(FloorSurface(l_poly), plane_z=0.0, border=border)
    domains = inset_rings(l_poly, border)
    assert patches
    assert domains
    xs = [p[0] for ring in domains for p in ring]
    ys = [p[1] for ring in domains for p in ring]
    xmin, ymin = min(xs), min(ys)
    width, height = max(xs) - xmin, max(ys) - ymin
    dx = width / _fit_count(width, en12464_spacing(width))
    dy = height / _fit_count(height, en12464_spacing(height))
    assert not any(p.center[0] > 3.0 and p.center[1] > 3.0 for p in patches)
    for p in patches:
        cx, cy = p.center[0], p.center[1]
        assert any(point_in_polygon((cx, cy), ring) for ring in domains)
        i = (cx - xmin) / dx - 0.5
        j = (cy - ymin) / dy - 0.5
        assert abs(i - round(i)) < 1e-6
        assert abs(j - round(j)) < 1e-6


def test_floor_patches_inset_can_empty():
    tiny = [(0, 0), (0.8, 0), (0.8, 0.8), (0, 0.8)]
    assert generate_patches(FloorSurface(tiny), plane_z=0.0, border=0.5) == []


def test_wall_patches_equal_fit():
    wall = WallSurface("W1", (0.0, 0.0), (4.2, 0.0), 3.0, (0.0, 1.0))
    patches = generate_patches(wall, 0.5, plane_z=0.0)
    ns = _fit_count(4.2, 0.5)
    nz = _fit_count(3.0, 0.5)
    assert len(patches) == ns * nz
    assert len({round(p.area, 9) for p in patches}) == 1


def test_subdivide_wall_patches_maps_onto_coarse():
    from app.services.geometry_service import subdivide_wall_patches

    wall = WallSurface("W1", (0.0, 0.0), (4.25, 0.0), 3.0, (0.0, 1.0))
    coarse = generate_patches(wall, 0.5, plane_z=0.0)
    fine, coarse_idx = subdivide_wall_patches(coarse, wall)
    assert len(fine) == 4 * len(coarse)
    assert sorted(coarse_idx) == [i for i in range(len(coarse)) for _ in range(4)]
    assert coarse_idx[0] == 0
    assert coarse_idx[-1] == len(coarse) - 1


def test_wall_evaluation_grid_15pct_capped_and_1m_neglect():
    from app.domain.models import Wall
    from app.services.geometry_service import generate_wall_evaluation_grid, resolve_wall_border

    assert resolve_wall_border(4.0, 3.0, None) == pytest.approx(0.45)
    assert resolve_wall_border(8.0, 5.0, None) == pytest.approx(0.5)
    assert resolve_wall_border(4.0, 3.0, 0.25) == pytest.approx(0.25)
    tiny = Wall(id="W9", start=(0.0, 0.0), end=(0.9, 0.0), length=0.9, normal=(0.0, 1.0), height=3.0)
    patches, meta = generate_wall_evaluation_grid(tiny, resolve_wall_border(tiny.length, tiny.height, None))
    assert patches == []
    edge = Wall(id="W1", start=(0.0, 0.0), end=(1.0, 0.0), length=1.0, normal=(0.0, 1.0), height=3.0)
    patches, _ = generate_wall_evaluation_grid(edge, resolve_wall_border(edge.length, edge.height, None))
    assert patches == []
    kept = Wall(id="W2", start=(0.0, 0.0), end=(1.01, 0.0), length=1.01, normal=(0.0, 1.0), height=3.0)
    patches, meta = generate_wall_evaluation_grid(kept, resolve_wall_border(kept.length, kept.height, None))
    assert patches
    assert meta["border"] == pytest.approx(min(0.15 * 1.01, 0.5))


def test_per_axis_spacing_matches_relux_8x8():
    from app.services.geometry_service import generate_floor_evaluation_grid, generate_wall_evaluation_grid
    from app.domain.models import Wall

    demov1 = [(0, 0), (4.85, 0), (4.85, 5.26), (1.45, 5.26), (1.45, 4.33), (0.55, 4.33), (0.55, 1.63), (0, 1.63)]
    _, meta = generate_floor_evaluation_grid(demov1, 0.0, 0.5)
    assert int(meta["nx"]) == 8
    assert int(meta["ny"]) == 8
    assert meta["spacingX"] == pytest.approx(en12464_spacing(3.85), rel=0.05)
    assert meta["spacingY"] == pytest.approx(en12464_spacing(4.26), rel=0.05)
    wall = Wall(id="W1", start=(0.0, 0.0), end=(4.0, 0.0), length=4.0, normal=(0.0, 1.0), height=2.0)
    _, wmeta = generate_wall_evaluation_grid(wall, 0.3)
    assert int(wmeta["nx"]) == _fit_count(3.4, en12464_spacing(3.4))
    assert int(wmeta["ny"]) == _fit_count(1.4, en12464_spacing(1.4))


def test_horizontal_border_defaults_to_half_metre():
    from app.services.geometry_service import resolve_horizontal_border

    assert resolve_horizontal_border([(0, 0), (8, 0), (8, 6), (0, 6)], None) == pytest.approx(0.5)
    assert resolve_horizontal_border([(0, 0), (8, 0), (8, 6), (0, 6)], 0.25) == pytest.approx(0.25)


def test_zero_area_polygon_fails():
    try:
        define_room([(0, 0), (1, 0), (2, 0)], height=3)
    except GeometryError as exc:
        assert exc.code == "GEOMETRY_INVALID"
    else:
        raise AssertionError("expected GeometryError")


def test_shapely_clip_keeps_inner_corner():
    l_poly = [(0, 0), (4, 0), (4, 1), (1, 1), (1, 3), (0, 3)]
    rings = clip_rect_to_polygon((0.5, 0.5, 1.5, 1.5), l_poly)
    assert rings
    assert point_in_polygon((0.75, 0.75), l_poly)
    assert not point_in_polygon((2, 2), l_poly)
    assert signed_area([(0, 0), (1, 0), (1, 1), (0, 1)]) > 0
