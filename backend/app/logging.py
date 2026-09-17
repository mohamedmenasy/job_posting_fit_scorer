"""JSON log lines (spec §12). Callers pass structured data via extra={"fields": {...}}."""

import json
import logging
from datetime import UTC, datetime

from app.config import Settings


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        line = {
            "ts": datetime.fromtimestamp(record.created, UTC).isoformat(),
            "level": record.levelname.lower(),
            "logger": record.name,
            "event": record.getMessage(),
            **getattr(record, "fields", {}),
        }
        if record.exc_info:
            line["exc_type"] = record.exc_info[0].__name__
        return json.dumps(line, default=str)


def configure_logging(settings: Settings) -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    app_logger = logging.getLogger("app")
    app_logger.handlers[:] = [handler]
    app_logger.setLevel(settings.log_level.upper())
    app_logger.propagate = False
    # SDK debug logging prints full request bodies (the resume) — never go below warning by default.
    logging.getLogger("typesafe_sdk").setLevel(settings.typesafe_log_level.upper())
