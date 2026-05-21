"""Signal weight optimizer.

Runs the simulation engine iteratively, treating signal weights as parameters
to optimize. Each generation:
  1. Runs the simulation with the current weight set
  2. Scores the result (win rate + avg P&L composite)
  3. Generates N mutated children by perturbing each weight
  4. Keeps the best child as the next generation's parent
  5. Records the convergence history

After convergence (or max generations), the best weights are persisted to the
signal_weights table and used for all future simulations on that symbol.

Algorithm: hill-climbing with random restarts — simple, fast, interpretable.
No black-box ML; every weight change is traceable to a specific signal.
"""
from __future__ import annotations

import copy
import json
import math
import random
import uuid
from datetime import datetime
from typing import Any, AsyncGenerator, Dict, List, Optional, Tuple

import aiosqlite

from app.db.database import get_db
from app.services.historical_simulation import (
    DEFAULT_WEIGHTS,
    WeightMap,
    run_simulation,
)

# ── Optimizer config ──────────────────────────────────────────────────────────

# Weight bounds — prevent degenerate solutions
WEIGHT_BOUNDS: Dict[str, Tuple[float, float]] = {
    "sma20":          (0.0, 3.0),
    "sma_cross":      (0.0, 3.0),
    "sma200":         (0.0, 2.0),
    "rsi_extreme":    (0.0, 4.0),
    "rsi_mild":       (0.0, 3.0),
    "macd_cross":     (0.0, 3.0),
    "macd_accel":     (0.0, 2.0),
    "bb_band":        (0.0, 3.0),
    "volume_confirm": (0.0, 2.5),
    "momentum_5bar":  (0.0, 2.0),
    "edge_threshold": (0.2, 1.5),
}

# Fitness: multi-objective — win rate, avg P&L, directional balance, calibration
def _fitness(result: Dict[str, Any]) -> float:
    total = result.get("total_predictions", 0)
    completed = result.get("wins", 0) + result.get("losses", 0)
    if total == 0 or completed < 10:
        return 0.0

    # Penalise if too many neutrals (model is being too conservative)
    neutral_rate = (total - completed) / total
    if neutral_rate > 0.80:
        return 0.0

    wr = result.get("win_rate") or 0.0
    avg_pnl = result.get("avg_pnl_pct") or 0.0

    # Directional balance: reward models that work for both calls AND puts
    by_dir = result.get("by_direction", {})
    call_wr = (by_dir.get("call") or {}).get("win_rate") or 0.0
    put_wr  = (by_dir.get("put")  or {}).get("win_rate") or 0.0
    call_n  = (by_dir.get("call") or {}).get("total", 0)
    put_n   = (by_dir.get("put")  or {}).get("total", 0)
    # Penalise if one direction has < 5 trades (not enough to trust)
    if call_n < 5 or put_n < 5:
        balance_score = 0.0
    else:
        # Reward when both directions are above 50%
        balance_score = min(call_wr, put_wr)

    # Calibration bonus: reward when high-confidence predictions win more
    calibration = result.get("calibration", [])
    cal_bonus = 0.0
    if len(calibration) >= 2:
        # Check if win rate increases with confidence buckets
        rates = [b["actual_win_rate"] for b in calibration]
        if rates == sorted(rates):  # monotonically increasing
            cal_bonus = 3.0

    # P&L score normalised to 0-100
    pnl_score = min(100.0, max(0.0, avg_pnl * 10 + 50))

    # Composite: 55% win rate + 20% P&L + 20% balance + 5% calibration
    return 0.55 * wr + 0.20 * pnl_score + 0.20 * balance_score + cal_bonus


def _diversity_penalty(candidate: Dict[str, float], population: List[Dict[str, float]],
                        threshold: float = 0.05) -> float:
    """
    Return a small penalty if this candidate is too similar to existing population members.
    Encourages exploration of diverse weight configurations.
    """
    if not population:
        return 0.0
    keys = list(candidate.keys())
    for member in population:
        dist = sum(abs(candidate.get(k, 0) - member.get(k, 0)) for k in keys) / len(keys)
        if dist < threshold:
            return -2.0  # penalty for near-duplicate
    return 0.0


