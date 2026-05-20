"""Best option recommendation engine.

Given a symbol (or a list), runs the full Nexus analysis stack and returns
the single best call or put to buy right now, with full reasoning.

Pipeline:
  1. Fetch live quote + technicals
  2. Run historical simulation with learned weights
  3. Score the directional signal (call vs put vs skip)
  4. Fetch options chain — find the best strike/expiry
  5. Score each contract on: delta, IV rank, liquidity, risk/reward
  6. Return the top recommendation with full rationale + voice script
"""
from __future__ import annotations

import math
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

from app.services.market_data import market_data_service
from app.services.historical_simulation import (
    run_simulation, DEFAULT_WEIGHTS, _rsi, _macd, _bollinger,
    _sma, _volume_ratio,
)
from app.services.signal_optimizer import load_active_weights
from app.services.web_research import search_web

# ── Scoring helpers ───────────────────────────────────────────────────────────

def _score_direction(bars: List[Dict], weights: Dict) -> Dict[str, Any]:
    """Run the full signal stack on the most recent bar and return a direction score."""
    if len(bars) < 80:
        return {"direction": "neutral", "confidence": 0.40, "signals": [], "bull": 0, "bear": 0}

    closes = [b["close"] for b in bars[-80:]]
    volumes = [b.get("volume", 0) for b in bars[-80:]]
    price = closes[-1]

    bull, bear = 0.0, 0.0
    signals: List[Dict[str, Any]] = []

    w = {**DEFAULT_WEIGHTS, **weights}

    # SMA trend
    sma20 = _sma(closes, 20)
    sma50 = _sma(closes, min(50, len(closes)))
    sma200 = _sma(closes, min(200, len(closes)))
    if sma20:
        if price > sma20:
            bull += w["sma20"]
            signals.append({"name": "SMA20", "value": f"${sma20:.2f}", "signal": "bullish",
                            "detail": f"Price ${price:.2f} above SMA20 ${sma20:.2f}"})
        else:
            bear += w["sma20"]
            signals.append({"name": "SMA20", "value": f"${sma20:.2f}", "signal": "bearish",
                            "detail": f"Price ${price:.2f} below SMA20 ${sma20:.2f}"})
    if sma50 and sma20:
        if sma20 > sma50:
            bull += w["sma_cross"]
            signals.append({"name": "SMA Cross", "value": "Golden", "signal": "bullish",
                            "detail": f"SMA20 ${sma20:.2f} > SMA50 ${sma50:.2f}"})
        else:
            bear += w["sma_cross"]
            signals.append({"name": "SMA Cross", "value": "Death", "signal": "bearish",
                            "detail": f"SMA20 ${sma20:.2f} < SMA50 ${sma50:.2f}"})
    if sma200:
        if price > sma200:
            bull += w["sma200"]
            signals.append({"name": "SMA200", "value": f"${sma200:.2f}", "signal": "bullish",
                            "detail": f"Price above long-term trend ${sma200:.2f}"})
        else:
            bear += w["sma200"]
            signals.append({"name": "SMA200", "value": f"${sma200:.2f}", "signal": "bearish",
                            "detail": f"Price below long-term trend ${sma200:.2f}"})

    # RSI
    rsi = _rsi(closes)
    if rsi is not None:
        if rsi < 30:
            bull += w["rsi_extreme"]
            signals.append({"name": "RSI", "value": str(rsi), "signal": "bullish",
                            "detail": f"RSI {rsi} — deeply oversold, mean reversion likely"})
        elif rsi < 40:
            bull += w["rsi_mild"]
            signals.append({"name": "RSI", "value": str(rsi), "signal": "bullish",
                            "detail": f"RSI {rsi} — oversold territory"})
        elif rsi > 70:
            bear += w["rsi_extreme"]
            signals.append({"name": "RSI", "value": str(rsi), "signal": "bearish",
                            "detail": f"RSI {rsi} — deeply overbought, pullback risk"})
        elif rsi > 60:
            bear += w["rsi_mild"]
            signals.append({"name": "RSI", "value": str(rsi), "signal": "bearish",
                            "detail": f"RSI {rsi} — approaching overbought"})
        else:
            signals.append({"name": "RSI", "value": str(rsi), "signal": "neutral",
                            "detail": f"RSI {rsi} — neutral zone"})

    # MACD
    macd_line, macd_sig, macd_hist = _macd(closes)
    if macd_line is not None and macd_sig is not None:
        if macd_line > macd_sig:
            bull += w["macd_cross"]
            signals.append({"name": "MACD", "value": f"{macd_line:.3f}", "signal": "bullish",
                            "detail": f"MACD {macd_line:.3f} above signal {macd_sig:.3f}"})
        else:
            bear += w["macd_cross"]
            signals.append({"name": "MACD", "value": f"{macd_line:.3f}", "signal": "bearish",
                            "detail": f"MACD {macd_line:.3f} below signal {macd_sig:.3f}"})

    # Bollinger Bands
    bb = _bollinger(closes)
    if bb["pct_b"] is not None:
        pct_b = bb["pct_b"]
        if pct_b < 0.15:
            bull += w["bb_band"]
            signals.append({"name": "Bollinger %B", "value": f"{pct_b:.2f}", "signal": "bullish",
                            "detail": f"Price near lower band — oversold ({pct_b:.0%} of band)"})
        elif pct_b > 0.85:
            bear += w["bb_band"]
            signals.append({"name": "Bollinger %B", "value": f"{pct_b:.2f}", "signal": "bearish",
                            "detail": f"Price near upper band — overbought ({pct_b:.0%} of band)"})
        else:
            signals.append({"name": "Bollinger %B", "value": f"{pct_b:.2f}", "signal": "neutral",
                            "detail": f"Price mid-band ({pct_b:.0%})"})

    # Volume
    vol_ratio = _volume_ratio([b.get("volume", 0) for b in bars[-25:]])
    if vol_ratio and vol_ratio > 1.5:
        if bull > bear:
            bull += w["volume_confirm"]
            signals.append({"name": "Volume", "value": f"{vol_ratio:.1f}×", "signal": "bullish",
                            "detail": f"Volume {vol_ratio:.1f}× average — confirms bullish move"})
        else:
            bear += w["volume_confirm"]
            signals.append({"name": "Volume", "value": f"{vol_ratio:.1f}×", "signal": "bearish",
                            "detail": f"Volume {vol_ratio:.1f}× average — confirms bearish move"})

    edge = bull - bear
    total = max(bull + bear, 1.0)
    thresh = w.get("edge_threshold", 0.6)

    if abs(edge) < thresh:
        direction = "neutral"
        confidence = 0.42
    elif edge > 0:
        direction = "call"
        confidence = min(0.88, 0.48 + min(abs(edge) / total, 1) * 0.40)
    else:
        direction = "put"
        confidence = min(0.88, 0.48 + min(abs(edge) / total, 1) * 0.40)

    return {
        "direction": direction,
        "confidence": round(confidence, 2),
        "bull_score": round(bull, 2),
        "bear_score": round(bear, 2),
        "edge": round(edge, 2),
        "signals": signals,
        "rsi": rsi,
        "macd": round(macd_line, 4) if macd_line else None,
        "sma20": round(sma20, 2) if sma20 else None,
        "sma50": round(sma50, 2) if sma50 else None,
        "bb_pct_b": bb.get("pct_b"),
        "vol_ratio": vol_ratio,
    }


