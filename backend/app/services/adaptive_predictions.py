"""Adaptive options prediction journal.

The engine turns current technical context into a call/put/neutral thesis,
stores each materially new thesis, and scores older theses against subsequent
price action. The learning loop is deliberately transparent and conservative:
it adjusts confidence from observed outcomes, but never claims certainty.
"""
from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

import aiosqlite

from app.db.database import get_db


DISCLAIMER = (
    "Adaptive predictions are probabilistic research signals, not guarantees "
    "or financial advice. Options can lose 100% of premium paid."
)


@dataclass
class DirectionStats:
    total: int = 0
    wins: int = 0
    losses: int = 0

    @property
    def win_rate(self) -> Optional[float]:
        if self.total == 0:
            return None
        return round(self.wins / self.total * 100, 1)

    @property
    def factor(self) -> float:
        if self.total < 4:
            return 1.0
        rate = self.wins / self.total
        if rate >= 0.62:
            return 1.08
        if rate <= 0.38:
            return 0.88
        return 1.0


class AdaptivePredictionService:
    """Generate, persist, and review Nexus options predictions."""

    horizon_days = 30
    min_move_pct = 0.01

    async def build_prediction(
        self,
        symbol: str,
        quote: Dict[str, Any],
        technicals: Dict[str, Any],
        patterns: Dict[str, Any],
        bars: List[Dict[str, Any]],
        session_id: str = "console",
        event_intelligence: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        symbol = symbol.upper()
        await self._score_due_predictions(symbol, bars)

        stats = await self._performance(symbol)
        raw = self._score_current_setup(quote, technicals, patterns, event_intelligence)
        adjusted = self._apply_learning_adjustment(raw, stats)
        await self._store_if_new(symbol, adjusted, quote, technicals, patterns, session_id, event_intelligence)
        updated_stats = await self._performance(symbol)

        return {
            "symbol": symbol,
            "prediction": adjusted,
            "review": updated_stats,
            "disclaimer": DISCLAIMER,
        }

    def _score_current_setup(
        self,
        quote: Dict[str, Any],
        technicals: Dict[str, Any],
        patterns: Dict[str, Any],
        event_intelligence: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        price = float(quote.get("price") or quote.get("close") or 0)
        bullish = 0.0
        bearish = 0.0
        rationale: List[str] = []
        risks: List[str] = []

        summary = patterns.get("summary", {}) if patterns else {}
        bullish += float(summary.get("bullish_signals") or 0) * 0.7
        bearish += float(summary.get("bearish_signals") or 0) * 0.7
        bias = summary.get("bias")
        if bias == "bullish":
            bullish += 1.2
            rationale.append("Pattern stack currently leans bullish.")
        elif bias == "bearish":
            bearish += 1.2
            rationale.append("Pattern stack currently leans bearish.")

        rsi = technicals.get("rsi")
        if rsi is not None:
            if rsi < 35:
                bullish += 1.1
                rationale.append(f"RSI {rsi:.1f} is oversold, which can support a call/bounce thesis.")
            elif rsi > 65:
                bearish += 1.1
                rationale.append(f"RSI {rsi:.1f} is overbought, which can support a put/pullback thesis.")

        macd = technicals.get("macd")
        macd_signal = technicals.get("macd_signal")
        if macd is not None and macd_signal is not None:
            if macd > macd_signal:
                bullish += 0.9
                rationale.append("MACD is above signal, showing bullish momentum.")
            else:
                bearish += 0.9
                rationale.append("MACD is below signal, showing bearish momentum.")

        sma50 = technicals.get("sma_50")
        sma200 = technicals.get("sma_200")
        if price and sma50 and sma200:
            if price > sma50 > sma200:
                bullish += 1.3
                rationale.append("Price is above SMA50 and SMA200 in bullish alignment.")
            elif price < sma50 < sma200:
                bearish += 1.3
                rationale.append("Price is below SMA50 and SMA200 in bearish alignment.")
                risks.append("Trend alignment can persist longer than expected.")

        squeeze = patterns.get("bollinger_squeeze", {}) if patterns else {}
        if squeeze.get("squeeze"):
            rationale.append("Bollinger squeeze is active, so direction may expand quickly after confirmation.")
            risks.append("Compression setups can break either direction.")

        event_composite = (event_intelligence or {}).get("composite", {})
        event_bias = event_composite.get("bias")
        event_confidence = float(event_composite.get("confidence") or 0)
        event_scores = event_composite.get("raw_scores", {})
        event_weight = min(2.0, max(event_confidence, 0) * 2.2)
        if event_bias == "bullish":
            bullish += event_weight
            rationale.append("News/social event intelligence leans bullish for calls.")
        elif event_bias == "bearish":
            bearish += event_weight
            rationale.append("News/social event intelligence leans bearish for puts.")
        elif event_bias == "volatility":
            bullish += event_weight * 0.35
            bearish += event_weight * 0.35
            rationale.append("Event intelligence favors volatility; directional conviction should be confirmed.")
            risks.append("Event-driven volatility can reward either calls or puts depending on the break.")
        if event_scores:
            risks.append(
                "Event signal mix: "
                f"bullish {event_scores.get('bullish', 0)}, "
                f"bearish {event_scores.get('bearish', 0)}, "
                f"volatility {event_scores.get('volatility', 0)}."
            )

        edge = bullish - bearish
        total_signal = max(bullish + bearish, 1.0)
        if abs(edge) < 0.8:
            direction = "neutral"
            confidence = 0.42
            target = None
            stop = None
            rationale.append("Bullish and bearish evidence is close; waiting for confirmation is favored.")
        elif edge > 0:
            direction = "call"
            confidence = min(0.82, 0.48 + min(abs(edge) / total_signal, 1) * 0.34)
            target = price * (1 + max(0.03, min(abs(edge) * 0.012, 0.12))) if price else None
            stop = price * 0.96 if price else None
        else:
            direction = "put"
            confidence = min(0.82, 0.48 + min(abs(edge) / total_signal, 1) * 0.34)
            target = price * (1 - max(0.03, min(abs(edge) * 0.012, 0.12))) if price else None
            stop = price * 1.04 if price else None

        return {
            "direction": direction,
            "option_type": None if direction == "neutral" else direction,
            "confidence": round(confidence, 2),
            "horizon_days": self.horizon_days,
            "entry_price": round(price, 2) if price else 0,
            "target_price": round(target, 2) if target else None,
            "stop_loss": round(stop, 2) if stop else None,
            "raw_scores": {"bullish": round(bullish, 2), "bearish": round(bearish, 2)},
            "rationale": rationale[:6],
            "risks": risks[:5],
        }

    def _apply_learning_adjustment(
        self,
        prediction: Dict[str, Any],
        performance: Dict[str, Any],
    ) -> Dict[str, Any]:
        direction = prediction["direction"]
        direction_stats = performance.get("by_direction", {}).get(direction)
        factor = direction_stats.get("learning_factor", 1.0) if direction_stats else 1.0

        # Streak factor: recent consecutive wins/losses amplify adjustment
        streak = performance.get("current_streak", {})
        streak_dir = streak.get("direction")
        streak_len = streak.get("length", 0)
        streak_type = streak.get("type")  # "win" or "loss"
        streak_mult = 1.0
        if streak_dir == direction and streak_len >= 3:
            if streak_type == "win":
                streak_mult = min(1.15, 1.0 + streak_len * 0.03)
            elif streak_type == "loss":
                streak_mult = max(0.82, 1.0 - streak_len * 0.04)

        combined_factor = round(factor * streak_mult, 3)
        adjusted = {**prediction}
        adjusted["confidence"] = round(max(0.25, min(0.88, prediction["confidence"] * combined_factor)), 2)
        adjusted["learning_adjustment"] = {
            "factor": round(factor, 2),
            "streak_mult": round(streak_mult, 2),
            "combined_factor": combined_factor,
            "reason": self._factor_reason(direction, direction_stats, streak),
        }
        return adjusted

    def _factor_reason(self, direction: str, stats: Optional[Dict[str, Any]],
                       streak: Optional[Dict[str, Any]] = None) -> str:
        parts = []
        if not stats or stats.get("total", 0) < 4:
            parts.append(f"Not enough completed {direction} predictions for a strong adjustment yet.")
        else:
            rate = stats.get("win_rate")
            f = stats.get("learning_factor", 1.0)
            if f > 1:
                parts.append(f"Recent {direction} predictions are working ({rate}% win rate) — confidence nudged up.")
            elif f < 1:
                parts.append(f"Recent {direction} predictions underperformed ({rate}% win rate) — confidence reduced.")
            else:
                parts.append(f"Completed {direction} predictions are balanced ({rate}% win rate).")

        if streak and streak.get("direction") == direction and streak.get("length", 0) >= 3:
            stype = streak.get("type", "")
            slen = streak.get("length", 0)
            if stype == "win":
                parts.append(f"On a {slen}-prediction win streak — momentum boost applied.")
            elif stype == "loss":
                parts.append(f"On a {slen}-prediction loss streak — caution applied.")

        return " ".join(parts)

    async def _store_if_new(
        self,
        symbol: str,
        prediction: Dict[str, Any],
        quote: Dict[str, Any],
        technicals: Dict[str, Any],
        patterns: Dict[str, Any],
        session_id: str,
        event_intelligence: Optional[Dict[str, Any]] = None,
    ) -> None:
        price = prediction.get("entry_price") or 0
        if price <= 0:
            return

        async with get_db() as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                """
                SELECT predicted_direction, entry_price, confidence, created_at
                FROM prediction_events
                WHERE symbol = ?
                ORDER BY created_at DESC
                LIMIT 1
                """,
                (symbol,),
            )
            last = await cursor.fetchone()
            if last:
                created = datetime.fromisoformat(last["created_at"])
                price_delta = abs(price - float(last["entry_price"])) / max(price, 1)
                same_direction = last["predicted_direction"] == prediction["direction"]
                if same_direction and price_delta < 0.015 and datetime.utcnow() - created < timedelta(days=3):
                    return

            await db.execute(
                """
                INSERT INTO prediction_events (
                    id, session_id, symbol, created_at, horizon_days, entry_price,
                    predicted_direction, confidence, target_price, stop_loss,
                    feature_snapshot, rationale
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(uuid.uuid4()),
                    session_id,
                    symbol,
                    datetime.utcnow().isoformat(),
                    prediction["horizon_days"],
                    price,
                    prediction["direction"],
                    prediction["confidence"],
                    prediction.get("target_price"),
                    prediction.get("stop_loss"),
                    json.dumps({
                        "quote": quote,
                        "technicals": technicals,
                        "patterns_summary": patterns.get("summary", {}),
                        "event_intelligence": (event_intelligence or {}).get("composite", {}),
                    }),
                    json.dumps(prediction.get("rationale", [])),
                ),
            )
            await db.commit()

    async def _score_due_predictions(self, symbol: str, bars: List[Dict[str, Any]]) -> None:
        if not bars:
            return

        async with get_db() as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                """
                SELECT * FROM prediction_events
                WHERE symbol = ? AND outcome_status = 'pending'
                ORDER BY created_at ASC
                """,
                (symbol,),
            )
            rows = await cursor.fetchall()

            for row in rows:
                created = datetime.fromisoformat(row["created_at"])
                due_at = created + timedelta(days=int(row["horizon_days"]))
                if datetime.utcnow() < due_at:
                    continue

                exit_bar = self._first_bar_on_or_after(bars, due_at)
                if not exit_bar:
                    continue

                exit_price = float(exit_bar["close"])
                entry_price = float(row["entry_price"])
                direction = row["predicted_direction"]
                move_pct = (exit_price - entry_price) / entry_price if entry_price else 0
                if direction == "call":
                    pnl_pct = move_pct * 100
                    won = move_pct >= self.min_move_pct
                elif direction == "put":
                    pnl_pct = -move_pct * 100
                    won = move_pct <= -self.min_move_pct
                else:
                    pnl_pct = -abs(move_pct) * 100
                    won = abs(move_pct) <= 0.02

                status = "win" if won else "loss"
                notes = self._mistake_notes(direction, move_pct, row["feature_snapshot"]) if not won else []
                await db.execute(
                    """
                    UPDATE prediction_events
                    SET outcome_status = ?, outcome_checked_at = ?, exit_price = ?,
                        pnl_pct = ?, mistake_notes = ?
                    WHERE id = ?
                    """,
                    (
                        status,
                        datetime.utcnow().isoformat(),
                        round(exit_price, 2),
                        round(pnl_pct, 2),
                        json.dumps(notes),
                        row["id"],
                    ),
                )
            await db.commit()

    def _first_bar_on_or_after(
        self,
        bars: List[Dict[str, Any]],
        due_at: datetime,
    ) -> Optional[Dict[str, Any]]:
        due_date = due_at.date().isoformat()
        for bar in bars:
            if bar.get("date", "") >= due_date:
                return bar
        return None

    def _mistake_notes(self, direction: str, move_pct: float, snapshot_json: str) -> List[str]:
        snapshot = json.loads(snapshot_json or "{}")
        tech = snapshot.get("technicals", {})
        event_intel = snapshot.get("event_intelligence", {})
        notes = []

        # Core failure reason
        if direction == "call" and move_pct < 0:
            severity = "sharply" if move_pct < -5 else "modestly"
            notes.append(f"Bullish thesis failed — underlying moved {severity} lower ({move_pct:+.1f}%).")
        elif direction == "put" and move_pct > 0:
            severity = "sharply" if move_pct > 5 else "modestly"
            notes.append(f"Bearish thesis failed — underlying moved {severity} higher ({move_pct:+.1f}%).")
        elif direction == "neutral":
            notes.append(f"Neutral thesis failed — price expanded {abs(move_pct):.1f}% beyond the quiet range.")

        # RSI context
        rsi = tech.get("rsi")
        if rsi is not None:
            if 45 <= rsi <= 55:
                notes.append("RSI was mid-range at entry — setup lacked directional conviction.")
            elif direction == "call" and rsi > 65:
                notes.append("RSI was already elevated at entry — overbought conditions may have capped upside.")
            elif direction == "put" and rsi < 35:
                notes.append("RSI was already oversold at entry — bounce risk was elevated.")

        # Trend alignment
        sma50 = tech.get("sma_50")
        sma200 = tech.get("sma_200")
        price_at_entry = snapshot.get("quote", {}).get("price")
        if sma50 and sma200 and price_at_entry:
            if direction == "call" and float(price_at_entry) < float(sma50):
                notes.append("Price was below SMA50 at entry — trend was not aligned with the bullish thesis.")
            elif direction == "put" and float(price_at_entry) > float(sma50):
                notes.append("Price was above SMA50 at entry — trend was not aligned with the bearish thesis.")

        # Event intelligence conflict
        event_bias = event_intel.get("bias")
        if event_bias and event_bias != "neutral":
            if (direction == "call" and event_bias == "bearish") or (direction == "put" and event_bias == "bullish"):
                notes.append(f"Event intelligence was {event_bias} at entry — conflicted with the {direction} thesis.")

        if not sma50 or not sma200:
            notes.append("Moving-average context was incomplete — confidence should stay conservative in future.")

        return notes[:5]

    async def _performance(self, symbol: str) -> Dict[str, Any]:
        async with get_db() as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                """
                SELECT * FROM prediction_events
                WHERE symbol = ?
                ORDER BY created_at DESC
                LIMIT 200
                """,
                (symbol,),
            )
            rows = await cursor.fetchall()

        completed = [r for r in rows if r["outcome_status"] in ("win", "loss", "flat")]
        pending = [r for r in rows if r["outcome_status"] == "pending"]
        wins = [r for r in completed if r["outcome_status"] == "win"]
        losses = [r for r in completed if r["outcome_status"] == "loss"]

        by_direction = {}
        for direction in ("call", "put", "neutral"):
            ds = DirectionStats()
            for row in completed:
                if row["predicted_direction"] != direction:
                    continue
                ds.total += 1
                if row["outcome_status"] == "win":
                    ds.wins += 1
                elif row["outcome_status"] == "loss":
                    ds.losses += 1
            by_direction[direction] = {
                "total": ds.total,
                "wins": ds.wins,
                "losses": ds.losses,
                "win_rate": ds.win_rate,
                "learning_factor": round(ds.factor, 2),
            }

        recent_mistakes = []
        for row in losses[:5]:
            recent_mistakes.append({
                "created_at": row["created_at"],
                "direction": row["predicted_direction"],
                "confidence": row["confidence"],
                "entry_price": row["entry_price"],
                "exit_price": row["exit_price"],
                "pnl_pct": row["pnl_pct"],
                "notes": json.loads(row["mistake_notes"] or "[]"),
            })

        recent_predictions = []
        for row in rows[:10]:
            recent_predictions.append({
                "created_at": row["created_at"],
                "direction": row["predicted_direction"],
                "confidence": row["confidence"],
                "entry_price": row["entry_price"],
                "target_price": row["target_price"],
                "stop_loss": row["stop_loss"],
                "outcome_status": row["outcome_status"],
                "exit_price": row["exit_price"],
                "pnl_pct": row["pnl_pct"],
            })

        # ── Current streak ──
        current_streak = self._compute_streak(completed)

        # ── Best/worst confidence bands ──
        confidence_analysis = self._analyze_confidence_bands(completed)

        # ── Avg hold P&L by direction ──
        avg_pnl_by_dir = {}
        for direction in ("call", "put", "neutral"):
            dp = [r for r in completed if r["predicted_direction"] == direction and r["pnl_pct"] is not None]
            if dp:
                avg_pnl_by_dir[direction] = round(sum(float(r["pnl_pct"]) for r in dp) / len(dp), 2)

        return {
            "completed": len(completed),
            "pending": len(pending),
            "wins": len(wins),
            "losses": len(losses),
            "win_rate": round(len(wins) / len(completed) * 100, 1) if completed else None,
            "by_direction": by_direction,
            "current_streak": current_streak,
            "confidence_analysis": confidence_analysis,
            "avg_pnl_by_direction": avg_pnl_by_dir,
            "recent_mistakes": recent_mistakes,
            "recent_predictions": recent_predictions,
        }

    def _compute_streak(self, completed: list) -> Dict[str, Any]:
        """Find the current consecutive win/loss streak across all directions."""
        if not completed:
            return {"type": None, "length": 0, "direction": None}
        # completed is ordered DESC by created_at
        streak_type = completed[0]["outcome_status"]
        streak_dir = completed[0]["predicted_direction"]
        length = 0
        for row in completed:
            if row["outcome_status"] == streak_type and row["predicted_direction"] == streak_dir:
                length += 1
            else:
                break
        return {"type": streak_type, "length": length, "direction": streak_dir}

    def _analyze_confidence_bands(self, completed: list) -> List[Dict[str, Any]]:
        """Break predictions into confidence buckets and show actual accuracy per band."""
        buckets = [(0.25, 0.50, "25-50%"), (0.50, 0.65, "50-65%"),
                   (0.65, 0.75, "65-75%"), (0.75, 0.88, "75-88%")]
        result = []
        for lo, hi, label in buckets:
            band = [r for r in completed if lo <= float(r["confidence"]) < hi]
            if not band:
                continue
            wins_b = sum(1 for r in band if r["outcome_status"] == "win")
            result.append({
                "band": label,
                "total": len(band),
                "wins": wins_b,
                "actual_win_rate": round(wins_b / len(band) * 100, 1),
                "calibrated": abs(wins_b / len(band) - (lo + hi) / 2) < 0.12,
            })
        return result


adaptive_prediction_service = AdaptivePredictionService()
