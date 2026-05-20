"""Historical simulation engine — upgraded with MACD, Bollinger Bands,
volume analysis, and adaptive learning from live prediction outcomes.
"""
from __future__ import annotations

import math
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

# ── World-event database ──────────────────────────────────────────────────────

WORLD_EVENTS: List[Dict[str, Any]] = [
    {"date": "1990-08-02", "end": "1991-02-28", "title": "Gulf War", "category": "geopolitical", "impact": "bearish",
     "description": "Iraq invades Kuwait; oil shock and market uncertainty drove broad selloff before swift coalition victory sparked recovery."},
    {"date": "1994-02-04", "end": "1994-12-31", "title": "Fed Rate Hike Cycle 1994", "category": "macro", "impact": "bearish",
     "description": "Fed raised rates 7 times in 12 months, triggering bond market crash and equity volatility."},
    {"date": "1997-07-02", "end": "1997-12-31", "title": "Asian Financial Crisis", "category": "macro", "impact": "bearish",
     "description": "Thai baht devaluation triggered currency crises across Southeast Asia, spreading to global markets."},
    {"date": "1998-08-17", "end": "1998-10-15", "title": "Russian Debt Default / LTCM", "category": "macro", "impact": "bearish",
     "description": "Russia defaulted on domestic debt; LTCM collapse required Fed-orchestrated bailout."},
    {"date": "1999-01-01", "end": "2000-03-10", "title": "Dot-com Bubble Peak", "category": "macro", "impact": "bullish",
     "description": "Internet mania drove NASDAQ to all-time highs; tech valuations detached from fundamentals."},
    {"date": "2000-03-10", "end": "2002-10-09", "title": "Dot-com Crash", "category": "macro", "impact": "bearish",
     "description": "NASDAQ fell 78% from peak; hundreds of internet companies went bankrupt."},
    {"date": "2001-09-11", "end": "2001-09-21", "title": "9/11 Terrorist Attacks", "category": "geopolitical", "impact": "bearish",
     "description": "Markets closed for 4 days; reopened to largest single-week point drop in Dow history at the time."},
    {"date": "2003-03-20", "end": "2003-05-01", "title": "Iraq War Begins", "category": "geopolitical", "impact": "volatility",
     "description": "US-led invasion of Iraq; initial uncertainty gave way to rally on swift military progress."},
    {"date": "2005-08-29", "end": "2005-09-30", "title": "Hurricane Katrina", "category": "weather", "impact": "bearish",
     "description": "Catastrophic hurricane devastated Gulf Coast; oil/gas infrastructure damage spiked energy prices."},
    {"date": "2007-06-01", "end": "2009-03-09", "title": "Global Financial Crisis", "category": "macro", "impact": "bearish",
     "description": "Subprime mortgage collapse triggered worst financial crisis since 1929; S&P 500 fell 57%."},
    {"date": "2008-09-15", "end": "2008-09-30", "title": "Lehman Brothers Collapse", "category": "macro", "impact": "bearish",
     "description": "Largest bankruptcy in US history froze credit markets and accelerated the financial crisis."},
    {"date": "2010-05-06", "end": "2010-05-06", "title": "Flash Crash", "category": "macro", "impact": "volatility",
     "description": "Dow plunged ~1000 points in minutes before recovering; exposed algorithmic trading fragility."},
    {"date": "2011-03-11", "end": "2011-04-30", "title": "Japan Earthquake & Fukushima", "category": "weather", "impact": "bearish",
     "description": "Magnitude 9.0 earthquake and nuclear disaster disrupted global supply chains."},
    {"date": "2011-08-05", "end": "2011-08-31", "title": "US Credit Rating Downgrade", "category": "macro", "impact": "bearish",
     "description": "S&P downgraded US AAA rating for first time; markets fell sharply on debt ceiling crisis."},
    {"date": "2014-03-01", "end": "2014-12-31", "title": "Russia Annexes Crimea", "category": "geopolitical", "impact": "bearish",
     "description": "Geopolitical tensions and sanctions on Russia created uncertainty in energy and European markets."},
    {"date": "2015-08-24", "end": "2015-09-30", "title": "China Market Crash / Black Monday", "category": "macro", "impact": "bearish",
     "description": "Chinese stocks fell 8.5% in one day; global contagion fears triggered worldwide selloff."},
    {"date": "2016-06-23", "end": "2016-07-15", "title": "Brexit Vote", "category": "geopolitical", "impact": "bearish",
     "description": "UK voted to leave EU; pound fell to 30-year low, global markets dropped sharply."},
    {"date": "2016-11-08", "end": "2016-11-30", "title": "Trump Election 2016", "category": "geopolitical", "impact": "bullish",
     "description": "Surprise Trump victory initially caused futures selloff but markets rallied on infrastructure/tax cut hopes."},
    {"date": "2018-01-26", "end": "2018-02-28", "title": "Volatility Spike / VIX Explosion", "category": "macro", "impact": "bearish",
     "description": "VIX doubled in days; inverse-volatility ETFs collapsed, triggering broader correction."},
    {"date": "2018-10-01", "end": "2018-12-24", "title": "Q4 2018 Selloff", "category": "macro", "impact": "bearish",
     "description": "Fed rate hikes, trade war fears, and growth concerns drove worst December since 1931."},
    {"date": "2019-05-01", "end": "2019-08-31", "title": "US-China Trade War Escalation", "category": "geopolitical", "impact": "bearish",
     "description": "Tariff escalation between US and China created supply chain uncertainty and market volatility."},
    {"date": "2020-01-20", "end": "2020-03-23", "title": "COVID-19 Pandemic Crash", "category": "pandemic", "impact": "bearish",
     "description": "Fastest bear market in history; S&P 500 fell 34% in 33 days as pandemic lockdowns began."},
    {"date": "2020-03-23", "end": "2020-12-31", "title": "COVID Recovery Rally", "category": "macro", "impact": "bullish",
     "description": "Unprecedented Fed/fiscal stimulus drove fastest recovery from bear market in history."},
    {"date": "2021-01-27", "end": "2021-02-05", "title": "GameStop Short Squeeze", "category": "social", "impact": "volatility",
     "description": "Reddit's WallStreetBets coordinated massive short squeeze in GME; hedge funds lost billions."},
    {"date": "2021-11-01", "end": "2022-12-31", "title": "Fed Inflation Fight / Rate Hike Cycle", "category": "macro", "impact": "bearish",
     "description": "Fastest rate hike cycle in 40 years to combat 40-year high inflation; S&P fell 25%."},
    {"date": "2022-02-24", "end": "2022-12-31", "title": "Russia Invades Ukraine", "category": "geopolitical", "impact": "bearish",
     "description": "Full-scale invasion triggered energy crisis, food supply disruptions, and global inflation surge."},
    {"date": "2023-03-10", "end": "2023-03-31", "title": "Silicon Valley Bank Collapse", "category": "macro", "impact": "bearish",
     "description": "Second-largest US bank failure triggered regional banking crisis and contagion fears."},
    {"date": "2023-10-07", "end": "2023-12-31", "title": "Israel-Hamas War", "category": "geopolitical", "impact": "volatility",
     "description": "Hamas attack on Israel and subsequent war raised Middle East tensions and oil price uncertainty."},
    {"date": "2024-01-01", "end": "2024-12-31", "title": "AI Investment Boom", "category": "macro", "impact": "bullish",
     "description": "Generative AI mania drove massive capital flows into tech; NVDA became most valuable company."},
    {"date": "2024-11-05", "end": "2024-12-31", "title": "Trump Election 2024", "category": "geopolitical", "impact": "bullish",
     "description": "Trump re-election drove rally in financials, energy, and crypto on deregulation expectations."},
    {"date": "2025-01-01", "end": "2025-06-30", "title": "Global Tariff War 2025", "category": "geopolitical", "impact": "bearish",
     "description": "Sweeping US tariffs on imports triggered retaliatory measures and global trade uncertainty."},
]


