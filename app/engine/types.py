"""Engine input/output types. Framework-free: no FastAPI, no pydantic, no providers.

Any module (`http`, `automate`, scripts, tests) builds an EngineInput and calls
app.engine.calculate — the engine never imports its callers back.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.app_settings import (
    CEILING_REFLECTANCE_FACTOR,
    FLOOR_REFLECTANCE_FACTOR,
    MAINTENANCE_FACTOR,
    MAX_SOLVER_PATCHES,
    NUM_BOUNCES,
    SOLVER_CELL,
    WALL_REFLECTANCE_FACTOR,
    WORK_PLANE_HEIGHT,
    C0_ORIENTATION_OFFSET_DEG,
)
from app.domain.models import Fixture, FixturePlacement, Matrix, Patch, Vec2, Vec3  # noqa: F401

Weights = tuple[list[int], list[int], list[float], int, int]


@dataclass(frozen=True)
class RoomInput:
    polygon: list[Vec2]
    ceiling_height: float
    mounting_height: float | None = None  # None = at ceiling
    work_plane_height: float = WORK_PLANE_HEIGHT
    floor_zone: float | None = 0.5
    wall_zone: float | None = None


@dataclass(frozen=True)
class PhysicsOptions:
    wall_reflectance: float = WALL_REFLECTANCE_FACTOR
    floor_reflectance: float = FLOOR_REFLECTANCE_FACTOR
    ceiling_reflectance: float = CEILING_REFLECTANCE_FACTOR
    bounces: int = NUM_BOUNCES  # 0 = direct only (cheap prune pass for automate)
    maintenance_factor: float = MAINTENANCE_FACTOR
    c0_offset_deg: float = C0_ORIENTATION_OFFSET_DEG
    solver_cell: float = SOLVER_CELL
    max_solver_patches: int = MAX_SOLVER_PATCHES


@dataclass(frozen=True)
class EngineInput:
    room: RoomInput
    placements: list[FixturePlacement]


@dataclass(frozen=True)
class EvalGrids:
    """EN 12464 evaluation grids. Standalone output of step S2."""

    floor: list[Patch]
    floor_meta: dict[str, float] = field(default_factory=dict)
    floor_border: float = 0.5
    walls: dict[str, list[Patch]] = field(default_factory=dict)
    wall_metas: dict[str, dict[str, float]] = field(default_factory=dict)
    ceiling: list[Patch] = field(default_factory=list)
    ceiling_meta: dict[str, float] = field(default_factory=dict)
    ceiling_border: float = 0.5
    work_z: float = WORK_PLANE_HEIGHT


@dataclass(frozen=True)
class SolverCache:
    """Fixture-independent solver mesh. Build once per room, reuse for every
    candidate layout (automate path). ponytail: F/G transfer matrices are
    still rebuilt per run() call inside the radiosity solver; hoist them here
    when profiling says the automate search needs it."""

    floor_full: list[Patch] = field(default_factory=list)
    floor_full_meta: dict[str, float] = field(default_factory=dict)
    ceiling_full: list[Patch] = field(default_factory=list)
    ceiling_full_meta: dict[str, float] = field(default_factory=dict)
    wall_full: dict[str, list[Patch]] = field(default_factory=dict)
    wall_full_metas: dict[str, dict[str, float]] = field(default_factory=dict)
    sources: list[Patch] = field(default_factory=list)
    floor_weights: Weights = field(default_factory=lambda: ([0], [], [], 0, 0))
    ceiling_weights: Weights = field(default_factory=lambda: ([0], [], [], 0, 0))
    wall_weights: dict[str, Weights] = field(default_factory=dict)
    cell: float = SOLVER_CELL
    degraded: bool = False


@dataclass(frozen=True)
class EvalSummary:
    average: float
    minimum: float
    maximum: float
    uniformity: float
    min_index: int
    max_index: int
    count: int


@dataclass(frozen=True)
class EngineResult:
    """Domain-level result. HTTP layer maps this to CalculateResponse DTOs."""

    fixtures: list[Fixture] = field(default_factory=list)
    eval: EvalGrids = field(default_factory=EvalGrids)
    direct_floor: dict[str, Matrix] = field(default_factory=dict)  # fixtureId → maintained
    direct_walls: dict[str, dict[str, Matrix]] = field(default_factory=dict)  # wallId → fixtureId
    direct_ceiling: dict[str, Matrix] = field(default_factory=dict)
    indirect_floor: dict[str, Matrix] = field(default_factory=dict)  # originId → maintained
    indirect_ceiling: dict[str, Matrix] = field(default_factory=dict)
    indirect_walls: dict[str, dict[str, Matrix]] = field(default_factory=dict)
    total_floor: Matrix = field(default_factory=lambda: Matrix([], {}))
    total_ceiling: Matrix = field(default_factory=lambda: Matrix([], {}))
    total_walls: dict[str, Matrix] = field(default_factory=dict)
    evaluation: EvalSummary = field(
        default_factory=lambda: EvalSummary(0.0, 0.0, 0.0, 0.0, 0, 0, 0)
    )
    ceiling_evaluation: EvalSummary | None = None
    wall_evaluations: dict[str, EvalSummary] = field(default_factory=dict)
    bounces: int = 0
    ceiling_height: float = 0.0
    mounting_height: float = 0.0
    solver_cell: float = SOLVER_CELL
    solver_degraded: bool = False
    options: PhysicsOptions = field(default_factory=PhysicsOptions)
