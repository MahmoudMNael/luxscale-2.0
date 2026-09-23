from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.app_settings import (
    CEILING_REFLECTANCE_FACTOR,
    FLOOR_REFLECTANCE_FACTOR,
    WALL_REFLECTANCE_FACTOR,
)
from app.automate.layouts import frange
from app.schemas.calculate import FixturePlacementDto
from app.schemas.geometry import Point2D

_MAX_CANDIDATES = 2000

# Application derivation rule: mountingHeight >= this -> "industrial",
# else "interior". EDIT HERE to change the threshold.
APPLICATION_HEIGHT_THRESHOLD_M = 3.0

FixtureApplication = Literal["interior", "industrial"]


def application_for_mounting_height(mounting_height: float) -> FixtureApplication:
    """Derive fixture application from mounting height. EDIT threshold above."""
    return "industrial" if mounting_height >= APPLICATION_HEIGHT_THRESHOLD_M else "interior"


class TargetDto(BaseModel):
    """Resolved target echoed back in the response (derived from the standard)."""

    model_config = ConfigDict(populate_by_name=True, serialize_by_alias=True)

    avgLux: float = Field(..., gt=0, description="Required maintained Eavg, lux")
    uniformity: float = Field(..., ge=0, le=1, description="Required U0 = Emin/Eavg")
    maxOverdesign: float = Field(default=0.3, ge=0, description="Allowed Eavg excess ratio")


class SpacingRange(BaseModel):
    min: float = Field(..., gt=0)
    max: float = Field(..., gt=0)
    step: float = Field(..., gt=0)


class SearchSpaceDto(BaseModel):
    spacingX: SpacingRange = SpacingRange(min=1.5, max=4.0, step=0.5)
    spacingY: SpacingRange = SpacingRange(min=1.5, max=4.0, step=0.5)
    offsetFractions: list[float] = Field(
        default=[0.5], min_length=1, description="Symmetric offset as fraction of spacing"
    )
    rotations: list[float] = Field(default=[0.0, 90.0], min_length=1)
    maxFixtures: int = Field(default=64, ge=1)
    minWallClearance: float = Field(default=0.0, ge=0)
    shrMax: float = Field(default=1.5, gt=0, description="Max spacing / mounting-height ratio")


class AutomateRequest(BaseModel):
    """Automate input — JSON body (no file uploads).

    - `activityId`: required, resolves via
      GET {STANDARDS_BASE_URL}/api/v1/standards/{activityId}.
    - `variantIds`: optional variant UUIDs. None/empty = all main-solution
      variants for the derived application
      (GET {FIXTURES_BASE_URL}/api/v1/fixtures/variants/
       ?application={app}&is_main_solution=true).
    - `ceilingHeight` + `mountingHeight`: both required (no `height` fallback).
    - Reflectances: optional, None = app_settings defaults.
    - No `target`, no `power`, no `fixtureIds`, no `iesFiles`.
    """

    model_config = ConfigDict(populate_by_name=True)

    polygon: list[Point2D] = Field(..., min_length=3)
    ceilingHeight: float = Field(..., gt=0, description="Ceiling plane height in meters")
    mountingHeight: float = Field(..., gt=0, description="Fixture mounting height in meters")
    workPlaneHeight: float = Field(default=0.0, ge=0)
    floorZone: float | None = Field(default=0.5, ge=0)
    wallZone: float | None = Field(default=None, ge=0)
    wallReflectance: float | None = Field(
        default=None, ge=0, le=1,
        description=f"Wall reflectance; None = app_settings ({WALL_REFLECTANCE_FACTOR})",
    )
    floorReflectance: float | None = Field(
        default=None, ge=0, le=1,
        description=f"Floor reflectance; None = app_settings ({FLOOR_REFLECTANCE_FACTOR})",
    )
    ceilingReflectance: float | None = Field(
        default=None, ge=0, le=1,
        description=f"Ceiling reflectance; None = app_settings ({CEILING_REFLECTANCE_FACTOR})",
    )
    activityId: str = Field(
        ..., min_length=1, description="Standard id key for the target illuminance/uniformity",
    )
    variantIds: list[str] | None = Field(
        default=None,
        description="Variant UUIDs from the fixtures provider; None/empty = all main-solution variants for the derived application",
    )
    search: SearchSpaceDto = Field(default_factory=SearchSpaceDto)
    topK: int = Field(default=5, ge=1, le=20)
    stageB: int = Field(default=12, ge=1, le=50, description="Full-physics verifications")

    @property
    def application(self) -> FixtureApplication:
        return application_for_mounting_height(self.mountingHeight)

    @model_validator(mode="after")
    def _check(self):
        if self.mountingHeight > self.ceilingHeight:
            raise ValueError("mountingHeight cannot exceed ceilingHeight")
        if self.variantIds is not None and len(self.variantIds) == 0:
            # Empty list == auto-list, normalize downstream; keep as-is here.
            pass
        for name in ("spacingX", "spacingY"):
            rng = getattr(self.search, name)
            if rng.min > rng.max:
                raise ValueError(f"'search.{name}.min' cannot exceed max.")
        if any(not 0.0 <= f <= 1.0 for f in self.search.offsetFractions):
            raise ValueError("'search.offsetFractions' must be within [0, 1].")
        n = (
            len(frange(self.search.spacingX.min, self.search.spacingX.max, self.search.spacingX.step))
            * len(frange(self.search.spacingY.min, self.search.spacingY.max, self.search.spacingY.step))
            * len(self.search.offsetFractions)
            * len(self.search.rotations)
        )
        if n > _MAX_CANDIDATES:
            raise ValueError(f"Search space has {n} candidates (max {_MAX_CANDIDATES}); widen steps.")
        return self


class GridHintDto(BaseModel):
    spacingX: float
    spacingY: float
    offsetX: float
    offsetY: float
    rotation: float


class SolutionDto(BaseModel):
    fixtureId: str
    fixtureCount: int
    placements: list[FixturePlacementDto]
    grid: GridHintDto
    average: float
    minimum: float
    maximum: float
    uniformity: float
    overdesign: float
    powerW: float | None = None
    powerDensity: float | None = None


class AutomateResponse(BaseModel):
    target: TargetDto
    solutions: list[SolutionDto]
    evaluatedA: int = Field(..., description="Direct-only candidates ranked")
    evaluatedB: int = Field(..., description="Full-physics verifications")
    pruned: dict[str, int]
    closestMiss: SolutionDto | None = None
