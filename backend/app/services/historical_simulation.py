"""Historical simulation engine.

Given a symbol and date range, replays Nexus's prediction logic bar-by-bar
against actual OHLCV data and scores each prediction against what actually
happened. Returns a timeline of predictions vs outcomes plus annotated
world events that coincided with notable price moves.
"""
from __future__ import annotations

import math
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

# ── Curated world-event database ─────────────────────────────────────────────
# Each entry: (date_start, date_end, title, category, impact, description)
# impact: "bullish" | "bearish" | "volatility"
# category: "geopolitical" | "macro" | "weather" | "social" | "regulatory" | "pandemic"

WORLD_EVENTS: List[Dict[str, Any]] = [
    # ── 1990s ──
    {"date": "1990-08-02", "end": "1991-02-28", "title": "Gulf War", "category": "geopolitical", "impact": "bearish", "description": "Iraq invades Kuwait; oil shock and market uncertainty drove broad selloff before swift coalition victory sparked recovery."},
    {"date": "1994-02-04", "end": "1994-12-31", "title": "Fed rate hike cycle 1994", "category": "macro", "impact": "bearish", "description": "Fed raised rates 7 times in 12 months, triggering bond market crash and equity volatility."},
    {"date": "1997-07-02", "end": "1997-12-31", "title": "Asian Financial Crisis", "category": "macro", "impact": "bearish", "description": "Thai baht devaluation triggered currency crises across Southeast Asia, spreading to global markets."},
    {"date": "1998-08-17", "end": "1998-10-15", "title": "Russian Debt Default / LTCM", "category": "macro", "impact": "bearish", "description": "Russia defaulted on domestic debt; LTCM collapse required Fed-orchestrated bailout."},
    {"date": "1999-01-01", "end": "2000-03-10", "title": "Dot-com Bubble Peak", "category": "macro", "impact": "bullish", "description": "Internet mania drove NASDAQ to all-time highs; tech valuations detached from fundamentals."},
    # ── 2000s ──
    {"date": "2000-03-10", "end": "2002-10-09", "title": "Dot-com Crash", "category": "macro", "impact": "bearish", "description": "NASDAQ fell 78% from peak; hundreds of internet companies went bankrupt."},
    {"date": "2001-09-11", "end": "2001-09-21", "title": "9/11 Terrorist Attacks", "category": "geopolitical", "impact": "bearish", "description": "Markets closed for 4 days; reopened to largest single-week point drop in Dow history at the time."},
    {"date": "2003-03-20", "end": "2003-05-01", "title": "Iraq War begins", "category": "geopolitical", "impact": "volatility", "description": "US-led invasion of Iraq; initial uncertainty gave way to rally on swift military progress."},
    {"date": "2005-08-29", "end": "2005-09-30", "title": "Hurricane Katrina", "category": "weather", "impact": "bearish", "description": "Catastrophic hurricane devastated Gulf Coast; oil/gas infrastructure damage spiked energy prices."},
    {"date": "2007-06-01", "end": "2009-03-09", "title": "Global Financial Crisis", "category": "macro", "impact": "bearish", "description": "Subprime mortgage collapse triggered worst financial crisis since 1929; S&P 500 fell 57%."},
    {"date": "2008-09-15", "end": "2008-09-30", "title": "Lehman Brothers Collapse", "category": "macro", "impact": "bearish", "description": "Largest bankruptcy in US history froze credit markets and accelerated the financial crisis."},
    # ── 2010s ──
    {"date": "2010-04-20", "end": "2010-09-30", "title": "Deepwater Horizon Oil Spill", "category": "regulatory", "impact": "bearish", "description": "Largest marine oil spill in history; BP lost 50% of market cap, energy sector under pressure."},
    {"date": "2010-05-06", "end": "2010-05-06", "title": "Flash Crash", "category": "macro", "impact": "volatility", "description": "Dow plunged ~1000 points in minutes before recovering; exposed algorithmic trading fragility."},
    {"date": "2011-03-11", "end": "2011-04-30", "title": "Japan Earthquake & Tsunami / Fukushima", "category": "weather", "impact": "bearish", "description": "Magnitude 9.0 earthquake and nuclear disaster disrupted global supply chains."},
    {"date": "2011-08-05", "end": "2011-08-31", "title": "US Credit Rating Downgrade", "category": "macro", "impact": "bearish", "description": "S&P downgraded US AAA rating for first time; markets fell sharply on debt ceiling crisis."},
    {"date": "2014-03-01", "end": "2014-12-31", "title": "Russia annexes Crimea", "category": "geopolitical", "impact": "bearish", "description": "Geopolitical tensions and sanctions on Russia created uncertainty in energy and European markets."},
    {"date": "2015-08-24", "end": "2015-09-30", "title": "China Market Crash / Black Monday", "category": "macro", "impact": "bearish", "description": "Chinese stocks fell 8.5% in one day; global contagion fears triggered worldwide selloff."},
    {"date": "2016-06-23", "end": "2016-07-15", "title": "Brexit Vote", "category": "geopolitical", "impact": "bearish", "description": "UK voted to leave EU; pound fell to 30-year low, global markets dropped sharply."},
    {"date": "2016-11-08", "end": "2016-11-30", "title": "Trump Election 2016", "category": "geopolitical", "impact": "bullish", "description": "Surprise Trump victory initially caused futures selloff but markets rallied on infrastructure/tax cut hopes."},
    {"date": "2018-01-26", "end": "2018-02-28", "title": "Volatility Spike / VIX Explosion", "category": "macro", "impact": "bearish", "description": "VIX doubled in days; inverse-volatility ETFs collapsed, triggering broader correction."},
    {"date": "2018-10-01", "end": "2018-12-24", "title": "Q4 2018 Selloff", "category": "macro", "impact": "bearish", "description": "Fed rate hikes, trade war fears, and growth concerns drove worst December since 1931."},
    {"date": "2019-05-01", "end": "2019-08-31", "title": "US-China Trade War Escalation", "category": "geopolitical", "impact": "bearish", "description": "Tariff escalation between US and China created supply chain uncertainty and market volatility."},
    # ── 2020s ──
    {"date": "2020-01-20", "end": "2020-03-23", "title": "COVID-19 Pandemic Crash", "category": "pandemic", "impact": "bearish", "description": "Fastest bear market in history; S&P 500 fell 34% in 33 days as pandemic lockdowns began."},
    {"date": "2020-03-23", "end": "2020-12-31", "title": "COVID Recovery Rally", "category": "macro", "impact": "bullish", "description": "Unprecedented Fed/fiscal stimulus drove fastest recovery from bear market in history."},
    {"date": "2021-01-27", "end": "2021-02-05", "title": "GameStop Short Squeeze", "category": "social", "impact": "volatility", "description": "Reddit's WallStreetBets coordinated massive short squeeze in GME; hedge funds lost billions."},
    {"date": "2021-11-01", "end": "2022-12-31", "title": "Fed Inflation Fight / Rate Hike Cycle", "category": "macro", "impact": "bearish", "description": "Fastest rate hike cycle in 40 years to combat 40-year high inflation; S&P fell 25%."},
    {"date": "2022-02-24", "end": "2022-12-31", "title": "Russia invades Ukraine", "category": "geopolitical", "impact": "bearish", "description": "Full-scale invasion triggered energy crisis, food supply disruptions, and global inflation surge."},
    {"date": "2023-03-10", "end": "2023-03-31", "title": "Silicon Valley Bank Collapse", "category": "macro", "impact": "bearish", "description": "Second-largest US bank failure triggered regional banking crisis and contagion fears."},
    {"date": "2023-10-07", "end": "2023-12-31", "title": "Israel-Hamas War", "category": "geopolitical", "impact": "volatility", "description": "Hamas attack on Israel and subsequent war raised Middle East tensions and oil price uncertainty."},
    {"date": "2024-01-01", "end": "2024-12-31", "title": "AI Investment Boom", "category": "macro", "impact": "bullish", "description": "Generative AI mania drove massive capital flows into tech; NVDA became most valuable company."},
    {"date": "2024-11-05", "end": "2024-12-31", "title": "Trump Election 2024", "category": "geopolitical", "impact": "bullish", "description": "Trump re-election drove rally in financials, energy, and crypto on deregulation expectations."},
    {"date": "2025-01-01", "end": "2025-06-30", "title": "Global Tariff War 2025", "category": "geopolitical", "impact": "bearish", "description": "Sweeping US tariffs on imports triggered retaliatory measures and global trade uncertainty."},
]


