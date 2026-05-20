"""Research memory service.

Persists findings Nexus discovers during research sessions so they survive
across conversations. Findings are surfaced in the system prompt when
relevant to the current symbol or topic.
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

import aiosqlite

from app.db.database import get_db


class ResearchMemoryService:

    async def store_finding(
        self,
        content: str,
        category: str,
        session_id: str = "console",
        symbol: Optional[str] = None,
        source_url: Optional[str] = None,
        confidence: float = 0.8,
    ) -> str:
        finding_id = str(uuid.uuid4())
        now = datetime.utcnow().isoformat()
        async with get_db() as db:
            await db.execute(
                """
                INSERT INTO research_findings
                    (id, session_id, symbol, category, content,
                     source_url, confidence, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (finding_id, session_id, symbol.upper() if symbol else None,
                 category, content, source_url, confidence, now),
            )
            await db.commit()
        return finding_id

    async def get_findings(
        self,
        symbol: Optional[str] = None,
        category: Optional[str] = None,
        limit: int = 20,
    ) -> List[Dict[str, Any]]:
        async with get_db() as db:
            db.row_factory = aiosqlite.Row
            if symbol:
                cursor = await db.execute(
                    """
                    SELECT * FROM research_findings
                    WHERE symbol = ? OR symbol IS NULL
                    ORDER BY created_at DESC LIMIT ?
                    """,
                    (symbol.upper(), limit),
                )
            else:
                cursor = await db.execute(
                    "SELECT * FROM research_findings ORDER BY created_at DESC LIMIT ?",
                    (limit,),
                )
            rows = await cursor.fetchall()
        return [dict(r) for r in rows]

    async def build_context_for_prompt(
        self,
        symbol: Optional[str] = None,
        max_findings: int = 5,
    ) -> str:
        """Return a compact string of relevant findings for system prompt injection."""
        findings = await self.get_findings(symbol=symbol, limit=max_findings)
        if not findings:
            return ""
        lines = ["\n## Nexus Research Memory"]
        for f in findings:
            sym_tag = f" [{f['symbol']}]" if f.get("symbol") else ""
            lines.append(f"- [{f['category']}{sym_tag}] {f['content'][:200]}")
        return "\n".join(lines)

    async def get_recent_research_sessions(self, limit: int = 5) -> List[Dict[str, Any]]:
        async with get_db() as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                """
                SELECT session_id, COUNT(*) as findings, MAX(created_at) as last_at
                FROM research_findings
                GROUP BY session_id
                ORDER BY last_at DESC LIMIT ?
                """,
                (limit,),
            )
            rows = await cursor.fetchall()
        return [dict(r) for r in rows]


research_memory_service = ResearchMemoryService()