def _score_contract(
    contract: Dict[str, Any],
    direction: str,
    price: float,
    confidence: float,
) -> float:
    """
    Score an options contract for suitability. Higher = better.
    Factors: delta alignment, IV rank, bid-ask spread, open interest, DTE.
    """
    score = 0.0

    delta = abs(contract.get("delta") or 0)
    iv = contract.get("implied_volatility") or contract.get("iv") or 0
    bid = contract.get("bid") or 0
    ask = contract.get("ask") or 0
    oi = contract.get("open_interest") or 0
    volume = contract.get("volume") or 0
    dte = contract.get("days_to_expiry") or contract.get("dte") or 30

    # Delta: prefer 0.35–0.55 (near ATM but not too far OTM)
    if 0.30 <= delta <= 0.60:
        score += 30.0
    elif 0.20 <= delta < 0.30 or 0.60 < delta <= 0.70:
        score += 15.0
    elif delta < 0.15:
        score -= 20.0  # too far OTM — lottery ticket

    # DTE: prefer 21–45 days (enough time, not too much theta decay)
    if 21 <= dte <= 45:
        score += 25.0
    elif 14 <= dte < 21 or 45 < dte <= 60:
        score += 12.0
    elif dte < 7:
        score -= 30.0  # 0DTE — very risky
    elif dte > 90:
        score -= 5.0   # too much time value

    # Bid-ask spread: tighter = better liquidity
    mid = (bid + ask) / 2 if bid and ask else 0
    spread_pct = (ask - bid) / mid if mid > 0 else 1.0
    if spread_pct < 0.05:
        score += 20.0
    elif spread_pct < 0.10:
        score += 10.0
    elif spread_pct > 0.25:
        score -= 15.0

    # Open interest + volume: liquidity
    if oi > 1000:
        score += 15.0
    elif oi > 500:
        score += 8.0
    elif oi < 100:
        score -= 10.0

    if volume > 500:
        score += 10.0
    elif volume > 100:
        score += 5.0

    # IV: prefer moderate IV (not too high = expensive, not too low = no move)
    if 0.20 <= iv <= 0.50:
        score += 10.0
    elif iv > 0.80:
        score -= 10.0  # very expensive

    # Confidence bonus: higher confidence → prefer slightly higher delta
    if confidence >= 0.70 and 0.45 <= delta <= 0.65:
        score += 8.0

    return round(score, 1)


