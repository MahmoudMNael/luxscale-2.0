"""External fixture/variant provider — admin contract §4, §5, §2 (env: FIXTURES_BASE_URL).

Flow used by the automate endpoint:
1. Resolve variants (main-solution only):
   - variantIds given -> filter the paginated variant list by those UUIDs.
   - variantIds empty/None -> all variants for the derived application.
   - List endpoint: GET {base}/api/v1/fixtures/variants/?application={app}
     &is_main_solution=true&page&limit  (§5.1, paginated envelope §1.1).
     `is_main_solution` filters by the PARENT fixture's flag — non-main
     variants never enter the automate catalog.
2. Per variant, download IES bytes:
     GET {base}/api/v1/assets/{ies_file_id}  (§2.3, raw bytes, no envelope).
3. Ratings come from the variant response (NEVER the IES file):
     watts  = variant.power, lumens = power * efficacy.
     See app/services/variant_photometrics.py (single edit point).

NOTE: the contract nests variant detail under a fixture
(GET /fixtures/{fid}/variants/{vid}); there is no GET /variants/{vid}.
So explicit variantIds are resolved via the list endpoint + UUID filter.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

from app.domain.exceptions import ProviderError
from app.schemas.fixtures import VariantDetailResponse
from app.services.variant_photometrics import variant_lumens, variant_wattage

API_PREFIX = "/api/v1"
_PAGE_LIMIT = 100

# Variant API dimensions arrive in MILLIMETERS (metric); FixtureSpec and the
# engine work in meters. Single conversion point — EDIT HERE if the unit changes.
MM_PER_M = 1000.0


def _mm_to_m(value: float | None) -> float | None:
    """mm -> m; None/non-positive pass through as None (IES fallback applies)."""
    if value is None:
        return None
    try:
        meters = float(value) / MM_PER_M
    except (TypeError, ValueError):
        return None
    return meters if meters > 0 else None


def api_base(base_url: str) -> str:
    """Base URL + `/api/v1`, unless the base URL already ends with it.

    `.env` values may be either `http://host:8001` or
    `http://host:8001/api/v1` — both resolve to the same admin endpoints
    instead of double-prefixing (`/api/v1/api/v1/...` -> 404).
    """
    base = base_url.rstrip("/")
    if base.endswith(API_PREFIX):
        return base
    return base + API_PREFIX


@dataclass(frozen=True)
class FixtureSpec:
    """Internal carrier: one automate catalog entry == one main-solution variant."""

    id: str  # catalog key == variant UUID string
    fixture_id: str
    variant_id: str
    ies_text: str
    wattage: float | None = None
    lumens: float | None = None
    efficacy: float | None = None
    power: float | None = None
    # Luminous-opening size in METERS (converted from the variant API's
    # millimeters). None per axis = fall back to the IES header value.
    length: float | None = None
    width: float | None = None
    height: float | None = None
    is_main_solution: bool = True
    applications: tuple[str, ...] = ("interior",)


class FixtureProvider(Protocol):
    def list_main_variants(self, application: str) -> list[FixtureSpec]: ...
    def get_variants(
        self,
        variant_ids: list[str],
        application: str | None = None,
        *,
        main_only: bool = True,
    ) -> list[FixtureSpec]: ...


def _get_json(url: str, timeout_s: float) -> dict:
    try:
        with urllib.request.urlopen(url, timeout=timeout_s) as response:
            if response.status != 200:
                raise ProviderError(f"Fixtures API returned HTTP {response.status} for {url}.")
            try:
                data = json.loads(response.read().decode("utf-8"))
            except ValueError as exc:
                raise ProviderError(f"Fixtures API returned invalid JSON for {url}.") from exc
    except urllib.error.HTTPError as exc:
        raise ProviderError(f"Fixtures API returned HTTP {exc.code} for {url}.") from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise ProviderError(f"Fixtures API unreachable ({url}): {exc}.") from exc
    if not isinstance(data, dict):
        raise ProviderError(f"Fixtures API returned invalid payload for {url}.")
    return data


def _get_bytes(url: str, timeout_s: float) -> bytes:
    try:
        with urllib.request.urlopen(url, timeout=timeout_s) as response:
            if response.status != 200:
                raise ProviderError(f"Fixtures API returned HTTP {response.status} for {url}.")
            return response.read()
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            raise ProviderError(f"Asset not found ({url}).") from exc
        raise ProviderError(f"Fixtures API returned HTTP {exc.code} for {url}.") from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise ProviderError(f"Fixtures API unreachable ({url}): {exc}.") from exc


def _parse_variant_list(payload: dict, url: str) -> tuple[list[VariantDetailResponse], dict | None]:
    data = payload.get("data", [])
    pagination = payload.get("pagination")
    if not isinstance(data, list):
        raise ProviderError(f"Fixtures API returned invalid payload for {url}.")
    variants: list[VariantDetailResponse] = []
    for item in data:
        try:
            variants.append(VariantDetailResponse.model_validate(item))
        except Exception as exc:
            raise ProviderError(f"Fixtures API variant payload invalid ({url}): {exc}.") from exc
    return variants, pagination if isinstance(pagination, dict) else None


class RestFixtureProvider:
    """Admin-contract fixture provider. Uses urllib only."""

    def __init__(self, base_url: str | None = None, timeout_s: float = 5.0) -> None:
        base = base_url if base_url is not None else os.environ.get("FIXTURES_BASE_URL", "")
        self.base_url = api_base(base) if base.rstrip("/") else ""
        self.timeout_s = timeout_s
        print(f"RestFixtureProvider: base_url={self.base_url}, timeout_s={timeout_s}")

    def _fetch_variants(
        self,
        application: str | None = None,
        is_main_solution: bool | None = None,
    ) -> list[VariantDetailResponse]:
        if not self.base_url:
            raise ProviderError("FIXTURES_BASE_URL is not configured.")
        out: list[VariantDetailResponse] = []
        page = 1
        while True:
            params: dict[str, str | int] = {"page": page, "limit": _PAGE_LIMIT}
            if application:
                params["application"] = application
            if is_main_solution is not None:
                params["is_main_solution"] = "true" if is_main_solution else "false"
            query = urllib.parse.urlencode(params)
            url = f"{self.base_url}/fixtures/variants/?{query}"
            payload = _get_json(url, self.timeout_s)
            variants, pagination = _parse_variant_list(payload, url)
            out.extend(variants)
            if pagination is None:
                break
            total_pages = int(pagination.get("total_pages", page))
            if page >= total_pages:
                break
            page += 1
        return out

    def _download_ies(self, ies_file_id: UUID) -> str:
        url = f"{self.base_url}/assets/{ies_file_id}"
        raw = _get_bytes(url, self.timeout_s)
        try:
            return raw.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ProviderError(f"IES asset {ies_file_id} is not UTF-8 text.") from exc

    def _to_spec(self, variant: VariantDetailResponse) -> FixtureSpec:
        ies_text = self._download_ies(variant.ies_file_id)
        return spec_from_variant(variant, ies_text)

    def list_main_variants(self, application: str) -> list[FixtureSpec]:
        if application not in ("interior", "industrial"):
            raise ProviderError(f"Unknown application '{application}'.")
        variants = self._fetch_variants(application=application, is_main_solution=True)
        specs = [self._to_spec(v) for v in variants if v.fixture.is_main_solution]
        if not specs:
            raise ProviderError(
                f"No main-solution variants found for application '{application}'."
            )
        return specs

    def get_variants(
        self,
        variant_ids: list[str],
        application: str | None = None,
        *,
        main_only: bool = True,
    ) -> list[FixtureSpec]:
        if main_only and application not in ("interior", "industrial"):
            raise ProviderError(f"Unknown application '{application}'.")
        is_main = True if main_only else None
        variants = self._fetch_variants(application=application if main_only else None, is_main_solution=is_main)
        if main_only:
            variants = [v for v in variants if v.fixture.is_main_solution]
        by_id = {str(v.id).lower(): v for v in variants}
        missing = [vid for vid in variant_ids if str(vid).lower() not in by_id]
        if missing:
            msg = (
                f"Variant(s) not found as main-solution '{application}' variants: {missing}."
                if main_only
                else f"Variant(s) not found in catalog: {missing}."
            )
            raise ProviderError(msg)
        return [self._to_spec(by_id[str(vid).lower()]) for vid in variant_ids]

    # Legacy single-fixture lookup kept for internal/dev use (not used by automate).
    def get_one(self, fixture_id: str) -> FixtureSpec:
        raise ProviderError("Use list_main_variants/get_variants (variant-based).")

    def get_many(self, fixture_ids: list[str]) -> list[FixtureSpec]:
        raise ProviderError("Use list_main_variants/get_variants (variant-based).")


class InMemoryFixtureProvider:
    """Test/dev stub with the same interface (no network)."""

    def __init__(self, specs: dict[str, FixtureSpec] | None = None) -> None:
        self._specs: dict[str, FixtureSpec] = dict(specs or {})

    def add(self, spec: FixtureSpec) -> None:
        self._specs[spec.id] = spec

    def _matching(self, application: str | None = None, main_only: bool = True) -> list[FixtureSpec]:
        specs = list(self._specs.values())
        if main_only:
            specs = [s for s in specs if s.is_main_solution]
        if application:
            specs = [s for s in specs if application in s.applications]
        return specs

    def list_main_variants(self, application: str) -> list[FixtureSpec]:
        specs = self._matching(application, main_only=True)
        if not specs:
            raise ProviderError(
                f"No main-solution variants found for application '{application}'."
            )
        return specs

    def get_variants(
        self,
        variant_ids: list[str],
        application: str | None = None,
        *,
        main_only: bool = True,
    ) -> list[FixtureSpec]:
        pool = {str(s.id).lower(): s for s in self._matching(application, main_only=main_only)}
        missing = [vid for vid in variant_ids if str(vid).lower() not in pool]
        if missing:
            msg = (
                f"Variant(s) not found as main-solution '{application}' variants: {missing}."
                if main_only
                else f"Variant(s) not found in catalog: {missing}."
            )
            raise ProviderError(msg)
        ordered = [pool[str(vid).lower()] for vid in variant_ids]
        return ordered

    def get_one(self, fixture_id: str) -> FixtureSpec:
        try:
            return self._specs[fixture_id]
        except KeyError as exc:
            raise ProviderError(f"Unknown fixture '{fixture_id}'.") from exc

    def get_many(self, fixture_ids: list[str]) -> list[FixtureSpec]:
        return [self.get_one(fid) for fid in fixture_ids]


def spec_from_variant(variant: VariantDetailResponse, ies_text: str) -> FixtureSpec:
    """VariantDetailResponse + downloaded IES text -> FixtureSpec (pure, no I/O).

    Dimensions convert mm -> m here; None per axis means "fall back to the
    IES header value" downstream (see apply_variant_dimensions).
    """
    length = _mm_to_m(variant.dimension_length)
    width = _mm_to_m(variant.dimension_width)
    if length is None and width is None:
        # Round opening with no rectangular dims: square from the radius.
        radius_m = _mm_to_m(variant.dimension_radius)
        if radius_m is not None:
            length = width = 2.0 * radius_m
    return FixtureSpec(
        id=str(variant.id),
        fixture_id=str(variant.fixture_id),
        variant_id=str(variant.id),
        ies_text=ies_text,
        wattage=variant_wattage(variant),
        lumens=variant_lumens(variant),
        efficacy=float(variant.efficacy),
        power=float(variant.power),
        length=length,
        width=width,
        height=_mm_to_m(variant.dimension_depth),
        is_main_solution=bool(variant.fixture.is_main_solution),
        applications=tuple(variant.fixture.applications),
    )


__all__ = [
    "FixtureProvider",
    "FixtureSpec",
    "InMemoryFixtureProvider",
    "RestFixtureProvider",
    "api_base",
    "spec_from_variant",
]