def get_events_for_range(start_date: str, end_date: str) -> List[Dict[str, Any]]:
    """Return world events that overlap with the given date range."""
    start = datetime.strptime(start_date[:10], "%Y-%m-%d")
    end = datetime.strptime(end_date[:10], "%Y-%m-%d")
    result = []
    for ev in WORLD_EVENTS:
        ev_start = datetime.strptime(ev["date"], "%Y-%m-%d")
        ev_end = datetime.strptime(ev["end"], "%Y-%m-%d")
        if ev_start <= end and ev_end >= start:
            result.append({
                "date": ev["date"],
                "end_date": ev["end"],
                "title": ev["title"],
                "category": ev["category"],
                "impact": ev["impact"],
                "description": ev["description"],
            })
    return result


def _sma(values: List[float], period: int) -> Optional[float]:
    if len(values) < period:
        return None
    return sum(values[-period:]) / period


def _rsi(values: List[float], period: int = 14) -> Optional[float]:
    if len(values) < period + 1:
        return None
    gains, losses = 0.0, 0.0
    for i in range(-period, 0):
        d = values[i] - values[i - 1]
        if d > 0:
            gains += d
        else:
            losses -= d
    avg_gain = gains / period
    avg_loss = losses / period
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return round(100 - 100 / (1 + rs), 1)


