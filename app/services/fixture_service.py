from __future__ import annotations

import math

from app.domain.exceptions import NoFixturesError
from app.domain.models import Fixture, IESProfile, Room, Vec3
from app.schemas.grid import GridInput
from app.services.vector_math import EPS, normalize, point_in_polygon

_ELEMENT = 0.2


def generate_fixture_grid(
    room: Room,
    grid: GridInput,
    mounting_height: float,
    ies_profile: IESProfile,
    *,
    aim_direction: tuple[float, float, float] = (0.0, 0.0, -1.0),
    rotation: float = 0.0,
) -> list[Fixture]:
    xs = [p[0] for p in room.polygon]
    ys = [p[1] for p in room.polygon]
    xmin, xmax, ymin, ymax = min(xs), max(xs), min(ys), max(ys)
    aim = normalize(aim_direction)
    fixtures: list[Fixture] = []
    n = 1
    for y in _axis(ymin, ymax, grid.y.spacing, grid.y.offset_beginning, grid.y.offset_ending):
        for x in _axis(xmin, xmax, grid.x.spacing, grid.x.offset_beginning, grid.x.offset_ending):
            if not point_in_polygon((x, y), room.polygon):
                continue
            fixtures.append(
                Fixture(
                    id=f"F{n}",
                    position=(x, y, mounting_height - ies_profile.height / 2.0),
                    aim_direction=aim,
                    rotation=rotation,
                    ies_profile=ies_profile,
                )
            )
            n += 1
    if not fixtures:
        raise NoFixturesError("No fixtures fall inside the room polygon for the given grid.")
    return fixtures


def luminous_opening(fixture: Fixture) -> tuple[list[Vec3], list[Vec3]]:
    # ponytail: rectangle in the aim-perpendicular plane only; 5-face box if a tall opening emits at 90°.
    cx, cy, cz = fixture.position
    length, width = fixture.ies_profile.length, fixture.ies_profile.width
    rot = math.radians(fixture.rotation)
    ux, uy = math.cos(rot), math.sin(rot)
    vx, vy = -math.sin(rot), math.cos(rot)
    hl, hw = length / 2.0, width / 2.0
    corners = [
        (cx - ux * hl - vx * hw, cy - uy * hl - vy * hw, cz),
        (cx + ux * hl - vx * hw, cy + uy * hl - vy * hw, cz),
        (cx + ux * hl + vx * hw, cy + uy * hl + vy * hw, cz),
        (cx - ux * hl + vx * hw, cy - uy * hl + vy * hw, cz),
    ]
    nx = max(1, math.ceil(length / _ELEMENT - EPS))
    ny = max(1, math.ceil(width / _ELEMENT - EPS))
    dx, dy = length / nx, width / ny
    elements = [
        (
            cx + ux * ((i + 0.5) * dx - hl) + vx * ((j + 0.5) * dy - hw),
            cy + uy * ((i + 0.5) * dx - hl) + vy * ((j + 0.5) * dy - hw),
            cz,
        )
        for j in range(ny)
        for i in range(nx)
    ]
    return corners, elements


def _axis(lo: float, hi: float, spacing: float, offset_beginning: float, offset_ending: float) -> list[float]:
    start = lo + offset_beginning
    stop = hi - offset_ending
    points: list[float] = []
    x = start
    while x <= stop + EPS:
        points.append(x)
        x += spacing
    return points
