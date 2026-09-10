from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

Vec2 = tuple[float, float]
Vec3 = tuple[float, float, float]


@dataclass(frozen=True)
class Wall:
    id: str
    start: Vec2
    end: Vec2
    length: float
    normal: Vec2
    height: float


@dataclass(frozen=True)
class Room:
    polygon: list[Vec2]
    height: float
    walls: list[Wall]
    step: float = 1.0


@dataclass(frozen=True)
class Patch:
    id: str
    surface_type: Literal["floor", "wall"]
    parent_id: str
    center: Vec3
    normal: Vec3
    area: float
    size: float


@dataclass(frozen=True)
class IESProfile:
    vertical_angles: list[float]
    horizontal_angles: list[float]
    candela_table: list[list[float]]
    multiplier: float
    ballast_factor: float
    ballast_lamp_factor: float
    flux_scale: float
    width: float
    length: float
    height: float


@dataclass(frozen=True)
class Fixture:
    id: str
    position: Vec3
    aim_direction: Vec3
    rotation: float
    ies_profile: IESProfile


@dataclass(frozen=True)
class Matrix:
    values: list[float]
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class RayGeometry:
    distance: float
    theta_source: float
    phi_source: float
    theta_incidence: float


@dataclass(frozen=True)
class FloorSurface:
    polygon: list[Vec2]
    type: Literal["floor"] = "floor"


@dataclass(frozen=True)
class WallSurface:
    wall_id: str
    start: Vec2
    end: Vec2
    height: float
    normal: Vec2
    type: Literal["wall"] = "wall"
