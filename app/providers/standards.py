"""External standard-activity provider. REST JSON, no auth (env: STANDARDS_BASE_URL)."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Protocol

from app.domain.exceptions import ProviderError


@dataclass(frozen=True)
class StandardTarget:
    activity_id: str
    avg_lux: float
    uniformity: float
    max_overdesign: float = 0.3
    work_plane_height: float | None = None
    wall_zone: float | None = None


class StandardProvider(Protocol):
    def get_target(self, activity_id: str) -> StandardTarget: ...


def _get(url: str, timeout_s: float) -> dict:
    try:
        with urllib.request.urlopen(url, timeout=timeout_s) as response:
            if response.status != 200:
                raise ProviderError(f"Standards API returned HTTP {response.status} for {url}.")
            try:
                data = json.loads(response.read().decode("utf-8"))
            except ValueError as exc:
                raise ProviderError(f"Standards API returned invalid JSON for {url}.") from exc
    except urllib.error.HTTPError as exc:
        raise ProviderError(f"Standards API returned HTTP {exc.code} for {url}.") from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise ProviderError(f"Standards API unreachable ({url}): {exc}.") from exc
    if not isinstance(data, dict):
        raise ProviderError(f"Standards API returned invalid payload for {url}.")
    return data


def _target_from(activity_id: str, data: dict) -> StandardTarget:
    try:
        avg = float(data.get("avgLux", data.get("avg_lux")))
        uni = float(data.get("uniformity", data.get("u0")))
    except (TypeError, ValueError) as exc:
        raise ProviderError(f"Standards API payload for '{activity_id}' lacks avgLux/uniformity.") from exc

    def _opt(*keys: str) -> float | None:
        for key in keys:
            if data.get(key) is not None:
                return float(data[key])
        return None

    return StandardTarget(
        activity_id=activity_id,
        avg_lux=avg,
        uniformity=uni,
        max_overdesign=float(data.get("maxOverdesign", data.get("max_overdesign", 0.3))),
        work_plane_height=_opt("workPlaneHeight", "work_plane_height"),
        wall_zone=_opt("wallZone", "wall_zone"),
    )


class RestStandardProvider:
    """GET {base}/activities/{id}. Pony: plain urllib, no new deps."""

    def __init__(self, base_url: str | None = None, timeout_s: float = 5.0) -> None:
        base = base_url if base_url is not None else os.environ.get("STANDARDS_BASE_URL", "")
        self.base_url = base.rstrip("/")
        self.timeout_s = timeout_s

    def get_target(self, activity_id: str) -> StandardTarget:
        if not self.base_url:
            raise ProviderError("STANDARDS_BASE_URL is not configured.")
        data = _get(f"{self.base_url}/activities/{activity_id}", self.timeout_s)
        return _target_from(activity_id, data)


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


__all__ = ["StandardTarget", "StandardProvider", "RestStandardProvider", "InMemoryStandardProvider"]
