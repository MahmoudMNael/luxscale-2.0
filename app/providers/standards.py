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


class InMemoryStandardProvider:
    """Test/dev stub with the same interface (no network)."""

    def __init__(self, targets: dict[str, StandardTarget] | None = None) -> None:
        self._targets: dict[str, StandardTarget] = dict(targets or {})

    def add(self, target: StandardTarget) -> None:
        self._targets[target.activity_id] = target

    def get_target(self, activity_id: str) -> StandardTarget:
        try:
            return self._targets[activity_id]
        except KeyError as exc:
            raise ProviderError(f"Unknown activity '{activity_id}'.") from exc


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
