from __future__ import annotations

import math

from app.domain.models import Fixture, Matrix, Patch, RayGeometry, Vec3
from app.services.fixture_service import luminous_opening
from app.services.ies_service import get_candela
from app.services.vector_math import EPS, angle_deg, wrap_deg


def compute_ray_geometry(fixture: Fixture, patch: Patch, source: Vec3 | None = None) -> RayGeometry:
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
        phi_source = wrap_deg(math.degrees(math.atan2(to_patch[1], to_patch[0])) + fixture.rotation)
    return RayGeometry(distance, theta_source, phi_source, theta_incidence)


def compute_direct_illuminance(fixture: Fixture, patch: Patch) -> float:
    _, elements = luminous_opening(fixture)
    n = len(elements)
    total = 0.0
    for origin in elements:
        ray = compute_ray_geometry(fixture, patch, origin)
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
) -> Matrix:
    metadata: dict = {
        "kind": "direct",
        "surfaceType": surface_type,
        "patchSize": patch_size,
        "fixtureId": fixture.id,
    }
    if wall_id is not None:
        metadata["wallId"] = wall_id
    return Matrix([compute_direct_illuminance(fixture, patch) for patch in patches], metadata)
