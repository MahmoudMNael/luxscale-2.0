from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.schemas.geometry import PatchDto, Point2D, Vec3Dto
from app.schemas.grid import GridInput
from app.schemas.matrix import MatrixDto


class EvaluationDto(BaseModel):
    model_config = ConfigDict(populate_by_name=True, serialize_by_alias=True)

    average: float = Field(..., description="Eavg over EN 12464 evaluation points, lux")
    minimum: float = Field(..., description="Emin over evaluation points, lux")
    maximum: float = Field(..., description="Emax over evaluation points, lux")
    uniformity: float = Field(..., description="U0 = Emin / Eavg")
    minPoint: Vec3Dto = Field(..., description="Center of the Emin evaluation point")
    maxPoint: Vec3Dto = Field(..., description="Center of the Emax evaluation point")
    count: int = Field(..., description="Number of EN 12464 evaluation points")
    spacing: float = Field(..., description="EN 12464 target spacing p (max of axes), meters")
    spacingX: float = Field(default=0.0, description="EN 12464 per-axis spacing px, meters")
    spacingY: float = Field(default=0.0, description="EN 12464 per-axis spacing py, meters")
    nx: int = Field(..., description="Cells along X over the inset bounding box")
    ny: int = Field(..., description="Cells along Y over the inset bounding box")
    wallZone: float = Field(..., description="Applied boundary inset, meters")
    workPlaneHeight: float = Field(..., description="Applied calculation-surface height, meters")


class FixtureDto(BaseModel):
    id: str
    position: Vec3Dto
    aimDirection: Vec3Dto
    rotation: float = 0.0
    length: float = Field(..., description="Luminous opening along C0, metres")
    width: float = Field(..., description="Luminous opening along C90, metres")
    height: float = Field(..., description="Luminous opening height, metres")
    corners: list[Vec3Dto] = Field(..., min_length=4, max_length=4, description="World-space opening corners, CCW")
    elements: list[Vec3Dto] = Field(..., min_length=1, description="Sample points used in the direct I/N sum")


class FixturePlacementDto(BaseModel):
    model_config = ConfigDict(populate_by_name=True, serialize_by_alias=True)

    id: str | None = Field(default=None, description="Fixture id; defaults to F1, F2, ...")
    x: float = Field(..., description="Plan X, meters")
    y: float = Field(..., description="Plan Y, meters")
    z: float | None = Field(
        default=None, gt=0, description="Mounting height of this fixture; defaults to mountingHeight"
    )
    rotation: float | None = Field(
        default=None, ge=0, le=360, description="In-room rotation; defaults to luminaireRotation"
    )
    aimDirection: Vec3Dto | None = Field(default=None, description="Aim; defaults to straight down")
    iesRef: str | None = Field(
        default=None, description="Photometry key: uploaded IES filename or provider fixture id"
    )


class CalculateRequest(BaseModel):
    model_config = ConfigDict(
        populate_by_name=True,
        json_schema_extra={
            "examples": [
                {
                    "polygon": [
                        {"x": 0, "y": 0},
                        {"x": 8, "y": 0},
                        {"x": 8, "y": 6},
                        {"x": 0, "y": 6},
                    ],
                    "height": 3.0,
                    "grid": {
                        "x": {"spacing": 2.0, "offsetBeginning": 1.0, "offsetEnding": 1.0},
                        "y": {"spacing": 2.0, "offsetBeginning": 1.0, "offsetEnding": 1.0},
                    },
                }
            ]
        },
    )

    polygon: list[Point2D] = Field(
        ...,
        min_length=3,
        description="Room footprint vertices in meters (closing vertex optional)",
    )
    height: float = Field(..., gt=0, description="Room height in meters (fallback for ceiling/mounting heights)")
    ceilingHeight: float | None = Field(
        default=None,
        gt=0,
        description="Ceiling plane height in meters; walls extend to this. Defaults to height.",
    )
    mountingHeight: float | None = Field(
        default=None,
        gt=0,
        description="Fixture mounting height in meters (e.g. pendant drop below ceiling). Defaults to ceilingHeight.",
    )
    grid: GridInput | None = Field(
        default=None, description="Regular luminaire grid (legacy). Exactly one of grid/fixtures."
    )
    fixtures: list[FixturePlacementDto] | None = Field(
        default=None, min_length=1, description="Free fixture positions. Exactly one of grid/fixtures."
    )
    workPlaneHeight: float = Field(
        default=0.0,
        ge=0,
        description="DIALux-like calculation-surface height in meters (0 = true floor)",
    )
    floorZone: float | None = Field(
        default=0.5,
        ge=0,
        description="Floor/ceiling boundary inset in meters; default 0.5, None also resolves to 0.5",
    )
    wallZone: float | None = Field(
        default=None,
        ge=0,
        description="Wall boundary inset in meters; None = auto 15% rule min(0.15*min(L,H), 0.5). Walls with min(L,H) <= 1.0 m are neglected",
    )
    luminaireRotation: float = Field(
        default=0.0,
        ge=0,
        le=360,
        description="In-room rotation of the luminaire housing in degrees, added to the photometric C-planes",
    )

    @model_validator(mode="after")
    def _check_mounting_not_above_ceiling(self):
        if (
            self.ceilingHeight is not None
            and self.mountingHeight is not None
            and self.mountingHeight > self.ceilingHeight
        ):
            raise ValueError("mountingHeight cannot exceed ceilingHeight")
        if (self.grid is None) == (self.fixtures is None):
            raise ValueError("Exactly one of 'grid' or 'fixtures' must be given.")
        return self


