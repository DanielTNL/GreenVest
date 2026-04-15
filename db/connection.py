"""Database connection helpers."""

from __future__ import annotations

import sqlite3
from pathlib import Path


def connect_sqlite(path: str | Path) -> sqlite3.Connection:
    """Create a SQLite connection with sensible defaults for local analytics."""

    connection = sqlite3.connect(str(path))
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON;")
    connection.execute("PRAGMA journal_mode = WAL;")
    connection.execute("PRAGMA synchronous = NORMAL;")
    return connection
