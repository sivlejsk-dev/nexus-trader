"""Market data router — quotes, OHLCV, technicals, patterns."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query

from app.services.market_data import market_data_service
from app.services.pattern_recognition import pattern_engine
from app.nexus_core.reasoning import reasoning_engine

router = APIRouter(prefix="/market", tags=["market"])


@router.get("/quote/{symbol}")
async def get_quote(symbol: str):
    """Current quote for a symbol."""
    data = await market_data_service.get_quote(symbol.upper())
    if data.get("error"):
        raise HTTPException(status_code=503, detail=data["error"])
    return data


@router.get("/history/{symbol}")
async def get_history(
    symbol: str,
    years: int = Query(default=5, ge=1, le=50),
    timespan: str = Query(default="day", pattern="^(day|week|month)$"),
):
    """Historical OHLCV bars. years=50 fetches from market inception where available."""
    bars = await market_data_service.get_historical_ohlcv(symbol.upper(), years=years, timespan=timespan)
    if not bars:
        raise HTTPException(status_code=404, detail=f"No historical data found for {symbol}")
    return {"symbol": symbol.upper(), "timespan": timespan, "count": len(bars), "bars": bars}


@router.get("/technicals/{symbol}")
async def get_technicals(symbol: str):
    """Key technical indicators: RSI, MACD, SMA50, SMA200."""
    data = await market_data_service.get_technicals(symbol.upper())
    return {"symbol": symbol.upper(), "technicals": data}


@router.get("/patterns/{symbol}")
async def get_patterns(
    symbol: str,
    years: int = Query(default=2, ge=1, le=10),
):
    """Run full pattern recognition on historical data."""
    bars = await market_data_service.get_historical_ohlcv(symbol.upper(), years=years)
    if not bars:
        raise HTTPException(status_code=404, detail=f"No data for {symbol}")
    result = pattern_engine.analyze(bars, symbol=symbol.upper())
    return result


@router.get("/analysis/{symbol}")
async def get_full_analysis(symbol: str):
    """
    Combined quote + technicals + pattern recognition + structured reasoning.
    This is the primary endpoint for the visual console.
    """
    import asyncio

    quote_task = market_data_service.get_quote(symbol.upper())
    tech_task = market_data_service.get_technicals(symbol.upper())
    hist_task = market_data_service.get_historical_ohlcv(symbol.upper(), years=2)

    quote, technicals, bars = await asyncio.gather(
        quote_task, tech_task, hist_task, return_exceptions=True
    )

    result: Dict[str, Any] = {"symbol": symbol.upper()}

    if not isinstance(quote, Exception):
        result["quote"] = quote
    if not isinstance(technicals, Exception):
        result["technicals"] = technicals

    patterns_data = {}
    if not isinstance(bars, Exception) and bars:
        patterns_data = pattern_engine.analyze(bars, symbol=symbol.upper())
        result["patterns"] = patterns_data
        # Return last 252 bars (1 year) for charting
        result["chart_bars"] = bars[-252:]

    # Structured reasoning
    if not isinstance(technicals, Exception) and technicals:
        price = result.get("quote", {}).get("price", 0)
        volume = result.get("quote", {}).get("volume", 0)
        reasoning = reasoning_engine.analyze_technicals({
            **technicals,
            "price": price,
            "volume": volume,
        })
        result["reasoning"] = reasoning.to_dict()

    return result
