from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.optimize.layouts import frange
from app.schemas.calculate import FixturePlacementDto
from app.schemas.geometry import Point2D

_MAX_CANDIDATES = 2000


class TargetDto(BaseModel):
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


class OptimizeRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    polygon: list[Point2D] = Field(..., min_length=3)
    height: float = Field(..., gt=0)
    ceilingHeight: float | None = Field(default=None, gt=0)
    mountingHeight: float | None = Field(default=None, gt=0)
    workPlaneHeight: float = Field(default=0.0, ge=0)
    floorZone: float | None = Field(default=0.5, ge=0)
    wallZone: float | None = Field(default=None, ge=0)
    target: TargetDto | None = Field(default=None, description="Inline target (or activityId)")
    activityId: str | None = Field(default=None, description="Standards-provider activity id")
    fixtureIds: list[str] | None = Field(
        default=None, min_length=1, description="Catalog ids from the fixtures provider"
    )
    power: dict[str, float] | None = Field(
        default=None, description="Watts per uploaded file name (for power density ranking)"
    )
    search: SearchSpaceDto = Field(default_factory=SearchSpaceDto)
    topK: int = Field(default=5, ge=1, le=20)
    stageB: int = Field(default=12, ge=1, le=50, description="Full-physics verifications")

    @model_validator(mode="after")
    def _check(self):
        if (self.target is None) == (self.activityId is None):
            raise ValueError("Exactly one of 'target' or 'activityId' must be given.")
        if self.target is None and not self.fixtureIds:
            raise ValueError("'fixtureIds' is required with 'activityId' (no uploads to compare).")
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


class OptimizeResponse(BaseModel):
    target: TargetDto
    solutions: list[SolutionDto]
    evaluatedA: int = Field(..., description="Direct-only candidates ranked")
    evaluatedB: int = Field(..., description="Full-physics verifications")
    pruned: dict[str, int]
    closestMiss: SolutionDto | None = None
