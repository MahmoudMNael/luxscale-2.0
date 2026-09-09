from __future__ import annotations

from typing import Any


class AppError(Exception):
    """Domain error mapped to HTTP by exception handlers."""

    def __init__(
        self,
        message: str,
        *,
        code: str = "APP_ERROR",
        status_code: int = 400,
        details: list[dict[str, Any]] | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.code = code
        self.status_code = status_code
        self.details = details


class GeometryError(AppError):
    def __init__(self, message: str, *, details: list[dict[str, Any]] | None = None) -> None:
        super().__init__(message, code="GEOMETRY_INVALID", status_code=400, details=details)


class IesParseError(AppError):
    def __init__(self, message: str, *, details: list[dict[str, Any]] | None = None) -> None:
        super().__init__(message, code="IES_PARSE", status_code=400, details=details)


class NoFixturesError(AppError):
    def __init__(self, message: str, *, details: list[dict[str, Any]] | None = None) -> None:
        super().__init__(message, code="NO_FIXTURES", status_code=400, details=details)
