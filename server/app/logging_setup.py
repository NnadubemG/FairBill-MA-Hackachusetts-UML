"""Privacy-preserving, error-only logging.

Requirements (product + spec):
  - Log ERRORS only. No info/debug logging of payloads.
  - NEVER log request or response bodies, nor the text sent to / returned from
    Anthropic.
  - Access logging, if any, records only non-body metadata
    (method, route, status, latency, request id).
  - The Anthropic API key must never appear in a log line.

The single `log_error` helper accepts only non-body metadata by construction —
there is no parameter through which a body could be passed.
"""

from __future__ import annotations

import logging
from typing import Optional

_LOGGER_NAME = "medbill"
_configured = False


def configure_logging() -> None:
    """Configure the root + app loggers at ERROR level, once.

    Uvicorn's access logger (which would otherwise print request lines) is set to
    ERROR as well so normal request bodies/paths are not emitted. We intentionally
    do NOT attach a formatter that includes message bodies.
    """
    global _configured
    if _configured:
        return

    handler = logging.StreamHandler()
    # Metadata-only format: level, logger name, message. No body fields.
    handler.setFormatter(
        logging.Formatter("%(levelname)s %(name)s: %(message)s")
    )

    root = logging.getLogger()
    root.setLevel(logging.ERROR)
    # Avoid duplicate handlers if something already attached one.
    if not root.handlers:
        root.addHandler(handler)

    logging.getLogger(_LOGGER_NAME).setLevel(logging.ERROR)

    # Quiet uvicorn's body/access chatter; keep only errors.
    for noisy in ("uvicorn.access",):
        logging.getLogger(noisy).setLevel(logging.ERROR)
    # uvicorn.error stays at ERROR (its name notwithstanding, it carries startup
    # and error messages we do want).
    logging.getLogger("uvicorn.error").setLevel(logging.ERROR)

    _configured = True


def log_error(
    route: str,
    status: int,
    *,
    request_id: Optional[str] = None,
    message: str = "",
) -> None:
    """Log a single error line of NON-BODY metadata only.

    Parameters are deliberately limited to metadata. There is intentionally no
    way to pass a request/response body or model text through this function.
    """
    logger = logging.getLogger(_LOGGER_NAME)
    rid = request_id or "-"
    # `message` is meant for short, non-sensitive context (e.g. an exception class
    # name). Callers must never pass bodies or model text here.
    logger.error("route=%s status=%s request_id=%s %s", route, status, rid, message)
