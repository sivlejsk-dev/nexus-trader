"""Chat router — Nexus AI conversation with persistent SQLite memory."""
from __future__ import annotations

import uuid
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.nexus_core.conversation import conversation_engine
from app.nexus_core.conversation import extract_symbols, classify_intent
from app.nexus_core.memory_store import (
    get_memory_store,
    list_sessions,
    delete_session,
    rename_session,
)
from app.nexus_core.reasoning import reasoning_engine
from app.services.market_data import market_data_service
from app.services.app_control import app_control_service
from app.services.session_learning import session_learning_service
from app.services.symbol_resolver import resolve_symbol

router = APIRouter(prefix="/chat", tags=["chat"])


# ── Request / Response models ─────────────────────────────────────────────────

class ChatRequest(BaseModel):
    message: str
    session_id: Optional[str] = None
    symbol: Optional[str] = None
    include_reasoning: bool = False
    voice_mode: bool = False


class ChatResponse(BaseModel):
    response: str
    session_id: str
    intent: str
    symbols: List[str]
    active_symbol: Optional[str]
    reasoning: Optional[Dict[str, Any]] = None
    market_context: Optional[Dict[str, Any]] = None
    triggered_actions: Optional[List[str]] = None
    simulation: Optional[Dict[str, Any]] = None
    what_if: Optional[Dict[str, Any]] = None
    tutorial: Optional[Dict[str, Any]] = None
    app_context: Optional[Dict[str, Any]] = None
    prediction_history: Optional[Dict[str, Any]] = None
    # App control
    app_commands: Optional[List[Dict[str, Any]]] = None        # safe, auto-execute
    pending_confirmations: Optional[List[Dict[str, Any]]] = None  # need user confirm
    # Voice reasoning
    voice_reasoning: Optional[str] = None  # spoken summary of prediction rationale
    # Session insights extracted this turn
    new_insights: Optional[List[Dict[str, Any]]] = None
    # Tool calls made during this response (for research panel)
    tool_log: Optional[List[Dict[str, Any]]] = None


