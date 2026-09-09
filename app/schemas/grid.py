from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


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


class GridInput(BaseModel):
    model_config = ConfigDict(populate_by_name=True, serialize_by_alias=True)

    x: AxisGrid
    y: AxisGrid
