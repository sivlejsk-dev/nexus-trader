"""High-level Nexus decision synthesis.

This layer turns the lower-level prediction, technical, participation, and
event signals into one simple answer that can be reused by voice, chat, and UI.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional


DISCLAIMER = (
    "Nexus decisions are research signals for education, not financial advice. "
    "Confirm the setup and manage risk before any trade."
)


class NexusDecisionEngine:
    """Create a compact action plan from a full market analysis payload."""

    def build_decision(self, analysis: Dict[str, Any]) -> Dict[str, Any]:
        symbol = analysis.get("symbol", "")
        quote = analysis.get("quote") or {}
        price = _num(quote.get("price") or quote.get("close"))
        prediction = ((analysis.get("adaptive_prediction") or {}).get("prediction") or {})
        reasoning = analysis.get("reasoning") or {}
        participation = analysis.get("participation") or {}
        patterns = analysis.get("patterns") or {}
        event_composite = ((analysis.get("event_intelligence") or {}).get("composite") or {})

        direction = prediction.get("direction") or "neutral"
        if direction not in {"call", "put", "neutral"}:
            direction = "neutral"

        confidence = _num(prediction.get("confidence"), default=0.42)
        confidence = _blend_confidence(confidence, reasoning.get("confidence"))

        drivers: List[str] = []
        warnings: List[str] = []
        contradictions = 0

        for item in (prediction.get("rationale") or [])[:3]:
            if item not in drivers:
                drivers.append(item)

        pattern_bias = ((patterns.get("summary") or {}).get("bias") or "neutral").lower()
        if pattern_bias in {"bullish", "bearish"}:
            drivers.append(f"Pattern stack leans {pattern_bias}.")
            if _conflicts(direction, pattern_bias):
                contradictions += 1
                warnings.append(f"Pattern bias conflicts with the {direction} thesis.")

        if participation.get("available"):
            impact = participation.get("outcome_impact") or {}
            impact_direction = (impact.get("direction") or "neutral").lower()
            label = str(participation.get("pressure_label") or "balanced").replace("_", " ")
            buy_pct = participation.get("buy_volume_pct")
            sell_pct = participation.get("sell_volume_pct")
            drivers.append(f"Participation reads {label}: {buy_pct}% estimated buying versus {sell_pct}% estimated selling.")
            if impact_direction in {"bullish", "bearish"} and _conflicts(direction, impact_direction):
                contradictions += 1
                confidence -= 0.08
                warnings.append("Buy/sell participation is fighting the thesis.")
            elif impact_direction in {"bullish", "bearish"}:
                confidence += min(0.05, _num(participation.get("conviction")) * 0.06)
            for risk in impact.get("risks", [])[:2]:
                if risk not in warnings:
                    warnings.append(risk)

        event_bias = (event_composite.get("bias") or "neutral").lower()
        event_confidence = _num(event_composite.get("confidence"))
        if event_bias in {"bullish", "bearish", "volatility"}:
            drivers.append(f"Event intelligence reads {event_bias} with {int(event_confidence * 100)}% confidence.")
            if event_bias in {"bullish", "bearish"} and _conflicts(direction, event_bias):
                contradictions += 1
                confidence -= 0.06
                warnings.append("Event intelligence does not confirm the thesis.")
            elif event_bias in {"bullish", "bearish"}:
                confidence += min(0.04, event_confidence * 0.04)
            elif event_bias == "volatility":
                warnings.append("Event risk may move price sharply in either direction.")

        for risk in (prediction.get("risks") or [])[:3]:
            if risk not in warnings:
                warnings.append(risk)

        confidence = round(max(0.18, min(0.9, confidence)), 2)
        action = self._choose_action(direction, confidence, contradictions, price)

        target = prediction.get("target_price")
        stop = prediction.get("stop_loss")
        reason = _build_reason(action, direction, confidence, drivers, contradictions)
        best_next_step = _best_next_step(action, direction, target, stop)

        return {
            "symbol": symbol,
            "action": action,
            "direction": direction,
            "confidence": confidence,
            "confidence_pct": int(round(confidence * 100)),
            "reason": reason,
            "target": target,
            "stop": stop,
            "entry_price": prediction.get("entry_price") or price,
            "best_next_step": best_next_step,
            "risk": _risk_summary(warnings, contradictions),
            "drivers": drivers[:5],
            "warnings": warnings[:5],
            "contradictions": contradictions,
            "disclaimer": DISCLAIMER,
        }

    @staticmethod
    def _choose_action(direction: str, confidence: float, contradictions: int, price: Optional[float]) -> str:
        if not price:
            return "wait"
        if direction == "neutral":
            return "wait" if confidence >= 0.35 else "avoid"
        if contradictions >= 2:
            return "avoid"
        if confidence >= 0.67 and contradictions == 0:
            return "buy"
        if confidence >= 0.52:
            return "watch"
        if confidence <= 0.36:
            return "avoid"
        return "wait"


def _num(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _blend_confidence(prediction_confidence: float, reasoning_confidence: Any) -> float:
    if reasoning_confidence is None:
        return prediction_confidence
    return prediction_confidence * 0.78 + _num(reasoning_confidence, prediction_confidence) * 0.22


def _conflicts(direction: str, bias: str) -> bool:
    return (direction == "call" and bias == "bearish") or (direction == "put" and bias == "bullish")


def _build_reason(
    action: str,
    direction: str,
    confidence: float,
    drivers: List[str],
    contradictions: int,
) -> str:
    direction_text = {"call": "calls/upside", "put": "puts/downside", "neutral": "no clear direction"}[direction]
    action_text = {
        "buy": "Nexus sees a tradable setup",
        "watch": "Nexus sees a possible setup, but wants confirmation",
        "wait": "Nexus does not see a clean entry yet",
        "avoid": "Nexus sees too much conflict for a clean trade",
    }[action]
    conflict_text = f" There are {contradictions} conflicting major signals." if contradictions else ""
    driver_text = f" Main driver: {drivers[0]}" if drivers else ""
    return f"{action_text} for {direction_text} with {int(confidence * 100)}% confidence.{driver_text}{conflict_text}".strip()


def _best_next_step(action: str, direction: str, target: Any, stop: Any) -> str:
    if action == "buy":
        side = "call" if direction == "call" else "put"
        risk = f" Use the stop near {stop} and target near {target}." if target and stop else " Define target and stop before entry."
        return f"Confirm price is still moving with the thesis, then compare liquid {side} contracts or a defined-risk spread.{risk}"
    if action == "watch":
        return "Set an alert at the confirmation level and wait for volume plus price to agree before entering."
    if action == "avoid":
        return "Skip the trade until the conflicting signals clear or a new setup forms."
    return "Wait for a stronger directional break, then ask Nexus to re-check the symbol."


def _risk_summary(warnings: List[str], contradictions: int) -> str:
    if warnings:
        return warnings[0]
    if contradictions:
        return "Major signals conflict, so confidence is reduced."
    return "No single risk dominates, but this remains a probabilistic signal."


nexus_decision_engine = NexusDecisionEngine()
