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
    spacing = en12464_spacing(max(width, height))
    nx, ny = _fit_count(width, spacing), _fit_count(height, spacing)
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
    spacing = en12464_spacing(max(width, height))
    dx = width / _fit_count(width, spacing)
    dy = height / _fit_count(height, spacing)
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
