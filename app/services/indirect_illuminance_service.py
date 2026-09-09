from __future__ import annotations

import math

from app.domain.exceptions import GeometryError
from app.domain.models import Matrix, Patch
from app.services.vector_math import EPS, angle_deg


def compute_indirect_contribution(
    source_patch: Patch,
    source_illuminance: float,
    target_patch: Patch,
    reflectance: float,
) -> float:
    line = (
        target_patch.center[0] - source_patch.center[0],
        target_patch.center[1] - source_patch.center[1],
        target_patch.center[2] - source_patch.center[2],
    )
    distance = math.sqrt(line[0] ** 2 + line[1] ** 2 + line[2] ** 2)
    if distance < EPS:
        return 0.0
    theta1 = angle_deg(source_patch.normal, line)
    theta2 = angle_deg(target_patch.normal, (-line[0], -line[1], -line[2]))
    if theta1 >= 90.0 or theta2 >= 90.0:
        return 0.0
    return (
        source_illuminance
        * reflectance
        * source_patch.area
        * math.cos(math.radians(theta1))
        * math.cos(math.radians(theta2))
    ) / (math.pi * distance**2)


def compute_indirect_matrix_from_wall(
    wall_patches: list[Patch],
    wall_direct_matrix: Matrix,
    floor_patches: list[Patch],
    reflectance: float,
    *,
    source_wall_id: str,
    patch_size: float,
) -> Matrix:
    if len(wall_direct_matrix.values) != len(wall_patches):
        raise GeometryError("Cannot sum matrices with different patch layouts.")
    values = []
    for target in floor_patches:
        total = 0.0
        for source, e_source in zip(wall_patches, wall_direct_matrix.values, strict=True):
            total += compute_indirect_contribution(source, e_source, target, reflectance)
        values.append(total)
    return Matrix(
        values,
        {
            "kind": "indirect",
            "surfaceType": "floor",
            "sourceWallId": source_wall_id,
            "patchSize": patch_size,
        },
    )
