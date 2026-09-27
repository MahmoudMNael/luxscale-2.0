"""Standards DTOs — mirrors admin-api-contract.md §3.

Backend: `GET {STANDARDS_BASE_URL}/api/v1/standards/...` (env: STANDARDS_BASE_URL).
Standard `id` is a client-supplied deterministic string key
(e.g. `"en12464_1_v2019_6_1_1"`), NOT a UUID.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class StandardMetadataDto(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    standard_code: str = Field(..., min_length=1)
    version_year: str = Field(..., min_length=1)
    is_latest: bool


class StandardHierarchyDto(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    category_table_number: str = Field(..., min_length=1)
    category_title: str = Field(..., min_length=1)
    ref_number: str = Field(..., min_length=1)
    page: int = Field(..., ge=1)


class StandardParametersDto(BaseModel):
    """All fields optional/nullable, all numbers >= 0 unless noted (§3.8)."""

    model_config = ConfigDict(populate_by_name=True)

    em_r_lx: float | None = Field(default=None, ge=0)
    em_u_lx: float | None = Field(default=None, ge=0)
    uo: float | None = Field(default=None, ge=0, le=1)
    ra: float | None = Field(default=None, ge=0, le=100)
    ugr_rugl: float | None = Field(default=None, ge=0)
    ez_lx: float | None = Field(default=None, ge=0)
    em_wall_lx: float | None = Field(default=None, ge=0)
    em_ceiling_lx: float | None = Field(default=None, ge=0)


class StandardResponse(BaseModel):
    """`GET /standards/{standard_id}` envelope data (§3.5, §3.8)."""

    model_config = ConfigDict(populate_by_name=True)

    id: str
    qdrant_point_id: str
    standard_metadata: StandardMetadataDto
    hierarchy: StandardHierarchyDto
    activity: str
    parameters: StandardParametersDto
    specific_requirements: str | None = None
    searchable_text: str
    content_hash: str
    created_at: datetime
    updated_at: datetime

    def target_illuminance(self) -> float:
        """Maintained Eavg for the automate search.

        EDIT HERE if the source field changes: prefers `em_r_lx`,
        falls back to `em_u_lx`. Raises ValueError when both are missing.
        """
        if self.parameters.em_r_lx is not None:
            return float(self.parameters.em_r_lx)
        if self.parameters.em_u_lx is not None:
            return float(self.parameters.em_u_lx)
        raise ValueError(f"Standard '{self.id}' has no em_r_lx/em_u_lx target.")

    def target_uniformity(self) -> float:
        """U0 for the automate search. EDIT HERE if the source field changes."""
        if self.parameters.uo is None:
            raise ValueError(f"Standard '{self.id}' has no uo uniformity.")
        return float(self.parameters.uo)


class StandardCategoryResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    standard_metadata: StandardMetadataDto
    category_table_number: str
    category_title: str


__all__ = [
    "StandardCategoryResponse",
    "StandardHierarchyDto",
    "StandardMetadataDto",
    "StandardParametersDto",
    "StandardResponse",
]
