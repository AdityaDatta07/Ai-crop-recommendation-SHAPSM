"""FastAPI application factory.

Thin by design: middleware, error handlers, routers. All the thinking lives in
services/ and in the imported services/geo and services/ml packages.
"""

from __future__ import annotations

import logging
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from apps.api.core.config import get_settings
from apps.api.core.errors import register_exception_handlers
from apps.api.core.reference import load_reference
from apps.api.core.repository import build_repository, resolve_repository
from apps.api.routers import chat, geo, meta, prices, recommendations
from apps.api.schemas import contract as api
from apps.api.services.recommendation_service import new_request_id
from services.geo import geo_backend_name

VERSION = "1.0.0"

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    logging.basicConfig(
        level=getattr(logging, settings.log_level.upper(), logging.INFO),
        format='{"level":"%(levelname)s","logger":"%(name)s","msg":"%(message)s"}',
    )

    # Fail fast at startup if the reference data is inconsistent. Better to
    # refuse to boot than to serve numbers with broken provenance.
    reference = load_reference()
    logger.info("Reference data loaded: %d crops", len(reference.crops))

    app.state.repository = build_repository(settings)

    # Announce the actual data sources. A server silently running on mock data
    # while its .env says otherwise is exactly the failure this prevents.
    backend = geo_backend_name()
    logger.info(
        "Data sources: geo=%s, prices=%s, db=%s",
        backend,
        "agmarknet" if settings.agmarknet_configured else "MSP fallback",
        "supabase" if settings.supabase_configured else "memory",
    )
    if backend == "mock" and settings.earth_engine_configured:
        logger.warning(
            "Earth Engine credentials are present but USE_MOCK_GEO is not false — "
            "serving mock geo data."
        )

    yield


def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(
        title="Crop Recommendation API",
        version=VERSION,
        description="See docs/api-contract.md. The document is authoritative; this API mirrors it.",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=False,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["*"],
        expose_headers=["X-Request-Id"],
    )

    @app.middleware("http")
    async def request_context(request: Request, call_next):
        """One id per request, on the response and on every log line.

        Contract section 5: X-Request-Id is set on every response, without
        exception - which is why this wraps everything including failures.
        """
        request_id = request.headers.get("X-Request-Id") or new_request_id()
        request.state.request_id = request_id

        started = time.perf_counter()
        response = await call_next(request)
        elapsed_ms = (time.perf_counter() - started) * 1000

        response.headers["X-Request-Id"] = request_id
        logger.info(
            "%s %s -> %d in %.0fms (%s)",
            request.method,
            request.url.path,
            response.status_code,
            elapsed_ms,
            request_id,
        )
        return response

    register_exception_handlers(app)

    app.include_router(recommendations.router)
    app.include_router(chat.router)
    app.include_router(geo.router)
    app.include_router(meta.router)
    app.include_router(prices.router)

    @app.get("/health", response_model=api.HealthResponse, tags=["health"])
    def health() -> api.HealthResponse:
        """Liveness plus dependency reachability. Not versioned, no /api/v1."""
        return api.HealthResponse(
            status="ok",
            version=VERSION,
            geo_service=geo_backend_name(),
            db=resolve_repository(app).health(),
        )

    return app


app = create_app()
