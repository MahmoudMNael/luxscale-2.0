from __future__ import annotations

import math

from app.domain.models import Fixture, Matrix, Patch, RayGeometry, Vec3
from app.services.fixture_service import luminous_opening
from app.services.ies_service import get_candela
from app.services.vector_math import (
    EPS,
    Vec2,
    angle_deg,
    is_convex_polygon,
    segment_inside_room,
    visibility_polygon,
    wrap_deg,
)


def compute_ray_geometry(
    fixture: Fixture, patch: Patch, source: Vec3 | None = None, *, c0_offset_deg: float = 0.0
) -> RayGeometry:
    ox, oy, oz = fixture.position if source is None else source
    to_patch = (
        patch.center[0] - ox,
        patch.center[1] - oy,
        patch.center[2] - oz,
    )
    distance = math.sqrt(to_patch[0] ** 2 + to_patch[1] ** 2 + to_patch[2] ** 2)
    theta_source = angle_deg(fixture.aim_direction, to_patch)
    toward_source = (
        ox - patch.center[0],
        oy - patch.center[1],
        oz - patch.center[2],
    )
    theta_incidence = angle_deg(patch.normal, toward_source)
    cross = (
        fixture.aim_direction[1] * to_patch[2] - fixture.aim_direction[2] * to_patch[1],
        fixture.aim_direction[2] * to_patch[0] - fixture.aim_direction[0] * to_patch[2],
        fixture.aim_direction[0] * to_patch[1] - fixture.aim_direction[1] * to_patch[0],
    )
    if math.sqrt(cross[0] ** 2 + cross[1] ** 2 + cross[2] ** 2) < EPS:
        phi_source = 0.0
    else:
        phi_source = wrap_deg(math.degrees(math.atan2(to_patch[1], to_patch[0])) + fixture.rotation + c0_offset_deg)
    return RayGeometry(distance, theta_source, phi_source, theta_incidence)


def compute_direct_illuminance(
    fixture: Fixture,
    patch: Patch,
    room_polygon: list[Vec2] | object | None = None,
    *,
    c0_offset_deg: float = 0.0,
) -> float:
    _, elements = luminous_opening(fixture)
    n = len(elements)
    vis_room = _visibility_for_direct(room_polygon)
    total = 0.0
    for origin in elements:
        if vis_room is not None:
            if not segment_inside_room(
                (origin[0], origin[1]), (patch.center[0], patch.center[1]), vis_room
            ):
                continue
        ray = compute_ray_geometry(fixture, patch, origin, c0_offset_deg=c0_offset_deg)
        if ray.distance < EPS or ray.theta_incidence >= 90.0:
            continue
        intensity = get_candela(fixture.ies_profile, ray.theta_source, ray.phi_source) / n
        total += (intensity / (ray.distance**2)) * math.cos(math.radians(ray.theta_incidence))
    return total


def compute_direct_matrix(
    fixture: Fixture,
    patches: list[Patch],
    surface_type: str,
    *,
    patch_size: float,
    wall_id: str | None = None,
    room_polygon: list[Vec2] | object | None = None,
    c0_offset_deg: float = 0.0,
) -> Matrix:
    from shapely.geometry import LineString
    from shapely.prepared import prep

    metadata: dict = {
        "kind": "direct",
        "surfaceType": surface_type,
        "patchSize": patch_size,
        "fixtureId": fixture.id,
    }
    if wall_id is not None:
        metadata["wallId"] = wall_id
    vis_room = _visibility_for_direct(room_polygon)
    if room_polygon is not None:
        metadata["occlusion"] = "room-polygon"
    prepared = prep(vis_room) if vis_room is not None else None
    _, elements = luminous_opening(fixture)
    n = len(elements)
    out: list[float] = []
    for patch in patches:
        total = 0.0
        for origin in elements:
            if prepared is not None:
                if not prepared.covers(
                    LineString([(origin[0], origin[1]), (patch.center[0], patch.center[1])])
                ):
                    continue
            ray = compute_ray_geometry(fixture, patch, origin, c0_offset_deg=c0_offset_deg)
            if ray.distance < EPS or ray.theta_incidence >= 90.0:
                continue
            intensity = get_candela(fixture.ies_profile, ray.theta_source, ray.phi_source) / n
            total += (intensity / (ray.distance**2)) * math.cos(math.radians(ray.theta_incidence))
        out.append(total)
    return Matrix(out, metadata)


def _visibility_for_direct(room_polygon: list[Vec2] | object | None) -> object | None:
    """Buffered room for direct occlusion (Relux parity).

    Wall centres sit exactly on the boundary; exact covers() flickers on
    float noise and zeroes whole walls. 3 mm outward buffer absorbs noise
    without changing real occlusion (same as indirect path).
    """
    if room_polygon is None:
        return None
    if isinstance(room_polygon, list):
        if is_convex_polygon(room_polygon):
            return None
        return visibility_polygon(room_polygon)
    return room_polygon
