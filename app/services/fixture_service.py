from __future__ import annotations

from app.domain.exceptions import NoFixturesError
from app.domain.models import Fixture, IESProfile, Room
from app.schemas.grid import GridInput
from app.services.vector_math import EPS, normalize, point_in_polygon


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
                    position=(x, y, mounting_height),
                    aim_direction=aim,
                    rotation=rotation,
                    ies_profile=ies_profile,
                )
            )
            n += 1
    if not fixtures:
        raise NoFixturesError("No fixtures fall inside the room polygon for the given grid.")
    return fixtures


def _axis(lo: float, hi: float, spacing: float, offset_beginning: float, offset_ending: float) -> list[float]:
    start = lo + offset_beginning
    stop = hi - offset_ending
    points: list[float] = []
    x = start
    while x <= stop + EPS:
        points.append(x)
        x += spacing
    return points