def _pick_best_strike(
    chain: List[Dict[str, Any]],
    direction: str,
    price: float,
    confidence: float,
) -> Optional[Dict[str, Any]]:
    """Pick the best contract from an options chain."""
    if not chain:
        return None

    # Filter to the right type
    opt_type = "call" if direction == "call" else "put"
    contracts = [c for c in chain if (c.get("type") or c.get("option_type") or "").lower() == opt_type]
    if not contracts:
        contracts = chain  # fallback: use all

    # Score each
    scored = []
    for c in contracts:
        s = _score_contract(c, direction, price, confidence)
        scored.append((s, c))

    if not scored:
        return None

    scored.sort(key=lambda x: x[0], reverse=True)
    best_score, best = scored[0]
    best["_nexus_score"] = best_score
    return best


def _synthetic_contract(
    symbol: str,
    direction: str,
    price: float,
    confidence: float,
    rsi: Optional[float],
) -> Dict[str, Any]:
    """
    Generate a synthetic contract recommendation when no live chain is available.
    Uses standard options theory to suggest strike/expiry.
    """
    # Target delta ~0.40 → strike ~2-4% OTM for calls, ~2-4% OTM for puts
    if direction == "call":
        strike = round(price * 1.03, 0)  # ~3% OTM call
    else:
        strike = round(price * 0.97, 0)  # ~3% OTM put

    # Expiry: 30 days out (next monthly)
    expiry = (datetime.utcnow() + timedelta(days=30)).strftime("%Y-%m-%d")

    # Rough premium estimate: ~2-4% of stock price for near-ATM 30-day option
    est_premium = round(price * 0.025, 2)

    return {
        "symbol": symbol,
        "type": direction,
        "strike": strike,
        "expiry": expiry,
        "days_to_expiry": 30,
        "estimated_premium": est_premium,
        "delta": 0.40,
        "is_synthetic": True,
        "note": "Live options chain unavailable — this is a model-based estimate. Verify actual prices before trading.",
    }


# ── Main engine ───────────────────────────────────────────────────────────────

