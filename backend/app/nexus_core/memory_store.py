"""
Persistent Memory Store — SQLite-backed conversation memory.

Every session, turn, preference, and market fact is written to
nexus_memory.db so all conversations survive server restarts.
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

import aiosqlite
from app.db.database import get_db


# ── Session helpers ───────────────────────────────────────────────────────────

async def ensure_session(session_id: str, title: str = "New conversation") -> None:
    now = datetime.utcnow().isoformat()
    async with get_db() as db:
        db.row_factory = aiosqlite.Row
        await db.execute(
            """
            INSERT INTO sessions (id, title, created_at, updated_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(id) DO NOTHING
            """,
            (session_id, title, now, now),
        )
        await db.commit()


async def touch_session(session_id: str) -> None:
    now = datetime.utcnow().isoformat()
    async with get_db() as db:
        db.row_factory = aiosqlite.Row
        await db.execute(
            "UPDATE sessions SET updated_at = ? WHERE id = ?",
            (now, session_id),
        )
        await db.commit()


async def rename_session(session_id: str, title: str) -> None:
    async with get_db() as db:
        db.row_factory = aiosqlite.Row
        await db.execute(
            "UPDATE sessions SET title = ?, updated_at = ? WHERE id = ?",
            (title, datetime.utcnow().isoformat(), session_id),
        )
        await db.commit()


async def list_sessions() -> List[Dict[str, Any]]:
    """Return all sessions ordered by most recently updated."""
    async with get_db() as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            """
            SELECT s.id, s.title, s.created_at, s.updated_at,
                   COUNT(t.id) AS turn_count
            FROM sessions s
            LEFT JOIN turns t ON t.session_id = s.id
            GROUP BY s.id
            ORDER BY s.updated_at DESC
            """,
        )
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]


async def delete_session(session_id: str) -> None:
    async with get_db() as db:
        db.row_factory = aiosqlite.Row
        await db.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
        await db.commit()


# ── MemoryStore ───────────────────────────────────────────────────────────────

class MemoryStore:
    """Per-session memory backed by SQLite."""

    def __init__(self, session_id: str):
        self.session_id = session_id
        self.user_id = session_id
        self.total_stores = 0
        self.total_retrievals = 0
        self._session_ensured = False

    async def _ensure(self) -> None:
        if not self._session_ensured:
            await ensure_session(self.session_id)
            self._session_ensured = True

    # ── Episodic ──────────────────────────────────────────────

    async def add_turn(
        self,
        role: str,
        content: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        await self._ensure()
        item_id = str(uuid.uuid4())
        now = datetime.utcnow().isoformat()
        meta = metadata or {}
        async with get_db() as db:
            db.row_factory = aiosqlite.Row
            await db.execute(
                """
                INSERT INTO turns (id, session_id, role, content, intent, symbols, timestamp)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    item_id,
                    self.session_id,
                    role,
                    content,
                    meta.get("intent"),
                    json.dumps(meta.get("symbols", [])),
                    now,
                ),
            )
            if role == "user":
                cursor = await db.execute(
                    "SELECT COUNT(*) FROM turns WHERE session_id = ? AND role = 'user'",
                    (self.session_id,),
                )
                row = await cursor.fetchone()
                if row and row[0] == 1:
                    title = content[:60] + ("..." if len(content) > 60 else "")
                    await db.execute(
                        "UPDATE sessions SET title = ?, updated_at = ? WHERE id = ?",
                        (title, now, self.session_id),
                    )
                else:
                    await db.execute(
                        "UPDATE sessions SET updated_at = ? WHERE id = ?",
                        (now, self.session_id),
                    )
            await db.commit()
        self.total_stores += 1
        return item_id

    async def get_recent_turns(self, n: int = 50) -> List[Dict[str, Any]]:
        self.total_retrievals += 1
        async with get_db() as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                """
                SELECT id, role, content, intent, symbols, timestamp
                FROM turns
                WHERE session_id = ?
                ORDER BY timestamp ASC
                LIMIT ?
                """,
                (self.session_id, n),
            )
            rows = await cursor.fetchall()
        return [
            {
                "id": r["id"],
                "role": r["role"],
                "content": r["content"],
                "intent": r["intent"],
                "symbols": json.loads(r["symbols"] or "[]"),
                "timestamp": r["timestamp"],
            }
            for r in rows
        ]

    async def get_all_turns(self) -> List[Dict[str, Any]]:
        return await self.get_recent_turns(n=10_000)

    async def get_conversation_messages(self, n: int = 20) -> List[Dict[str, str]]:
        turns = await self.get_recent_turns(n)
        return [{"role": t["role"], "content": t["content"]} for t in turns]

    async def clear_turns(self) -> None:
        async with get_db() as db:
            db.row_factory = aiosqlite.Row
            await db.execute(
                "DELETE FROM turns WHERE session_id = ?", (self.session_id,)
            )
            await db.commit()

    # ── Preferences ───────────────────────────────────────────

    async def set_preference(self, key: str, value: Any) -> None:
        await self._ensure()
        now = datetime.utcnow().isoformat()
        async with get_db() as db:
            db.row_factory = aiosqlite.Row
            await db.execute(
                """
                INSERT INTO preferences (session_id, key, value, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(session_id, key) DO UPDATE
                SET value = excluded.value, updated_at = excluded.updated_at
                """,
                (self.session_id, key, json.dumps(value), now),
            )
            await db.commit()

    async def get_preference(self, key: str, default: Any = None) -> Any:
        async with get_db() as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                "SELECT value FROM preferences WHERE session_id = ? AND key = ?",
                (self.session_id, key),
            )
            row = await cursor.fetchone()
        if row is None:
            return default
        return json.loads(row["value"])

    async def get_all_preferences(self) -> Dict[str, Any]:
        async with get_db() as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                "SELECT key, value FROM preferences WHERE session_id = ?",
                (self.session_id,),
            )
            rows = await cursor.fetchall()
        return {r["key"]: json.loads(r["value"]) for r in rows}

    # ── Working memory shortcuts ──────────────────────────────

    async def set_active_symbol(self, symbol: str) -> None:
        await self.set_preference("active_symbol", symbol.upper())

    async def get_active_symbol(self) -> Optional[str]:
        return await self.get_preference("active_symbol")

    async def set_active_context(self, context: Dict[str, Any]) -> None:
        await self.set_preference("active_context", context)

    async def get_active_context(self) -> Dict[str, Any]:
        return await self.get_preference("active_context", {})

    # ── Semantic (market facts) ───────────────────────────────

    async def store_market_fact(self, symbol: str, fact: Dict[str, Any]) -> None:
        await self._ensure()
        now = datetime.utcnow().isoformat()
        async with get_db() as db:
            db.row_factory = aiosqlite.Row
            await db.execute(
                "INSERT INTO market_facts (session_id, symbol, fact, stored_at) VALUES (?, ?, ?, ?)",
                (self.session_id, symbol.upper(), json.dumps(fact), now),
            )
            await db.execute(
                """
                DELETE FROM market_facts
                WHERE session_id = ? AND symbol = ?
                  AND rowid NOT IN (
                      SELECT rowid FROM market_facts
                      WHERE session_id = ? AND symbol = ?
                      ORDER BY stored_at DESC LIMIT 50
                  )
                """,
                (self.session_id, symbol.upper(), self.session_id, symbol.upper()),
            )
            await db.commit()

    async def get_market_facts(self, symbol: str) -> List[Dict[str, Any]]:
        async with get_db() as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                """
                SELECT fact, stored_at FROM market_facts
                WHERE session_id = ? AND symbol = ?
                ORDER BY stored_at DESC LIMIT 50
                """,
                (self.session_id, symbol.upper()),
            )
            rows = await cursor.fetchall()
        return [{"stored_at": r["stored_at"], **json.loads(r["fact"])} for r in rows]

    # ── Stats ─────────────────────────────────────────────────

    async def get_statistics(self) -> Dict[str, Any]:
        async with get_db() as db:
            db.row_factory = aiosqlite.Row
            t_cur = await db.execute(
                "SELECT COUNT(*) FROM turns WHERE session_id = ?", (self.session_id,)
            )
            t_row = await t_cur.fetchone()
            p_cur = await db.execute(
                "SELECT COUNT(*) FROM preferences WHERE session_id = ?", (self.session_id,)
            )
            p_row = await p_cur.fetchone()
            f_cur = await db.execute(
                "SELECT COUNT(DISTINCT symbol) FROM market_facts WHERE session_id = ?",
                (self.session_id,),
            )
            f_row = await f_cur.fetchone()
        return {
            "session_id": self.session_id,
            "total_stores": self.total_stores,
            "total_retrievals": self.total_retrievals,
            "episodic_turns": t_row[0] if t_row else 0,
            "preferences": p_row[0] if p_row else 0,
            "semantic_symbols": f_row[0] if f_row else 0,
        }


# ── Store registry ────────────────────────────────────────────────────────────

_stores: Dict[str, MemoryStore] = {}


def get_memory_store(session_id: str) -> MemoryStore:
    if session_id not in _stores:
        _stores[session_id] = MemoryStore(session_id)
    return _stores[session_id]
