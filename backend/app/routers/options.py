"""Options router — chains, Greeks, strategy scoring, unusual activity, backtest."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from app.services.market_data import market_data_service
from app.services.options_analysis import (
    options_engine,
    black_scholes,
    score_strategies,
    backtest_long_option,
)

router = APIRouter(prefix="/options", tags=["options"])


# ── Greeks calculator ─────────────────────────────────────────────────────────

class GreeksRequest(BaseModel):
    underlying_price: float
    strike: float
    days_to_expiry: int
    implied_volatility: float   # e.g. 0.30 for 30%
    risk_free_rate: float = 0.05
    option_type: str = "call"   # "call" or "put"


@router.post("/greeks")
async def compute_greeks(req: GreeksRequest):
    """Compute Black-Scholes price and Greeks for a single option."""
    result = black_scholes(
        S=req.underlying_price,
        K=req.strike,
        T=req.days_to_expiry / 365,
        r=req.risk_free_rate,
        sigma=req.implied_volatility,
        option_type=req.option_type,
    )
    return {
        "input": req.model_dump(),
        "greeks": result,
        "disclaimer": (
            "Theoretical values only. Real market prices may differ due to "
            "supply/demand, early exercise premium, and model assumptions."
        ),
    }


# ── Options chain ─────────────────────────────────────────────────────────────

@router.get("/chain/{symbol}")
async def get_options_chain(
    symbol: str,
    expiration_date: Optional[str] = Query(default=None, description="YYYY-MM-DD"),
    option_type: Optional[str] = Query(default=None, pattern="^(call|put)$"),
):
    """Fetch and enrich the options chain for a symbol."""
    quote = await market_data_service.get_quote(symbol.upper())
    underlying_price = quote.get("price", 0)

    chain = await market_data_service.get_options_chain(
        symbol.upper(), expiration_date, option_type
    )
    if not chain:
        raise HTTPException(
            status_code=404,
            detail=f"No options chain data for {symbol}. Ensure POLYGON_API_KEY is configured.",
        )

    enriched = options_engine.analyze_chain(chain, underlying_price)
    return {
        "symbol": symbol.upper(),
        "underlying_price": underlying_price,
        "expiration_date": expiration_date,
        **enriched,
    }


# ── Unusual options activity ──────────────────────────────────────────────────

@router.get("/unusual/{symbol}")
async def get_unusual_activity(symbol: str):
    """Detect unusual options activity (volume/OI ratio spikes)."""
    activity = await market_data_service.get_unusual_options_activity(symbol.upper())
    return {
        "symbol": symbol.upper(),
        "unusual_contracts": activity,
        "count": len(activity),
        "note": (
            "Unusual activity is defined as volume ≥ 2× open interest with ≥500 contracts. "
            "This may indicate institutional positioning but is not a guaranteed signal."
        ),
    }


# ── Strategy scoring ──────────────────────────────────────────────────────────

@router.get("/strategies/{symbol}")
async def get_strategy_recommendations(
    symbol: str,
    days_to_expiry: int = Query(default=30, ge=1, le=365),
):
    """Score options strategies based on current market conditions."""
    import asyncio

    quote_task = market_data_service.get_quote(symbol.upper())
    tech_task = market_data_service.get_technicals(symbol.upper())
    quote, technicals = await asyncio.gather(quote_task, tech_task, return_exceptions=True)

    underlying_price = quote.get("price", 0) if not isinstance(quote, Exception) else 0
    rsi = None
    trend = "sideways"

    if not isinstance(technicals, Exception) and technicals:
        rsi = technicals.get("rsi")
        sma50 = technicals.get("sma_50")
        sma200 = technicals.get("sma_200")
        if underlying_price and sma50 and sma200:
            if underlying_price > sma50 > sma200:
                trend = "uptrend"
            elif underlying_price < sma50 < sma200:
                trend = "downtrend"

    # IV rank placeholder — requires historical IV data (Polygon paid tier)
    iv_rank = 50.0

    strategies = [
        s.to_dict() for s in score_strategies(
            underlying_price=underlying_price,
            trend=trend,
            iv_rank=iv_rank,
            days_to_expiry=days_to_expiry,
            rsi=rsi,
        )
    ]

    return {
        "symbol": symbol.upper(),
        "underlying_price": underlying_price,
        "trend": trend,
        "iv_rank": iv_rank,
        "rsi": rsi,
        "days_to_expiry": days_to_expiry,
        "strategies": strategies,
        "disclaimer": (
            "Strategy scores are algorithmic suggestions based on market conditions. "
            "They do not constitute financial advice. Always assess your own risk tolerance."
        ),
    }


# ── Backtest ──────────────────────────────────────────────────────────────────

class BacktestRequest(BaseModel):
    symbol: str
    option_type: str = "call"          # "call" or "put"
    strike_offset_pct: float = 0.05    # 5% OTM
    days_to_expiry: int = 30
    iv_assumption: float = 0.30        # 30% IV
    years: int = 5


@router.post("/backtest")
async def run_backtest(req: BacktestRequest):
    """Backtest a simple long call or put strategy on historical data."""
    bars = await market_data_service.get_historical_ohlcv(
        req.symbol.upper(), years=req.years
    )
    if not bars:
        raise HTTPException(status_code=404, detail=f"No historical data for {req.symbol}")

    result = backtest_long_option(
        bars=bars,
        option_type=req.option_type,
        strike_offset_pct=req.strike_offset_pct,
        dte=req.days_to_expiry,
        iv_assumption=req.iv_assumption,
    )
    return {"symbol": req.symbol.upper(), **result}