class ConfirmCommandRequest(BaseModel):
    confirmed: bool


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
    if symbol:
        symbol = resolve_symbol(symbol, context=req.message)["symbol"]

    # Fetch live market context
    market_ctx: Optional[Dict[str, Any]] = None
    if symbol:
        try:
            market_ctx = await market_data_service.get_full_analysis(symbol, session_id=session_id)
        except Exception:
            pass

    response_text, metadata = await conversation_engine.chat(
        req.message, memory, market_context=market_ctx, voice_mode=req.voice_mode
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

    # ── App control: extract commands from response ──
    # Only trust explicit commands embedded by Nexus. Natural-language inference
    # on the assistant response can misread examples like "simulate ASML" as an
    # instruction. Deterministic user-intent commands are added below.
    all_cmds = [cmd for cmd in app_control_service.extract(response_text) if cmd.get("_source") == "explicit"]
    safe_cmds, critical_cmds = app_control_service.classify(all_cmds)
    intent = metadata.get("intent") or classify_intent(req.message)
    if symbol and not safe_cmds:
        if intent in {"stock_analysis", "predict", "options_analysis", "best_option"}:
            safe_cmds.append({"type": "analyze", "symbol": symbol, "label": f"Analyze {symbol}"})
        elif intent == "simulate":
            safe_cmds.append({"type": "simulate", "symbol": symbol, "years": 5, "label": f"Simulate {symbol}"})
        elif intent == "event_analysis":
            safe_cmds.append({"type": "navigate", "path": f"/events?symbol={symbol}", "label": f"Events for {symbol}"})
        elif intent == "watchlist" and "add" in req.message.lower():
            safe_cmds.append({"type": "watchlist_add", "symbol": symbol, "label": f"Track {symbol}"})
    tutorial_meta = metadata.get("tutorial") or {}
    if tutorial_meta.get("app_command"):
        tutorial_cmd = tutorial_meta["app_command"]
        if tutorial_cmd not in safe_cmds:
            safe_cmds.append(tutorial_cmd)

    # Log all commands; critical ones await confirmation
    for cmd in safe_cmds:
        await app_control_service.log(session_id, cmd, requires_confirm=False)
    pending_confirms = []
    for cmd in critical_cmds:
        cmd_id = await app_control_service.log(session_id, cmd, requires_confirm=True)
        pending_confirms.append({"id": cmd_id, **cmd})

    # ── Session learning: extract insights from this turn ──
    new_insights = await session_learning_service.extract_and_store(
        session_id=session_id,
        user_message=req.message,
        assistant_response=response_text,
        symbol=symbol,
        intent=intent,
    )

    # ── Voice reasoning: always build a spoken summary when there's structured data ──
    voice_reasoning = None
    if market_ctx and market_ctx.get("decision"):
        voice_reasoning = _build_decision_voice(market_ctx["decision"])
    if metadata.get("tutorial"):
        voice_reasoning = metadata["tutorial"].get("voice_reasoning") or voice_reasoning
    elif metadata.get("what_if"):
        voice_reasoning = _build_what_if_voice(metadata["what_if"])
    elif metadata.get("prediction_history"):
        pred = metadata["prediction_history"]
        voice_reasoning = _build_voice_reasoning(pred, symbol)
    elif metadata.get("simulation"):
        sim = metadata["simulation"]
        voice_reasoning = _build_simulation_voice(sim)
    else:
        # Strip markdown from the response so TTS reads it cleanly
        import re
        clean = re.sub(r'\[\[NEXUS_CMD:[^\]]*\]\]', '', response_text)
        clean = re.sub(r'```[\s\S]*?```', '', clean)
        clean = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', clean)
        clean = re.sub(r'[*_`#>]', '', clean)
        clean = re.sub(r'\s+', ' ', clean).strip()
        voice_reasoning = clean

    return ChatResponse(
        response=response_text,
        session_id=session_id,
        intent=metadata.get("intent", "general"),
        symbols=metadata.get("symbols", []),
        active_symbol=metadata.get("active_symbol"),
        reasoning=reasoning_result,
        market_context=market_ctx,
        triggered_actions=metadata.get("triggered_actions", []),
        simulation=metadata.get("simulation"),
        what_if=metadata.get("what_if"),
        tutorial=metadata.get("tutorial"),
        app_context=metadata.get("app_context"),
        prediction_history=metadata.get("prediction_history"),
        app_commands=safe_cmds if safe_cmds else None,
        pending_confirmations=pending_confirms if pending_confirms else None,
        voice_reasoning=voice_reasoning,
        new_insights=new_insights if new_insights else None,
        tool_log=metadata.get("tool_log") or None,
    )


def _build_what_if_voice(result: Dict[str, Any]) -> str:
    symbol = result.get("symbol", "this symbol")
    summary = result.get("summary") or f"I ran the what-if for {symbol}."
    rr = result.get("risk_reward")
    next_step = result.get("next_step", "")
    risk_reward = f"Risk reward is {rr}." if rr is not None else "Risk reward is not available."
    return f"{summary} {risk_reward} {next_step} This is informational only, not financial advice."


def _build_decision_voice(decision: Dict[str, Any]) -> str:
    """Build a concise spoken summary of the one-shot Nexus decision."""
    symbol = decision.get("symbol") or "this symbol"
    action = decision.get("action", "wait")
    direction = decision.get("direction", "neutral")
    confidence = decision.get("confidence_pct", 0)
    reason = decision.get("reason", "")
    next_step = decision.get("best_next_step", "")
    risk = decision.get("risk", "")
    parts = [
        f"Nexus says {action} on {symbol}, with a {direction} bias and {confidence} percent confidence.",
    ]
    if reason:
        parts.append(reason)
    if next_step:
        parts.append(next_step)
    if risk:
        parts.append(f"Main risk: {risk}")
    parts.append("This is informational only, not financial advice.")
    return " ".join(parts)


def _build_simulation_voice(sim: Dict[str, Any]) -> str:
    """Build a concise spoken summary of a simulation result."""
    symbol = sim.get("symbol", "this symbol")
    wr = sim.get("win_rate")
    total = sim.get("total_predictions", 0)
    avg_pnl = sim.get("avg_pnl_pct")
    horizon = sim.get("horizon_days", 20)
    by_dir = sim.get("by_direction", {})
    call_wr = (by_dir.get("call") or {}).get("win_rate")
    put_wr = (by_dir.get("put") or {}).get("win_rate")
    regime_stats = sim.get("regime_stats", {})

    parts = []
    parts.append(f"I ran a historical simulation on {symbol} over {total} prediction windows using a {horizon}-day horizon.")

    if wr is not None:
        tone = "strong" if wr >= 60 else "decent" if wr >= 52 else "below average"
        parts.append(f"The overall win rate was {wr} percent, which is {tone}.")

    if call_wr is not None and put_wr is not None:
        better = "calls" if call_wr >= put_wr else "puts"
        parts.append(f"Calls hit {call_wr} percent and puts hit {put_wr} percent, so {better} performed better historically.")

    if avg_pnl is not None:
        direction_word = "positive" if avg_pnl >= 0 else "negative"
        parts.append(f"The average P and L per trade was {avg_pnl:+.1f} percent, which is {direction_word}.")

    # Best regime
    if regime_stats:
        best_regime = max(regime_stats.items(), key=lambda x: x[1].get("win_rate", 0), default=None)
        if best_regime:
            rname = best_regime[0].replace("_", " ")
            rwr = best_regime[1].get("win_rate", 0)
            parts.append(f"The model performed best in {rname} markets with a {rwr} percent win rate.")

    parts.append("Keep in mind this is a backtest and past results do not guarantee future performance.")
    return " ".join(parts)


def _build_voice_reasoning(pred_data: Dict[str, Any], symbol: Optional[str]) -> str:
    """Build a concise spoken summary of the current prediction rationale."""
    pred = pred_data.get("prediction", {})
    direction = pred.get("direction", "neutral")
    confidence = pred.get("confidence", 0)
    rationale = pred.get("rationale", [])
    review = pred_data.get("review", {})
    wr = review.get("win_rate")

    parts = []
    sym = symbol or pred_data.get("symbol", "this symbol")
    dir_word = {"call": "bullish", "put": "bearish", "neutral": "neutral"}.get(direction, direction)
    conf_pct = int(confidence * 100)
    parts.append(f"My current thesis on {sym} is {dir_word}, with {conf_pct} percent confidence.")

    if rationale:
        parts.append("The key signals are: " + ". ".join(rationale[:3]) + ".")

    # Target and stop
    target = pred.get("target_price")
    stop = pred.get("stop_loss")
    entry = pred.get("entry_price")
    if target and entry:
        parts.append(f"My target is {target:.2f} from the current price of {entry:.2f}.")
    if stop:
        parts.append(f"I would stop out below {stop:.2f}.")

    if wr is not None:
        tone = "solid" if wr >= 60 else "moderate" if wr >= 50 else "below average"
        parts.append(f"My recent track record on {sym} is {wr} percent win rate, which is {tone}.")

    # Streak
    streak = review.get("current_streak", {})
    if streak and streak.get("length", 0) >= 3:
        stype = streak.get("type", "")
        slen = streak.get("length", 0)
        sdir = streak.get("direction", "")
        if stype == "win":
            parts.append(f"I am on a {slen}-prediction win streak on {sdir}s, so momentum is in my favor.")
        elif stype == "loss":
            parts.append(f"I am on a {slen}-prediction loss streak on {sdir}s, so treat this with extra caution.")

    adj = pred.get("learning_adjustment", {})
    combined = adj.get("combined_factor", adj.get("factor", 1.0))
    if combined > 1.05:
        parts.append("My learning system has boosted confidence based on recent performance.")
    elif combined < 0.95:
        parts.append("My learning system has reduced confidence due to recent underperformance.")

    parts.append("This is not financial advice. Always manage your risk.")
    return " ".join(parts)


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


# ── App control ───────────────────────────────────────────────────────────────

@router.post("/commands/{cmd_id}/confirm")
async def confirm_command(cmd_id: str, req: ConfirmCommandRequest):
    """Confirm or reject a pending critical command."""
    result = await app_control_service.confirm(cmd_id, req.confirmed)
    return {"cmd_id": cmd_id, "confirmed": result}


@router.get("/commands/{session_id}/pending")
async def get_pending_commands(session_id: str):
    """Return commands awaiting user confirmation for a session."""
    return {"commands": await app_control_service.pending(session_id)}


@router.get("/commands/{session_id}/history")
async def get_command_history(session_id: str):
    """Return recent command history for a session."""
    return {"commands": await app_control_service.history(session_id)}


@router.get("/context/{session_id}")
async def get_app_context(session_id: str):
    """Return the compact app/user context Nexus uses for contextual guidance."""
    from app.services.app_context import app_context_service
    memory = get_memory_store(session_id)
    active_symbol = await memory.get_active_symbol()
    return await app_context_service.build(session_id, active_symbol)


# ── Session insights ──────────────────────────────────────────────────────────

@router.get("/insights/{session_id}")
async def get_session_insights(session_id: str):
    """Return distilled insights learned from a session's conversations."""
    from app.services.session_learning import session_learning_service as sls
    insights = await sls.get_insights(session_id)
    summary = await sls.get_session_summary(session_id)
    return {"session_id": session_id, "insights": insights, "summary": summary}


# ── Cross-session memory summary ──────────────────────────────────────────────

@router.get("/memory/summary")
async def memory_summary():
    """
    Return a cross-session summary: most-discussed symbols, recent scenarios,
    and prediction outcomes across all sessions. Used by Nexus to recall context.
    """
    from app.db.database import get_db
    import aiosqlite as _aiosqlite

    async with get_db() as db:
        db.row_factory = _aiosqlite.Row

        # Most mentioned symbols across all turns
        cursor = await db.execute("""
            SELECT symbols, COUNT(*) as cnt
            FROM turns
            WHERE symbols IS NOT NULL AND symbols != '[]'
            GROUP BY symbols
            ORDER BY cnt DESC
            LIMIT 20
        """)
        symbol_rows = await cursor.fetchall()

        # Recent simulation-like queries
        cursor2 = await db.execute("""
            SELECT content, timestamp, session_id
            FROM turns
            WHERE role = 'user'
              AND (content LIKE '%simulat%' OR content LIKE '%backtest%'
                   OR content LIKE '%from 19%' OR content LIKE '%from 20%'
                   OR content LIKE '%years ago%')
            ORDER BY timestamp DESC
            LIMIT 10
        """)
        scenario_rows = await cursor2.fetchall()

        # Prediction outcomes
        cursor3 = await db.execute("""
            SELECT symbol, predicted_direction, outcome_status, pnl_pct, created_at
            FROM prediction_events
            ORDER BY created_at DESC
            LIMIT 20
        """)
        pred_rows = await cursor3.fetchall()

    import json as _json

    # Aggregate symbols
    symbol_counts: dict = {}
    for row in symbol_rows:
        try:
            syms = _json.loads(row["symbols"])
            for s in syms:
                symbol_counts[s] = symbol_counts.get(s, 0) + row["cnt"]
        except Exception:
            pass

    top_symbols = sorted(symbol_counts.items(), key=lambda x: x[1], reverse=True)[:10]

    scenarios = [
        {"query": row["content"][:120], "timestamp": row["timestamp"], "session_id": row["session_id"]}
        for row in scenario_rows
    ]

    predictions = [
        {
            "symbol": row["symbol"],
            "direction": row["predicted_direction"],
            "outcome": row["outcome_status"],
            "pnl_pct": row["pnl_pct"],
            "date": row["created_at"][:10],
        }
        for row in pred_rows
    ]

    return {
        "top_symbols": [{"symbol": s, "mentions": c} for s, c in top_symbols],
        "recent_scenarios": scenarios,
        "recent_predictions": predictions,
    }
