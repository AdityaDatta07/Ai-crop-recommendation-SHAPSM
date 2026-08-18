"""The error envelope, in one place.

api-contract.md section 2.3: every non-2xx response has the same shape, no
exceptions. Route code raises a typed domain exception and never constructs an
error response by hand, so there is one place to change and one shape to test.
"""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException


class DomainError(Exception):
    """Base for everything the API deliberately turns into an error response."""

    code = "INTERNAL_ERROR"
    status = 500

    def __init__(self, message: str, field: str | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.field = field


class ValidationFailed(DomainError):
    code = "VALIDATION_ERROR"
    status = 400


class InvalidLocation(DomainError):
    code = "INVALID_LOCATION"
    status = 400


class UnsupportedSeason(DomainError):
    code = "UNSUPPORTED_SEASON"
    status = 400


class NotFound(DomainError):
    code = "NOT_FOUND"
    status = 404


class NoDataForLocation(DomainError):
    code = "NO_DATA_FOR_LOCATION"
    status = 422


class RateLimited(DomainError):
    code = "RATE_LIMITED"
    status = 429


class UpstreamFailed(DomainError):
    code = "UPSTREAM_FAILED"
    status = 502


def envelope(
    code: str, message: str, request_id: str, field: str | None = None
) -> dict[str, dict[str, str]]:
    body: dict[str, str] = {"code": code, "message": message, "request_id": request_id}
    if field:
        body["field"] = field
    return {"error": body}


def _request_id(request: Request) -> str:
    return getattr(request.state, "request_id", "unknown")


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(DomainError)
    async def _domain(request: Request, exc: DomainError) -> JSONResponse:
        request_id = _request_id(request)
        return JSONResponse(
            status_code=exc.status,
            content=envelope(exc.code, exc.message, request_id, exc.field),
            headers={"X-Request-Id": request_id},
        )

    @app.exception_handler(RequestValidationError)
    async def _validation(request: Request, exc: RequestValidationError) -> JSONResponse:
        request_id = _request_id(request)
        first = exc.errors()[0] if exc.errors() else {}
        # loc looks like ("body", "location", "lat"); drop the "body" prefix so
        # the field path matches what the client sent.
        location = [str(part) for part in first.get("loc", ()) if part != "body"]
        return JSONResponse(
            status_code=400,
            content=envelope(
                "VALIDATION_ERROR",
                first.get("msg", "Request failed validation."),
                request_id,
                ".".join(location) or None,
            ),
            headers={"X-Request-Id": request_id},
        )

    @app.exception_handler(StarletteHTTPException)
    async def _http(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        request_id = _request_id(request)
        code = {404: "NOT_FOUND", 429: "RATE_LIMITED"}.get(exc.status_code, "INTERNAL_ERROR")
        return JSONResponse(
            status_code=exc.status_code,
            content=envelope(code, str(exc.detail), request_id),
            headers={"X-Request-Id": request_id},
        )

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception) -> JSONResponse:
        request_id = _request_id(request)
        # The real detail goes to the logs with the request id; the client gets
        # a stable shape and nothing that leaks internals.
        import logging

        logging.getLogger(__name__).exception("Unhandled error on request %s", request_id)
        return JSONResponse(
            status_code=500,
            content=envelope("INTERNAL_ERROR", "Something went wrong on our side.", request_id),
            headers={"X-Request-Id": request_id},
        )