def _score_bar(closes: List[float], i: int) -> Dict[str, Any]:
    """Score a single bar using simplified Nexus logic."""
    window = closes[max(0, i - 60): i + 1]
    if len(window) < 20:
        return {"direction": "neutral", "confidence": 0.40, "bullish": 0.0, "bearish": 0.0}

    price = window[-1]
    bullish = 0.0
    bearish = 0.0
    rationale = []

    sma20 = _sma(window, 20)
    sma50 = _sma(window, min(50, len(window)))
    rsi = _rsi(window)

    if sma20 and price > sma20:
        bullish += 1.0
        rationale.append("Price above SMA20")
    elif sma20:
        bearish += 1.0
        rationale.append("Price below SMA20")

    if sma50 and sma20 and sma20 > sma50:
        bullish += 0.8
        rationale.append("SMA20 > SMA50 (golden alignment)")
    elif sma50 and sma20 and sma20 < sma50:
        bearish += 0.8
        rationale.append("SMA20 < SMA50 (death cross)")

    if rsi is not None:
        if rsi < 35:
            bullish += 1.2
            rationale.append(f"RSI {rsi} oversold")
        elif rsi > 65:
            bearish += 1.2
            rationale.append(f"RSI {rsi} overbought")

    # Momentum: last 5 bars
    if len(window) >= 6:
        mom = (window[-1] - window[-6]) / window[-6] * 100
        if mom > 2:
            bullish += 0.6
        elif mom < -2:
            bearish += 0.6

    edge = bullish - bearish
    total = max(bullish + bearish, 1.0)
    if abs(edge) < 0.5:
        direction = "neutral"
        confidence = 0.42
    elif edge > 0:
        direction = "call"
        confidence = min(0.82, 0.48 + min(abs(edge) / total, 1) * 0.34)
    else:
        direction = "put"
        confidence = min(0.82, 0.48 + min(abs(edge) / total, 1) * 0.34)

    return {
        "direction": direction,
        "confidence": round(confidence, 2),
        "bullish": round(bullish, 2),
        "bearish": round(bearish, 2),
        "rationale": rationale[:3],
        "rsi": rsi,
        "sma20": round(sma20, 2) if sma20 else None,
        "sma50": round(sma50, 2) if sma50 else None,
    }


