from app.domain.exceptions import GeometryError
from app.domain.models import FloorSurface
from app.services.geometry_service import define_room, generate_patches
from app.services.vector_math import clip_rect_to_polygon, point_in_polygon, signed_area


def test_ccw_room_has_inward_normals():
    room = define_room([(0, 0), (4, 0), (4, 3), (0, 3)], height=2.5)
    assert len(room.walls) == 4
    south = next(w for w in room.walls if w.id == "W1")
    assert south.normal[1] > 0


def test_floor_patches_clip_to_l_shape():
    l_poly = [(0, 0), (4, 0), (4, 1), (1, 1), (1, 3), (0, 3)]
    patches = generate_patches(FloorSurface(l_poly), patch_size=1.0, plane_z=0.0)
    assert patches
    assert all(p.area > 0 for p in patches)
    assert all(p.center[2] == 0.0 for p in patches)
    assert abs(sum(p.area for p in patches) - 6.0) < 1e-6


def test_floor_patches_inset_rect():
    patches = generate_patches(
        FloorSurface([(0, 0), (4, 0), (4, 3), (0, 3)]),
        patch_size=0.5,
        plane_z=0.0,
        border=0.5,
    )
    xs = [p.center[0] for p in patches]
    ys = [p.center[1] for p in patches]
    assert len(patches) == 24
    assert abs(min(xs) - 0.75) < 1e-6
    assert abs(max(xs) - 3.25) < 1e-6
    assert abs(min(ys) - 0.75) < 1e-6
    assert abs(max(ys) - 2.25) < 1e-6
    assert abs(sum(p.area for p in patches) - 6.0) < 1e-6


def test_floor_patches_inset_skips_l_inner_edge():
    l_poly = [(0, 0), (8, 0), (8, 3), (3, 3), (3, 8), (0, 8)]
    patches = generate_patches(FloorSurface(l_poly), patch_size=0.5, plane_z=0.0, border=0.5)
    assert patches
    assert not any(p.center[0] > 3.1 and 2.4 < p.center[1] < 3.0 for p in patches)
    assert any(abs(p.center[0] - 0.75) < 1e-6 and abs(p.center[1] - 0.75) < 1e-6 for p in patches)


def test_floor_patches_inset_can_empty():
    tiny = [(0, 0), (0.8, 0), (0.8, 0.8), (0, 0.8)]
    assert generate_patches(FloorSurface(tiny), patch_size=0.5, plane_z=0.0, border=0.5) == []


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
