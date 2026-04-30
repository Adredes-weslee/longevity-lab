"""API middleware utilities."""

from __future__ import annotations

import logging
import re
import time
import uuid
from collections.abc import Awaitable, Callable

from fastapi import Request, Response

REQUEST_ID_HEADER = "X-Request-ID"

_logger = logging.getLogger(__name__)
_REQUEST_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")


def _normalize_request_id(value: str | None) -> str:
    """Return a safe request ID suitable for logs and headers.

    If the inbound value is empty/invalid, generate a UUID4 hex string.
    """
    if not value:
        return uuid.uuid4().hex
    candidate = value.strip()
    if not _REQUEST_ID_PATTERN.match(candidate):
        return uuid.uuid4().hex
    return candidate


async def request_logging_middleware(
    request: Request,
    call_next: Callable[[Request], Awaitable[Response]],
) -> Response:
    """Attach/propagate request IDs and emit a single structured completion log line.

    The middleware:
      - Uses inbound `X-Request-ID` if present; otherwise generates a UUID.
      - Adds `X-Request-ID` to the response headers.
      - Logs one completion line with request_id, method, path, status_code, duration_ms.
    """
    request_id = _normalize_request_id(request.headers.get(REQUEST_ID_HEADER))

    request.state.request_id = request_id

    start = time.perf_counter()
    try:
        response = await call_next(request)
    except Exception:
        duration_ms = int((time.perf_counter() - start) * 1000)
        _logger.exception(
            "request_failed request_id=%s method=%s path=%s duration_ms=%s",
            request_id,
            request.method,
            request.url.path,
            duration_ms,
        )
        raise

    duration_ms = int((time.perf_counter() - start) * 1000)

    response.headers[REQUEST_ID_HEADER] = request_id

    _logger.info(
        "request_completed request_id=%s method=%s path=%s status_code=%s duration_ms=%s",
        request_id,
        request.method,
        request.url.path,
        response.status_code,
        duration_ms,
    )
    return response
