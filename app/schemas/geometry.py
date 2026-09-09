from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class Point2D(BaseModel):
    x: float = Field(..., description="Plan X, meters")
    y: float = Field(..., description="Plan Y, meters")


class Vec3Dto(BaseModel):
    x: float
    y: float
    z: float


class PatchDto(BaseModel):
    id: str
    surfaceType: Literal["floor", "wall"]
    parentId: str = Field(..., description="'floor' or the wall id")
    center: Vec3Dto
    normal: Vec3Dto
    area: float = Field(..., description="Patch area, m²")
    size: float = Field(..., description="Nominal cell size, m")
