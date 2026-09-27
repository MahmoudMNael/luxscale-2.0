"""Fixtures/variants/assets DTOs — mirrors admin-api-contract.md §2, §4, §5, §6.

Backend: `GET {FIXTURES_BASE_URL}/api/v1/fixtures/...` and
`GET {FIXTURES_BASE_URL}/api/v1/assets/{asset_id}` (env: FIXTURES_BASE_URL).
Asset download (§2.3) returns raw file bytes (no JSON envelope).
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.common import OptionalDecimalFloat

FixtureApplication = Literal["interior", "industrial"]


class AssetResponse(BaseModel):
    """§2.4. `id` is then referenced by fixture/variant payloads as `*_file_id`."""

    model_config = ConfigDict(populate_by_name=True)

    id: UUID
    relative_path: str
    original_filename: str
    mime_type: str
    size_bytes: int = Field(..., ge=0)
    created_at: datetime


class FixtureSummaryResponse(BaseModel):
    """§4.6. List endpoints return this (no variants nested)."""

    model_config = ConfigDict(populate_by_name=True)

    id: UUID
    manufacturer_name: str
    name: str
    is_main_solution: bool
    applications: list[FixtureApplication]
    created_at: datetime
    updated_at: datetime


class VariantImageResponse(BaseModel):
    """§6.3. `id` is the variant-image record id (use for DELETE), not the asset id."""

    model_config = ConfigDict(populate_by_name=True)

    id: UUID
    variant_id: UUID
    image_file_id: UUID
    image_file: AssetResponse


class VariantResponse(BaseModel):
    """§5.7. Watts/efficacy source of truth for the automate search.

    - `power` (int, W) and `efficacy` (int, lm/W) come from THIS response,
      never from the IES file. See `app/services/variant_photometrics.py`
      (EDIT THERE to change the lumens formula).
    - `ies_file_id` points at the IES asset; photometry SHAPE still comes
      from the downloaded IES bytes via `load_ies`.
    """

    model_config = ConfigDict(populate_by_name=True)

    id: UUID
    fixture_id: UUID
    name: str
    chip: str
    driver: str
    power: int = Field(..., ge=0)
    efficacy: int = Field(..., ge=0)
    power_factor: float
    cri: float
    mechanical_protections: list[str] = Field(default_factory=list)
    electrical_protections: list[str] = Field(default_factory=list)
    dimension_length: OptionalDecimalFloat = None
    dimension_width: OptionalDecimalFloat = None
    dimension_depth: OptionalDecimalFloat = None
    dimension_radius: OptionalDecimalFloat = None
    model_3d_file_id: UUID | None = None
    model_3d_file: AssetResponse | None = None
    ies_file_id: UUID
    ies_file: AssetResponse
    images: list[VariantImageResponse] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime


class VariantDetailResponse(VariantResponse):
    """§5.4: everything in `VariantResponse` plus parent `fixture` summary."""

    fixture: FixtureSummaryResponse


class FixtureResponse(FixtureSummaryResponse):
    """§4.3: summary + `variants: VariantResponse[]` (may be empty)."""

    variants: list[VariantResponse] = Field(default_factory=list)


__all__ = [
    "AssetResponse",
    "FixtureApplication",
    "FixtureResponse",
    "FixtureSummaryResponse",
    "VariantDetailResponse",
    "VariantImageResponse",
    "VariantResponse",
]
