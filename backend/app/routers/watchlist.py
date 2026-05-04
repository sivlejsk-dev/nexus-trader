"""Watchlist router — persistent per-session watchlist via SQLite memory."""
from __future__ import annotations

from typing import Any, Dict, List

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.nexus_core.memory_store import get_memory_store
from app.services.market_data import market_data_service

router = APIRouter(prefix="/watchlist", tags=["watchlist"])

WATCHLIST_KEY = "watchlist"


async def _get_watchlist(session_id: str) -> List[str]:
    memory = get_memory_store(session_id)
    return await memory.get_preference(WATCHLIST_KEY, [])


async def _save_watchlist(session_id: str, symbols: List[str]) -> None:
    memory = get_memory_store(session_id)
    await memory.set_preference(WATCHLIST_KEY, symbols)


class WatchlistItem(BaseModel):
    symbol: str


@router.get("/{session_id}")
async def get_watchlist(session_id: str):
    symbols = await _get_watchlist(session_id)
    if not symbols:
        return {"session_id": session_id, "symbols": [], "quotes": []}

    import asyncio
    quotes = await asyncio.gather(
        *[market_data_service.get_quote(s) for s in symbols],
        return_exceptions=True,
    )
    quote_list = [
        q if not isinstance(q, Exception) else {"symbol": symbols[i], "error": str(q)}
        for i, q in enumerate(quotes)
    ]
    return {"session_id": session_id, "symbols": symbols, "quotes": quote_list}


@router.post("/{session_id}")
async def add_to_watchlist(session_id: str, item: WatchlistItem):
    symbols = await _get_watchlist(session_id)
    sym = item.symbol.upper()
    if sym not in symbols:
        symbols.append(sym)
        await _save_watchlist(session_id, symbols)
    return {"session_id": session_id, "symbols": symbols, "added": sym}


@router.delete("/{session_id}/{symbol}")
async def remove_from_watchlist(session_id: str, symbol: str):
    symbols = await _get_watchlist(session_id)
    sym = symbol.upper()
    if sym not in symbols:
        raise HTTPException(status_code=404, detail=f"{sym} not in watchlist")
    symbols.remove(sym)
    await _save_watchlist(session_id, symbols)
    return {"session_id": session_id, "symbols": symbols, "removed": sym}
