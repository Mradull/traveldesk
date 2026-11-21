"""
Structured JSON logging; the fallback sink when error_logs cannot be written. Never logs passwords, tokens or keys.

Owner: Joyal (M1)  |  Spec: Agile Spec v2.0  (Logging, error storage and tracing)

Every 'traveldesk.*' logger writes one JSON object per line to the backend console, e.g.
  {"time": "2026-11-20T10:15:02+05:30", "level": "ERROR", "logger": "traveldesk.errors",
   "event": "error_log_write_failed", "error_code": "NOT_FOUND", "correlation_id": "..."}
Callers pass messages that are already JSON (json.dumps of safe fields only); plain text is wrapped.
"""

import json
import logging
import sys
from datetime import datetime, timezone


class JsonFormatter(logging.Formatter):
    """One JSON object per log line; a JSON message is merged into it, plain text goes in 'message'."""

    def format(self, record: logging.LogRecord) -> str:
        entry = {
            "time": datetime.fromtimestamp(record.created, timezone.utc).astimezone().isoformat(timespec="seconds"),
            "level": record.levelname,
            "logger": record.name,
        }
        message = record.getMessage()
        try:
            parsed = json.loads(message)
        except (TypeError, ValueError):
            parsed = None
        if isinstance(parsed, dict):
            entry.update(parsed)
        else:
            entry["message"] = message
        return json.dumps(entry, default=str)


def configure_logging(level: str = "INFO", log_format: str = "json") -> None:
    """Attach one console handler to the 'traveldesk' logger (safe to call more than once)."""
    logger = logging.getLogger("traveldesk")
    logger.setLevel(level.upper())
    if not any(getattr(handler, "_traveldesk", False) for handler in logger.handlers):
        handler = logging.StreamHandler(sys.stderr)
        handler._traveldesk = True  # type: ignore[attr-defined]
        handler.setFormatter(
            JsonFormatter() if log_format.lower() == "json" else logging.Formatter("%(levelname)s %(name)s %(message)s")
        )
        logger.addHandler(handler)
