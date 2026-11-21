"""
Assigns request_id, reads or creates correlation_id (X-Correlation-ID), times each request, echoes both ids in headers.

Owner: Joyal (M1)  |  Spec: Agile Spec v2.0
"""

import re
import time
from uuid import uuid4

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp


class RequestContextMiddleware(BaseHTTPMiddleware):
    def __init__(
        self,
        app: ASGIApp,
        correlation_header: str = "X-Correlation-ID",
    ) -> None:
        super().__init__(app)
        self.correlation_header = correlation_header

    async def dispatch(
        self,
        request: Request,
        call_next: RequestResponseEndpoint,
    ) -> Response:
        request_id = str(uuid4())
        correlation_id = request.headers.get(self.correlation_header, "").strip()
        if not re.fullmatch(r"[A-Za-z0-9._:-]{1,128}", correlation_id):
            correlation_id = str(uuid4())

        request.state.request_id = request_id
        request.state.correlation_id = correlation_id
        started = time.perf_counter()
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        response.headers["X-Correlation-ID"] = correlation_id
        response.headers["X-Response-Time-Ms"] = str(
            round((time.perf_counter() - started) * 1000)
        )
        return response
