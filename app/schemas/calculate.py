from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.geometry import PatchDto, Point2D, Vec3Dto
from app.schemas.grid import GridInput
from app.schemas.matrix import MatrixDto


class FixtureDto(BaseModel):
    id: str
    position: Vec3Dto
    aimDirection: Vec3Dto
    rotation: float = 0.0


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
    height: float = Field(..., gt=0, description="Room height in meters")
    grid: GridInput


class CalculateResponse(BaseModel):
    fixtures: list[FixtureDto]
    floorPatches: list[PatchDto]
    wallPatches: dict[str, list[PatchDto]] = Field(..., description="wallId → patches")
    directFloorMatrices: dict[str, MatrixDto] = Field(..., description="fixtureId → matrix")
    directWallMatrices: dict[str, dict[str, MatrixDto]] = Field(
        ...,
        description="wallId → fixtureId → matrix",
    )
    indirectFloorMatrices: dict[str, MatrixDto] = Field(..., description="wallId → matrix")
    totalFloorIlluminance: MatrixDto
