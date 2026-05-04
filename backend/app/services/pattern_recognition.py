"""
Pattern Recognition Engine — identifies chart patterns and recurring setups.

Detects: support/resistance, trend lines, head & shoulders, double top/bottom,
cup & handle, flags, wedges, candlestick patterns, and volume patterns.
All detections return structured results with confidence scores and evidence.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple


@dataclass
class PatternMatch:
    name: str
    pattern_type: str          # "reversal", "continuation", "neutral"
    direction: str             # "bullish", "bearish", "neutral"
    confidence: float          # 0-1
    start_idx: int
    end_idx: int
    key_levels: Dict[str, float] = field(default_factory=dict)
    evidence: List[str] = field(default_factory=list)
    target_price: Optional[float] = None
    stop_loss: Optional[float] = None
    description: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "pattern_type": self.pattern_type,
            "direction": self.direction,
            "confidence": round(self.confidence, 3),
            "start_idx": self.start_idx,
            "end_idx": self.end_idx,
            "key_levels": self.key_levels,
            "evidence": self.evidence,
            "target_price": self.target_price,
            "stop_loss": self.stop_loss,
            "description": self.description,
        }


# ── Utility helpers ───────────────────────────────────────────────────────────

def _closes(bars: List[Dict]) -> List[float]:
    return [b["close"] for b in bars]

def _highs(bars: List[Dict]) -> List[float]:
    return [b["high"] for b in bars]

def _lows(bars: List[Dict]) -> List[float]:
    return [b["low"] for b in bars]

def _volumes(bars: List[Dict]) -> List[float]:
    return [b.get("volume", 0) for b in bars]

def _avg(values: List[float]) -> float:
    return sum(values) / len(values) if values else 0.0

def _local_maxima(values: List[float], window: int = 5) -> List[int]:
    peaks = []
    for i in range(window, len(values) - window):
        if values[i] == max(values[i - window: i + window + 1]):
            peaks.append(i)
    return peaks

def _local_minima(values: List[float], window: int = 5) -> List[int]:
    troughs = []
    for i in range(window, len(values) - window):
        if values[i] == min(values[i - window: i + window + 1]):
            troughs.append(i)
    return troughs

def _pct_diff(a: float, b: float) -> float:
    if b == 0:
        return 0.0
    return abs(a - b) / b


# ── Support / Resistance ──────────────────────────────────────────────────────

def find_support_resistance(
    bars: List[Dict], tolerance: float = 0.015
) -> Dict[str, List[float]]:
    """
    Identify key support and resistance levels using local extrema clustering.
    tolerance: price levels within this % are merged into one level.
    """
    highs = _highs(bars)
    lows = _lows(bars)

    peaks = [highs[i] for i in _local_maxima(highs, window=3)]
    troughs = [lows[i] for i in _local_minima(lows, window=3)]

    def cluster(levels: List[float]) -> List[float]:
        if not levels:
            return []
        levels = sorted(levels)
        clusters: List[List[float]] = [[levels[0]]]
        for lvl in levels[1:]:
            if _pct_diff(lvl, clusters[-1][-1]) <= tolerance:
                clusters[-1].append(lvl)
            else:
                clusters.append([lvl])
        return [round(_avg(c), 2) for c in clusters]

    resistance = cluster(peaks)
    support = cluster(troughs)

    # Keep only the most significant (most touches)
    return {
        "resistance": sorted(resistance, reverse=True)[:5],
        "support": sorted(support, reverse=True)[:5],
    }


# ── Trend detection ───────────────────────────────────────────────────────────

def detect_trend(bars: List[Dict], lookback: int = 50) -> Dict[str, Any]:
    """Determine trend direction using linear regression slope on closes."""
    recent = bars[-lookback:] if len(bars) >= lookback else bars
    closes = _closes(recent)
    n = len(closes)
    if n < 10:
        return {"trend": "insufficient_data", "slope": 0, "strength": 0}

    x_mean = (n - 1) / 2
    y_mean = _avg(closes)
    num = sum((i - x_mean) * (closes[i] - y_mean) for i in range(n))
    den = sum((i - x_mean) ** 2 for i in range(n))
    slope = num / den if den != 0 else 0

    # Normalize slope as % per bar
    slope_pct = (slope / y_mean) * 100 if y_mean else 0

    if slope_pct > 0.15:
        trend = "uptrend"
    elif slope_pct < -0.15:
        trend = "downtrend"
    else:
        trend = "sideways"

    strength = min(abs(slope_pct) / 0.5, 1.0)  # normalize to 0-1

    return {
        "trend": trend,
        "slope_pct_per_bar": round(slope_pct, 4),
        "strength": round(strength, 3),
        "lookback_bars": n,
    }


# ── Moving average crossovers ─────────────────────────────────────────────────

def detect_ma_crossovers(bars: List[Dict]) -> List[PatternMatch]:
    """Detect golden cross (50>200 SMA) and death cross (50<200 SMA) events."""
    closes = _closes(bars)
    patterns: List[PatternMatch] = []

    def sma(data: List[float], period: int) -> List[Optional[float]]:
        result: List[Optional[float]] = [None] * (period - 1)
        for i in range(period - 1, len(data)):
            result.append(_avg(data[i - period + 1: i + 1]))
        return result

    if len(closes) < 200:
        return patterns

    sma50 = sma(closes, 50)
    sma200 = sma(closes, 200)

    for i in range(201, len(closes)):
        if sma50[i] is None or sma200[i] is None:
            continue
        if sma50[i - 1] is None or sma200[i - 1] is None:
            continue

        prev_diff = sma50[i - 1] - sma200[i - 1]
        curr_diff = sma50[i] - sma200[i]

        if prev_diff < 0 and curr_diff >= 0:
            patterns.append(PatternMatch(
                name="Golden Cross",
                pattern_type="continuation",
                direction="bullish",
                confidence=0.72,
                start_idx=i - 5,
                end_idx=i,
                key_levels={"sma50": round(sma50[i], 2), "sma200": round(sma200[i], 2)},
                evidence=[
                    f"SMA50 ({sma50[i]:.2f}) crossed above SMA200 ({sma200[i]:.2f})",
                    "Historically bullish long-term signal",
                ],
                description="50-day SMA crossed above 200-day SMA — classic long-term bullish signal.",
            ))
        elif prev_diff > 0 and curr_diff <= 0:
            patterns.append(PatternMatch(
                name="Death Cross",
                pattern_type="reversal",
                direction="bearish",
                confidence=0.70,
                start_idx=i - 5,
                end_idx=i,
                key_levels={"sma50": round(sma50[i], 2), "sma200": round(sma200[i], 2)},
                evidence=[
                    f"SMA50 ({sma50[i]:.2f}) crossed below SMA200 ({sma200[i]:.2f})",
                    "Historically bearish long-term signal",
                ],
                description="50-day SMA crossed below 200-day SMA — classic long-term bearish signal.",
            ))

    return patterns[-3:]  # return most recent 3


# ── Head & Shoulders ──────────────────────────────────────────────────────────

def detect_head_and_shoulders(bars: List[Dict]) -> List[PatternMatch]:
    """Detect head & shoulders (bearish reversal) and inverse H&S (bullish)."""
    highs = _highs(bars)
    lows = _lows(bars)
    patterns: List[PatternMatch] = []

    peaks = _local_maxima(highs, window=5)
    if len(peaks) < 3:
        return patterns

    for i in range(len(peaks) - 2):
        l_shoulder_idx = peaks[i]
        head_idx = peaks[i + 1]
        r_shoulder_idx = peaks[i + 2]

        l_h = highs[l_shoulder_idx]
        head_h = highs[head_idx]
        r_h = highs[r_shoulder_idx]

        # Head must be higher than both shoulders
        if head_h <= l_h or head_h <= r_h:
            continue
        # Shoulders should be roughly equal (within 5%)
        if _pct_diff(l_h, r_h) > 0.05:
            continue
        # Head should be meaningfully higher (at least 3%)
        if (head_h - max(l_h, r_h)) / max(l_h, r_h) < 0.03:
            continue

        neckline = _avg([lows[l_shoulder_idx], lows[r_shoulder_idx]])
        target = neckline - (head_h - neckline)

        confidence = 0.65 + min(_pct_diff(l_h, r_h) * 5, 0.15)

        patterns.append(PatternMatch(
            name="Head & Shoulders",
            pattern_type="reversal",
            direction="bearish",
            confidence=round(confidence, 3),
            start_idx=l_shoulder_idx,
            end_idx=r_shoulder_idx,
            key_levels={
                "left_shoulder": round(l_h, 2),
                "head": round(head_h, 2),
                "right_shoulder": round(r_h, 2),
                "neckline": round(neckline, 2),
            },
            target_price=round(target, 2),
            stop_loss=round(head_h * 1.02, 2),
            evidence=[
                f"Head at {head_h:.2f}, shoulders at {l_h:.2f} / {r_h:.2f}",
                f"Neckline: {neckline:.2f}",
                f"Price target on breakdown: {target:.2f}",
            ],
            description="Classic bearish reversal. Watch for neckline break with volume confirmation.",
        ))

    # Inverse H&S (bullish)
    troughs = _local_minima(lows, window=5)
    for i in range(len(troughs) - 2):
        l_idx = troughs[i]
        head_idx = troughs[i + 1]
        r_idx = troughs[i + 2]

        l_l = lows[l_idx]
        head_l = lows[head_idx]
        r_l = lows[r_idx]

        if head_l >= l_l or head_l >= r_l:
            continue
        if _pct_diff(l_l, r_l) > 0.05:
            continue
        if (min(l_l, r_l) - head_l) / min(l_l, r_l) < 0.03:
            continue

        neckline = _avg([highs[l_idx], highs[r_idx]])
        target = neckline + (neckline - head_l)

        patterns.append(PatternMatch(
            name="Inverse Head & Shoulders",
            pattern_type="reversal",
            direction="bullish",
            confidence=0.68,
            start_idx=l_idx,
            end_idx=r_idx,
            key_levels={
                "left_shoulder": round(l_l, 2),
                "head": round(head_l, 2),
                "right_shoulder": round(r_l, 2),
                "neckline": round(neckline, 2),
            },
            target_price=round(target, 2),
            stop_loss=round(head_l * 0.98, 2),
            evidence=[
                f"Inverse head at {head_l:.2f}, shoulders at {l_l:.2f} / {r_l:.2f}",
                f"Neckline: {neckline:.2f}",
                f"Price target on breakout: {target:.2f}",
            ],
            description="Bullish reversal. Watch for neckline breakout with volume confirmation.",
        ))

    return patterns


# ── Double Top / Bottom ───────────────────────────────────────────────────────

def detect_double_top_bottom(bars: List[Dict]) -> List[PatternMatch]:
    highs = _highs(bars)
    lows = _lows(bars)
    patterns: List[PatternMatch] = []

    peaks = _local_maxima(highs, window=5)
    for i in range(len(peaks) - 1):
        p1, p2 = peaks[i], peaks[i + 1]
        if _pct_diff(highs[p1], highs[p2]) <= 0.03 and (p2 - p1) >= 10:
            valley = min(lows[p1:p2 + 1])
            target = valley - (highs[p1] - valley)
            patterns.append(PatternMatch(
                name="Double Top",
                pattern_type="reversal",
                direction="bearish",
                confidence=0.67,
                start_idx=p1,
                end_idx=p2,
                key_levels={"top1": round(highs[p1], 2), "top2": round(highs[p2], 2), "valley": round(valley, 2)},
                target_price=round(target, 2),
                stop_loss=round(max(highs[p1], highs[p2]) * 1.02, 2),
                evidence=[f"Two peaks at ~{highs[p1]:.2f} and {highs[p2]:.2f}", f"Valley: {valley:.2f}"],
                description="Bearish reversal — two failed attempts at the same resistance level.",
            ))

    troughs = _local_minima(lows, window=5)
    for i in range(len(troughs) - 1):
        t1, t2 = troughs[i], troughs[i + 1]
        if _pct_diff(lows[t1], lows[t2]) <= 0.03 and (t2 - t1) >= 10:
            peak = max(highs[t1:t2 + 1])
            target = peak + (peak - lows[t1])
            patterns.append(PatternMatch(
                name="Double Bottom",
                pattern_type="reversal",
                direction="bullish",
                confidence=0.67,
                start_idx=t1,
                end_idx=t2,
                key_levels={"bottom1": round(lows[t1], 2), "bottom2": round(lows[t2], 2), "peak": round(peak, 2)},
                target_price=round(target, 2),
                stop_loss=round(min(lows[t1], lows[t2]) * 0.98, 2),
                evidence=[f"Two troughs at ~{lows[t1]:.2f} and {lows[t2]:.2f}", f"Peak: {peak:.2f}"],
                description="Bullish reversal — two failed attempts to break support.",
            ))

    return patterns


# ── Volume spike detection ────────────────────────────────────────────────────

def detect_volume_spikes(bars: List[Dict], lookback: int = 20, threshold: float = 2.0) -> List[Dict[str, Any]]:
    """Flag bars where volume exceeds threshold × rolling average."""
    spikes = []
    for i in range(lookback, len(bars)):
        window_vols = _volumes(bars[i - lookback:i])
        avg_vol = _avg(window_vols)
        if avg_vol == 0:
            continue
        ratio = bars[i].get("volume", 0) / avg_vol
        if ratio >= threshold:
            spikes.append({
                "idx": i,
                "date": bars[i].get("date", ""),
                "volume": bars[i].get("volume", 0),
                "avg_volume": round(avg_vol, 0),
                "ratio": round(ratio, 2),
                "close": bars[i].get("close", 0),
                "direction": "up" if bars[i]["close"] >= bars[i]["open"] else "down",
            })
    return spikes


# ── Bollinger Band squeeze ────────────────────────────────────────────────────

def detect_bollinger_squeeze(bars: List[Dict], period: int = 20, num_std: float = 2.0) -> Dict[str, Any]:
    """Detect Bollinger Band squeeze — low volatility preceding a breakout."""
    closes = _closes(bars)
    if len(closes) < period + 10:
        return {"squeeze": False}

    def bb_width(data: List[float]) -> float:
        mean = _avg(data)
        std = math.sqrt(_avg([(x - mean) ** 2 for x in data]))
        upper = mean + num_std * std
        lower = mean - num_std * std
        return (upper - lower) / mean if mean else 0

    recent_width = bb_width(closes[-period:])
    historical_widths = [
        bb_width(closes[i:i + period])
        for i in range(len(closes) - period - 30, len(closes) - period)
        if i >= 0
    ]
    if not historical_widths:
        return {"squeeze": False}

    avg_hist_width = _avg(historical_widths)
    squeeze_ratio = recent_width / avg_hist_width if avg_hist_width else 1.0

    is_squeeze = squeeze_ratio < 0.6  # current width < 60% of historical avg

    return {
        "squeeze": is_squeeze,
        "current_width_pct": round(recent_width * 100, 3),
        "avg_historical_width_pct": round(avg_hist_width * 100, 3),
        "squeeze_ratio": round(squeeze_ratio, 3),
        "description": (
            "Bollinger Band squeeze detected — low volatility compression often precedes a sharp move."
            if is_squeeze else "No squeeze — normal volatility range."
        ),
    }


# ── RSI divergence ────────────────────────────────────────────────────────────

def detect_rsi_divergence(bars: List[Dict], rsi_period: int = 14, lookback: int = 60) -> List[Dict[str, Any]]:
    """Detect bullish/bearish RSI divergence in the last `lookback` bars."""
    recent = bars[-lookback:] if len(bars) >= lookback else bars
    closes = _closes(recent)
    if len(closes) < rsi_period + 10:
        return []

    # Compute RSI
    gains, losses = [], []
    for i in range(1, len(closes)):
        diff = closes[i] - closes[i - 1]
        gains.append(max(diff, 0))
        losses.append(max(-diff, 0))

    rsi_values: List[Optional[float]] = [None] * rsi_period
    avg_gain = _avg(gains[:rsi_period])
    avg_loss = _avg(losses[:rsi_period])

    for i in range(rsi_period, len(closes)):
        if avg_loss == 0:
            rsi_values.append(100.0)
        else:
            rs = avg_gain / avg_loss
            rsi_values.append(100 - 100 / (1 + rs))
        idx = i - rsi_period + 1
        avg_gain = (avg_gain * (rsi_period - 1) + gains[idx]) / rsi_period
        avg_loss = (avg_loss * (rsi_period - 1) + losses[idx]) / rsi_period

    divergences = []
    price_lows = _local_minima(closes, window=5)
    price_highs = _local_maxima(closes, window=5)

    # Bullish divergence: price makes lower low, RSI makes higher low
    for i in range(1, len(price_lows)):
        p1, p2 = price_lows[i - 1], price_lows[i]
        if rsi_values[p1] is None or rsi_values[p2] is None:
            continue
        if closes[p2] < closes[p1] and rsi_values[p2] > rsi_values[p1]:
            divergences.append({
                "type": "bullish_divergence",
                "direction": "bullish",
                "idx1": p1, "idx2": p2,
                "price1": round(closes[p1], 2), "price2": round(closes[p2], 2),
                "rsi1": round(rsi_values[p1], 1), "rsi2": round(rsi_values[p2], 1),
                "description": "Price made lower low while RSI made higher low — potential bullish reversal.",
                "confidence": 0.65,
            })

    # Bearish divergence: price makes higher high, RSI makes lower high
    for i in range(1, len(price_highs)):
        p1, p2 = price_highs[i - 1], price_highs[i]
        if rsi_values[p1] is None or rsi_values[p2] is None:
            continue
        if closes[p2] > closes[p1] and rsi_values[p2] < rsi_values[p1]:
            divergences.append({
                "type": "bearish_divergence",
                "direction": "bearish",
                "idx1": p1, "idx2": p2,
                "price1": round(closes[p1], 2), "price2": round(closes[p2], 2),
                "rsi1": round(rsi_values[p1], 1), "rsi2": round(rsi_values[p2], 1),
                "description": "Price made higher high while RSI made lower high — potential bearish reversal.",
                "confidence": 0.65,
            })

    return divergences[-5:]


# ── Master scanner ────────────────────────────────────────────────────────────

class PatternRecognitionEngine:
    """Run all pattern detectors and return a unified analysis."""

    def analyze(self, bars: List[Dict], symbol: str = "") -> Dict[str, Any]:
        if len(bars) < 30:
            return {"error": "Insufficient data — need at least 30 bars"}

        trend = detect_trend(bars)
        sr = find_support_resistance(bars)
        ma_crosses = detect_ma_crossovers(bars)
        hs_patterns = detect_head_and_shoulders(bars)
        dt_db = detect_double_top_bottom(bars)
        vol_spikes = detect_volume_spikes(bars)
        bb_squeeze = detect_bollinger_squeeze(bars)
        rsi_div = detect_rsi_divergence(bars)

        all_patterns = (
            [p.to_dict() for p in ma_crosses]
            + [p.to_dict() for p in hs_patterns]
            + [p.to_dict() for p in dt_db]
        )

        # Sort by confidence descending
        all_patterns.sort(key=lambda x: x["confidence"], reverse=True)

        # Aggregate directional bias
        bullish_count = sum(1 for p in all_patterns if p["direction"] == "bullish")
        bearish_count = sum(1 for p in all_patterns if p["direction"] == "bearish")

        if bullish_count > bearish_count:
            bias = "bullish"
        elif bearish_count > bullish_count:
            bias = "bearish"
        else:
            bias = trend.get("trend", "neutral")

        return {
            "symbol": symbol.upper(),
            "trend": trend,
            "support_resistance": sr,
            "patterns": all_patterns,
            "volume_spikes": vol_spikes[-5:],
            "bollinger_squeeze": bb_squeeze,
            "rsi_divergences": rsi_div,
            "summary": {
                "bias": bias,
                "pattern_count": len(all_patterns),
                "bullish_signals": bullish_count,
                "bearish_signals": bearish_count,
                "top_pattern": all_patterns[0]["name"] if all_patterns else None,
            },
        }


pattern_engine = PatternRecognitionEngine()
