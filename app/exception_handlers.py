from __future__ import annotations

import logging

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.domain.exceptions import AppError
from app.middleware.request_context import get_request_id
from app.schemas.errors import ErrorBody, ErrorCode, ErrorDetail, ErrorResponse

_log = logging.getLogger("app.exception_handlers")


def _body(code: ErrorCode, message: str, details: list[ErrorDetail] | None = None) -> dict:
    return ErrorResponse(
        error=ErrorBody(code=code, message=message, details=details, requestId=get_request_id())
    ).model_dump(by_alias=True)


def _json(status: int, code: ErrorCode, message: str, details: list[ErrorDetail] | None = None) -> JSONResponse:
    return JSONResponse(
        status_code=status,
        content=_body(code, message, details),
        headers={"X-Request-ID": get_request_id()},
    )


async def app_error_handler(_: Request, exc: AppError) -> JSONResponse:
    _log.warning("code=%s message=%s", exc.code, exc.message)
    details = [ErrorDetail(**d) for d in exc.details] if exc.details else None
    return _json(exc.status_code, ErrorCode(exc.code), exc.message, details)


async def utf8_error_handler(_: Request, exc: UnicodeDecodeError) -> JSONResponse:
    _log.warning("IES file is not UTF-8: %s", exc.reason)
    return _json(400, ErrorCode.IES_ENCODING, "IES file must be UTF-8 text.")


async def validation_handler(_: Request, exc: RequestValidationError) -> JSONResponse:
    details = [
        ErrorDetail(
            field=".".join(str(p) for p in err.get("loc", ()) if p != "body") or None,
            issue=str(err.get("msg", "")),
        )
        for err in exc.errors()
    ]
    _log.info("validation failed")
    return _json(422, ErrorCode.VALIDATION_ERROR, "Request validation failed.", details)


async def unhandled_handler(_: Request, exc: Exception) -> JSONResponse:
    _log.error("unhandled exception", exc_info=exc)
    return _json(500, ErrorCode.INTERNAL_ERROR, "Internal server error.")