def get_events_for_range(start_date: str, end_date: str) -> List[Dict[str, Any]]:
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


# ── Technical indicator helpers ───────────────────────────────────────────────

def _sma(values: List[float], period: int) -> Optional[float]:
    if len(values) < period:
        return None
    return sum(values[-period:]) / period


def _ema(values: List[float], period: int) -> Optional[float]:
    if len(values) < period:
        return None
    k = 2.0 / (period + 1)
    ema = sum(values[:period]) / period
    for v in values[period:]:
        ema = v * k + ema * (1 - k)
    return ema


def _macd(values: List[float]) -> Tuple[Optional[float], Optional[float], Optional[float]]:
    """Returns (macd_line, signal_line, histogram)."""
    if len(values) < 35:
        return None, None, None
    fast = _ema(values, 12)
    slow = _ema(values, 26)
    if fast is None or slow is None:
        return None, None, None
    macd_line = fast - slow
    # Signal: 9-period EMA of MACD — approximate with last 9 MACD values
    macd_series = []
    for i in range(9, 0, -1):
        f = _ema(values[:-i] if i > 0 else values, 12)
        s = _ema(values[:-i] if i > 0 else values, 26)
        if f is not None and s is not None:
            macd_series.append(f - s)
    if len(macd_series) < 9:
        return macd_line, None, None
    signal = sum(macd_series[-9:]) / 9
    return macd_line, signal, macd_line - signal


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


