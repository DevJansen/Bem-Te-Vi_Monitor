"""SQLite connection helpers — all data stays on the local machine."""

from __future__ import annotations

import sqlite3
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

_local = threading.local()


def _configure_connection(conn: sqlite3.Connection) -> sqlite3.Connection:
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA synchronous = NORMAL")
    return conn


def get_connection(db_path: Path) -> sqlite3.Connection:
    """Return a thread-local SQLite connection."""
    key = str(db_path.resolve())
    cache: dict[str, sqlite3.Connection] = getattr(_local, "connections", {})
    conn = cache.get(key)
    if conn is None:
        db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = _configure_connection(
            sqlite3.connect(str(db_path), check_same_thread=False, timeout=30.0)
        )
        cache[key] = conn
        _local.connections = cache
    return conn


@contextmanager
def db_session(db_path: Path) -> Iterator[sqlite3.Connection]:
    conn = get_connection(db_path)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise


def close_all_connections() -> None:
    cache: dict[str, sqlite3.Connection] = getattr(_local, "connections", {})
    for conn in cache.values():
        try:
            conn.close()
        except Exception:
            pass
    _local.connections = {}
