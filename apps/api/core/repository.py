"""Persistence for the 30-day replay window.

Supabase when it is configured, memory when it is not. That is not a hedge - it
means a fresh clone runs with no database, and the moment SUPABASE_URL and the
service-role key are present the same code persists for real.

The service-role key never leaves the server. The client only ever holds the
anon key, and reads results through the RLS policy in db/policies.sql.
"""

from __future__ import annotations

import json
import logging
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Protocol

from apps.api.core.config import Settings

logger = logging.getLogger(__name__)

RETENTION_DAYS = 30

# Deliberately inside data/, which is git-ignored for runtime artefacts.
DEFAULT_SQLITE_PATH = Path(__file__).resolve().parents[3] / "data" / "results.db"


class ResultRepository(Protocol):
    def save(self, request_id: str, payload: dict) -> None: ...
    def get(self, request_id: str) -> dict | None: ...
    def health(self) -> str: ...


class MemoryRepository:
    """In-process store. Fine for development and for the demo; lost on restart."""

    def __init__(self) -> None:
        self._store: dict[str, tuple[datetime, dict]] = {}

    def save(self, request_id: str, payload: dict) -> None:
        self._store[request_id] = (datetime.now(timezone.utc), payload)
        self._evict()

    def get(self, request_id: str) -> dict | None:
        entry = self._store.get(request_id)
        if entry is None:
            return None
        created, payload = entry
        if datetime.now(timezone.utc) - created > timedelta(days=RETENTION_DAYS):
            self._store.pop(request_id, None)
            return None
        return payload

    def health(self) -> str:
        return "memory"

    def _evict(self) -> None:
        cutoff = datetime.now(timezone.utc) - timedelta(days=RETENTION_DAYS)
        for key in [k for k, (created, _) in self._store.items() if created < cutoff]:
            self._store.pop(key, None)


