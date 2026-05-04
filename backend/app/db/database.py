"""
SQLite database — persistent storage for all conversation memory.

Schema:
  sessions    — one row per chat session (id, title, created_at, updated_at)
  turns       — every conversation turn (session_id, role, content, metadata)
  preferences — per-session key/value store (watchlist, active symbol, etc.)
  market_facts — cached market knowledge per symbol
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import aiosqlite

# Store the DB next to the backend package so it persists across restarts
_DB_PATH = Path(os.getenv("NEXUS_DB_PATH", Path(__file__).parent.parent.parent / "nexus_memory.db"))

_SCHEMA = """
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;

CREATE TABLE IF NOT EXISTS sessions (
    id          TEXT PRIMARY KEY,
    title       TEXT NOT NULL DEFAULT 'New conversation',
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS turns (
    id          TEXT PRIMARY KEY,
    session_id  TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    role        TEXT NOT NULL,          -- 'user' | 'assistant' | 'system'
    content     TEXT NOT NULL,
    intent      TEXT,
    symbols     TEXT,                   -- JSON array
    timestamp   TEXT NOT NULL,
    CONSTRAINT role_check CHECK (role IN ('user','assistant','system'))
);
CREATE INDEX IF NOT EXISTS idx_turns_session ON turns(session_id, timestamp);

CREATE TABLE IF NOT EXISTS preferences (
    session_id  TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    key         TEXT NOT NULL,
    value       TEXT NOT NULL,          -- JSON-encoded
    updated_at  TEXT NOT NULL,
    PRIMARY KEY (session_id, key)
);

CREATE TABLE IF NOT EXISTS market_facts (
    session_id  TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    symbol      TEXT NOT NULL,
    fact        TEXT NOT NULL,          -- JSON-encoded
    stored_at   TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_facts_symbol ON market_facts(session_id, symbol);
"""


def get_db() -> aiosqlite.Connection:
    """
    Return an aiosqlite connection context manager.

    Usage:
        async with get_db() as db:
            await db.execute(...)

    aiosqlite.connect() returns a context manager directly — do NOT await it
    before using as a context manager.
    """
    conn = aiosqlite.connect(_DB_PATH)
    # Row factory must be set after the connection opens; we do it in init_db
    # and rely on callers setting it per-connection via the context manager.
    return conn


async def init_db() -> None:
    """Create tables if they don't exist. Called once at startup."""
    async with aiosqlite.connect(_DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        await db.executescript(_SCHEMA)
        await db.commit()