def _bollinger(values: List[float], period: int = 20, num_std: float = 2.0) -> Dict[str, Optional[float]]:
    if len(values) < period:
        return {"upper": None, "middle": None, "lower": None, "width_pct": None, "pct_b": None}
    window = values[-period:]
    mid = sum(window) / period
    variance = sum((v - mid) ** 2 for v in window) / period
    std = math.sqrt(variance)
    upper = mid + num_std * std
    lower = mid - num_std * std
    price = values[-1]
    width_pct = (upper - lower) / mid * 100 if mid else None
    pct_b = (price - lower) / (upper - lower) if (upper - lower) > 0 else 0.5
    return {
        "upper": round(upper, 2),
        "middle": round(mid, 2),
        "lower": round(lower, 2),
        "width_pct": round(width_pct, 2) if width_pct else None,
        "pct_b": round(pct_b, 3),
    }


def _atr(bars: List[Dict[str, Any]], period: int = 14) -> Optional[float]:
    if len(bars) < period + 1:
        return None
    trs = []
    for i in range(1, len(bars)):
        h = bars[i]["high"]
        l = bars[i]["low"]
        pc = bars[i - 1]["close"]
        trs.append(max(h - l, abs(h - pc), abs(l - pc)))
    if len(trs) < period:
        return None
    return round(sum(trs[-period:]) / period, 4)


def _volume_ratio(volumes: List[float], period: int = 20) -> Optional[float]:
    """Current volume vs N-period average."""
    if len(volumes) < period + 1:
        return None
    avg = sum(volumes[-period - 1:-1]) / period
    if avg == 0:
        return None
    return round(volumes[-1] / avg, 2)


# ── Default signal weights (baseline) ────────────────────────────────────────
# Each key maps to the base contribution weight for that signal.
# The optimizer mutates these to find the best-performing combination.

DEFAULT_WEIGHTS: Dict[str, float] = {
    "sma20":          1.00,   # price vs SMA20
    "sma_cross":      0.80,   # SMA20 vs SMA50 cross
    "sma200":         0.60,   # price vs SMA200
    "rsi_extreme":    1.50,   # RSI < 30 or > 70
    "rsi_mild":       0.90,   # RSI 30-40 or 60-70
    "macd_cross":     0.90,   # MACD vs signal line
    "macd_accel":     0.40,   # MACD histogram direction
    "bb_band":        1.10,   # price near BB upper/lower
    "volume_confirm": 0.70,   # high volume confirmation
    "momentum_5bar":  0.60,   # 5-bar price momentum
    "edge_threshold": 0.60,   # minimum edge to avoid neutral
}

WeightMap = Dict[str, float]


# ── Bar scorer — full signal stack ────────────────────────────────────────────

