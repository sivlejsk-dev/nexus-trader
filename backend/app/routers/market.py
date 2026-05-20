"""Market data router — quotes, OHLCV, technicals, patterns."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query

from app.services.market_data import market_data_service
from app.services.pattern_recognition import pattern_engine
from app.services.adaptive_predictions import adaptive_prediction_service
from app.services.event_intelligence import event_intelligence_service
from app.services.historical_simulation import run_simulation, get_events_for_range
from app.services.model_refinement import model_refinement_service
from app.services.signal_optimizer import signal_optimizer
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


@router.get("/events/world")
async def get_world_events(
    start: str = Query(default="2000-01-01", description="YYYY-MM-DD"),
    end: str = Query(default="2025-12-31", description="YYYY-MM-DD"),
):
    """Return curated world events (wars, macro, weather, social) for a date range."""
    return {"events": get_events_for_range(start, end)}


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
    """Force-score pending predictions and refresh model accuracy stats."""
    bars = await market_data_service.get_historical_ohlcv(symbol.upper(), years=2)
    if not bars:
        raise HTTPException(status_code=404, detail=f"No price data for {symbol}")
    await adaptive_prediction_service._score_due_predictions(symbol.upper(), bars)
    # Refresh rolling accuracy after scoring
    accuracy = await model_refinement_service.refresh(symbol.upper())
    return {"scored": True, "symbol": symbol.upper(), "accuracy_updated": accuracy}


@router.get("/model-stats/{symbol}")
async def get_model_stats(symbol: str):
    """Rolling model accuracy stats for a symbol — win rates per signal, confidence adjustments."""
    stats = await model_refinement_service.get_stats(symbol.upper())
    return stats


@router.get("/model-stats")
async def get_global_model_stats():
    """Cross-symbol model performance summary."""
    return await model_refinement_service.get_global_summary()


@router.get("/simulate/{symbol}")
async def simulate_history(
    symbol: str,
    years: int = Query(default=5, ge=1, le=30),
    horizon_days: int = Query(default=20, ge=5, le=60),
    sample_every: int = Query(default=10, ge=5, le=30),
):
    """
    Replay Nexus prediction logic across historical bars for a symbol.
    Returns predictions with actual outcomes, accuracy metrics, and world events.
    """
    bars = await market_data_service.get_historical_ohlcv(symbol.upper(), years=years)
    if not bars:
        raise HTTPException(status_code=404, detail=f"No historical data for {symbol}")
    result = run_simulation(bars, symbol.upper(), horizon_days=horizon_days, sample_every=sample_every)
    return result


@router.get("/unified/{symbol}")
async def unified_analysis(
    symbol: str,
    years: int = Query(default=5, ge=1, le=30),
    horizon_days: int = Query(default=20, ge=5, le=60),
    sample_every: int = Query(default=10, ge=5, le=30),
    session_id: str = Query(default="console"),
):
    """
    Unified analysis: historical simulation (with adaptive learning from live
    predictions) + live prediction history + signal quality breakdown + world
    events — all in one call. Used by the Analysis page.
    """
    import asyncio
    import json as _json
    import aiosqlite as _aiosqlite
    from app.db.database import get_db

    sym = symbol.upper()

    # Fetch bars and live predictions concurrently
    bars_task = market_data_service.get_historical_ohlcv(sym, years=years)
    live_task = _fetch_live_predictions(sym)
    bars, live_preds = await asyncio.gather(bars_task, live_task)

    # Refresh model accuracy in background (non-blocking)
    import asyncio as _asyncio
    _asyncio.create_task(model_refinement_service.refresh(sym))

    if not bars:
        raise HTTPException(status_code=404, detail=f"No historical data for {sym}")

    # Load learned weights for this symbol (falls back to defaults if none saved)
    active_weights = await signal_optimizer.load_weights(sym)

    # Run upgraded simulation with adaptive learning + learned weights
    sim = run_simulation(
        bars, sym,
        horizon_days=horizon_days,
        sample_every=sample_every,
        live_predictions=live_preds,
        weights=active_weights,
    )
    sim["using_learned_weights"] = active_weights != __import__(
        "app.services.historical_simulation", fromlist=["DEFAULT_WEIGHTS"]
    ).DEFAULT_WEIGHTS

    # Build live performance summary
    completed = [p for p in live_preds if p.get("outcome_status") in ("win", "loss", "flat")]
    wins_live = [p for p in completed if p.get("outcome_status") == "win"]
    losses_live = [p for p in completed if p.get("outcome_status") == "loss"]
    pending_live = [p for p in live_preds if p.get("outcome_status") == "pending"]

    by_dir_live: dict = {}
    for direction in ("call", "put", "neutral"):
        ds = [p for p in completed if p.get("direction") == direction]
        dw = [p for p in ds if p.get("outcome_status") == "win"]
        total = len(ds)
        wins_d = len(dw)
        wr = round(wins_d / total * 100, 1) if total else None
        factor = 1.0
        if total >= 4:
            rate = wins_d / total
            factor = 1.08 if rate >= 0.62 else (0.88 if rate <= 0.38 else 1.0)
        by_dir_live[direction] = {
            "total": total, "wins": wins_d, "losses": total - wins_d,
            "win_rate": wr, "learning_factor": round(factor, 2),
        }

    live_performance = {
        "total": len(completed),
        "wins": len(wins_live),
        "losses": len(losses_live),
        "pending": len(pending_live),
        "win_rate": round(len(wins_live) / len(completed) * 100, 1) if completed else None,
        "by_direction": by_dir_live,
    }

    return {
        "symbol": sym,
        "simulation": sim,
        "live_predictions": {
            "symbol": sym,
            "predictions": live_preds[:50],
            "performance": live_performance,
        },
    }


async def _fetch_live_predictions(symbol: str) -> list:
    """Load live prediction records from DB for adaptive learning input."""
    import json as _json
    import aiosqlite as _aiosqlite
    from app.db.database import get_db

    try:
        async with get_db() as db:
            db.row_factory = _aiosqlite.Row
            cursor = await db.execute(
                "SELECT * FROM prediction_events WHERE symbol=? ORDER BY created_at DESC LIMIT 200",
                (symbol,),
            )
            rows = await cursor.fetchall()
        result = []
        for row in rows:
            result.append({
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
                "rationale": _json.loads(row["rationale"] or "[]"),
                "mistake_notes": _json.loads(row["mistake_notes"] or "[]"),
            })
        return result
    except Exception:
        return []


# ── Signal weight optimization ────────────────────────────────────────────────

@router.post("/optimize/{symbol}")
async def optimize_symbol(
    symbol: str,
    years: int = Query(default=5, ge=1, le=20),
    horizon_days: int = Query(default=20, ge=5, le=60),
    generations: int = Query(default=40, ge=5, le=100),
    children: int = Query(default=8, ge=4, le=20),
    save: bool = Query(default=True, description="Persist best weights after optimization"),
):
    """
    Run the iterative signal weight optimizer for a symbol.

    Replays the simulation N generations, mutating signal weights each time,
    keeping the best-performing weight set. Returns convergence history,
    baseline vs optimized comparison, and the top changed signals.

    If save=true, the best weights are persisted and used for all future
    simulations on this symbol.
    """
    sym = symbol.upper()

    bars = await market_data_service.get_historical_ohlcv(sym, years=years)
    if not bars:
        raise HTTPException(status_code=404, detail=f"No historical data for {sym}")

    live_preds = await _fetch_live_predictions(sym)

    result = await signal_optimizer.optimize(
        bars=bars,
        symbol=sym,
        horizon_days=horizon_days,
        sample_every=10,
        max_generations=generations,
        children_per_gen=children,
        live_predictions=live_preds,
    )

    if save and result["optimized"]["win_rate"] is not None:
        await signal_optimizer.save_weights(
            symbol=sym,
            weights=result["optimized"]["weights"],
            win_rate=result["optimized"]["win_rate"],
            avg_pnl=result["optimized"]["avg_pnl_pct"],
            total_trades=result["optimized"]["total_predictions"] or 0,
            generation=result["generations_run"],
            notes=f"Optimized {years}Y {horizon_days}d horizon, {result['generations_run']} generations",
        )
        await signal_optimizer.save_run(sym, years, horizon_days, result)
        result["weights_saved"] = True
    else:
        result["weights_saved"] = False

    # Strip full simulation predictions from response to keep payload small
    if "full_simulation" in result:
        fs = result["full_simulation"]
        result["full_simulation"] = {
            k: v for k, v in fs.items() if k != "predictions"
        }

    return result


@router.get("/optimize/{symbol}/history")
async def optimization_history(symbol: str, limit: int = Query(default=10, ge=1, le=50)):
    """Return past optimization runs for a symbol."""
    return {
        "symbol": symbol.upper(),
        "runs": await signal_optimizer.history(symbol.upper(), limit=limit),
    }


@router.get("/optimize/{symbol}/weights")
async def get_active_weights(symbol: str):
    """Return the currently active signal weights for a symbol."""
    from app.services.historical_simulation import DEFAULT_WEIGHTS
    weights = await signal_optimizer.load_weights(symbol.upper())
    is_default = weights == DEFAULT_WEIGHTS
    return {
        "symbol": symbol.upper(),
        "weights": weights,
        "is_default": is_default,
        "default_weights": DEFAULT_WEIGHTS,
    }


@router.delete("/optimize/{symbol}/weights")
async def reset_weights(symbol: str):
    """Reset learned weights back to defaults for a symbol."""
    await signal_optimizer.reset(symbol.upper())
    return {"symbol": symbol.upper(), "reset": True}


# ── Best-option engine ────────────────────────────────────────────────────────

@router.get("/best-option/{symbol}")
async def get_best_option_single(
    symbol: str,
    include_research: bool = Query(default=True, description="Fetch recent news for context"),
):
    """
    Run the full best-option pipeline on a single symbol.

    Returns the highest-scoring call or put contract with:
    - Direction + confidence from the full signal stack
    - Best contract: strike, expiry, premium, delta, DTE
    - Risk/reward: breakeven, max loss, expected value
    - Rationale bullets and a voice-ready script
    - Historical simulation win rate for this direction
    """
    from app.services.best_option import get_best_option

    sym = symbol.upper()
    result = await get_best_option(sym, include_research=include_research)

    if result.get("error"):
        raise HTTPException(status_code=404, detail=result["error"])

    return result


@router.post("/best-option")
async def get_best_option_multi(
    symbols: List[str] = Query(description="Ticker symbols to analyse, e.g. AAPL,TSLA,SPY"),
    include_research: bool = Query(default=True),
):
    """
    Run the best-option engine across multiple symbols concurrently.

    Scores each symbol independently, then returns:
    - `best`: the single highest-confidence recommendation across all symbols
    - `all`: per-symbol results for comparison
    """
    import asyncio
    from app.services.best_option import get_best_option

    if not symbols:
        raise HTTPException(status_code=422, detail="At least one symbol required")

    syms = [s.upper() for s in symbols[:8]]  # cap at 8 concurrent

    tasks = [get_best_option(s, include_research=include_research) for s in syms]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    all_results = []
    for sym, r in zip(syms, results):
        if isinstance(r, Exception):
            all_results.append({"symbol": sym, "error": str(r)})
        else:
            all_results.append(r)

    # Pick the highest-confidence non-neutral result
    valid = [r for r in all_results if not r.get("error") and r.get("direction") != "neutral"]
    best = max(valid, key=lambda r: r.get("confidence", 0)) if valid else (all_results[0] if all_results else {})

    return {
        "best": best,
        "all": all_results,
        "symbol_count": len(syms),
    }