def _clamp(val: float, key: str) -> float:
    lo, hi = WEIGHT_BOUNDS.get(key, (0.0, 5.0))
    return round(max(lo, min(hi, val)), 4)


def _mutate(weights: WeightMap, temperature: float) -> WeightMap:
    """Perturb weights by Gaussian noise scaled by temperature (0–1)."""
    child = {}
    for k, v in weights.items():
        sigma = temperature * 0.4 * (WEIGHT_BOUNDS.get(k, (0, 2))[1] - WEIGHT_BOUNDS.get(k, (0, 2))[0])
        child[k] = _clamp(v + random.gauss(0, max(sigma, 0.01)), k)
    return child


def _random_weights() -> WeightMap:
    """Generate a random weight set within bounds — used for restarts."""
    return {
        k: _clamp(random.uniform(lo, hi), k)
        for k, (lo, hi) in WEIGHT_BOUNDS.items()
    }


# ── Main optimizer ────────────────────────────────────────────────────────────

async def optimize_weights(
    bars: List[Dict[str, Any]],
    symbol: str,
    horizon_days: int = 20,
    sample_every: int = 10,
    max_generations: int = 40,
    children_per_gen: int = 8,
    patience: int = 8,
    live_predictions: Optional[List[Dict[str, Any]]] = None,
    seed: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Iteratively optimize signal weights for a symbol.

    Returns:
        best_weights, baseline_result, best_result, convergence history,
        all generation snapshots.
    """
    if seed is not None:
        random.seed(seed)

    # ── Baseline: run with default weights ──
    baseline = run_simulation(
        bars, symbol,
        horizon_days=horizon_days,
        sample_every=sample_every,
        live_predictions=live_predictions,
        weights=DEFAULT_WEIGHTS,
    )
    baseline_fitness = _fitness(baseline)
    baseline_wr = baseline.get("win_rate") or 0.0

    # ── Load previously learned weights as starting point if available ──
    saved = await _load_active_weights(symbol)
    current_weights = saved if saved else copy.deepcopy(DEFAULT_WEIGHTS)

    best_weights = copy.deepcopy(current_weights)
    best_result = run_simulation(
        bars, symbol,
        horizon_days=horizon_days,
        sample_every=sample_every,
        live_predictions=live_predictions,
        weights=current_weights,
    )
    best_fitness = _fitness(best_result)

    convergence: List[Dict[str, Any]] = [{
        "generation": 0,
        "win_rate": best_result.get("win_rate"),
        "avg_pnl": best_result.get("avg_pnl_pct"),
        "fitness": round(best_fitness, 3),
        "weights": copy.deepcopy(current_weights),
        "improved": True,
    }]

    no_improve_streak = 0
    temperature = 1.0  # starts high (explore), anneals down (exploit)
    # Population of elite weight sets for diversity pressure
    elite_population: List[WeightMap] = [copy.deepcopy(current_weights)]

    for gen in range(1, max_generations + 1):
        # Anneal temperature: linear decay
        temperature = max(0.05, 1.0 - (gen / max_generations) * 0.95)

        # Generate children — mix of mutations from current + elite members
        candidates: List[Tuple[float, WeightMap, Dict]] = []
        for ci in range(children_per_gen):
            # Every 3rd child mutates from a random elite member (diversity)
            parent = random.choice(elite_population) if (ci % 3 == 2 and len(elite_population) > 1) else current_weights
            child_w = _mutate(parent, temperature)
            child_result = run_simulation(
                bars, symbol,
                horizon_days=horizon_days,
                sample_every=sample_every,
                live_predictions=live_predictions,
                weights=child_w,
            )
            raw_fit = _fitness(child_result)
            div_pen = _diversity_penalty(child_w, elite_population)
            candidates.append((raw_fit + div_pen, child_w, child_result, raw_fit))

        # Pick best child
        candidates.sort(key=lambda x: x[0], reverse=True)
        best_child_fitness_adj, best_child_w, best_child_result, best_child_raw = candidates[0]

        improved = best_child_raw > best_fitness
        if improved:
            best_fitness = best_child_raw
            best_weights = copy.deepcopy(best_child_w)
            best_result = best_child_result
            current_weights = copy.deepcopy(best_child_w)
            no_improve_streak = 0
            # Add to elite population (keep top 5)
            elite_population.append(copy.deepcopy(best_child_w))
            if len(elite_population) > 5:
                elite_population.pop(0)
        else:
            no_improve_streak += 1
            # Accept slightly worse solution occasionally (simulated annealing)
            delta = best_child_raw - best_fitness
            accept_prob = math.exp(delta / max(temperature * 10, 0.01))
            if random.random() < accept_prob * 0.3:
                current_weights = copy.deepcopy(best_child_w)

        convergence.append({
            "generation": gen,
            "win_rate": best_result.get("win_rate"),
            "avg_pnl": best_result.get("avg_pnl_pct"),
            "fitness": round(best_fitness, 3),
            "temperature": round(temperature, 3),
            "improved": improved,
            "weights": copy.deepcopy(best_weights),
        })

        # Random restart if stuck
        if no_improve_streak >= patience:
            current_weights = _random_weights()
            no_improve_streak = 0

        # Early stop: fitness plateaued for 2× patience
        if no_improve_streak >= patience * 2:
            break

    # ── Compute weight deltas vs baseline ──
    weight_changes = {
        k: {
            "baseline": round(DEFAULT_WEIGHTS.get(k, 0), 4),
            "optimized": round(best_weights.get(k, 0), 4),
            "delta": round(best_weights.get(k, 0) - DEFAULT_WEIGHTS.get(k, 0), 4),
        }
        for k in DEFAULT_WEIGHTS
    }

    # Sort by absolute delta to surface biggest changes
    top_changes = sorted(
        weight_changes.items(),
        key=lambda x: abs(x[1]["delta"]),
        reverse=True,
    )

    improvement_pct = (
        round((best_result.get("win_rate", 0) - baseline_wr) / max(baseline_wr, 1) * 100, 1)
        if baseline_wr else None
    )

    return {
        "symbol": symbol,
        "generations_run": len(convergence) - 1,
        "baseline": {
            "win_rate": baseline.get("win_rate"),
            "avg_pnl_pct": baseline.get("avg_pnl_pct"),
            "total_predictions": baseline.get("total_predictions"),
            "weights": DEFAULT_WEIGHTS,
        },
        "optimized": {
            "win_rate": best_result.get("win_rate"),
            "avg_pnl_pct": best_result.get("avg_pnl_pct"),
            "total_predictions": best_result.get("total_predictions"),
            "weights": best_weights,
        },
        "improvement_pct": improvement_pct,
        "weight_changes": dict(top_changes),
        "top_changed_signals": [k for k, _ in top_changes[:5]],
        "convergence": convergence,
        "full_simulation": best_result,
    }


# ── Persistence ───────────────────────────────────────────────────────────────

async def save_optimized_weights(
    symbol: str,
    weights: WeightMap,
    win_rate: Optional[float],
    avg_pnl: Optional[float],
    total_trades: int,
    generation: int,
    notes: str = "",
) -> str:
    """Deactivate old weights and save new best weights for a symbol."""
    run_id = str(uuid.uuid4())
    now = datetime.utcnow().isoformat()
    async with get_db() as db:
        # Deactivate previous active weights
        await db.execute(
            "UPDATE signal_weights SET is_active = 0 WHERE symbol = ?",
            (symbol.upper(),),
        )
        # Insert new active weights
        await db.execute(
            """
            INSERT INTO signal_weights
                (id, symbol, weights, generation, win_rate, avg_pnl_pct,
                 total_trades, is_active, created_at, notes)
            VALUES (?, ?, ?, ?, ?, ?, ?, 1, ?, ?)
            """,
            (run_id, symbol.upper(), json.dumps(weights),
             generation, win_rate, avg_pnl, total_trades, now, notes),
        )
        await db.commit()
    return run_id


async def save_optimization_run(
    symbol: str,
    years: int,
    horizon_days: int,
    result: Dict[str, Any],
) -> str:
    """Persist the full optimization run for audit and replay."""
    run_id = str(uuid.uuid4())
    now = datetime.utcnow().isoformat()
    # Trim convergence to save space — keep every 5th generation + last
    conv = result.get("convergence", [])
    slim_conv = [
        {k: v for k, v in c.items() if k != "weights"}  # strip weights from history
        for i, c in enumerate(conv)
        if i % 5 == 0 or i == len(conv) - 1
    ]
    async with get_db() as db:
        await db.execute(
            """
            INSERT INTO optimization_runs
                (id, symbol, years, horizon_days, generations, best_win_rate,
                 baseline_win_rate, improvement_pct, convergence, best_weights, completed_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                run_id, symbol.upper(), years, horizon_days,
                result.get("generations_run", 0),
                result["optimized"].get("win_rate"),
                result["baseline"].get("win_rate"),
                result.get("improvement_pct"),
                json.dumps(slim_conv),
                json.dumps(result["optimized"]["weights"]),
                now,
            ),
        )
        await db.commit()
    return run_id