def _score_bar(
    bars: List[Dict[str, Any]],
    i: int,
    weights: Optional[WeightMap] = None,
) -> Dict[str, Any]:
    """Score a single bar using the full Nexus signal stack with injectable weights."""
    w = {**DEFAULT_WEIGHTS, **(weights or {})}

    window_bars = bars[max(0, i - 80): i + 1]
    closes = [b["close"] for b in window_bars]
    volumes = [b.get("volume", 0) for b in window_bars]

    if len(closes) < 20:
        return {"direction": "neutral", "confidence": 0.40, "bullish": 0.0, "bearish": 0.0, "rationale": []}

    price = closes[-1]
    bullish = 0.0
    bearish = 0.0
    rationale: List[str] = []

    # ── SMA trend ──
    sma20 = _sma(closes, 20)
    sma50 = _sma(closes, min(50, len(closes)))
    sma200 = _sma(closes, min(200, len(closes)))

    if sma20:
        if price > sma20:
            bullish += w["sma20"]
            rationale.append("Price above SMA20")
        else:
            bearish += w["sma20"]
            rationale.append("Price below SMA20")

    if sma50 and sma20:
        if sma20 > sma50:
            bullish += w["sma_cross"]
            rationale.append("SMA20 > SMA50 (golden alignment)")
        else:
            bearish += w["sma_cross"]
            rationale.append("SMA20 < SMA50 (death cross)")

    if sma200 and sma50:
        if price > sma200:
            bullish += w["sma200"]
        else:
            bearish += w["sma200"]

    # ── RSI ──
    rsi = _rsi(closes)
    if rsi is not None:
        if rsi < 30:
            bullish += w["rsi_extreme"]
            rationale.append(f"RSI {rsi} deeply oversold")
        elif rsi < 40:
            bullish += w["rsi_mild"]
            rationale.append(f"RSI {rsi} oversold")
        elif rsi > 70:
            bearish += w["rsi_extreme"]
            rationale.append(f"RSI {rsi} deeply overbought")
        elif rsi > 60:
            bearish += w["rsi_mild"]
            rationale.append(f"RSI {rsi} overbought")

    # ── MACD ──
    macd_line, macd_signal, macd_hist = _macd(closes)
    if macd_line is not None and macd_signal is not None:
        if macd_line > macd_signal:
            bullish += w["macd_cross"]
            rationale.append("MACD above signal (bullish momentum)")
        else:
            bearish += w["macd_cross"]
            rationale.append("MACD below signal (bearish momentum)")
        if macd_hist is not None and len(closes) > 36:
            prev_macd, prev_sig, prev_hist = _macd(closes[:-1])
            if prev_hist is not None:
                if macd_hist > prev_hist:
                    bullish += w["macd_accel"]
                else:
                    bearish += w["macd_accel"]

    # ── Bollinger Bands ──
    bb = _bollinger(closes)
    if bb["pct_b"] is not None:
        pct_b = bb["pct_b"]
        if pct_b < 0.1:
            bullish += w["bb_band"]
            rationale.append("Price near lower Bollinger Band (oversold)")
        elif pct_b > 0.9:
            bearish += w["bb_band"]
            rationale.append("Price near upper Bollinger Band (overbought)")
        if bb["width_pct"] is not None and bb["width_pct"] < 4.0:
            rationale.append("Bollinger squeeze — breakout likely")

    # ── Volume confirmation ──
    vol_ratio = _volume_ratio(volumes)
    if vol_ratio is not None and vol_ratio > 1.5:
        if bullish > bearish:
            bullish += w["volume_confirm"]
            rationale.append(f"Volume {vol_ratio}x avg confirms bullish move")
        else:
            bearish += w["volume_confirm"]
            rationale.append(f"Volume {vol_ratio}x avg confirms bearish move")

    # ── Short-term momentum (5-bar) ──
    if len(closes) >= 6:
        mom = (closes[-1] - closes[-6]) / closes[-6] * 100
        if mom > 3:
            bullish += w["momentum_5bar"]
        elif mom < -3:
            bearish += w["momentum_5bar"]

    # ── ATR-based volatility context ──
    atr = _atr(window_bars)

    edge = bullish - bearish
    total = max(bullish + bearish, 1.0)
    edge_thresh = max(0.1, w.get("edge_threshold", 0.60))
    if abs(edge) < edge_thresh:
        direction = "neutral"
        confidence = 0.42
    elif edge > 0:
        direction = "call"
        confidence = min(0.85, 0.48 + min(abs(edge) / total, 1) * 0.37)
    else:
        direction = "put"
        confidence = min(0.85, 0.48 + min(abs(edge) / total, 1) * 0.37)

    return {
        "direction": direction,
        "confidence": round(confidence, 2),
        "bullish": round(bullish, 2),
        "bearish": round(bearish, 2),
        "rationale": rationale[:4],
        "rsi": rsi,
        "sma20": round(sma20, 2) if sma20 else None,
        "sma50": round(sma50, 2) if sma50 else None,
        "macd": round(macd_line, 4) if macd_line is not None else None,
        "macd_signal": round(macd_signal, 4) if macd_signal is not None else None,
        "bb_pct_b": bb.get("pct_b"),
        "bb_width_pct": bb.get("width_pct"),
        "vol_ratio": vol_ratio,
        "atr": atr,
    }


