"""
Core Reasoning Framework — adapted from Nexus for financial analysis.

Provides structured reasoning over market data: deductive (rule-based signals),
inductive (pattern-based), and abductive (best-explanation) modes.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple


class ReasoningMode(Enum):
    DEDUCTIVE = "deductive"    # Rule-based: if RSI > 70 → overbought
    INDUCTIVE = "inductive"    # Pattern-based: historical recurrence
    ABDUCTIVE = "abductive"    # Best explanation for observed price action
    COMPARATIVE = "comparative"  # Compare multiple instruments/strikes


class ConfidenceLevel(Enum):
    LOW = "low"          # < 40%
    MODERATE = "moderate"  # 40–65%
    HIGH = "high"        # 65–80%
    VERY_HIGH = "very_high"  # > 80%


@dataclass
class ReasoningStep:
    description: str
    evidence: List[str] = field(default_factory=list)
    confidence: float = 0.5
    mode: ReasoningMode = ReasoningMode.DEDUCTIVE


@dataclass
class ReasoningResult:
    conclusion: str
    steps: List[ReasoningStep] = field(default_factory=list)
    confidence: float = 0.5
    mode: ReasoningMode = ReasoningMode.DEDUCTIVE
    supporting_data: Dict[str, Any] = field(default_factory=dict)
    risks: List[str] = field(default_factory=list)
    disclaimer: str = (
        "This analysis is for informational purposes only and does not constitute "
        "financial advice. Options trading involves significant risk of loss. "
        "Always conduct your own research and consult a licensed financial advisor."
    )

    @property
    def confidence_level(self) -> ConfidenceLevel:
        if self.confidence < 0.4:
            return ConfidenceLevel.LOW
        elif self.confidence < 0.65:
            return ConfidenceLevel.MODERATE
        elif self.confidence < 0.80:
            return ConfidenceLevel.HIGH
        return ConfidenceLevel.VERY_HIGH

    def to_dict(self) -> Dict[str, Any]:
        return {
            "conclusion": self.conclusion,
            "confidence": self.confidence,
            "confidence_level": self.confidence_level.value,
            "mode": self.mode.value,
            "steps": [
                {
                    "description": s.description,
                    "evidence": s.evidence,
                    "confidence": s.confidence,
                }
                for s in self.steps
            ],
            "supporting_data": self.supporting_data,
            "risks": self.risks,
            "disclaimer": self.disclaimer,
        }


class MarketReasoningEngine:
    """
    Applies structured reasoning to market data and AI-generated analysis.

    Used to validate, structure, and enrich raw LLM responses with
    evidence-based reasoning chains before returning to the user.
    """

    # ── Technical signal rules ────────────────────────────────

    RSI_OVERBOUGHT = 70
    RSI_OVERSOLD = 30
    VOLUME_SPIKE_MULTIPLIER = 2.0  # 2x average = notable
    IV_PERCENTILE_HIGH = 75        # IV rank > 75 → elevated premium

    def analyze_technicals(self, data: Dict[str, Any]) -> ReasoningResult:
        """
        Apply deductive rules to technical indicator data.

        data keys: rsi, macd, macd_signal, volume, avg_volume,
                   price, sma_20, sma_50, sma_200, bb_upper, bb_lower
        """
        steps: List[ReasoningStep] = []
        signals: List[str] = []
        risks: List[str] = []
        confidence = 0.5

        rsi = data.get("rsi")
        if rsi is not None:
            if rsi > self.RSI_OVERBOUGHT:
                steps.append(ReasoningStep(
                    description=f"RSI at {rsi:.1f} — overbought territory",
                    evidence=[f"RSI={rsi:.1f} > {self.RSI_OVERBOUGHT}"],
                    confidence=0.7,
                    mode=ReasoningMode.DEDUCTIVE,
                ))
                signals.append("bearish_rsi")
                risks.append("Overbought RSI may indicate near-term pullback")
            elif rsi < self.RSI_OVERSOLD:
                steps.append(ReasoningStep(
                    description=f"RSI at {rsi:.1f} — oversold territory",
                    evidence=[f"RSI={rsi:.1f} < {self.RSI_OVERSOLD}"],
                    confidence=0.7,
                    mode=ReasoningMode.DEDUCTIVE,
                ))
                signals.append("bullish_rsi")

        macd = data.get("macd")
        macd_signal = data.get("macd_signal")
        if macd is not None and macd_signal is not None:
            if macd > macd_signal:
                steps.append(ReasoningStep(
                    description="MACD above signal line — bullish momentum",
                    evidence=[f"MACD={macd:.4f} > Signal={macd_signal:.4f}"],
                    confidence=0.65,
                    mode=ReasoningMode.DEDUCTIVE,
                ))
                signals.append("bullish_macd")
            else:
                steps.append(ReasoningStep(
                    description="MACD below signal line — bearish momentum",
                    evidence=[f"MACD={macd:.4f} < Signal={macd_signal:.4f}"],
                    confidence=0.65,
                    mode=ReasoningMode.DEDUCTIVE,
                ))
                signals.append("bearish_macd")

        volume = data.get("volume")
        avg_volume = data.get("avg_volume")
        if volume and avg_volume and avg_volume > 0:
            ratio = volume / avg_volume
            if ratio >= self.VOLUME_SPIKE_MULTIPLIER:
                steps.append(ReasoningStep(
                    description=f"Volume spike: {ratio:.1f}x average — institutional activity likely",
                    evidence=[f"Volume={volume:,} vs Avg={avg_volume:,}"],
                    confidence=0.75,
                    mode=ReasoningMode.INDUCTIVE,
                ))
                signals.append("volume_spike")

        price = data.get("price")
        sma_50 = data.get("sma_50")
        sma_200 = data.get("sma_200")
        if price and sma_50 and sma_200:
            if price > sma_50 > sma_200:
                steps.append(ReasoningStep(
                    description="Price above SMA50 > SMA200 — bullish trend alignment",
                    evidence=[f"Price={price:.2f} > SMA50={sma_50:.2f} > SMA200={sma_200:.2f}"],
                    confidence=0.72,
                    mode=ReasoningMode.DEDUCTIVE,
                ))
                signals.append("bullish_trend")
            elif price < sma_50 < sma_200:
                steps.append(ReasoningStep(
                    description="Price below SMA50 < SMA200 — bearish trend alignment",
                    evidence=[f"Price={price:.2f} < SMA50={sma_50:.2f} < SMA200={sma_200:.2f}"],
                    confidence=0.72,
                    mode=ReasoningMode.DEDUCTIVE,
                ))
                signals.append("bearish_trend")
                risks.append("Downtrend confirmed by moving average alignment")

        # Derive conclusion
        bullish = sum(1 for s in signals if s.startswith("bullish"))
        bearish = sum(1 for s in signals if s.startswith("bearish"))
        total = bullish + bearish

        if total == 0:
            conclusion = "Insufficient technical data for a directional signal."
            confidence = 0.3
        elif bullish > bearish:
            confidence = 0.5 + (bullish / max(total, 1)) * 0.35
            conclusion = f"Bullish bias ({bullish}/{total} signals). Consider call options or long positions."
        elif bearish > bullish:
            confidence = 0.5 + (bearish / max(total, 1)) * 0.35
            conclusion = f"Bearish bias ({bearish}/{total} signals). Consider put options or defensive positioning."
        else:
            conclusion = "Mixed signals — market direction unclear. Wait for confirmation."
            confidence = 0.4

        return ReasoningResult(
            conclusion=conclusion,
            steps=steps,
            confidence=min(confidence, 0.92),
            mode=ReasoningMode.DEDUCTIVE,
            supporting_data={"signals": signals},
            risks=risks,
        )

    def analyze_options_setup(self, data: Dict[str, Any]) -> ReasoningResult:
        """
        Reason about an options trade setup.

        data keys: option_type (call/put), strike, expiry_days, iv_rank,
                   delta, theta, gamma, vega, underlying_price, bid, ask
        """
        steps: List[ReasoningStep] = []
        risks: List[str] = []

        option_type = data.get("option_type", "call").lower()
        iv_rank = data.get("iv_rank", 50)
        delta = data.get("delta", 0.5)
        theta = data.get("theta", 0)
        expiry_days = data.get("expiry_days", 30)
        bid = data.get("bid", 0)
        ask = data.get("ask", 0)
        spread_pct = ((ask - bid) / ask * 100) if ask > 0 else 0

        # IV rank assessment
        if iv_rank > self.IV_PERCENTILE_HIGH:
            steps.append(ReasoningStep(
                description=f"IV Rank at {iv_rank:.0f}% — elevated premium, favor selling strategies",
                evidence=[f"IV Rank={iv_rank:.0f}% > {self.IV_PERCENTILE_HIGH}%"],
                confidence=0.75,
                mode=ReasoningMode.DEDUCTIVE,
            ))
            risks.append("High IV can collapse after catalyst events (IV crush)")
        else:
            steps.append(ReasoningStep(
                description=f"IV Rank at {iv_rank:.0f}% — normal/low premium, favor buying strategies",
                evidence=[f"IV Rank={iv_rank:.0f}% ≤ {self.IV_PERCENTILE_HIGH}%"],
                confidence=0.65,
                mode=ReasoningMode.DEDUCTIVE,
            ))

        # Delta assessment
        if abs(delta) > 0.7:
            steps.append(ReasoningStep(
                description=f"Deep ITM option (|delta|={abs(delta):.2f}) — high directional exposure",
                evidence=[f"|delta|={abs(delta):.2f} > 0.70"],
                confidence=0.8,
                mode=ReasoningMode.DEDUCTIVE,
            ))
        elif abs(delta) < 0.3:
            steps.append(ReasoningStep(
                description=f"OTM option (|delta|={abs(delta):.2f}) — lower probability, higher leverage",
                evidence=[f"|delta|={abs(delta):.2f} < 0.30"],
                confidence=0.8,
                mode=ReasoningMode.DEDUCTIVE,
            ))
            risks.append("OTM options expire worthless more often — size positions accordingly")

        # Theta decay
        if expiry_days < 14 and theta < -0.05:
            risks.append(f"Rapid theta decay with {expiry_days} DTE — time is working against long positions")

        # Spread quality
        if spread_pct > 5:
            risks.append(f"Wide bid-ask spread ({spread_pct:.1f}%) — liquidity risk, use limit orders")

        conclusion = (
            f"{'Call' if option_type == 'call' else 'Put'} option setup: "
            f"IV Rank {iv_rank:.0f}%, delta {delta:.2f}, {expiry_days} DTE. "
            f"{'Elevated IV favors premium selling.' if iv_rank > self.IV_PERCENTILE_HIGH else 'Normal IV favors directional buying.'}"
        )

        return ReasoningResult(
            conclusion=conclusion,
            steps=steps,
            confidence=0.65,
            mode=ReasoningMode.DEDUCTIVE,
            supporting_data=data,
            risks=risks,
        )

    def synthesize_multi_signal(
        self,
        technical: Optional[ReasoningResult],
        options: Optional[ReasoningResult],
        pattern: Optional[Dict[str, Any]],
    ) -> ReasoningResult:
        """Combine technical, options, and pattern signals into a unified view."""
        all_steps: List[ReasoningStep] = []
        all_risks: List[str] = []
        confidences: List[float] = []

        if technical:
            all_steps.extend(technical.steps)
            all_risks.extend(technical.risks)
            confidences.append(technical.confidence)

        if options:
            all_steps.extend(options.steps)
            all_risks.extend(options.risks)
            confidences.append(options.confidence)

        if pattern:
            all_steps.append(ReasoningStep(
                description=f"Pattern detected: {pattern.get('name', 'Unknown')} "
                            f"(historical win rate: {pattern.get('win_rate', 0):.0%})",
                evidence=pattern.get("evidence", []),
                confidence=pattern.get("confidence", 0.5),
                mode=ReasoningMode.INDUCTIVE,
            ))
            confidences.append(pattern.get("confidence", 0.5))

        avg_confidence = sum(confidences) / len(confidences) if confidences else 0.4

        conclusion = (
            "Multi-signal synthesis complete. "
            f"Aggregate confidence: {avg_confidence:.0%}. "
            "Review individual signals above before acting."
        )

        return ReasoningResult(
            conclusion=conclusion,
            steps=all_steps,
            confidence=avg_confidence,
            mode=ReasoningMode.COMPARATIVE,
            risks=list(set(all_risks)),
        )


# Singleton
reasoning_engine = MarketReasoningEngine()