async def get_best_option(
    symbol: str,
    include_research: bool = True,
    session_id: str = "console",
) -> Dict[str, Any]:
    """
    Full pipeline: analyse symbol → pick direction → find best contract.
    Returns a complete recommendation with rationale and voice script.
    """
    sym = symbol.upper()

    # 1. Fetch bars + live quote in parallel
    import asyncio
    bars_task = market_data_service.get_historical_ohlcv(sym, years=2)
    quote_task = market_data_service.get_quote(sym)
    bars, quote = await asyncio.gather(bars_task, quote_task, return_exceptions=True)

    if isinstance(bars, Exception) or not bars:
        return {"error": f"No price data for {sym}", "symbol": sym}
    if isinstance(quote, Exception):
        quote = {}

    price = quote.get("price") or (bars[-1]["close"] if bars else 0)
    if not price:
        return {"error": "Could not determine current price", "symbol": sym}

    # 2. Load learned weights
    weights = await load_active_weights(sym)
    using_learned = weights != DEFAULT_WEIGHTS

    # 3. Score direction
    direction_score = _score_direction(bars, weights)
    direction = direction_score["direction"]
    confidence = direction_score["confidence"]

    # 4. Run simulation for historical context
    sim = run_simulation(bars, sym, horizon_days=20, sample_every=10, weights=weights)
    sim_wr = sim.get("win_rate")
    sim_dir_stats = sim.get("by_direction", {}).get(direction, {})

    # 5. Fetch options chain
    chain: List[Dict[str, Any]] = []
    try:
        chain = await market_data_service.get_options_chain(sym)
    except Exception:
        pass

    # 6. Pick best contract
    if chain and direction != "neutral":
        best_contract = _pick_best_strike(chain, direction, price, confidence)
    elif direction != "neutral":
        best_contract = _synthetic_contract(sym, direction, price, confidence, direction_score.get("rsi"))
    else:
        best_contract = None

    # 7. Optional: web research for recent news
    news_snippets: List[str] = []
    if include_research:
        try:
            news = await search_web(f"{sym} stock news today analyst", max_results=3, prefer_financial=True)
            for r in news.get("results", [])[:3]:
                if r.get("snippet"):
                    news_snippets.append(r["snippet"][:200])
        except Exception:
            pass

    # 8. Build risk/reward
    rr = _compute_risk_reward(best_contract, direction, price, confidence)

    # 9. Build voice script
    voice_script = _build_voice_script(
        sym, direction, confidence, price,
        direction_score, sim_wr, sim_dir_stats,
        best_contract, rr, news_snippets,
    )

    # 10. Build written rationale
    rationale = _build_rationale(
        sym, direction, confidence, price,
        direction_score, sim_wr, sim_dir_stats,
        best_contract, rr, news_snippets, using_learned,
    )

    return {
        "symbol": sym,
        "price": price,
        "direction": direction,
        "confidence": confidence,
        "direction_score": direction_score,
        "simulation": {
            "win_rate": sim_wr,
            "avg_pnl_pct": sim.get("avg_pnl_pct"),
            "total_predictions": sim.get("total_predictions"),
            "direction_stats": sim_dir_stats,
        },
        "contract": best_contract,
        "risk_reward": rr,
        "news_snippets": news_snippets,
        "rationale": rationale,
        "voice_script": voice_script,
        "using_learned_weights": using_learned,
        "chain_available": len(chain) > 0,
        "generated_at": datetime.utcnow().isoformat(),
    }


def _compute_risk_reward(
    contract: Optional[Dict],
    direction: str,
    price: float,
    confidence: float,
) -> Dict[str, Any]:
    if not contract:
        return {}

    premium = contract.get("ask") or contract.get("estimated_premium") or 0
    strike = contract.get("strike") or price
    dte = contract.get("days_to_expiry") or 30

    if premium <= 0:
        return {}

    cost_per_contract = premium * 100  # 1 contract = 100 shares

    # Target: 50-100% gain on premium (standard options target)
    target_premium = premium * 1.75
    max_loss = cost_per_contract

    # Breakeven
    if direction == "call":
        breakeven = strike + premium
        target_price = strike + target_premium
    else:
        breakeven = strike - premium
        target_price = strike - target_premium

    # Expected value using confidence as win probability
    win_prob = confidence
    avg_win = premium * 0.75  # conservative: 75% gain on premium
    avg_loss = premium        # lose full premium
    ev = win_prob * avg_win - (1 - win_prob) * avg_loss

    return {
        "premium": round(premium, 2),
        "cost_per_contract": round(cost_per_contract, 2),
        "breakeven": round(breakeven, 2),
        "target_price": round(target_price, 2),
        "max_loss": round(max_loss, 2),
        "expected_value": round(ev, 3),
        "risk_reward_ratio": round(avg_win / avg_loss, 2) if avg_loss > 0 else None,
        "dte": dte,
    }