# ── Adaptive learning from live predictions ───────────────────────────────────

def _build_learning_factors(live_predictions: List[Dict[str, Any]]) -> Dict[str, float]:
    """
    Compute per-direction confidence multipliers from completed live predictions.
    Mirrors the logic in AdaptivePredictionService but operates on raw dicts.
    """
    factors: Dict[str, float] = {"call": 1.0, "put": 1.0, "neutral": 1.0}
    for direction in ("call", "put", "neutral"):
        completed = [p for p in live_predictions
                     if p.get("direction") == direction
                     and p.get("outcome_status") in ("win", "loss")]
        if len(completed) < 4:
            continue
        wins = sum(1 for p in completed if p.get("outcome_status") == "win")
        rate = wins / len(completed)
        if rate >= 0.62:
            factors[direction] = 1.08
        elif rate <= 0.38:
            factors[direction] = 0.88
    return factors


# ── Main simulation runner ────────────────────────────────────────────────────

def run_simulation(
    bars: List[Dict[str, Any]],
    symbol: str,
    horizon_days: int = 20,
    sample_every: int = 10,
    live_predictions: Optional[List[Dict[str, Any]]] = None,
    weights: Optional[WeightMap] = None,
) -> Dict[str, Any]:
    """
    Replay Nexus prediction logic across historical bars.

    weights: signal weight map — if None, uses DEFAULT_WEIGHTS.
    live_predictions: completed live predictions used for adaptive learning factors.
    """
    if not bars:
        return {"predictions": [], "accuracy": {}, "events": []}

    learning_factors = _build_learning_factors(live_predictions or [])
    effective_weights = {**DEFAULT_WEIGHTS, **(weights or {})}
    predictions = []

    indices = list(range(80, len(bars) - horizon_days, sample_every))

    for i in indices:
        score = _score_bar(bars, i, weights=effective_weights)
        entry_bar = bars[i]
        entry_price = entry_bar["close"]

        exit_idx = min(i + horizon_days, len(bars) - 1)
        exit_bar = bars[exit_idx]
        exit_price = exit_bar["close"]
        actual_move_pct = (exit_price - entry_price) / entry_price * 100

        direction = score["direction"]
        raw_confidence = score["confidence"]
        # Apply adaptive learning factor
        factor = learning_factors.get(direction, 1.0)
        adjusted_confidence = round(max(0.25, min(0.88, raw_confidence * factor)), 2)

        if direction == "call":
            won = actual_move_pct >= 1.0
        elif direction == "put":
            won = actual_move_pct <= -1.0
        else:
            won = abs(actual_move_pct) <= 2.0

        pnl_pct = (
            actual_move_pct if direction == "call"
            else (-actual_move_pct if direction == "put"
                  else -abs(actual_move_pct))
        )

        predictions.append({
            "entry_date": entry_bar["date"],
            "exit_date": exit_bar["date"],
            "entry_price": round(entry_price, 2),
            "exit_price": round(exit_price, 2),
            "direction": direction,
            "confidence": adjusted_confidence,
            "raw_confidence": raw_confidence,
            "learning_factor": factor,
            "actual_move_pct": round(actual_move_pct, 2),
            "pnl_pct": round(pnl_pct, 2),
            "outcome": "win" if won else "loss",
            "rationale": score["rationale"],
            "rsi": score["rsi"],
            "sma20": score["sma20"],
            "macd": score["macd"],
            "bb_pct_b": score["bb_pct_b"],
            "vol_ratio": score["vol_ratio"],
            "bullish_score": score["bullish"],
            "bearish_score": score["bearish"],
        })

    # ── Accuracy metrics ──
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
            "learning_factor": learning_factors.get(d, 1.0),
        }

    # ── Signal quality breakdown ──
    signal_stats = _compute_signal_stats(predictions)

    events = get_events_for_range(bars[0]["date"], bars[-1]["date"]) if bars else []

    return {
        "symbol": symbol,
        "total_predictions": len(predictions),
        "wins": len(wins),
        "losses": len(completed) - len(wins),
        "win_rate": round(len(wins) / len(completed) * 100, 1) if completed else None,
        "avg_pnl_pct": round(sum(p["pnl_pct"] for p in completed) / len(completed), 2) if completed else None,
        "by_direction": by_dir,
        "signal_stats": signal_stats,
        "learning_factors": learning_factors,
        "weights_used": effective_weights,
        "predictions": predictions,
        "events": events,
        "horizon_days": horizon_days,
        "date_range": {
            "start": bars[0]["date"] if bars else None,
            "end": bars[-1]["date"] if bars else None,
        },
    }


