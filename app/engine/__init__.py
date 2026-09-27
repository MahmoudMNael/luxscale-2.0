"""Calculation engine. Import from any module — no FastAPI, no providers here."""

from app.engine.pipeline import (
    build_eval_grids,
    build_room,
    build_solver_cache,
    calculate,
    resolve_fixtures,
    run,
)
from app.engine.types import (
    EngineInput,
    EngineResult,
    EvalGrids,
    EvalSummary,
    PhysicsOptions,
    RoomInput,
    SolverCache,
)

__all__ = [
    "EngineInput",
    "EngineResult",
    "EvalGrids",
    "EvalSummary",
    "PhysicsOptions",
    "RoomInput",
    "SolverCache",
    "build_eval_grids",
    "build_room",
    "build_solver_cache",
    "calculate",
    "resolve_fixtures",
    "run",
]
