"""External fixture-catalog provider. REST JSON, no auth (env: FIXTURES_BASE_URL)."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Protocol

from app.domain.exceptions import ProviderError


@dataclass(frozen=True)
class FixtureSpec:
    id: str
    ies_text: str
    wattage: float | None = None
    lumens: float | None = None
    length: float | None = None
    width: float | None = None
    height: float | None = None


class FixtureProvider(Protocol):
    def get_one(self, fixture_id: str) -> FixtureSpec: ...
    def get_many(self, fixture_ids: list[str]) -> list[FixtureSpec]: ...


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


def _get_text(url: str, timeout_s: float) -> str:
    try:
        with urllib.request.urlopen(url, timeout=timeout_s) as response:
            if response.status != 200:
                raise ProviderError(f"Fixtures API returned HTTP {response.status} for {url}.")
            return response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        raise ProviderError(f"Fixtures API returned HTTP {exc.code} for {url}.") from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise ProviderError(f"Fixtures API unreachable ({url}): {exc}.") from exc


def _opt_float(data: dict, *keys: str) -> float | None:
    for key in keys:
        if data.get(key) is not None:
            return float(data[key])
    return None


class RestFixtureProvider:
    """GET {base}/fixtures/{id} -> {iesText|iesUrl, wattage, ...}. Pony: urllib only."""

    def __init__(self, base_url: str | None = None, timeout_s: float = 5.0) -> None:
        base = base_url if base_url is not None else os.environ.get("FIXTURES_BASE_URL", "")
        self.base_url = base.rstrip("/")
        self.timeout_s = timeout_s

    def get_one(self, fixture_id: str) -> FixtureSpec:
        if not self.base_url:
            raise ProviderError("FIXTURES_BASE_URL is not configured.")
        data = _get_json(f"{self.base_url}/fixtures/{fixture_id}", self.timeout_s)
        ies_text = data.get("iesText", data.get("ies_text"))
        if ies_text is None and data.get("iesUrl", data.get("ies_url")):
            ies_text = _get_text(data.get("iesUrl", data.get("ies_url")), self.timeout_s)
        if not ies_text:
            raise ProviderError(f"Fixtures API entry '{fixture_id}' has no iesText/iesUrl.")
        return FixtureSpec(
            id=str(data.get("id", fixture_id)),
            ies_text=ies_text,
            wattage=_opt_float(data, "wattage"),
            lumens=_opt_float(data, "lumens"),
            length=_opt_float(data, "length"),
            width=_opt_float(data, "width"),
            height=_opt_float(data, "height"),
        )

    def get_many(self, fixture_ids: list[str]) -> list[FixtureSpec]:
        return [self.get_one(fid) for fid in fixture_ids]


class InMemoryFixtureProvider:
    """Test/dev stub with the same interface (no network)."""

    def __init__(self, specs: dict[str, FixtureSpec] | None = None) -> None:
        self._specs: dict[str, FixtureSpec] = dict(specs or {})

    def add(self, spec: FixtureSpec) -> None:
        self._specs[spec.id] = spec

    def get_one(self, fixture_id: str) -> FixtureSpec:
        try:
            return self._specs[fixture_id]
        except KeyError as exc:
            raise ProviderError(f"Unknown fixture '{fixture_id}'.") from exc

    def get_many(self, fixture_ids: list[str]) -> list[FixtureSpec]:
        return [self.get_one(fid) for fid in fixture_ids]


__all__ = ["FixtureSpec", "FixtureProvider", "RestFixtureProvider", "InMemoryFixtureProvider"]
