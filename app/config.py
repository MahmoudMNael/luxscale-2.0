"""Startup config: load `.env` into process env (no third-party deps).

The providers read real process environment (`os.environ`) at request time.
`uvicorn` does NOT load `.env` by itself, so without this module a plain
`uvicorn app.main:app` start would report "STANDARDS_BASE_URL is not
configured" even with a correct `.env` sitting in the repo root.

Rules (same as python-dotenv defaults):
- Only fills keys missing from the real environment — exported vars win.
- Missing `.env` file is fine (silent no-op, e.g. production injects env).
- Supports `KEY=value`, `KEY="quoted value"`, `KEY='single'`, `export KEY=..`,
  full-line `#` comments and trailing ` #` comments on unquoted values.
"""

from __future__ import annotations

import os
from pathlib import Path

_ENV_FILE = Path(__file__).resolve().parents[1] / ".env"


def load_env_file(path: str | Path = _ENV_FILE) -> dict[str, str]:
    """Parse `path` and `setdefault` each key into `os.environ`. Returns loaded."""
    loaded: dict[str, str] = {}
    try:
        text = Path(path).read_text(encoding="utf-8")
    except OSError:
        return loaded
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        if line.lower().startswith("export "):
            line = line[7:].strip()
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip()
        if not key or not key.replace("_", "").isalnum():
            continue
        if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
            value = value[1:-1]
        else:  # strip trailing comment from unquoted values only
            hash_at = value.find(" #")
            if hash_at != -1:
                value = value[:hash_at].strip()
        if key not in os.environ:
            os.environ[key] = value
            loaded[key] = value
    return loaded


__all__ = ["load_env_file"]