async def _load_active_weights(symbol: str) -> Optional[WeightMap]:
    """Load the most recently saved active weights for a symbol."""
    try:
        async with get_db() as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                """
                SELECT weights FROM signal_weights
                WHERE symbol = ? AND is_active = 1
                ORDER BY created_at DESC LIMIT 1
                """,
                (symbol.upper(),),
            )
            row = await cursor.fetchone()
        if row:
            return json.loads(row["weights"])
    except Exception:
        pass
    return None


async def load_active_weights(symbol: str) -> WeightMap:
    """Public: return active weights or defaults."""
    saved = await _load_active_weights(symbol)
    return saved if saved else copy.deepcopy(DEFAULT_WEIGHTS)


async def get_optimization_history(symbol: str, limit: int = 10) -> List[Dict[str, Any]]:
    """Return past optimization runs for a symbol."""
    async with get_db() as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            """
            SELECT id, symbol, years, horizon_days, generations,
                   best_win_rate, baseline_win_rate, improvement_pct,
                   best_weights, completed_at
            FROM optimization_runs
            WHERE symbol = ?
            ORDER BY completed_at DESC
            LIMIT ?
            """,
            (symbol.upper(), limit),
        )
        rows = await cursor.fetchall()
    return [
        {
            "id": r["id"],
            "symbol": r["symbol"],
            "years": r["years"],
            "horizon_days": r["horizon_days"],
            "generations": r["generations"],
            "best_win_rate": r["best_win_rate"],
            "baseline_win_rate": r["baseline_win_rate"],
            "improvement_pct": r["improvement_pct"],
            "best_weights": json.loads(r["best_weights"]),
            "completed_at": r["completed_at"],
        }
        for r in rows
    ]


async def reset_weights(symbol: str) -> None:
    """Deactivate all learned weights — revert to defaults."""
    async with get_db() as db:
        await db.execute(
            "UPDATE signal_weights SET is_active = 0 WHERE symbol = ?",
            (symbol.upper(),),
        )
        await db.commit()


signal_optimizer = type(
    "_Opt", (),
    {
        "optimize": staticmethod(optimize_weights),
        "save_weights": staticmethod(save_optimized_weights),
        "save_run": staticmethod(save_optimization_run),
        "load_weights": staticmethod(load_active_weights),
        "history": staticmethod(get_optimization_history),
        "reset": staticmethod(reset_weights),
    }
)()