def _compute_signal_stats(predictions: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Break down win rates by signal conditions to show which signals work best."""
    stats: Dict[str, Dict[str, int]] = {
        "rsi_oversold": {"total": 0, "wins": 0},
        "rsi_overbought": {"total": 0, "wins": 0},
        "macd_bullish": {"total": 0, "wins": 0},
        "macd_bearish": {"total": 0, "wins": 0},
        "bb_lower": {"total": 0, "wins": 0},
        "bb_upper": {"total": 0, "wins": 0},
        "high_volume": {"total": 0, "wins": 0},
    }
    for p in predictions:
        won = p["outcome"] == "win"
        rsi = p.get("rsi")
        macd = p.get("macd")
        bb = p.get("bb_pct_b")
        vol = p.get("vol_ratio")

        if rsi is not None and rsi < 40 and p["direction"] == "call":
            stats["rsi_oversold"]["total"] += 1
            if won: stats["rsi_oversold"]["wins"] += 1
        if rsi is not None and rsi > 60 and p["direction"] == "put":
            stats["rsi_overbought"]["total"] += 1
            if won: stats["rsi_overbought"]["wins"] += 1
        if macd is not None and macd > 0 and p["direction"] == "call":
            stats["macd_bullish"]["total"] += 1
            if won: stats["macd_bullish"]["wins"] += 1
        if macd is not None and macd < 0 and p["direction"] == "put":
            stats["macd_bearish"]["total"] += 1
            if won: stats["macd_bearish"]["wins"] += 1
        if bb is not None and bb < 0.15 and p["direction"] == "call":
            stats["bb_lower"]["total"] += 1
            if won: stats["bb_lower"]["wins"] += 1
        if bb is not None and bb > 0.85 and p["direction"] == "put":
            stats["bb_upper"]["total"] += 1
            if won: stats["bb_upper"]["wins"] += 1
        if vol is not None and vol > 1.5:
            stats["high_volume"]["total"] += 1
            if won: stats["high_volume"]["wins"] += 1

    result = {}
    for key, s in stats.items():
        result[key] = {
            "total": s["total"],
            "wins": s["wins"],
            "win_rate": round(s["wins"] / s["total"] * 100, 1) if s["total"] else None,
        }
    return result


historical_simulation_service = type(
    "_Svc", (),
    {"run": staticmethod(run_simulation), "get_events": staticmethod(get_events_for_range)}
)()
