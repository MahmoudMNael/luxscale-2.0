from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, model_validator


class AxisGrid(BaseModel):
    model_config = ConfigDict(populate_by_name=True, serialize_by_alias=True)

    spacing: float = Field(..., gt=0, description="Fixture spacing along this axis, meters")
    offset_beginning: float = Field(
        ...,
        ge=0,
        alias="offsetBeginning",
        description="Inset from the bounding-box start, meters",
    )
    offset_ending: float = Field(
        ...,
        ge=0,
        alias="offsetEnding",
        description="Inset from the bounding-box end, meters",
    )


class GridCount(BaseModel):
    model_config = ConfigDict(populate_by_name=True, serialize_by_alias=True)

    count_x: int = Field(..., ge=1, alias="countX", description="Number of fixtures along X axis")
    count_y: int = Field(..., ge=1, alias="countY", description="Number of fixtures along Y axis")
    offset_fraction: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        alias="offsetFraction",
        description="Symmetric offset as fraction of spacing (0.5 = centered half-spacing to boundary)",
    )

    @property
    def nx(self) -> int:
        return self.count_x

    @property
    def ny(self) -> int:
        return self.count_y


class GridSpacing(BaseModel):
    model_config = ConfigDict(populate_by_name=True, serialize_by_alias=True)

    spacing_x: float = Field(..., gt=0, alias="spacingX", description="Spacing along X axis, meters")
    spacing_y: float = Field(..., gt=0, alias="spacingY", description="Spacing along Y axis, meters")
    auto_center: bool = Field(
        default=True, alias="autoCenter", description="Auto-center the grid within the room bounding box"
    )
    offset_x: float | None = Field(
        default=None, ge=0, alias="offsetX", description="Manual offset along X when autoCenter is False, meters"
    )
    offset_y: float | None = Field(
        default=None, ge=0, alias="offsetY", description="Manual offset along Y when autoCenter is False, meters"
    )


class GridInput(BaseModel):
    model_config = ConfigDict(populate_by_name=True, serialize_by_alias=True)

    x: AxisGrid | None = None
    y: AxisGrid | None = None
    count: GridCount | None = None
    spacing: GridSpacing | None = None

    @model_validator(mode="after")
    def _validate_grid(self):
        has_axis = bool(self.x and self.y)
        has_count = bool(self.count)
        has_spacing = bool(self.spacing)
        modes = sum([has_axis, has_count, has_spacing])
        if modes != 1:
            raise ValueError(
                "Exactly one grid specification mode must be provided: (x and y), count, or spacing."
            )
        return self

