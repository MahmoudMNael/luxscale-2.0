from __future__ import annotations

import logging

from app.app_settings import LOG_LEVEL
from app.middleware.request_context import get_request_id


class _RequestIdFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.requestId = get_request_id()
        return True


def configure_logging() -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(
        logging.Formatter("%(levelname)s %(name)s requestId=%(requestId)s %(message)s")
    )
    handler.addFilter(_RequestIdFilter())
    log = logging.getLogger("app")
    log.handlers.clear()
    log.addHandler(handler)
    log.setLevel(LOG_LEVEL)
    log.propagate = False
