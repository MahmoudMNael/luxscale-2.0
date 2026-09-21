from __future__ import annotations

import math

from app.domain.exceptions import NoFixturesError
from app.domain.models import Fixture, FixturePlacement, IESProfile, Room, Vec3
from app.schemas.grid import GridInput
from app.services.vector_math import EPS, normalize, point_in_polygon

import logging

_log = logging.getLogger(__name__)

_ELEMENT = 0.2


def build_fixtures(
    polygon: list[tuple[float, float]],
    placements: list[FixturePlacement],
    profiles: dict[str, IESProfile],
    mounting_default: float,
    default_ref: str | None = None,
) -> list[Fixture]:
    """Free placements -> domain fixtures. No grid involved.

    Skips placements outside the polygon (warns); raises NoFixturesError
    only when nothing remains. Per-fixture z/rotation/aim/photometry win
    over the shared defaults.
    """
    fixtures: list[Fixture] = []
    for placement in placements:
        if not point_in_polygon((placement.x, placement.y), polygon):
            _log.warning("fixture %s outside room polygon, skipped", placement.id)
            continue
        profile = profiles.get(placement.ies_ref or default_ref or "")
        if profile is None:  # caller validates refs; guard for direct use
            raise NoFixturesError(f"Fixture '{placement.id}' has no photometry profile.")
        z = placement.z if placement.z is not None else mounting_default - profile.height / 2.0
        fixtures.append(
            Fixture(
                id=placement.id,
                position=(placement.x, placement.y, z),
                aim_direction=normalize(placement.aim_direction),
                rotation=placement.rotation,
                ies_profile=profile,
            )
        )
    if not fixtures:
        raise NoFixturesError("No fixtures fall inside the room polygon for the given grid.")
    return fixtures


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
    placements: list[FixturePlacement] = []
    n = 1
    for y in axis_positions(ymin, ymax, grid.y.spacing, grid.y.offset_beginning, grid.y.offset_ending):
        for x in axis_positions(xmin, xmax, grid.x.spacing, grid.x.offset_beginning, grid.x.offset_ending):
            if not point_in_polygon((x, y), room.polygon):
                continue
            placements.append(
                FixturePlacement(id=f"F{n}", x=x, y=y, rotation=rotation, aim_direction=aim)
            )
            n += 1
    if not placements:
        raise NoFixturesError("No fixtures fall inside the room polygon for the given grid.")
    return build_fixtures(
        room.polygon, placements, {"default": ies_profile}, mounting_height, "default"
    )


def luminous_opening(fixture: Fixture) -> tuple[list[Vec3], list[Vec3]]:
    # C++ fast path (identical rectangle subdivision). Falls back on any issue.
    try:
        from app.services._luxcore_bridge import LuxCoreRuntime

        _mod = LuxCoreRuntime().module
        if _mod is not None:
            pos = [float(fixture.position[0]), float(fixture.position[1]), float(fixture.position[2])]
            corners = _mod.luminous_corners(
                pos, float(fixture.rotation),
                float(fixture.ies_profile.length), float(fixture.ies_profile.width),
            )
            elements = _mod.luminous_elements(
                pos, float(fixture.rotation),
                float(fixture.ies_profile.length), float(fixture.ies_profile.width),
            )
            return (
                [(float(c[0]), float(c[1]), float(c[2])) for c in corners.tolist()],
                [(float(e[0]), float(e[1]), float(e[2])) for e in elements.tolist()],
            )
    except Exception:
        pass
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


def axis_positions(lo: float, hi: float, spacing: float, offset_beginning: float, offset_ending: float) -> list[float]:
    start = lo + offset_beginning
    stop = hi - offset_ending
    points: list[float] = []
    x = start
    while x <= stop + EPS:
        points.append(x)
        x += spacing
    return points