def _build_voice_script(
    sym: str, direction: str, confidence: float, price: float,
    ds: Dict, sim_wr: Optional[float], sim_dir: Dict,
    contract: Optional[Dict], rr: Dict, news: List[str],
) -> str:
    """Build a natural spoken recommendation — short, punchy, no markdown."""
    dir_word = "call" if direction == "call" else "put"
    dir_move = "up" if direction == "call" else "down"
    conf_pct = int(confidence * 100)

    parts = []

    # Opening
    parts.append(
        f"My recommendation for {sym} right now is a {dir_word}. "
        f"I'm {conf_pct} percent confident the stock moves {dir_move}."
    )

    # Top 2 signals
    top_signals = [s for s in ds.get("signals", []) if s["signal"] != "neutral"][:2]
    if top_signals:
        sig_text = " and ".join(s["detail"] for s in top_signals)
        parts.append(f"The key signals are: {sig_text}.")

    # Simulation context
    if sim_wr is not None:
        dir_wr = sim_dir.get("win_rate")
        if dir_wr is not None:
            parts.append(
                f"Historically, my {dir_word} signals on {sym} have been right {dir_wr} percent of the time "
                f"over a 20-day window."
            )

    # Contract
    if contract and not contract.get("is_synthetic"):
        strike = contract.get("strike")
        expiry = contract.get("expiry") or contract.get("expiration_date")
        premium = contract.get("ask") or contract.get("estimated_premium")
        if strike and expiry:
            parts.append(
                f"The best contract is the {strike} strike {dir_word} expiring {expiry}, "
                f"trading around {premium} dollars per share."
            )
        if rr.get("breakeven"):
            parts.append(f"Breakeven is at {rr['breakeven']} dollars.")
    elif contract and contract.get("is_synthetic"):
        parts.append(
            f"I don't have live options data, but a {contract.get('strike')} strike "
            f"{dir_word} expiring in 30 days would be a reasonable starting point."
        )

    # News context
    if news:
        parts.append(f"Recent news context: {news[0][:120]}")

    # Risk
    parts.append(
        f"The main risk is that this thesis is wrong — in that case you lose the full premium. "
        f"Never risk more than you can afford to lose."
    )

    # Disclaimer
    parts.append("This is not financial advice. Always do your own research before trading.")

    return " ".join(parts)


def _build_rationale(
    sym: str, direction: str, confidence: float, price: float,
    ds: Dict, sim_wr: Optional[float], sim_dir: Dict,
    contract: Optional[Dict], rr: Dict, news: List[str],
    using_learned: bool,
) -> List[str]:
    """Build a structured list of rationale points for display."""
    lines = []
    dir_word = "CALL" if direction == "call" else "PUT"
    conf_pct = int(confidence * 100)

    lines.append(f"**Direction: {dir_word}** — {conf_pct}% confidence")
    lines.append(f"Current price: ${price:.2f}")

    for s in ds.get("signals", []):
        icon = "↑" if s["signal"] == "bullish" else ("↓" if s["signal"] == "bearish" else "→")
        lines.append(f"{icon} {s['detail']}")

    if sim_wr is not None:
        dir_wr = sim_dir.get("win_rate")
        lines.append(
            f"Historical simulation: {sim_wr}% overall win rate, "
            f"{dir_wr}% on {direction.upper()} signals specifically"
        )

    if using_learned:
        lines.append("Using optimized signal weights (learned from historical data)")

    if rr:
        lines.append(
            f"Risk/reward: premium ~${rr.get('premium')}, "
            f"breakeven ${rr.get('breakeven')}, "
            f"max loss ${rr.get('max_loss')}"
        )

    if news:
        lines.append(f"News: {news[0][:150]}")

    return lines


best_option_engine = type(
    "_Eng", (),
    {"analyze": staticmethod(get_best_option)},
)()
