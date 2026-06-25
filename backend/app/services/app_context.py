"""Session-level context awareness for Nexus chat."""
from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

import aiosqlite

from app.db.database import get_db


class AppContextService:
    """Build a compact summary of what the user has recently done in Nexus."""

    async def build(
        self,
        session_id: str,
        active_symbol: Optional[str] = None,
        market_context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        recent_turns, recent_commands, preferences = await _load_context_rows(session_id)
        watchlist = preferences.get("watchlist", [])
        symbol = active_symbol or preferences.get("active_symbol")
        recent_symbols = _recent_symbols(recent_turns, recent_commands, symbol)

        market_snapshot = None
        if market_context:
            quote = market_context.get("quote") or {}
            decision = market_context.get("decision") or {}
            event_composite = ((market_context.get("event_intelligence") or {}).get("composite") or {})
            market_snapshot = {
                "symbol": market_context.get("symbol") or symbol,
                "price": quote.get("price"),
                "change_pct": quote.get("change_pct"),
                "decision": {
                    "action": decision.get("action"),
                    "direction": decision.get("direction"),
                    "confidence_pct": decision.get("confidence_pct"),
                    "risk": decision.get("risk"),
                } if decision else None,
                "event_bias": event_composite.get("bias"),
                "event_confidence": event_composite.get("confidence"),
            }

        return {
            "session_id": session_id,
            "active_symbol": symbol,
            "recent_symbols": recent_symbols[:8],
            "watchlist": watchlist[:20] if isinstance(watchlist, list) else [],
            "recent_turns": recent_turns[-6:],
            "recent_actions": recent_commands[:8],
            "market_snapshot": market_snapshot,
            "summary": _summary(symbol, recent_symbols, recent_commands, watchlist, market_snapshot),
        }

    def to_prompt_block(self, context: Dict[str, Any]) -> str:
        if not context:
            return ""
        lines = ["## App/User Context"]
        summary = context.get("summary")
        if summary:
            lines.append(f"- Summary: {summary}")
        if context.get("active_symbol"):
            lines.append(f"- Active symbol: {context['active_symbol']}")
        if context.get("recent_symbols"):
            lines.append(f"- Recently discussed symbols: {', '.join(context['recent_symbols'][:6])}")
        if context.get("watchlist"):
            lines.append(f"- Watchlist: {', '.join(context['watchlist'][:8])}")
        actions = context.get("recent_actions") or []
        if actions:
            lines.append("- Recent app actions:")
            for action in actions[:5]:
                label = action.get("label") or action.get("type")
                symbol = action.get("symbol")
                suffix = f" {symbol}" if symbol else ""
                lines.append(f"  - {label}{suffix}")
        market = context.get("market_snapshot") or {}
        decision = market.get("decision") or {}
        if decision:
            lines.append(
                "- Current Nexus decision: "
                f"{decision.get('action')} / {decision.get('direction')} "
                f"at {decision.get('confidence_pct')}% confidence; risk: {decision.get('risk')}"
            )
        lines.append(
            "Use this context to avoid asking the user to repeat recent symbols, app actions, or preferences."
        )
        return "\n".join(lines)


async def _load_context_rows(session_id: str) -> tuple[List[Dict[str, Any]], List[Dict[str, Any]], Dict[str, Any]]:
    async with get_db() as db:
        db.row_factory = aiosqlite.Row
        turn_cursor = await db.execute(
            """
            SELECT role, content, intent, symbols, timestamp
            FROM turns
            WHERE session_id = ?
            ORDER BY timestamp DESC
            LIMIT 12
            """,
            (session_id,),
        )
        command_cursor = await db.execute(
            """
            SELECT command_type, payload, created_at
            FROM app_commands
            WHERE session_id = ?
            ORDER BY created_at DESC
            LIMIT 12
            """,
            (session_id,),
        )
        pref_cursor = await db.execute(
            "SELECT key, value FROM preferences WHERE session_id = ?",
            (session_id,),
        )
        turns = await turn_cursor.fetchall()
        commands = await command_cursor.fetchall()
        prefs = await pref_cursor.fetchall()

    recent_turns = [
        {
            "role": row["role"],
            "content": row["content"][:240],
            "intent": row["intent"],
            "symbols": json.loads(row["symbols"] or "[]"),
            "timestamp": row["timestamp"],
        }
        for row in reversed(turns)
    ]
    recent_commands = []
    for row in commands:
        payload = json.loads(row["payload"] or "{}")
        recent_commands.append({
            "type": row["command_type"],
            "created_at": row["created_at"],
            **payload,
        })
    preferences = {row["key"]: json.loads(row["value"]) for row in prefs}
    return recent_turns, recent_commands, preferences


def _recent_symbols(
    turns: List[Dict[str, Any]],
    commands: List[Dict[str, Any]],
    active_symbol: Optional[str],
) -> List[str]:
    seen: List[str] = []
    for symbol in [active_symbol]:
        if symbol and symbol not in seen:
            seen.append(symbol)
    for command in commands:
        symbol = command.get("symbol")
        if symbol and symbol not in seen:
            seen.append(symbol)
    for turn in reversed(turns):
        for symbol in turn.get("symbols") or []:
            if symbol and symbol not in seen:
                seen.append(symbol)
    return seen


def _summary(
    active_symbol: Optional[str],
    recent_symbols: List[str],
    recent_commands: List[Dict[str, Any]],
    watchlist: Any,
    market_snapshot: Optional[Dict[str, Any]],
) -> str:
    parts = []
    if active_symbol:
        parts.append(f"user is currently focused on {active_symbol}")
    elif recent_symbols:
        parts.append(f"recent symbols include {', '.join(recent_symbols[:3])}")
    if recent_commands:
        parts.append(f"last app action was {recent_commands[0].get('type')}")
    if isinstance(watchlist, list) and watchlist:
        parts.append(f"watchlist has {len(watchlist)} symbols")
    decision = ((market_snapshot or {}).get("decision") or {})
    if decision.get("action"):
        parts.append(
            f"latest decision is {decision.get('action')} {decision.get('direction')} "
            f"at {decision.get('confidence_pct')}%"
        )
    return "; ".join(parts) if parts else "no prior app context yet"


app_context_service = AppContextService()
