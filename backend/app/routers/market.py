"""Market data router — quotes, OHLCV, technicals, patterns."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query

from app.services.market_data import market_data_service
from app.services.pattern_recognition import pattern_engine
from app.services.adaptive_predictions import adaptive_prediction_service
from app.services.event_intelligence import event_intelligence_service
from app.nexus_core.reasoning import reasoning_engine
from app.core.config import settings

router = APIRouter(prefix="/market", tags=["market"])


@router.get("/providers")
async def get_market_providers():
    """Report configured market data sources without exposing secrets."""
    return {
        "providers": [
            {
                "name": "Polygon.io",
                "configured": bool(settings.polygon_api_key),
                "capabilities": ["realtime_quotes", "historical_ohlcv", "options_chains"],
            },
            {
                "name": "Alpha Vantage",
                "configured": bool(settings.alpha_vantage_api_key),
                "capabilities": ["quotes", "historical_ohlcv", "technical_indicators"],
            },
            {
                "name": "Yahoo Finance",
                "configured": True,
                "capabilities": ["delayed_quotes", "historical_ohlcv", "local_technical_indicators"],
            },
            {
                "name": "Tradier",
                "configured": bool(settings.tradier_api_key),
                "capabilities": ["options_chains"],
                "note": "Used as an options-chain fallback when Polygon is unavailable.",
            },
            {
                "name": "Event Intelligence",
                "configured": any(
                    [
                        settings.alpha_vantage_api_key,
                        settings.news_api_key,
                        settings.twitter_bearer_token,
                        settings.social_sentiment_api_url,
                    ]
                ),
                "capabilities": ["global_news", "social_sentiment", "viral_trends", "historical_event_outcomes"],
            },
        ],
        "active_fallback_order": ["Polygon.io", "Alpha Vantage", "Yahoo Finance"],
    }


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
async def get_full_analysis(
    symbol: str,
    session_id: str = Query(default="console", description="Prediction memory namespace"),
):
    """
    Combined quote + technicals + pattern recognition + structured reasoning.
    This is the primary endpoint for the visual console.
    """
    import asyncio

    quote_task = market_data_service.get_quote(symbol.upper())
    tech_task = market_data_service.get_technicals(symbol.upper())
    hist_task = market_data_service.get_historical_ohlcv(symbol.upper(), years=2)
    intelligence_task = event_intelligence_service.build_symbol_intelligence(symbol.upper(), fresh=True)

    quote, technicals, bars, event_intelligence = await asyncio.gather(
        quote_task, tech_task, hist_task, intelligence_task, return_exceptions=True
    )

    result: Dict[str, Any] = {"symbol": symbol.upper()}

    if not isinstance(quote, Exception):
        result["quote"] = quote
    if not isinstance(technicals, Exception):
        result["technicals"] = technicals
    if not isinstance(event_intelligence, Exception):
        result["event_intelligence"] = event_intelligence

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

    if (
        result.get("quote")
        and result["quote"].get("price")
        and not isinstance(technicals, Exception)
        and not isinstance(bars, Exception)
        and bars
    ):
        result["adaptive_prediction"] = await adaptive_prediction_service.build_prediction(
            symbol=symbol.upper(),
            quote=result["quote"],
            technicals=technicals if isinstance(technicals, dict) else {},
            patterns=patterns_data,
            bars=bars,
            session_id=session_id,
            event_intelligence=event_intelligence if isinstance(event_intelligence, dict) else None,
        )

    return result


@router.get("/events/{symbol}")
async def get_event_intelligence(symbol: str):
    """
    Fetch and classify real-world events (news, macro, geopolitical, social)
    for a symbol, with Nexus call/put bias analysis and historical analogues.
    """
    intel = await event_intelligence_service.build_symbol_intelligence(symbol.upper(), fresh=True)
    if isinstance(intel, Exception):
        raise HTTPException(status_code=503, detail=str(intel))

    # Enrich each event with a Nexus analysis string
    events = intel.get("events", [])
    for event in events:
        category = event.get("category", "unknown")
        direction = event.get("direction", "neutral")
        option_bias = event.get("option_bias", "neutral")
        title = event.get("title", "")
        sentiment = event.get("sentiment_score", 0)

        # Build a concise Nexus analysis
        bias_text = {
            "bullish": "This event leans bullish — calls may benefit if the move confirms.",
            "bearish": "This event leans bearish — puts may benefit if the move confirms.",
            "volatility": "This event could spike volatility in either direction — straddles or strangles may be worth considering.",
            "neutral": "This event has mixed or unclear directional implications.",
        }.get(option_bias, "Directional impact unclear.")

        category_context = {
            "earnings": "Earnings events historically cause the largest single-day moves.",
            "macro": "Macro data (Fed, CPI, GDP) affects broad market direction and sector rotation.",
            "geopolitical": "Geopolitical events can cause sharp, short-lived spikes in volatility.",
            "regulatory": "Regulatory actions can be binary events — approval or rejection drives large moves.",
            "product": "Product launches and recalls affect near-term revenue expectations.",
            "analyst": "Analyst rating changes shift institutional positioning.",
            "social_trend": "Social/viral trends can create short squeezes or momentum bursts.",
            "options_flow": "Unusual options flow often precedes informed directional moves.",
        }.get(category, "")

        event["nexus_analysis"] = f"{bias_text} {category_context}".strip()

    # Add source status
    intel["source_status"] = event_intelligence_service.source_status()

    return intel


@router.get("/predictions/{symbol}")
async def get_prediction_history(symbol: str):
    """Full prediction history for a symbol with performance metrics."""
    from app.db.database import get_db
    import aiosqlite
    import json

    async with get_db() as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            """
            SELECT * FROM prediction_events
            WHERE symbol = ?
            ORDER BY created_at DESC
            LIMIT 100
            """,
            (symbol.upper(),),
        )
        rows = await cursor.fetchall()

    predictions = []
    for row in rows:
        predictions.append({
            "id": row["id"],
            "created_at": row["created_at"],
            "direction": row["predicted_direction"],
            "confidence": row["confidence"],
            "entry_price": row["entry_price"],
            "target_price": row["target_price"],
            "stop_loss": row["stop_loss"],
            "outcome_status": row["outcome_status"],
            "exit_price": row["exit_price"],
            "pnl_pct": row["pnl_pct"],
            "rationale": json.loads(row["rationale"] or "[]"),
            "mistake_notes": json.loads(row["mistake_notes"] or "[]"),
        })

    # Compute performance
    completed = [p for p in predictions if p["outcome_status"] in ("win", "loss", "flat")]
    wins = [p for p in completed if p["outcome_status"] == "win"]
    losses = [p for p in completed if p["outcome_status"] == "loss"]
    pending = [p for p in predictions if p["outcome_status"] == "pending"]

    by_direction: dict = {}
    for direction in ("call", "put", "neutral"):
        ds = [p for p in completed if p["direction"] == direction]
        dw = [p for p in ds if p["outcome_status"] == "win"]
        dl = [p for p in ds if p["outcome_status"] == "loss"]
        total = len(ds)
        wins_d = len(dw)
        wr = round(wins_d / total * 100, 1) if total else None
        # Learning factor
        if total < 4:
            factor = 1.0
        else:
            rate = wins_d / total
            factor = 1.08 if rate >= 0.62 else (0.88 if rate <= 0.38 else 1.0)
        by_direction[direction] = {
            "total": total,
            "wins": wins_d,
            "losses": len(dl),
            "win_rate": wr,
            "learning_factor": round(factor, 2),
        }

    return {
        "symbol": symbol.upper(),
        "predictions": predictions,
        "performance": {
            "total": len(completed),
            "wins": len(wins),
            "losses": len(losses),
            "pending": len(pending),
            "win_rate": round(len(wins) / len(completed) * 100, 1) if completed else None,
            "by_direction": by_direction,
        },
    }


@router.post("/predictions/{symbol}/score")
async def score_predictions(symbol: str):
    """Force-score any pending predictions for a symbol against current price data."""
    bars = await market_data_service.get_historical_ohlcv(symbol.upper(), years=2)
    if not bars:
        raise HTTPException(status_code=404, detail=f"No price data for {symbol}")
    await adaptive_prediction_service._score_due_predictions(symbol.upper(), bars)
    return {"scored": True, "symbol": symbol.upper()}
