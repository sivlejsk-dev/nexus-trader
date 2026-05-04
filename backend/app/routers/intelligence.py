"""Event intelligence router — news/social ingestion and options-aware scoring."""
from __future__ import annotations

from typing import List

from fastapi import APIRouter, Query
from pydantic import BaseModel

from app.services.event_intelligence import event_intelligence_service

router = APIRouter(prefix="/intelligence", tags=["intelligence"])


class IngestRequest(BaseModel):
    symbols: List[str]


@router.get("/sources")
async def get_sources():
    """Report configured news/social sources without exposing secrets."""
    return {"sources": event_intelligence_service.source_status()}


@router.post("/ingest")
async def ingest(req: IngestRequest):
    """Fetch and persist fresh events for one or more symbols."""
    return await event_intelligence_service.ingest(req.symbols)


@router.get("/events/{symbol}")
async def get_symbol_events(
    symbol: str,
    fresh: bool = Query(default=True, description="Fetch latest provider data before returning events"),
):
    """Return classified market events, historical analogues, and call/put bias."""
    return await event_intelligence_service.build_symbol_intelligence(symbol, fresh=fresh)
