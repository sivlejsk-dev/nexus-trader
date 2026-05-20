"""Session learning service.

After each conversation turn, extracts structured insights from the exchange
and persists them to session_insights. These feed back into the system prompt
so Nexus remembers user preferences, risk tolerance, and strategy observations
across the session — and across sessions for the same symbol.
"""
from __future__ import annotations

import json
import re
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

import aiosqlite

from app.db.database import get_db

# ── Insight extraction patterns ───────────────────────────────────────────────

# (pattern, insight_type, template)
INSIGHT_PATTERNS = [
    # Risk tolerance
    (re.compile(r"\b(i('m| am) (very |quite )?(risk[- ]averse|conservative|cautious))\b", re.I),
     "risk_tolerance", "User is risk-averse / conservative."),
    (re.compile(r"\b(i('m| am) (ok|okay|fine|comfortable) with (high |more )?risk)\b", re.I),
     "risk_tolerance", "User is comfortable with higher risk."),
    (re.compile(r"\b(i (prefer|like|want) (small|tight|close) stops)\b", re.I),
     "risk_tolerance", "User prefers tight stop losses."),

    # Time horizon
    (re.compile(r"\b(i (trade|prefer|like) (0dte|same.?day|intraday|day trad)\w*)\b", re.I),
     "preference", "User prefers intraday / 0DTE options."),
    (re.compile(r"\b(i (trade|prefer|like|hold) (weekly|weeklies|1.?week)\w*)\b", re.I),
     "preference", "User prefers weekly options."),
    (re.compile(r"\b(i (trade|prefer|like|hold) (monthly|monthlies|leaps?|long.?dated)\w*)\b", re.I),
     "preference", "User prefers monthly or LEAPS options."),

    # Strategy preference
    (re.compile(r"\b(i (prefer|like|use|trade) (covered calls?|cash.?secured puts?|wheel)\w*)\b", re.I),
     "strategy", "User prefers income strategies (covered calls / wheel)."),
    (re.compile(r"\b(i (prefer|like|use|trade) (spreads?|debit spread|credit spread)\w*)\b", re.I),
     "strategy", "User prefers defined-risk spreads."),
    (re.compile(r"\b(i (prefer|like|use|trade) (naked|uncovered|directional)\w*)\b", re.I),
     "strategy", "User prefers directional / naked options."),
    (re.compile(r"\b(i (prefer|like|use|trade) (straddle|strangle|vol)\w*)\b", re.I),
     "strategy", "User prefers volatility plays (straddles / strangles)."),

    # Symbol interest
    (re.compile(r"\b(i (follow|watch|trade|like|focus on|specialize in))\s+([A-Z]{2,5})\b"),
     "preference", None),  # dynamic: symbol extracted from match

    # Observations about market
    (re.compile(r"\b(i (think|believe|feel|notice|see) (the market|stocks?|options?|price)\b.{10,80})", re.I),
     "observation", None),  # dynamic: content from match
]


def _extract_insights_from_text(
    text: str,
    symbol: Optional[str],
    role: str = "user",
) -> List[Dict[str, Any]]:
    """Extract structured insights from a single message."""
    insights = []
    seen = set()

    for pattern, insight_type, template in INSIGHT_PATTERNS:
        m = pattern.search(text)
        if not m:
            continue

        if template:
            content = template
        elif insight_type == "preference" and len(m.groups()) >= 3:
            sym = m.group(3).upper()
            content = f"User is interested in {sym}."
        elif insight_type == "observation":
            content = f"User observation: {m.group(1)[:120]}"
        else:
            content = m.group(0)[:120]

        key = (insight_type, content[:60])
        if key in seen:
            continue
        seen.add(key)

        insights.append({
            "insight_type": insight_type,
            "content": content,
            "symbol": symbol,
            "confidence": 0.75,
        })

    return insights


class SessionLearningService:

    async def extract_and_store(
        self,
        session_id: str,
        user_message: str,
        assistant_response: str,
        symbol: Optional[str],
        intent: str,
    ) -> List[Dict[str, Any]]:
        """Extract insights from a turn and persist new ones."""
        candidates = _extract_insights_from_text(user_message, symbol, role="user")

        # Also mine assistant response for confirmed observations
        if "win rate" in assistant_response.lower() or "confidence" in assistant_response.lower():
            candidates.append({
                "insight_type": "observation",
                "content": f"Nexus discussed prediction accuracy for {symbol or 'a symbol'} in this session.",
                "symbol": symbol,
                "confidence": 0.6,
            })

        stored = []
        for ins in candidates:
            if await self._is_new(session_id, ins):
                ins_id = await self._store(session_id, ins)
                stored.append({"id": ins_id, **ins})

        return stored

    async def _is_new(self, session_id: str, insight: Dict[str, Any]) -> bool:
        """Avoid storing duplicate insights in the same session."""
        async with get_db() as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                """
                SELECT id FROM session_insights
                WHERE session_id = ? AND insight_type = ?
                  AND content = ?
                LIMIT 1
                """,
                (session_id, insight["insight_type"], insight["content"]),
            )
            row = await cursor.fetchone()
        return row is None

    async def _store(self, session_id: str, insight: Dict[str, Any]) -> str:
        ins_id = str(uuid.uuid4())
        now = datetime.utcnow().isoformat()
        async with get_db() as db:
            await db.execute(
                """
                INSERT INTO session_insights
                    (id, session_id, symbol, insight_type, content, confidence, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (ins_id, session_id, insight.get("symbol"),
                 insight["insight_type"], insight["content"],
                 insight.get("confidence", 0.7), now),
            )
            await db.commit()
        return ins_id

    async def get_insights(
        self,
        session_id: str,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        async with get_db() as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                """
                SELECT id, symbol, insight_type, content, confidence, created_at
                FROM session_insights
                WHERE session_id = ?
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (session_id, limit),
            )
            rows = await cursor.fetchall()
        return [dict(r) for r in rows]

    async def get_insights_for_symbol(self, symbol: str, limit: int = 20) -> List[Dict[str, Any]]:
        """Cross-session insights for a symbol."""
        async with get_db() as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                """
                SELECT id, session_id, insight_type, content, confidence, created_at
                FROM session_insights
                WHERE symbol = ?
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (symbol.upper(), limit),
            )
            rows = await cursor.fetchall()
        return [dict(r) for r in rows]

    async def get_session_summary(self, session_id: str) -> Dict[str, Any]:
        """Summarise what Nexus has learned about this user in this session."""
        insights = await self.get_insights(session_id)
        by_type: Dict[str, List[str]] = {}
        for ins in insights:
            t = ins["insight_type"]
            by_type.setdefault(t, []).append(ins["content"])

        return {
            "total_insights": len(insights),
            "by_type": {k: v[:5] for k, v in by_type.items()},
            "risk_profile": by_type.get("risk_tolerance", [None])[0],
            "preferred_strategies": by_type.get("strategy", []),
            "preferences": by_type.get("preference", []),
        }

    async def build_system_prompt_addon(self, session_id: str) -> str:
        """Return a compact string to inject into the system prompt."""
        summary = await self.get_session_summary(session_id)
        if summary["total_insights"] == 0:
            return ""

        lines = ["## What Nexus has learned about this user"]
        if summary["risk_profile"]:
            lines.append(f"- Risk profile: {summary['risk_profile']}")
        for s in summary["preferred_strategies"]:
            lines.append(f"- Strategy preference: {s}")
        for p in summary["preferences"][:3]:
            lines.append(f"- Preference: {p}")
        return "\n".join(lines)


session_learning_service = SessionLearningService()
