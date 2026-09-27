from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.app_settings import (
    CEILING_REFLECTANCE_FACTOR,
    FLOOR_REFLECTANCE_FACTOR,
    WALL_REFLECTANCE_FACTOR,
)
from app.automate.layouts import frange
from app.schemas.geometry import PatchDto, Point2D, Vec3Dto
from app.schemas.matrix import MatrixDto

_MAX_CANDIDATES = 2000

# Application derivation rule: mountingHeight >= this -> "industrial",
# else "interior". EDIT HERE to change the threshold.
APPLICATION_HEIGHT_THRESHOLD_M = 3.0

FixtureApplication = Literal["interior", "industrial"]


def application_for_mounting_height(mounting_height: float) -> FixtureApplication:
    """Derive fixture application from mounting height. EDIT threshold above."""
    return "interior" if mounting_height <= APPLICATION_HEIGHT_THRESHOLD_M else "industrial"


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
    spacingX: SpacingRange | None = Field(
        default=None,
        description="Explicit X spacing range; None = server auto (from room size + mounting height)",
    )
    spacingY: SpacingRange | None = Field(
        default=None,
        description="Explicit Y spacing range; None = server auto (from room size + mounting height)",
    )
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
    - `maxOverdesign`: optional, None = standard default (0.3).
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
    maxOverdesign: float | None = Field(
        default=None,
        ge=0,
        description="Allowed Eavg excess ratio; None = standard default (0.3)",
    )
    search: SearchSpaceDto = Field(default_factory=SearchSpaceDto)
    topK: int = Field(default=5, ge=1, le=20, description="Solutions returned (most compact first)")
    stageB: int = Field(
        default=12, ge=1, le=50,
        description="Stage-B budget: per-fixture full-physics verifications "
        "(Stage A ranks all candidates cheaply with direct-only light; "
        "Stage B re-verifies this many shortlisted candidates per variant "
        "with full interreflection physics)",
    )

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
            if rng is None:
                continue  # auto-spacing: resolved + capped in the controller
            if rng.min > rng.max:
                raise ValueError(f"'search.{name}.min' cannot exceed max.")
        if any(not 0.0 <= f <= 1.0 for f in self.search.offsetFractions):
            raise ValueError("'search.offsetFractions' must be within [0, 1].")
        if self.search.spacingX is not None and self.search.spacingY is not None:
            n = (
                len(frange(self.search.spacingX.min, self.search.spacingX.max, self.search.spacingX.step))
                * len(frange(self.search.spacingY.min, self.search.spacingY.max, self.search.spacingY.step))
                * len(self.search.offsetFractions)
                * len(self.search.rotations)
            )
            if n > _MAX_CANDIDATES:
                raise ValueError(f"Search space has {n} candidates (max {_MAX_CANDIDATES}); widen steps.")
        return self


def candidate_count(sx: SpacingRange, sy: SpacingRange, n_offsets: int, n_rotations: int) -> int:
    """Total layout combos for explicit (or resolved) spacing ranges."""
    return (
        len(frange(sx.min, sx.max, sx.step))
        * len(frange(sy.min, sy.max, sy.step))
        * max(n_offsets, 1)
        * max(n_rotations, 1)
    )


class GridHintDto(BaseModel):
    spacingX: float
    spacingY: float
    offsetX: float
    offsetY: float
    rotation: float


class AutomatePlacementDto(BaseModel):
    """Fixture position in the room world frame (origin at the floor below
    the room origin): X/Y are plan meters, Z is meters above the floor.

    Deliberately NOT FixturePlacementDto: automate placements are engine
    output, always fully resolved — no per-fixture overrides, no IES
    references (photometry is fixed by the parent solution's variantId).
    """

    model_config = ConfigDict(populate_by_name=True, serialize_by_alias=True)

    id: str = Field(..., description="Fixture id (F1, F2, ... in layout order)")
    x: float = Field(..., description="Plan X, meters")
    y: float = Field(..., description="Plan Y, meters")
    z: float = Field(..., gt=0, description="Mounting height of this fixture, meters above floor")
    rotation: float = Field(default=0.0, description="In-room housing rotation, degrees")
    tiltAngle: float = Field(
        default=0.0, ge=0, le=90,
        description="Tilt from straight-down, degrees (0 = downlight; the search only generates downlights)",
    )


class AutomateFixtureDto(BaseModel):
    """Engine-resolved fixture for visualization (mirrors /calculate FixtureDto
    minus aimDirection, plus tiltAngle). Position z is the luminous-plane
    height (mounting minus half the opening height)."""

    model_config = ConfigDict(populate_by_name=True, serialize_by_alias=True)

    id: str
    position: Vec3Dto
    rotation: float = 0.0
    tiltAngle: float = Field(
        default=0.0, ge=0, le=90,
        description="Tilt from straight-down, degrees (0 = downlight)",
    )
    length: float = Field(..., description="Luminous opening along C0, metres")
    width: float = Field(..., description="Luminous opening along C90, metres")
    height: float = Field(..., description="Luminous opening height, metres")
    corners: list[Vec3Dto] = Field(..., min_length=4, max_length=4, description="World-space opening corners, CCW")
    elements: list[Vec3Dto] = Field(..., min_length=1, description="Sample points used in the direct sum")


class SolutionDto(BaseModel):
    variantId: str = Field(..., description="Variant UUID (automate catalog key)")
    fixtureCount: int = Field(..., description="Number of physical fixtures placed")
    placements: list[AutomatePlacementDto]
    fixtures: list[AutomateFixtureDto] = Field(
        default_factory=list,
        description="Engine-resolved fixtures (position, opening, corners/elements) for visualization",
    )
    grid: GridHintDto
    average: float
    minimum: float
    maximum: float
    uniformity: float
    overdesign: float
    powerW: float | None = None
    powerDensity: float | None = None
    missReason: str | None = Field(
        default=None,
        description="Why this layout missed (under_target | over_cap | uniformity); None on recommended solutions",
    )
    recommended: bool = Field(
        default=True,
        description="True = passed all checks. False = shown for reference only "
        "(over-cap pick in solutions, or any closestMiss entry)",
    )
    totalFloor: MatrixDto | None = Field(
        default=None,
        description="Maintained total floor illuminance (lux), one value per floorPatches entry, same order. "
        "Solutions only; None on the closest miss.",
    )


class AppliedSpacingDto(BaseModel):
    """Spacing range actually used (explicit input or server auto)."""

    min: float
    max: float
    step: float


class AutomateResponse(BaseModel):
    target: TargetDto
    application: FixtureApplication = Field(
        ..., description="Fixture application actually used, derived from mountingHeight (<= 3.0 → interior)"
    )
    solutions: list[SolutionDto]
    evaluatedA: int = Field(..., description="Direct-only candidates ranked")
    evaluatedB: int = Field(..., description="Full-physics verifications")
    pruned: dict[str, int]
    closestMiss: SolutionDto | None = None
    appliedSpacingX: AppliedSpacingDto = Field(..., description="X spacing range used (auto or explicit)")
    appliedSpacingY: AppliedSpacingDto = Field(..., description="Y spacing range used (auto or explicit)")
    floorPatches: list[PatchDto] = Field(
        default_factory=list,
        description="Shared EN 12464 floor evaluation patches (centers); totalFloor.values[i] ↔ floorPatches[i]",
    )
    floorMeta: dict = Field(
        default_factory=dict,
        description="Shared floor grid meta (spacing, nx, ny, dx, dy, bounds, border) + workPlaneHeight",
    )
