"""What-if trade outcome simulation."""
from __future__ import annotations

import re
from typing import Any, Dict, Optional


class WhatIfService:
    """Estimate simple trade outcomes from current price, target, and stop."""

    def is_what_if_request(self, message: str) -> bool:
        text = message.lower()
        return bool(re.search(r"\b(what if|what-if|scenario|if .* goes? to|if .* hits?|risk.?reward|outcome)\b", text))

    def parse_request(self, message: str, quote: Dict[str, Any], decision: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        text = message.lower().replace(",", "")
        current_price = _num(quote.get("price") or quote.get("close"))
        decision = decision or {}
        explicit_direction = "put" if "put" in text or "short" in text else "call" if "call" in text or "long" in text else None
        direction = explicit_direction or decision.get("direction") or "call"
        if direction not in {"call", "put", "neutral"}:
            direction = "call"

        numbers = [float(n) for n in re.findall(r"(?<![\w.])\$?(\d+(?:\.\d+)?)", text)]
        plausible_prices = [n for n in numbers if current_price and current_price * 0.35 <= n <= current_price * 1.8]
        target = _num(decision.get("target"), default=None)
        stop = _num(decision.get("stop"), default=None)

        if plausible_prices:
            target = plausible_prices[0]
        if len(plausible_prices) >= 2:
            stop = plausible_prices[1]
        stop_match = re.search(r"\bstop(?:\s+at|\s+near|\s+is)?\s+\$?(\d+(?:\.\d+)?)", text)
        target_match = re.search(r"\b(?:target|goes? to|hits?|reaches)\s+\$?(\d+(?:\.\d+)?)", text)
        if target_match:
            target = float(target_match.group(1))
        if stop_match:
            stop = float(stop_match.group(1))
        if explicit_direction is None and current_price and target is not None:
            direction = "call" if target > current_price else "put" if target < current_price else direction

        position_size = _extract_position_size(text)
        premium = _extract_premium(text)
        return {
            "direction": direction,
            "current_price": current_price,
            "target_price": target,
            "stop_price": stop,
            "position_size": position_size,
            "option_premium": premium,
        }

    def simulate(self, symbol: str, scenario: Dict[str, Any]) -> Dict[str, Any]:
        current = _num(scenario.get("current_price"))
        target = _num(scenario.get("target_price"), default=None)
        stop = _num(scenario.get("stop_price"), default=None)
        direction = scenario.get("direction") or "call"
        position_size = int(scenario.get("position_size") or 100)
        premium = _num(scenario.get("option_premium"), default=None)

        if not current:
            return {"symbol": symbol.upper(), "available": False, "summary": "No current price is available for this what-if."}
        if target is None:
            target = round(current * (1.04 if direction != "put" else 0.96), 2)
        if stop is None:
            stop = round(current * (0.97 if direction != "put" else 1.03), 2)

        target_move_pct = _move_pct(current, target)
        stop_move_pct = _move_pct(current, stop)
        if direction == "put":
            reward_pct = -target_move_pct
            risk_pct = max(0.0, stop_move_pct)
        else:
            reward_pct = target_move_pct
            risk_pct = max(0.0, -stop_move_pct)
        reward_pct = round(reward_pct, 2)
        risk_pct = round(risk_pct, 2)
        risk_reward = round(reward_pct / risk_pct, 2) if risk_pct > 0 else None

        stock_reward = round(abs(target - current) * position_size, 2)
        stock_risk = round(abs(current - stop) * position_size, 2)

        option_outcome = None
        if premium:
            contracts = max(1, position_size // 100)
            premium_at_risk = round(premium * 100 * contracts, 2)
            intrinsic_at_target = max(0.0, target - current) if direction == "call" else max(0.0, current - target)
            intrinsic_at_stop = max(0.0, stop - current) if direction == "call" else max(0.0, current - stop)
            est_target_value = round(intrinsic_at_target * 100 * contracts, 2)
            est_stop_value = round(intrinsic_at_stop * 100 * contracts, 2)
            option_outcome = {
                "contracts": contracts,
                "premium": premium,
                "premium_at_risk": premium_at_risk,
                "estimated_value_at_target": est_target_value,
                "estimated_value_at_stop": est_stop_value,
                "estimated_profit_at_target": round(est_target_value - premium_at_risk, 2),
                "estimated_loss_at_stop": round(est_stop_value - premium_at_risk, 2),
                "note": "Option estimate uses intrinsic value only; IV, time decay, and bid/ask spreads can materially change results.",
            }

        recommendation = "favorable" if risk_reward is not None and risk_reward >= 1.8 and reward_pct > 0 else "unfavorable"
        if risk_reward is not None and 1.0 <= risk_reward < 1.8:
            recommendation = "mixed"

        summary = (
            f"If {symbol.upper()} moves from {current:.2f} to {target:.2f}, the {direction} scenario has "
            f"about {reward_pct:.1f}% reward versus {risk_pct:.1f}% risk to {stop:.2f}."
        )
        return {
            "symbol": symbol.upper(),
            "available": True,
            "direction": direction,
            "current_price": round(current, 2),
            "target_price": round(target, 2),
            "stop_price": round(stop, 2),
            "reward_pct": reward_pct,
            "risk_pct": risk_pct,
            "risk_reward": risk_reward,
            "stock_reward": stock_reward,
            "stock_risk": stock_risk,
            "position_size": position_size,
            "option_outcome": option_outcome,
            "recommendation": recommendation,
            "summary": summary,
            "next_step": _next_step(recommendation),
            "disclaimer": "What-if simulations are simplified research estimates, not financial advice.",
        }


def _num(value: Any, default: Optional[float] = 0.0) -> Optional[float]:
    try:
        if value is None:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _move_pct(current: float, future: float) -> float:
    return (future - current) / current * 100 if current else 0.0


def _extract_position_size(text: str) -> int:
    shares = re.search(r"\b(\d+)\s+shares?\b", text)
    contracts = re.search(r"\b(\d+)\s+contracts?\b", text)
    if contracts:
        return max(100, int(contracts.group(1)) * 100)
    if shares:
        return max(1, int(shares.group(1)))
    return 100


def _extract_premium(text: str) -> Optional[float]:
    match = re.search(r"\b(?:premium|cost|paid|option)\s+(?:is|at|of)?\s*\$?(\d+(?:\.\d+)?)", text)
    return float(match.group(1)) if match else None


def _next_step(recommendation: str) -> str:
    if recommendation == "favorable":
        return "Confirm liquidity, event risk, and position size before considering the trade."
    if recommendation == "mixed":
        return "Improve the setup by finding a tighter stop, better entry, or higher-probability target."
    return "Wait or skip unless the target improves or the risk is reduced."


what_if_service = WhatIfService()
