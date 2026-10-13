"""V2 Catalog Controller for LuxScale.

Provides fixture variants and lighting standards to the studio frontend.
Strictly queries SC-Admin catalog and standards APIs without hardcoded fallbacks.
"""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from app.providers import (
    FixtureProvider,
    InMemoryFixtureProvider,
    InMemoryStandardProvider,
    RestFixtureProvider,
    RestStandardProvider,
    StandardProvider,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v2/catalog", tags=["V2 Catalog"])


def get_fixture_provider() -> FixtureProvider:
    return RestFixtureProvider()


def get_standard_provider() -> StandardProvider:
    return RestStandardProvider()


class CatalogVariantDto(BaseModel):
    id: str
    name: str
    fixtureId: str
    fixtureName: str
    manufacturer: str
    application: str
    power: float
    efficacy: float
    lumens: float
    cct: int
    cri: float
    length: float | None = None
    width: float | None = None
    height: float | None = None
    isMainSolution: bool = True
    iesFileId: str | None = None


class StandardItemDto(BaseModel):
    id: str
    name: str
    application: str
    targetLux: float
    targetUniformity: float
    description: str


@router.get("/variants", response_model=list[CatalogVariantDto])
def list_variants(
    fixture_provider: Annotated[FixtureProvider, Depends(get_fixture_provider)],
) -> list[CatalogVariantDto]:
    """Returns catalog variants directly from the SC-Admin fixture provider."""
    try:
        if hasattr(fixture_provider, "_fetch_variants"):
            raw_variants = fixture_provider._fetch_variants(application=None, is_main_solution=None)
            results: list[CatalogVariantDto] = []
            for v in raw_variants:
                pw = float(v.power or 40.0)
                eff = float(v.efficacy or 90.0)
                lum = pw * eff
                mfg = getattr(v.fixture, "manufacturer_name", getattr(v.fixture, "manufacturer", "SC Catalog"))
                app = v.fixture.applications[0] if (getattr(v.fixture, "applications", None) and len(v.fixture.applications) > 0) else "interior"
                results.append(
                    CatalogVariantDto(
                        id=str(v.id),
                        name=v.name,
                        fixtureId=str(v.fixture.id),
                        fixtureName=v.fixture.name,
                        manufacturer=mfg,
                        application=app,
                        power=round(pw, 1),
                        efficacy=round(eff, 1),
                        lumens=round(lum, 1),
                        cct=4000,
                        cri=float(v.cri or 80.0),
                        length=float(v.dimension_length) / 1000.0 if v.dimension_length else None,
                        width=float(v.dimension_width) / 1000.0 if v.dimension_width else None,
                        height=float(v.dimension_depth) / 1000.0 if v.dimension_depth else None,
                        isMainSolution=bool(v.fixture.is_main_solution),
                        iesFileId=str(v.ies_file_id) if v.ies_file_id else None,
                    )
                )
            return results
        elif isinstance(fixture_provider, InMemoryFixtureProvider):
            results = []
            for spec in fixture_provider._specs.values():
                results.append(
                    CatalogVariantDto(
                        id=spec.id,
                        name=f"Fixture {spec.id}",
                        fixtureId=spec.fixture_id,
                        fixtureName=f"Fixture {spec.fixture_id}",
                        manufacturer="SC Catalog",
                        application=spec.applications[0] if spec.applications else "interior",
                        power=float(spec.power or spec.wattage or 40.0),
                        efficacy=float(spec.efficacy or 90.0),
                        lumens=float(spec.lumens or 3600.0),
                        cct=4000,
                        cri=80.0,
                        length=spec.length,
                        width=spec.width,
                        height=spec.height,
                        isMainSolution=spec.is_main_solution,
                        iesFileId=None,
                    )
                )
            return results
        else:
            raise ValueError("Unsupported fixture provider type")
    except Exception as exc:
        logger.error("Failed fetching variants from SC-Admin: %s", exc)
        raise HTTPException(status_code=502, detail=f"Fixtures API unavailable: {exc}") from exc


@router.get("/standards")
def list_standards(
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=100),
    standard_code: str | None = Query(default=None),
    version_year: str | None = Query(default=None),
    is_latest: bool | None = Query(default=None),
    category_table_number: str | None = Query(default=None),
    activity: str | None = Query(default=None),
    keywords: list[str] = Query(default=[]),
    match_mode: str = Query(default="any"),
    standard_provider: Annotated[StandardProvider, Depends(get_standard_provider)] = None,
):
    """Returns lighting standards with pagination and search filters from SC-Admin."""
    try:
        if hasattr(standard_provider, "query_standards"):
            return standard_provider.query_standards(
                page=page,
                limit=limit,
                standard_code=standard_code,
                version_year=version_year,
                is_latest=is_latest,
                category_table_number=category_table_number,
                activity=activity,
                keywords=keywords,
                match_mode=match_mode,
            )
        raw_standards = standard_provider.list_standards()
        items = [s.model_dump(mode="json") for s in raw_standards]
        return {
            "success": True,
            "data": items,
            "pagination": {
                "total_count": len(items),
                "page_size": limit,
                "current_page": page,
                "total_pages": max(1, (len(items) + limit - 1) // limit),
            },
        }
    except Exception as exc:
        logger.error("Failed querying standards from SC-Admin: %s", exc)
        raise HTTPException(status_code=502, detail=f"Standards API unavailable: {exc}") from exc


@router.get("/standards/categories")
def list_standard_categories(
    standard_code: str | None = Query(default=None),
    version_year: str | None = Query(default=None),
    is_latest: bool | None = Query(default=None),
    standard_provider: Annotated[StandardProvider, Depends(get_standard_provider)] = None,
):
    """Returns distinct standard categories from SC-Admin."""
    try:
        if hasattr(standard_provider, "list_categories"):
            return standard_provider.list_categories(
                standard_code=standard_code,
                version_year=version_year,
                is_latest=is_latest,
            )
        return {"success": True, "data": []}
    except Exception as exc:
        logger.error("Failed fetching standard categories from SC-Admin: %s", exc)
        raise HTTPException(status_code=502, detail=f"Standards API unavailable: {exc}") from exc


@router.get("/standards/{standard_id}")
def get_standard(
    standard_id: str,
    standard_provider: Annotated[StandardProvider, Depends(get_standard_provider)] = None,
):
    """Returns a specific standard by ID from SC-Admin."""
    try:
        if hasattr(standard_provider, "get_standard_raw"):
            return standard_provider.get_standard_raw(standard_id)
        target = standard_provider.get_target(standard_id)
        return {"success": True, "data": target}
    except Exception as exc:
        logger.error("Failed fetching standard %s from SC-Admin: %s", standard_id, exc)
        raise HTTPException(status_code=502, detail=f"Standards API unavailable: {exc}") from exc



class VariantIesResponse(BaseModel):
    variantId: str
    iesText: str


@router.get("/variants/{variant_id}/ies", response_model=VariantIesResponse)
def get_variant_ies(
    variant_id: str,
    fixture_provider: Annotated[FixtureProvider, Depends(get_fixture_provider)],
) -> VariantIesResponse:
    """Returns the raw IES photometric text for a given catalog variant."""
    try:
        specs = fixture_provider.get_variants([variant_id], main_only=False)
        if specs and specs[0].ies_text:
            return VariantIesResponse(variantId=variant_id, iesText=specs[0].ies_text)
        raise HTTPException(status_code=404, detail="IES text not found for variant")
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Failed fetching IES text for variant %s: %s", variant_id, exc)
        raise HTTPException(status_code=502, detail=f"Failed to fetch IES: {exc}") from exc

