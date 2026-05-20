"""Model refinement service.

After each prediction is scored, this service:
1. Updates rolling accuracy stats in model_accuracy table per signal key
2. Recomputes confidence adjustment multipliers
3. Exposes a summary for the /market/model-stats endpoint and system prompt injection
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

import aiosqlite

from app.db.database import get_db

# Signal keys tracked — must match historical_simulation.py signal_stats keys
SIGNAL_KEYS = [
    "rsi_oversold", "rsi_overbought",
    "macd_bullish", "macd_bearish",
    "bb_lower", "bb_upper",
    "high_volume", "overall",
]

WINDOW_DAYS = [30, 90, 365]  # rolling windows to track


async def refresh_model_accuracy(symbol: str) -> Dict[str, Any]:
    """
    Recompute rolling accuracy for all signal keys for a symbol.
    Called after predictions are scored.
    """
    symbol = symbol.upper()
    now = datetime.utcnow()
    results: Dict[str, Any] = {}

    async with get_db() as db:
        db.row_factory = aiosqlite.Row

        for window in WINDOW_DAYS:
            cutoff = (now - timedelta(days=window)).isoformat()

            # Fetch completed predictions in window
            cursor = await db.execute(
                """
                SELECT predicted_direction, outcome_status, pnl_pct,
                       feature_snapshot, confidence, created_at
                FROM prediction_events
                WHERE symbol = ?
                  AND outcome_status IN ('win', 'loss')
                  AND created_at >= ?
                ORDER BY created_at DESC
                """,
                (symbol, cutoff),
            )
            rows = await cursor.fetchall()
            if not rows:
                continue

            # Overall accuracy
            total = len(rows)
            wins = sum(1 for r in rows if r["outcome_status"] == "win")
            pnls = [r["pnl_pct"] for r in rows if r["pnl_pct"] is not None]
            avg_pnl = round(sum(pnls) / len(pnls), 2) if pnls else None
            win_rate = round(wins / total * 100, 1) if total else None
            conf_adj = _compute_adj(wins, total)

            await _upsert_accuracy(db, symbol, "overall", "all", window,
                                   total, wins, win_rate, avg_pnl, conf_adj, now)

            # Per-direction
            for direction in ("call", "put", "neutral"):
                ds = [r for r in rows if r["predicted_direction"] == direction]
                if not ds:
                    continue
                dw = sum(1 for r in ds if r["outcome_status"] == "win")
                dpnls = [r["pnl_pct"] for r in ds if r["pnl_pct"] is not None]
                dwr = round(dw / len(ds) * 100, 1)
                davg = round(sum(dpnls) / len(dpnls), 2) if dpnls else None
                dadj = _compute_adj(dw, len(ds))
                await _upsert_accuracy(db, symbol, "overall", direction, window,
                                       len(ds), dw, dwr, davg, dadj, now)

            # Per-signal-key (from feature_snapshot)
            for sig_key in SIGNAL_KEYS[:-1]:  # skip 'overall'
                sig_rows = []
                for r in rows:
                    snap = json.loads(r["feature_snapshot"] or "{}")
                    tech = snap.get("technicals", {})
                    if _row_has_signal(sig_key, tech, r["predicted_direction"]):
                        sig_rows.append(r)
                if len(sig_rows) < 3:
                    continue
                sw = sum(1 for r in sig_rows if r["outcome_status"] == "win")
                spnls = [r["pnl_pct"] for r in sig_rows if r["pnl_pct"] is not None]
                swr = round(sw / len(sig_rows) * 100, 1)
                savg = round(sum(spnls) / len(spnls), 2) if spnls else None
                sadj = _compute_adj(sw, len(sig_rows))
                await _upsert_accuracy(db, symbol, sig_key, "all", window,
                                       len(sig_rows), sw, swr, savg, sadj, now)

            results[f"{window}d"] = {
                "total": total, "wins": wins, "win_rate": win_rate,
                "avg_pnl": avg_pnl, "conf_adj": conf_adj,
            }

        await db.commit()

    return results


def _compute_adj(wins: int, total: int) -> float:
    """Confidence multiplier: nudge up if strong, down if weak, neutral otherwise."""
    if total < 4:
        return 1.0
    rate = wins / total
    if rate >= 0.65:
        return round(min(1.20, 1.0 + (rate - 0.65) * 2.0), 3)
    if rate <= 0.35:
        return round(max(0.75, 1.0 - (0.35 - rate) * 2.0), 3)
    return 1.0


def _row_has_signal(sig_key: str, tech: Dict, direction: str) -> bool:
    rsi = tech.get("rsi")
    macd = tech.get("macd")
    macd_sig = tech.get("macd_signal")
    if sig_key == "rsi_oversold"   and rsi and rsi < 40 and direction == "call": return True
    if sig_key == "rsi_overbought" and rsi and rsi > 60 and direction == "put":  return True
    if sig_key == "macd_bullish"   and macd and macd_sig and macd > macd_sig and direction == "call": return True
    if sig_key == "macd_bearish"   and macd and macd_sig and macd < macd_sig and direction == "put":  return True
    return False


async def _upsert_accuracy(
    db: aiosqlite.Connection,
    symbol: str, sig_key: str, direction: str, window: int,
    total: int, wins: int, win_rate: Optional[float],
    avg_pnl: Optional[float], conf_adj: float, now: datetime,
) -> None:
    await db.execute(
        """
        INSERT INTO model_accuracy
            (id, symbol, signal_key, direction, window_days, total, wins,
             win_rate, avg_pnl_pct, confidence_adj, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(symbol, signal_key, direction, window_days) DO UPDATE SET
            total = excluded.total,
            wins = excluded.wins,
            win_rate = excluded.win_rate,
            avg_pnl_pct = excluded.avg_pnl_pct,
            confidence_adj = excluded.confidence_adj,
            updated_at = excluded.updated_at
        """,
        (str(uuid.uuid4()), symbol, sig_key, direction, window,
         total, wins, win_rate, avg_pnl, conf_adj, now.isoformat()),
    )


async def get_model_stats(symbol: str) -> Dict[str, Any]:
    """Return full model accuracy stats for a symbol — used by API and system prompt."""
    symbol = symbol.upper()
    async with get_db() as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            """
            SELECT signal_key, direction, window_days, total, wins,
                   win_rate, avg_pnl_pct, confidence_adj, updated_at
            FROM model_accuracy
            WHERE symbol = ?
            ORDER BY window_days, signal_key, direction
            """,
            (symbol,),
        )
        rows = await cursor.fetchall()

    stats: Dict[str, Any] = {"symbol": symbol, "windows": {}}
    for r in rows:
        w = str(r["window_days"]) + "d"
        if w not in stats["windows"]:
            stats["windows"][w] = {}
        key = f"{r['signal_key']}:{r['direction']}"
        stats["windows"][w][key] = {
            "total": r["total"],
            "wins": r["wins"],
            "win_rate": r["win_rate"],
            "avg_pnl_pct": r["avg_pnl_pct"],
            "confidence_adj": r["confidence_adj"],
            "updated_at": r["updated_at"],
        }

    # Best signal in 90d window
    best = None
    for key, v in stats["windows"].get("90d", {}).items():
        if v["total"] >= 4 and (best is None or (v["win_rate"] or 0) > (best[1]["win_rate"] or 0)):
            best = (key, v)
    stats["best_signal_90d"] = {"key": best[0], **best[1]} if best else None

    # Overall 90d adj
    overall = stats["windows"].get("90d", {}).get("overall:all")
    stats["overall_confidence_adj"] = overall["confidence_adj"] if overall else 1.0
    stats["overall_win_rate_90d"] = overall["win_rate"] if overall else None

    return stats


async def get_global_model_summary() -> Dict[str, Any]:
    """Cross-symbol model summary for system prompt injection."""
    async with get_db() as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            """
            SELECT symbol, win_rate, avg_pnl_pct, confidence_adj, total, updated_at
            FROM model_accuracy
            WHERE signal_key = 'overall' AND direction = 'all' AND window_days = 90
            ORDER BY total DESC
            LIMIT 20
            """,
        )
        rows = await cursor.fetchall()

    symbols = []
    for r in rows:
        symbols.append({
            "symbol": r["symbol"],
            "win_rate_90d": r["win_rate"],
            "avg_pnl_90d": r["avg_pnl_pct"],
            "confidence_adj": r["confidence_adj"],
            "total_predictions": r["total"],
        })

    best = max(symbols, key=lambda x: x["win_rate_90d"] or 0) if symbols else None
    worst = min(symbols, key=lambda x: x["win_rate_90d"] or 100) if symbols else None

    return {
        "tracked_symbols": len(symbols),
        "symbols": symbols,
        "best_performing": best,
        "worst_performing": worst,
    }


model_refinement_service = type(
    "_Svc", (),
    {
        "refresh": staticmethod(refresh_model_accuracy),
        "get_stats": staticmethod(get_model_stats),
        "get_global_summary": staticmethod(get_global_model_summary),
    }
)()
