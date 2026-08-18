"""Shared dependencies."""

from __future__ import annotations

from fastapi import Request

from apps.api.core.reference import ReferenceData, load_reference
from apps.api.core.repository import ResultRepository, resolve_repository


def get_reference() -> ReferenceData:
    return load_reference()


def get_repository(request: Request) -> ResultRepository:
    return resolve_repository(request.app)


def get_request_id(request: Request) -> str:
    return getattr(request.state, "request_id", "unknown")
