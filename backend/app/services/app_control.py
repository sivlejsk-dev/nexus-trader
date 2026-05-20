"""App control service.

Parses Nexus responses for embedded app-control commands, persists them,
and returns structured actions the frontend can execute. Commands that
involve trades or critical actions require explicit user confirmation.
"""
from __future__ import annotations

import json
import re
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

import aiosqlite

from app.db.database import get_db

# ── Command definitions ───────────────────────────────────────────────────────

# Commands Nexus can issue autonomously (no confirmation needed)
SAFE_COMMANDS = {
    "navigate",       # go to a page
    "analyze",        # run analysis on a symbol
    "simulate",       # run simulation
    "watchlist_add",  # add symbol to watchlist
    "watchlist_remove",
    "show_events",    # open events panel
    "show_analysis",  # open analysis page
}

# Commands that REQUIRE user confirmation before execution
CRITICAL_COMMANDS = {
    "trade_buy",
    "trade_sell",
    "trade_options",
    "clear_watchlist",
    "delete_session",
}

# ── Pattern matching for command extraction ───────────────────────────────────

# Nexus embeds commands as JSON blocks: [[NEXUS_CMD: {...}]]
CMD_PATTERN = re.compile(r'\[\[NEXUS_CMD:\s*(\{.*?\})\]\]', re.DOTALL)

# Natural language patterns → command inference
NAV_PATTERNS = [
    (re.compile(r'\b(go to|open|navigate to|show me|take me to)\s+(the\s+)?'
                r'(console|analysis|scanner|backtest|events|watchlist|chat|learn)\b', re.I),
     "navigate"),
    (re.compile(r'\b(run|start|do)\s+(an?\s+)?(analysis|simulation|backtest)\s+(on|for)?\s*([A-Z]{1,5})\b', re.I),
     "analyze"),
    (re.compile(r'\b(add|track|watch)\s+([A-Z]{1,5})\s+(to\s+)?(my\s+)?watchlist\b', re.I),
     "watchlist_add"),
    (re.compile(r'\b(simulate|replay|backtest)\s+([A-Z]{1,5})\b', re.I),
     "simulate"),
]

PAGE_MAP = {
    "console": "/console",
    "analysis": "/analysis",
    "scanner": "/scanner",
    "backtest": "/backtest",
    "events": "/events",
    "watchlist": "/watchlist",
    "chat": "/chat",
    "learn": "/learn",
}


def extract_commands_from_response(response: str) -> List[Dict[str, Any]]:
    """
    Extract structured commands from a Nexus response.
    Supports both explicit [[NEXUS_CMD:{...}]] blocks and natural language inference.
    """
    commands = []

    # Explicit embedded commands
    for match in CMD_PATTERN.finditer(response):
        try:
            cmd = json.loads(match.group(1))
            if "type" in cmd:
                cmd["_source"] = "explicit"
                commands.append(cmd)
        except json.JSONDecodeError:
            pass

    # Natural language inference (only if no explicit commands found)
    if not commands:
        for pattern, cmd_type in NAV_PATTERNS:
            m = pattern.search(response)
            if m:
                if cmd_type == "navigate":
                    page_word = m.group(3).lower()
                    path = PAGE_MAP.get(page_word)
                    if path:
                        commands.append({"type": "navigate", "path": path, "label": page_word, "_source": "inferred"})
                elif cmd_type in ("analyze", "simulate"):
                    groups = m.groups()
                    sym = groups[-1].upper() if groups else None
                    if sym:
                        commands.append({"type": cmd_type, "symbol": sym, "_source": "inferred"})
                elif cmd_type == "watchlist_add":
                    groups = m.groups()
                    sym = groups[1].upper() if len(groups) > 1 else None
                    if sym:
                        commands.append({"type": "watchlist_add", "symbol": sym, "_source": "inferred"})
                break  # one inferred command per response

    return commands


def classify_commands(commands: List[Dict[str, Any]]) -> Tuple[List[Dict], List[Dict]]:
    """Split commands into safe (auto-execute) and critical (need confirmation)."""
    safe, critical = [], []
    for cmd in commands:
        if cmd.get("type") in CRITICAL_COMMANDS:
            critical.append(cmd)
        else:
            safe.append(cmd)
    return safe, critical


async def log_command(
    session_id: str,
    command: Dict[str, Any],
    requires_confirm: bool,
) -> str:
    """Persist a command to app_commands table. Returns command id."""
    cmd_id = str(uuid.uuid4())
    now = datetime.utcnow().isoformat()
    async with get_db() as db:
        await db.execute(
            """
            INSERT INTO app_commands
                (id, session_id, command_type, payload, requires_confirm, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (cmd_id, session_id, command.get("type", "unknown"),
             json.dumps(command), 1 if requires_confirm else 0, now),
        )
        await db.commit()
    return cmd_id


async def confirm_command(cmd_id: str, confirmed: bool) -> bool:
    """Mark a command as confirmed or rejected."""
    now = datetime.utcnow().isoformat()
    async with get_db() as db:
        await db.execute(
            """
            UPDATE app_commands
            SET confirmed = ?, executed_at = ?
            WHERE id = ?
            """,
            (1 if confirmed else 0, now if confirmed else None, cmd_id),
        )
        await db.commit()
    return confirmed


async def get_pending_commands(session_id: str) -> List[Dict[str, Any]]:
    """Return commands awaiting confirmation for a session."""
    async with get_db() as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            """
            SELECT id, command_type, payload, created_at
            FROM app_commands
            WHERE session_id = ? AND requires_confirm = 1 AND confirmed IS NULL
            ORDER BY created_at DESC
            LIMIT 10
            """,
            (session_id,),
        )
        rows = await cursor.fetchall()
    return [
        {
            "id": r["id"],
            "type": r["command_type"],
            "payload": json.loads(r["payload"]),
            "created_at": r["created_at"],
        }
        for r in rows
    ]


async def get_command_history(session_id: str, limit: int = 20) -> List[Dict[str, Any]]:
    """Return recent command history for a session."""
    async with get_db() as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            """
            SELECT id, command_type, payload, requires_confirm, confirmed, executed_at, created_at
            FROM app_commands
            WHERE session_id = ?
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (session_id, limit),
        )
        rows = await cursor.fetchall()
    return [
        {
            "id": r["id"],
            "type": r["command_type"],
            "payload": json.loads(r["payload"]),
            "requires_confirm": bool(r["requires_confirm"]),
            "confirmed": r["confirmed"],
            "executed_at": r["executed_at"],
            "created_at": r["created_at"],
        }
        for r in rows
    ]


app_control_service = type(
    "_Svc", (),
    {
        "extract": staticmethod(extract_commands_from_response),
        "classify": staticmethod(classify_commands),
        "log": staticmethod(log_command),
        "confirm": staticmethod(confirm_command),
        "pending": staticmethod(get_pending_commands),
        "history": staticmethod(get_command_history),
    }
)()
