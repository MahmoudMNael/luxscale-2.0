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
