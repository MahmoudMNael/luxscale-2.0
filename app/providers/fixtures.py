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
    is_main_solution: bool = True
    applications: tuple[str, ...] = ("interior",)


class FixtureProvider(Protocol):
    def list_main_variants(self, application: str) -> list[FixtureSpec]: ...
    def get_variants(self, variant_ids: list[str], application: str) -> list[FixtureSpec]: ...


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

    def _fetch_all_main_variants(self, application: str) -> list[VariantDetailResponse]:
        if not self.base_url:
            raise ProviderError("FIXTURES_BASE_URL is not configured.")
        if application not in ("interior", "industrial"):
            raise ProviderError(f"Unknown application '{application}'.")
        out: list[VariantDetailResponse] = []
        page = 1
        while True:
            query = urllib.parse.urlencode(
                {
                    "application": application,
                    "is_main_solution": "true",
                    "page": page,
                    "limit": _PAGE_LIMIT,
                }
            )
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
        return FixtureSpec(
            id=str(variant.id),
            fixture_id=str(variant.fixture_id),
            variant_id=str(variant.id),
            ies_text=ies_text,
            wattage=variant_wattage(variant),
            lumens=variant_lumens(variant),
            efficacy=float(variant.efficacy),
            power=float(variant.power),
            is_main_solution=bool(variant.fixture.is_main_solution),
            applications=tuple(variant.fixture.applications),
        )

    def list_main_variants(self, application: str) -> list[FixtureSpec]:
        variants = self._fetch_all_main_variants(application)
        # Server already filtered is_main_solution=true; double-guard client-side.
        specs = [self._to_spec(v) for v in variants if v.fixture.is_main_solution]
        if not specs:
            raise ProviderError(
                f"No main-solution variants found for application '{application}'."
            )
        return specs

    def get_variants(self, variant_ids: list[str], application: str) -> list[FixtureSpec]:
        wanted = {str(v).lower() for v in variant_ids}
        variants = self._fetch_all_main_variants(application)
        by_id = {str(v.id).lower(): v for v in variants}
        missing = [vid for vid in variant_ids if str(vid).lower() not in by_id]
        if missing:
            raise ProviderError(
                f"Variant(s) not found as main-solution '{application}' variants: {missing}."
            )
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

    def _matching(self, application: str) -> list[FixtureSpec]:
        return [
            s
            for s in self._specs.values()
            if s.is_main_solution and application in s.applications
        ]

    def list_main_variants(self, application: str) -> list[FixtureSpec]:
        specs = self._matching(application)
        if not specs:
            raise ProviderError(
                f"No main-solution variants found for application '{application}'."
            )
        return specs

    def get_variants(self, variant_ids: list[str], application: str) -> list[FixtureSpec]:
        wanted = {str(v).lower() for v in variant_ids}
        pool = {str(s.id).lower(): s for s in self._matching(application)}
        missing = [vid for vid in variant_ids if str(vid).lower() not in pool]
        if missing:
            raise ProviderError(
                f"Variant(s) not found as main-solution '{application}' variants: {missing}."
            )
        ordered = [pool[str(vid).lower()] for vid in variant_ids]
        return ordered

    def get_one(self, fixture_id: str) -> FixtureSpec:
        try:
            return self._specs[fixture_id]
        except KeyError as exc:
            raise ProviderError(f"Unknown fixture '{fixture_id}'.") from exc

    def get_many(self, fixture_ids: list[str]) -> list[FixtureSpec]:
        return [self.get_one(fid) for fid in fixture_ids]


__all__ = [
    "FixtureProvider",
    "FixtureSpec",
    "InMemoryFixtureProvider",
    "RestFixtureProvider",
    "api_base",
]