class CalculateResponse(BaseModel):
    fixtures: list[FixtureDto]
    floorPatches: list[PatchDto]
    wallPatches: dict[str, list[PatchDto]] = Field(..., description="wallId → patches")
    ceilingPatches: list[PatchDto] = Field(default_factory=list, description="ceiling patches")
    directFloorMatrices: dict[str, MatrixDto] = Field(..., description="fixtureId → matrix")
    directWallMatrices: dict[str, dict[str, MatrixDto]] = Field(
        ...,
        description="wallId → fixtureId → matrix",
    )
    directCeilingMatrices: dict[str, MatrixDto] = Field(
        default_factory=dict, description="fixtureId → ceiling matrix"
    )
    indirectFloorMatrices: dict[str, MatrixDto] = Field(
        ...,
        description="originId → floor matrix from interreflection (walls, floor and ceiling re-emit), "
        "summed over all bounces originating from that surface",
    )
    indirectCeilingMatrices: dict[str, MatrixDto] = Field(
        default_factory=dict, description="originId → ceiling matrix from interreflection"
    )
    indirectWallMatrices: dict[str, dict[str, MatrixDto]] = Field(
        default_factory=dict, description="wallId → originId → wall matrix from interreflection"
    )
    totalFloorIlluminance: MatrixDto
    totalCeilingIlluminance: MatrixDto | None = Field(default=None, description="Maintained total on ceiling grid")
    totalWallIlluminance: dict[str, MatrixDto] = Field(default_factory=dict, description="wallId → maintained total")
    evaluation: EvaluationDto = Field(..., description="EN 12464 summary over the total floor matrix")
    ceilingEvaluation: EvaluationDto | None = Field(default=None, description="EN 12464 summary over ceiling")
    wallEvaluations: dict[str, EvaluationDto] = Field(default_factory=dict, description="wallId → EN 12464 summary")
    bounces: int = Field(..., description="Applied bounces (app_settings.NUM_BOUNCES)")
    wallReflectance: float = Field(..., description="Applied wall reflectance (app_settings.WALL_REFLECTANCE_FACTOR)")
    floorReflectance: float = Field(
        default=0.2, description="Applied floor reflectance (app_settings.FLOOR_REFLECTANCE_FACTOR)"
    )
    ceilingReflectance: float = Field(
        default=0.7, description="Applied ceiling reflectance (app_settings.CEILING_REFLECTANCE_FACTOR)"
    )
    ceilingHeight: float = Field(..., description="Applied ceiling plane height in meters")
    mountingHeight: float = Field(..., description="Applied fixture mounting height in meters")
    solverCell: float = Field(
        default=0.3, description="Effective radiosity solver cell in meters (0.3 unless the room needed more than MAX_SOLVER_PATCHES sources and was adaptively coarsened)"
    )
    solverDegraded: bool = Field(
        default=False, description="True when the solver mesh was coarsened beyond SOLVER_CELL to respect MAX_SOLVER_PATCHES (large rooms only)"
    )
