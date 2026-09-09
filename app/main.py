from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.utils import get_openapi
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

from app.controllers.calculate_controller import router
from app.domain.exceptions import AppError
from app.exception_handlers import (
    app_error_handler,
    unhandled_handler,
    utf8_error_handler,
    validation_handler,
)
from app.logging_config import configure_logging
from app.middleware.request_context import RequestContextMiddleware
from app.schemas.calculate import CalculateRequest

configure_logging()

_DEMO_DIR = Path(__file__).resolve().parents[1] / "demo"

app = FastAPI(title="LuxScale Lighting Engine", version="2.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(RequestContextMiddleware)
app.include_router(router)
app.add_exception_handler(AppError, app_error_handler)
app.add_exception_handler(UnicodeDecodeError, utf8_error_handler)
app.add_exception_handler(RequestValidationError, validation_handler)
app.add_exception_handler(Exception, unhandled_handler)


@app.get("/", include_in_schema=False)
def _root() -> RedirectResponse:
    return RedirectResponse("/demo/")


def _openapi() -> dict:
    if app.openapi_schema:
        return app.openapi_schema
    schema = get_openapi(title=app.title, version=app.version, routes=app.routes)
    js = CalculateRequest.model_json_schema(ref_template="#/components/schemas/{model}")
    defs = js.pop("$defs", {})
    components = schema.setdefault("components", {}).setdefault("schemas", {})
    components.update(defs)
    components["CalculateRequest"] = js
    schema["paths"]["/calculate"]["post"]["requestBody"] = {
        "required": True,
        "content": {
            "multipart/form-data": {
                "schema": {
                    "type": "object",
                    "required": ["payload", "iesFile"],
                    "properties": {
                        "payload": {"$ref": "#/components/schemas/CalculateRequest"},
                        "iesFile": {
                            "type": "string",
                            "format": "binary",
                            "description": "IES LM-63 photometry text file",
                        },
                    },
                },
                "encoding": {"payload": {"contentType": "application/json"}},
            }
        },
    }
    app.openapi_schema = schema
    return schema


app.openapi = _openapi
app.mount("/demo", StaticFiles(directory=_DEMO_DIR, html=True), name="demo")