def run_simulation(
    bars: List[Dict[str, Any]],
    symbol: str,
    horizon_days: int = 20,
    sample_every: int = 10,
) -> Dict[str, Any]:
    """
    Replay Nexus prediction logic across historical bars.
    Returns predictions with actual outcomes and accuracy metrics.
    """
    if not bars:
        return {"predictions": [], "accuracy": {}, "events": []}

    closes = [b["close"] for b in bars]
    predictions = []

    # Sample every N bars to avoid thousands of entries
    indices = list(range(30, len(bars) - horizon_days, sample_every))

    for i in indices:
        score = _score_bar(closes, i)
        entry_bar = bars[i]
        entry_price = entry_bar["close"]

        # Actual outcome: price horizon_days later
        exit_idx = min(i + horizon_days, len(bars) - 1)
        exit_bar = bars[exit_idx]
        exit_price = exit_bar["close"]
        actual_move_pct = (exit_price - entry_price) / entry_price * 100

        direction = score["direction"]
        if direction == "call":
            won = actual_move_pct >= 1.0
        elif direction == "put":
            won = actual_move_pct <= -1.0
        else:
            won = abs(actual_move_pct) <= 2.0

        pnl_pct = actual_move_pct if direction == "call" else (-actual_move_pct if direction == "put" else -abs(actual_move_pct))

        predictions.append({
            "entry_date": entry_bar["date"],
            "exit_date": exit_bar["date"],
            "entry_price": round(entry_price, 2),
            "exit_price": round(exit_price, 2),
            "direction": direction,
            "confidence": score["confidence"],
            "actual_move_pct": round(actual_move_pct, 2),
            "pnl_pct": round(pnl_pct, 2),
            "outcome": "win" if won else "loss",
            "rationale": score["rationale"],
            "rsi": score["rsi"],
            "sma20": score["sma20"],
        })

    # Accuracy metrics
    completed = [p for p in predictions if p["direction"] != "neutral"]
    wins = [p for p in completed if p["outcome"] == "win"]
    by_dir: Dict[str, Any] = {}
    for d in ("call", "put", "neutral"):
        ds = [p for p in predictions if p["direction"] == d]
        dw = [p for p in ds if p["outcome"] == "win"]
        by_dir[d] = {
            "total": len(ds),
            "wins": len(dw),
            "win_rate": round(len(dw) / len(ds) * 100, 1) if ds else None,
            "avg_pnl": round(sum(p["pnl_pct"] for p in ds) / len(ds), 2) if ds else None,
        }

    # Get events for the date range
    if bars:
        events = get_events_for_range(bars[0]["date"], bars[-1]["date"])
    else:
        events = []

    return {
        "symbol": symbol,
        "total_predictions": len(predictions),
        "wins": len(wins),
        "losses": len(completed) - len(wins),
        "win_rate": round(len(wins) / len(completed) * 100, 1) if completed else None,
        "avg_pnl_pct": round(sum(p["pnl_pct"] for p in completed) / len(completed), 2) if completed else None,
        "by_direction": by_dir,
        "predictions": predictions,
        "events": events,
        "horizon_days": horizon_days,
        "date_range": {
            "start": bars[0]["date"] if bars else None,
            "end": bars[-1]["date"] if bars else None,
        },
    }


historical_simulation_service = type("_Svc", (), {"run": staticmethod(run_simulation), "get_events": staticmethod(get_events_for_range)})()
