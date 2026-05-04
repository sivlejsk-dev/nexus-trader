"""
SQLite database — persistent storage for all conversation memory.

Schema:
  sessions    — one row per chat session (id, title, created_at, updated_at)
  turns       — every conversation turn (session_id, role, content, metadata)
  preferences — per-session key/value store (watchlist, active symbol, etc.)
  market_facts — cached market knowledge per symbol
  prediction_events — adaptive options thesis journal with outcome scoring
  market_events — news/social/catalyst events with adaptive outcome scoring
  event_learning — learned weights by source/category/direction
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

CREATE TABLE IF NOT EXISTS prediction_events (
    id                   TEXT PRIMARY KEY,
    session_id           TEXT NOT NULL DEFAULT 'console',
    symbol               TEXT NOT NULL,
    created_at           TEXT NOT NULL,
    horizon_days         INTEGER NOT NULL,
    entry_price          REAL NOT NULL,
    predicted_direction  TEXT NOT NULL,
    confidence           REAL NOT NULL,
    target_price         REAL,
    stop_loss            REAL,
    feature_snapshot     TEXT NOT NULL,
    rationale            TEXT NOT NULL,
    outcome_status       TEXT NOT NULL DEFAULT 'pending',
    outcome_checked_at   TEXT,
    exit_price           REAL,
    pnl_pct              REAL,
    mistake_notes        TEXT,
    CONSTRAINT prediction_direction_check CHECK (predicted_direction IN ('call', 'put', 'neutral')),
    CONSTRAINT prediction_outcome_check CHECK (outcome_status IN ('pending', 'win', 'loss', 'flat'))
);
CREATE INDEX IF NOT EXISTS idx_predictions_symbol_time ON prediction_events(symbol, created_at);
CREATE INDEX IF NOT EXISTS idx_predictions_outcome ON prediction_events(symbol, outcome_status);

CREATE TABLE IF NOT EXISTS market_events (
    id                      TEXT PRIMARY KEY,
    source                  TEXT NOT NULL,
    source_event_id          TEXT NOT NULL,
    symbol                  TEXT NOT NULL,
    event_time              TEXT NOT NULL,
    title                   TEXT NOT NULL,
    summary                 TEXT,
    url                     TEXT,
    category                TEXT NOT NULL,
    direction               TEXT NOT NULL,
    sentiment_score         REAL NOT NULL DEFAULT 0,
    virality_score          REAL NOT NULL DEFAULT 0,
    source_credibility      REAL NOT NULL DEFAULT 0.5,
    impact_score            REAL NOT NULL DEFAULT 0,
    confidence              REAL NOT NULL DEFAULT 0,
    option_bias             TEXT NOT NULL DEFAULT 'neutral',
    horizon_days            INTEGER NOT NULL DEFAULT 7,
    entry_price             REAL,
    exit_price              REAL,
    underlying_move_pct     REAL,
    call_result             TEXT,
    put_result              TEXT,
    outcome_status          TEXT NOT NULL DEFAULT 'pending',
    outcome_checked_at      TEXT,
    raw_payload             TEXT NOT NULL DEFAULT '{}',
    created_at              TEXT NOT NULL,
    UNIQUE(source, source_event_id, symbol),
    CONSTRAINT event_direction_check CHECK (direction IN ('bullish', 'bearish', 'neutral', 'volatility')),
    CONSTRAINT event_option_bias_check CHECK (option_bias IN ('call', 'put', 'straddle', 'neutral')),
    CONSTRAINT event_outcome_check CHECK (outcome_status IN ('pending', 'scored'))
);
CREATE INDEX IF NOT EXISTS idx_market_events_symbol_time ON market_events(symbol, event_time);
CREATE INDEX IF NOT EXISTS idx_market_events_outcome ON market_events(symbol, outcome_status);
CREATE INDEX IF NOT EXISTS idx_market_events_class ON market_events(category, direction, source);

CREATE TABLE IF NOT EXISTS event_learning (
    learning_key             TEXT PRIMARY KEY,
    source                   TEXT NOT NULL,
    category                 TEXT NOT NULL,
    direction                TEXT NOT NULL,
    total                    INTEGER NOT NULL DEFAULT 0,
    call_wins                INTEGER NOT NULL DEFAULT 0,
    put_wins                 INTEGER NOT NULL DEFAULT 0,
    avg_underlying_move_pct  REAL NOT NULL DEFAULT 0,
    impact_weight            REAL NOT NULL DEFAULT 1,
    updated_at               TEXT NOT NULL
);
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
