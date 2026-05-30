"""
SQLite-backed async cache using aiosqlite.
Stores serialized JSON blobs per data type with timestamps.
Handles concurrent async reads/writes safely.
Provides staleness metadata for UI display.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Any, Optional

import aiosqlite

logger = logging.getLogger(__name__)

_DB_PATH = Path(__file__).parent.parent / ".cache" / "db"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS cache (
    key         TEXT PRIMARY KEY,
    data        TEXT NOT NULL,
    fetched_at  TEXT NOT NULL
);
"""


class DataKey(str, Enum):
    ALERTS = "alerts"
    CONDITIONS = "conditions"
    INDICATORS = "indicators"
    FORECAST = "forecast"
    LOCATION = "location"


class StalenessLevel(str, Enum):
    FRESH = "fresh"
    AMBER = "amber"
    RED = "red"


class CacheStore:
    """
    Async SQLite cache with per-key TTL and staleness reporting.
    Use as an async context manager or call open()/close() explicitly.
    """

    def __init__(
        self,
        db_path: Path = _DB_PATH,
        amber_minutes: int = 5,
        red_minutes: int = 15,
    ) -> None:
        self._path = db_path
        self._amber_td = timedelta(minutes=amber_minutes)
        self._red_td = timedelta(minutes=red_minutes)
        self._db: Optional[aiosqlite.Connection] = None

    async def open(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._db = await aiosqlite.connect(self._path)
        self._db.row_factory = aiosqlite.Row
        await self._db.execute(_SCHEMA)
        await self._db.commit()
        logger.debug("Cache database opened at %s", self._path)

    async def close(self) -> None:
        if self._db:
            await self._db.close()
            self._db = None

    async def __aenter__(self) -> "CacheStore":
        await self.open()
        return self

    async def __aexit__(self, *_: Any) -> None:
        await self.close()

    def _assert_open(self) -> aiosqlite.Connection:
        if self._db is None:
            raise RuntimeError("CacheStore is not open. Call open() or use as context manager.")
        return self._db

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    async def set(self, key: DataKey, data: Any) -> None:
        db = self._assert_open()
        serialized = json.dumps(data, default=str)
        now = datetime.now().isoformat()
        await db.execute(
            """
            INSERT INTO cache (key, data, fetched_at)
            VALUES (?, ?, ?)
            ON CONFLICT(key) DO UPDATE SET data=excluded.data, fetched_at=excluded.fetched_at
            """,
            (key.value, serialized, now),
        )
        await db.commit()
        logger.debug("Cache SET: %s at %s", key.value, now)

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    async def get(self, key: DataKey) -> Optional[Any]:
        """Return deserialized cached data or None if not found."""
        db = self._assert_open()
        async with db.execute(
            "SELECT data FROM cache WHERE key = ?", (key.value,)
        ) as cursor:
            row = await cursor.fetchone()
            if row is None:
                return None
            return json.loads(row["data"])

    async def get_with_meta(
        self, key: DataKey
    ) -> tuple[Optional[Any], Optional[datetime], StalenessLevel]:
        """
        Returns (data, fetched_at, staleness_level).
        data is None if cache miss. fetched_at is None on miss.
        """
        db = self._assert_open()
        async with db.execute(
            "SELECT data, fetched_at FROM cache WHERE key = ?", (key.value,)
        ) as cursor:
            row = await cursor.fetchone()
            if row is None:
                return None, None, StalenessLevel.RED

            data = json.loads(row["data"])
            fetched_at = datetime.fromisoformat(row["fetched_at"])
            staleness = self._staleness(fetched_at)
            return data, fetched_at, staleness

    # ------------------------------------------------------------------
    # Staleness
    # ------------------------------------------------------------------

    def _staleness(self, fetched_at: datetime) -> StalenessLevel:
        age = datetime.now() - fetched_at
        if age >= self._red_td:
            return StalenessLevel.RED
        if age >= self._amber_td:
            return StalenessLevel.AMBER
        return StalenessLevel.FRESH

    async def staleness_of(self, key: DataKey) -> tuple[StalenessLevel, Optional[datetime]]:
        """Return staleness level and timestamp for a given key."""
        db = self._assert_open()
        async with db.execute(
            "SELECT fetched_at FROM cache WHERE key = ?", (key.value,)
        ) as cursor:
            row = await cursor.fetchone()
            if row is None:
                return StalenessLevel.RED, None
            fetched_at = datetime.fromisoformat(row["fetched_at"])
            return self._staleness(fetched_at), fetched_at

    # ------------------------------------------------------------------
    # Utility
    # ------------------------------------------------------------------

    async def clear(self, key: Optional[DataKey] = None) -> None:
        """Clear one key or the entire cache if key is None."""
        db = self._assert_open()
        if key:
            await db.execute("DELETE FROM cache WHERE key = ?", (key.value,))
        else:
            await db.execute("DELETE FROM cache")
        await db.commit()
