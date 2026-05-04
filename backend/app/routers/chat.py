"""Chat router — Nexus AI conversation with persistent SQLite memory."""
from __future__ import annotations

import uuid
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.nexus_core.conversation import conversation_engine
from app.nexus_core.conversation import extract_symbols
from app.nexus_core.memory_store import (
    get_memory_store,
    list_sessions,
    delete_session,
    rename_session,
)
from app.nexus_core.reasoning import reasoning_engine
from app.services.market_data import market_data_service

router = APIRouter(prefix="/chat", tags=["chat"])


# ── Request / Response models ─────────────────────────────────────────────────

class ChatRequest(BaseModel):
    message: str
    session_id: Optional[str] = None
    symbol: Optional[str] = None
    include_reasoning: bool = False


class ChatResponse(BaseModel):
    response: str
    session_id: str
    intent: str
    symbols: List[str]
    active_symbol: Optional[str]
    reasoning: Optional[Dict[str, Any]] = None
    market_context: Optional[Dict[str, Any]] = None


class RenameRequest(BaseModel):
    title: str


# ── Chat ──────────────────────────────────────────────────────────────────────

@router.post("", response_model=ChatResponse)
async def chat(req: ChatRequest):
    session_id = req.session_id or str(uuid.uuid4())
    memory = get_memory_store(session_id)

    # Resolve symbol before context fetch so natural messages like
    # "Talk me through NVDA calls" get live market data on the first turn.
    extracted_symbols = extract_symbols(req.message)
    symbol = req.symbol or (extracted_symbols[0] if extracted_symbols else None) or await memory.get_active_symbol()

    # Fetch live market context
    market_ctx: Optional[Dict[str, Any]] = None
    if symbol:
        try:
            market_ctx = await market_data_service.get_full_market_context(symbol)
        except Exception:
            pass

    response_text, metadata = await conversation_engine.chat(
        req.message, memory, market_context=market_ctx
    )

    # Structured reasoning overlay
    reasoning_result = None
    if req.include_reasoning and market_ctx:
        technicals = market_ctx.get("technicals", {})
        if technicals:
            r = reasoning_engine.analyze_technicals({
                **technicals,
                "price": market_ctx.get("price"),
                "volume": market_ctx.get("volume"),
                "avg_volume": market_ctx.get("avg_volume"),
            })
            reasoning_result = r.to_dict()

    return ChatResponse(
        response=response_text,
        session_id=session_id,
        intent=metadata.get("intent", "general"),
        symbols=metadata.get("symbols", []),
        active_symbol=metadata.get("active_symbol"),
        reasoning=reasoning_result,
        market_context=market_ctx,
    )


# ── Session management ────────────────────────────────────────────────────────

@router.get("/sessions")
async def get_sessions():
    """List all past sessions ordered by most recently updated."""
    sessions = await list_sessions()
    return {"sessions": sessions, "count": len(sessions)}


@router.get("/sessions/{session_id}")
async def get_session(session_id: str):
    """Return full conversation history for a session."""
    memory = get_memory_store(session_id)
    turns = await memory.get_all_turns()
    prefs = await memory.get_all_preferences()
    stats = await memory.get_statistics()
    return {
        "session_id": session_id,
        "turns": turns,
        "preferences": prefs,
        "statistics": stats,
    }


@router.patch("/sessions/{session_id}")
async def update_session(session_id: str, req: RenameRequest):
    """Rename a session."""
    await rename_session(session_id, req.title)
    return {"session_id": session_id, "title": req.title}


@router.delete("/sessions/{session_id}")
async def remove_session(session_id: str):
    """Permanently delete a session and all its memory."""
    await delete_session(session_id)
    # Also evict from in-process cache
    from app.nexus_core.memory_store import _stores
    _stores.pop(session_id, None)
    return {"deleted": True, "session_id": session_id}


# ── History helpers (kept for backwards compat) ───────────────────────────────

@router.get("/history/{session_id}")
async def get_history(session_id: str, n: int = 100):
    memory = get_memory_store(session_id)
    return {"session_id": session_id, "turns": await memory.get_recent_turns(n)}


@router.delete("/history/{session_id}")
async def clear_history(session_id: str):
    memory = get_memory_store(session_id)
    await memory.clear_turns()
    return {"cleared": True, "session_id": session_id}