class SqliteRepository:
    """A file on disk. No signup, no network, survives a restart.

    This is the default because the alternative was memory, and memory means
    every shareable /r/<id> link dies the moment the API restarts — including
    mid-demo, which is precisely when you would want to reopen a result.

    Supabase remains the deployment story: multiple instances need shared state
    and a file does not give you that. For a laptop, a single-file database is
    strictly better than losing the data.
    """

    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        # check_same_thread=False because FastAPI serves requests from a thread
        # pool; each call opens and closes its own short-lived connection.
        connection = sqlite3.connect(self.path, check_same_thread=False, timeout=5.0)
        connection.row_factory = sqlite3.Row
        return connection

    def _init_schema(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS recommendation_results (
                    request_id    TEXT PRIMARY KEY,
                    payload       TEXT NOT NULL,
                    district_code TEXT,
                    created_at    TEXT NOT NULL,
                    expires_at    TEXT NOT NULL
                )
                """
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS results_expires_at "
                "ON recommendation_results (expires_at)"
            )

    def save(self, request_id: str, payload: dict) -> None:
        now = datetime.now(timezone.utc)
        try:
            with self._connect() as connection:
                connection.execute(
                    "INSERT OR REPLACE INTO recommendation_results "
                    "(request_id, payload, district_code, created_at, expires_at) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (
                        request_id,
                        json.dumps(payload),
                        (payload.get("location_resolved") or {}).get("district_code"),
                        now.isoformat(),
                        (now + timedelta(days=RETENTION_DAYS)).isoformat(),
                    ),
                )
                # Cheap enough to do inline; no cron needed on a laptop.
                connection.execute(
                    "DELETE FROM recommendation_results WHERE expires_at < ?",
                    (now.isoformat(),),
                )
        except sqlite3.Error:
            # The answer is already computed. Losing the replay link is the
            # cheaper failure. architecture.md principle 2.
            logger.exception("Failed to persist result %s; returning it anyway", request_id)

    def get(self, request_id: str) -> dict | None:
        try:
            with self._connect() as connection:
                row = connection.execute(
                    "SELECT payload, expires_at FROM recommendation_results WHERE request_id = ?",
                    (request_id,),
                ).fetchone()
        except sqlite3.Error:
            logger.exception("Failed to read result %s", request_id)
            return None

        if row is None:
            return None
        if datetime.fromisoformat(row["expires_at"]) < datetime.now(timezone.utc):
            return None
        return json.loads(row["payload"])

    def health(self) -> str:
        try:
            with self._connect() as connection:
                connection.execute("SELECT 1 FROM recommendation_results LIMIT 1")
            return "sqlite"
        except sqlite3.Error:
            logger.exception("SQLite health check failed")
            return "unreachable"


class SupabaseRepository:
    """Postgres via Supabase. Table and policies live in db/schema.sql."""

    TABLE = "recommendation_results"

    def __init__(self, url: str, service_role_key: str) -> None:
        from supabase import create_client

        self._client = create_client(url, service_role_key)

    def save(self, request_id: str, payload: dict) -> None:
        expires_at = datetime.now(timezone.utc) + timedelta(days=RETENTION_DAYS)
        try:
            self._client.table(self.TABLE).upsert(
                {
                    "request_id": request_id,
                    "payload": payload,
                    "district_code": payload.get("location_resolved", {}).get("district_code"),
                    "expires_at": expires_at.isoformat(),
                }
            ).execute()
        except Exception:
            # A persistence failure must not cost the farmer their answer. The
            # response is already computed; losing the replay link is the
            # cheaper failure. architecture.md principle 2.
            logger.exception("Failed to persist result %s; returning it anyway", request_id)

    def get(self, request_id: str) -> dict | None:
        try:
            response = (
                self._client.table(self.TABLE)
                .select("payload, expires_at")
                .eq("request_id", request_id)
                .limit(1)
                .execute()
            )
        except Exception:
            logger.exception("Failed to read result %s", request_id)
            return None

        rows = response.data or []
        if not rows:
            return None

        row = rows[0]
        expires_at = row.get("expires_at")
        if expires_at and datetime.fromisoformat(expires_at) < datetime.now(timezone.utc):
            return None

        payload = row["payload"]
        return json.loads(payload) if isinstance(payload, str) else payload

    def health(self) -> str:
        try:
            self._client.table(self.TABLE).select("request_id").limit(1).execute()
            return "ok"
        except Exception:
            logger.exception("Supabase health check failed")
            return "unreachable"


def resolve_repository(app) -> ResultRepository:
    """Fetch the repository off app.state, building it if startup has not run.

    The lifespan hook is the normal path, but it does not fire under a bare
    TestClient or under some ASGI servers. Nothing should 500 over the order two
    initialisers happened to run in, so this is idempotent and safe to call from
    anywhere.
    """
    from apps.api.core.config import get_settings

    repository = getattr(app.state, "repository", None)
    if repository is None:
        repository = build_repository(get_settings())
        app.state.repository = repository
    return repository


def build_repository(settings: Settings) -> ResultRepository:
    """Supabase if configured, otherwise SQLite, and memory only if both fail.

    Order matters. Supabase is the deployment answer because several instances
    need shared state. SQLite is the right local default: results survive a
    restart with no signup and no network. Memory is a last resort, never a
    choice — it silently breaks every shareable link on restart.
    """
    if settings.supabase_configured:
        try:
            logger.info("Persistence: Supabase")
            return SupabaseRepository(settings.supabase_url, settings.supabase_service_role_key)
        except Exception:
            logger.exception("Supabase failed to initialise; falling back to SQLite")

    # RESULTS_DB_PATH lets you move the file off a network share or WSL mount,
    # where SQLite cannot take the locks it needs and raises "disk I/O error".
    import os

    path = Path(os.getenv("RESULTS_DB_PATH", "") or DEFAULT_SQLITE_PATH)
    try:
        repository = SqliteRepository(path)
        logger.info("Persistence: SQLite at %s", path)
        return repository
    except Exception as exc:
        logger.error(
            "SQLite could not open %s (%s: %s). Falling back to MEMORY — results "
            "will be lost on restart and shareable links will break. If this is a "
            "network drive or WSL mount, set RESULTS_DB_PATH to a local path.",
            path,
            type(exc).__name__,
            exc,
        )

    return MemoryRepository()
