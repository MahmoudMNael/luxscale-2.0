"""External standard provider — admin contract §3 (env: STANDARDS_BASE_URL).

`activityId` in the automate request IS the standard-id path key:
    GET {STANDARDS_BASE_URL}/api/v1/standards/{activityId}
-> success envelope (§1.1) with `data: StandardResponse`.

Target mapping (EDIT HERE if the source fields change):
- avg_lux    <- StandardResponse.target_illuminance() (em_r_lx, fallback em_u_lx)
- uniformity <- StandardResponse.target_uniformity()  (uo)
- max_overdesign has no contract source -> MAX_OVERDESIGN_DEFAULT below.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Protocol

from app.domain.exceptions import ProviderError
from app.schemas.standards import StandardResponse

API_PREFIX = "/api/v1"


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

# No contract source for allowed overdesign -> single editable default.
MAX_OVERDESIGN_DEFAULT = 0.3


@dataclass(frozen=True)
class StandardTarget:
    activity_id: str
    avg_lux: float
    uniformity: float
    max_overdesign: float = MAX_OVERDESIGN_DEFAULT
    work_plane_height: float | None = None
    wall_zone: float | None = None


class StandardProvider(Protocol):
    def get_target(self, activity_id: str) -> StandardTarget: ...
    def list_standards(self) -> list[StandardResponse]: ...


def _get_json(url: str, timeout_s: float) -> dict:
    try:
        with urllib.request.urlopen(url, timeout=timeout_s) as response:
            if response.status != 200:
                raise ProviderError(f"Standards API returned HTTP {response.status} for {url}.")
            try:
                data = json.loads(response.read().decode("utf-8"))
            except ValueError as exc:
                raise ProviderError(f"Standards API returned invalid JSON for {url}.") from exc
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            raise ProviderError(f"Standard '{url}' not found.") from exc
        raise ProviderError(f"Standards API returned HTTP {exc.code} for {url}.") from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise ProviderError(f"Standards API unreachable ({url}): {exc}.") from exc
    if not isinstance(data, dict):
        raise ProviderError(f"Standards API returned invalid payload for {url}.")
    return data


def target_from_standard(standard: StandardResponse) -> StandardTarget:
    """StandardResponse -> StandardTarget. EDIT mapping here if needed."""
    try:
        avg = standard.target_illuminance()
    except ValueError as exc:
        raise ProviderError(str(exc)) from exc
    try:
        uni = standard.target_uniformity()
    except ValueError as exc:
        raise ProviderError(str(exc)) from exc
    return StandardTarget(
        activity_id=standard.id,
        avg_lux=float(avg),
        uniformity=float(uni),
        max_overdesign=MAX_OVERDESIGN_DEFAULT,
    )


class RestStandardProvider:
    """GET {base}/api/v1/standards/{standard_id}. Plain urllib, no new deps."""

    def __init__(self, base_url: str | None = None, timeout_s: float = 5.0) -> None:
        base = base_url if base_url is not None else os.environ.get("STANDARDS_BASE_URL", "")
        self.base_url = api_base(base) if base.rstrip("/") else ""
        print(f"RestStandardProvider: base_url={self.base_url}, timeout_s={timeout_s}")
        self.timeout_s = timeout_s

    def get_target(self, activity_id: str) -> StandardTarget:
        if not self.base_url:
            raise ProviderError("STANDARDS_BASE_URL is not configured.")
        key = urllib.parse.quote(str(activity_id), safe="")
        payload = _get_json(f"{self.base_url}/standards/{key}", self.timeout_s)
        try:
            standard = StandardResponse.model_validate(payload.get("data", payload))
        except Exception as exc:
            raise ProviderError(f"Standards API payload for '{activity_id}' is invalid: {exc}.") from exc
        return target_from_standard(standard)

    def list_standards(self) -> list[StandardResponse]:
        if not self.base_url:
            raise ProviderError("STANDARDS_BASE_URL is not configured.")
        out: list[StandardResponse] = []
        page = 1
        while True:
            params = {"page": page, "limit": 100}
            query = urllib.parse.urlencode(params)
            url = f"{self.base_url}/standards/?{query}"
            payload = _get_json(url, self.timeout_s)
            data = payload.get("data", [])
            if not isinstance(data, list):
                raise ProviderError(f"Standards API returned invalid payload for {url}.")
            for item in data:
                try:
                    out.append(StandardResponse.model_validate(item))
                except Exception as exc:
                    raise ProviderError(f"Standards API record invalid ({url}): {exc}.") from exc
            pagination = payload.get("pagination")
            if not isinstance(pagination, dict):
                break
            total_pages = int(pagination.get("total_pages", page))
            if page >= total_pages:
                break
            page += 1
        return out

    def query_standards(
        self,
        page: int = 1,
        limit: int = 20,
        standard_code: str | None = None,
        version_year: str | None = None,
        is_latest: bool | None = None,
        category_table_number: str | None = None,
        activity: str | None = None,
        keywords: list[str] | None = None,
        match_mode: str = "any",
    ) -> dict:
        if not self.base_url:
            raise ProviderError("STANDARDS_BASE_URL is not configured.")
        params: dict[str, str] = {"page": str(page), "limit": str(limit)}
        if standard_code:
            params["standard_code"] = standard_code
        if version_year:
            params["version_year"] = version_year
        if is_latest is not None:
            params["is_latest"] = str(is_latest).lower()
        if category_table_number:
            params["category_table_number"] = category_table_number
        if activity:
            params["activity"] = activity
        if match_mode:
            params["match_mode"] = match_mode

        query_str = urllib.parse.urlencode(params)
        if keywords:
            for kw in keywords:
                query_str += f"&keywords={urllib.parse.quote_plus(kw)}"

        url = f"{self.base_url}/standards/?{query_str}"
        return _get_json(url, self.timeout_s)

    def list_categories(
        self,
        standard_code: str | None = None,
        version_year: str | None = None,
        is_latest: bool | None = None,
    ) -> dict:
        if not self.base_url:
            raise ProviderError("STANDARDS_BASE_URL is not configured.")
        params: dict[str, str] = {}
        if standard_code:
            params["standard_code"] = standard_code
        if version_year:
            params["version_year"] = version_year
        if is_latest is not None:
            params["is_latest"] = str(is_latest).lower()

        query_str = urllib.parse.urlencode(params)
        url = f"{self.base_url}/standards/categories{('?' + query_str) if query_str else ''}"
        return _get_json(url, self.timeout_s)

    def get_standard_raw(self, standard_id: str) -> dict:
        if not self.base_url:
            raise ProviderError("STANDARDS_BASE_URL is not configured.")
        key = urllib.parse.quote(str(standard_id), safe="")
        return _get_json(f"{self.base_url}/standards/{key}", self.timeout_s)


class InMemoryStandardProvider:
    """Test/dev stub with the same interface (no network)."""

    def __init__(
        self,
        targets: dict[str, StandardTarget] | None = None,
        standards: list[StandardResponse] | None = None,
    ) -> None:
        self._targets: dict[str, StandardTarget] = dict(targets or {})
        self._standards: list[StandardResponse] = list(standards or [])

    def add(self, target: StandardTarget) -> None:
        self._targets[target.activity_id] = target

    def get_target(self, activity_id: str) -> StandardTarget:
        try:
            return self._targets[activity_id]
        except KeyError as exc:
            raise ProviderError(f"Unknown activity '{activity_id}'.") from exc

    def list_standards(self) -> list[StandardResponse]:
        if self._standards:
            return list(self._standards)
        from datetime import datetime, timezone
        from app.schemas.standards import (
            StandardHierarchyDto,
            StandardMetadataDto,
            StandardParametersDto,
        )
        now = datetime.now(timezone.utc)
        results = []
        for target in self._targets.values():
            results.append(
                StandardResponse(
                    id=target.activity_id,
                    qdrant_point_id="stub-point-id",
                    standard_metadata=StandardMetadataDto(
                        standard_code="EN 12464-1",
                        version_year="2021",
                        is_latest=True,
                    ),
                    hierarchy=StandardHierarchyDto(
                        category_table_number="5.1",
                        category_title="Offices",
                        ref_number="5.1.1",
                        page=1,
                    ),
                    activity=f"Office - {target.activity_id}",
                    parameters=StandardParametersDto(
                        em_r_lx=target.avg_lux,
                        em_u_lx=target.avg_lux,
                        uo=target.uniformity,
                        ra=80.0,
                    ),
                    searchable_text=f"Office {target.activity_id}",
                    content_hash="stubhash",
                    created_at=now,
                    updated_at=now,
                )
            )
        return results

    def query_standards(self, **kwargs) -> dict:
        standards = self.list_standards()
        items = [s.model_dump(mode="json") for s in standards]
        return {
            "success": True,
            "data": items,
            "pagination": {
                "total_count": len(items),
                "page_size": 20,
                "current_page": 1,
                "total_pages": 1,
            },
        }

    def list_categories(self, **kwargs) -> dict:
        return {
            "success": True,
            "data": [
                {
                    "standard_metadata": {"standard_code": "EN 12464-1", "version_year": "2021", "is_latest": True},
                    "category_table_number": "5.1",
                    "category_title": "Offices",
                }
            ],
            "pagination": None,
        }

    def get_standard_raw(self, standard_id: str) -> dict:
        target = self.get_target(standard_id)
        return {
            "success": True,
            "data": {
                "id": target.activity_id,
                "activity": f"Office - {target.activity_id}",
                "parameters": {"em_r_lx": target.avg_lux, "uo": target.uniformity},
            },
        }


__all__ = [
    "API_PREFIX",
    "MAX_OVERDESIGN_DEFAULT",
    "RestStandardProvider",
    "StandardProvider",
    "StandardTarget",
    "InMemoryStandardProvider",
    "api_base",
    "target_from_standard",
]
