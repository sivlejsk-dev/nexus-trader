"""
Options Analysis Engine — Greeks, IV rank, unusual activity, strategy scoring.

Provides:
- Black-Scholes Greeks calculation (no external dependency)
- IV rank / IV percentile computation
- Options chain analysis and filtering
- Strategy recommendations based on market conditions
- Backtesting of options strategies on historical data
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple


# ── Black-Scholes ─────────────────────────────────────────────────────────────

def _norm_cdf(x: float) -> float:
    """Standard normal CDF via error function approximation."""
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))

def _norm_pdf(x: float) -> float:
    return math.exp(-0.5 * x * x) / math.sqrt(2 * math.pi)


def black_scholes(
    S: float,   # underlying price
    K: float,   # strike price
    T: float,   # time to expiry in years
    r: float,   # risk-free rate (e.g. 0.05)
    sigma: float,  # implied volatility (e.g. 0.25)
    option_type: str = "call",
) -> Dict[str, float]:
    """
    Compute Black-Scholes price and Greeks for a European option.
    Returns: price, delta, gamma, theta, vega, rho
    """
    if T <= 0 or sigma <= 0 or S <= 0 or K <= 0:
        return {"price": 0, "delta": 0, "gamma": 0, "theta": 0, "vega": 0, "rho": 0}

    d1 = (math.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * math.sqrt(T))
    d2 = d1 - sigma * math.sqrt(T)

    if option_type.lower() == "call":
        price = S * _norm_cdf(d1) - K * math.exp(-r * T) * _norm_cdf(d2)
        delta = _norm_cdf(d1)
        rho = K * T * math.exp(-r * T) * _norm_cdf(d2) / 100
    else:
        price = K * math.exp(-r * T) * _norm_cdf(-d2) - S * _norm_cdf(-d1)
        delta = _norm_cdf(d1) - 1
        rho = -K * T * math.exp(-r * T) * _norm_cdf(-d2) / 100

    gamma = _norm_pdf(d1) / (S * sigma * math.sqrt(T))
    vega = S * _norm_pdf(d1) * math.sqrt(T) / 100
    theta = (
        -(S * _norm_pdf(d1) * sigma) / (2 * math.sqrt(T))
        - r * K * math.exp(-r * T) * (_norm_cdf(d2) if option_type == "call" else _norm_cdf(-d2))
    ) / 365

    return {
        "price": round(price, 4),
        "delta": round(delta, 4),
        "gamma": round(gamma, 6),
        "theta": round(theta, 4),
        "vega": round(vega, 4),
        "rho": round(rho, 4),
        "d1": round(d1, 4),
        "d2": round(d2, 4),
    }


def implied_volatility(
    market_price: float,
    S: float,
    K: float,
    T: float,
    r: float,
    option_type: str = "call",
    max_iter: int = 100,
    tol: float = 1e-5,
) -> Optional[float]:
    """Newton-Raphson IV solver."""
    if T <= 0 or market_price <= 0:
        return None

    sigma = 0.3  # initial guess
    for _ in range(max_iter):
        bs = black_scholes(S, K, T, r, sigma, option_type)
        price = bs["price"]
        vega = bs["vega"] * 100  # un-normalize

        if abs(vega) < 1e-10:
            break

        diff = price - market_price
        if abs(diff) < tol:
            return round(sigma, 6)

        sigma -= diff / vega
        sigma = max(0.001, min(sigma, 10.0))  # clamp

    return round(sigma, 6)


# ── IV Rank / Percentile ──────────────────────────────────────────────────────

def compute_iv_rank(current_iv: float, iv_history: List[float]) -> Dict[str, float]:
    """
    IV Rank: where current IV sits relative to 52-week high/low.
    IV Percentile: % of days IV was below current level.
    """
    if not iv_history or current_iv <= 0:
        return {"iv_rank": 50.0, "iv_percentile": 50.0, "iv_52w_high": current_iv, "iv_52w_low": current_iv}

    iv_high = max(iv_history)
    iv_low = min(iv_history)

    if iv_high == iv_low:
        iv_rank = 50.0
    else:
        iv_rank = (current_iv - iv_low) / (iv_high - iv_low) * 100

    iv_percentile = sum(1 for iv in iv_history if iv < current_iv) / len(iv_history) * 100

    return {
        "iv_rank": round(iv_rank, 1),
        "iv_percentile": round(iv_percentile, 1),
        "iv_52w_high": round(iv_high, 4),
        "iv_52w_low": round(iv_low, 4),
        "current_iv": round(current_iv, 4),
    }


# ── Options strategy scoring ──────────────────────────────────────────────────

@dataclass
class StrategyScore:
    name: str
    direction: str          # bullish / bearish / neutral
    score: float            # 0-100
    rationale: List[str] = field(default_factory=list)
    max_profit: str = "unlimited"
    max_loss: str = "premium paid"
    breakeven: Optional[float] = None
    ideal_conditions: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "direction": self.direction,
            "score": round(self.score, 1),
            "rationale": self.rationale,
            "max_profit": self.max_profit,
            "max_loss": self.max_loss,
            "breakeven": self.breakeven,
            "ideal_conditions": self.ideal_conditions,
        }


def score_strategies(
    underlying_price: float,
    trend: str,           # "uptrend" / "downtrend" / "sideways"
    iv_rank: float,       # 0-100
    days_to_expiry: int,
    rsi: Optional[float] = None,
) -> List[StrategyScore]:
    """
    Score options strategies based on current market conditions.
    Returns strategies sorted by score descending.
    """
    strategies: List[StrategyScore] = []
    high_iv = iv_rank > 50
    low_iv = iv_rank < 30
    near_expiry = days_to_expiry < 21
    overbought = rsi is not None and rsi > 65
    oversold = rsi is not None and rsi < 35

    # ── Long Call ──────────────────────────────────────────────
    call_score = 0.0
    call_rationale = []
    if trend == "uptrend":
        call_score += 35
        call_rationale.append("Uptrend favors long calls")
    if low_iv:
        call_score += 30
        call_rationale.append(f"Low IV ({iv_rank:.0f}%) — cheap premium to buy")
    if oversold:
        call_score += 20
        call_rationale.append("Oversold RSI — potential bounce")
    if near_expiry:
        call_score -= 20
        call_rationale.append("Near expiry — theta decay accelerates")
    strategies.append(StrategyScore(
        name="Long Call",
        direction="bullish",
        score=max(0, call_score),
        rationale=call_rationale,
        max_profit="Unlimited",
        max_loss="Premium paid",
        ideal_conditions=["Low IV", "Strong uptrend", "30-60 DTE"],
    ))

    # ── Long Put ───────────────────────────────────────────────
    put_score = 0.0
    put_rationale = []
    if trend == "downtrend":
        put_score += 35
        put_rationale.append("Downtrend favors long puts")
    if low_iv:
        put_score += 30
        put_rationale.append(f"Low IV ({iv_rank:.0f}%) — cheap premium to buy")
    if overbought:
        put_score += 20
        put_rationale.append("Overbought RSI — potential pullback")
    if near_expiry:
        put_score -= 20
        put_rationale.append("Near expiry — theta decay accelerates")
    strategies.append(StrategyScore(
        name="Long Put",
        direction="bearish",
        score=max(0, put_score),
        rationale=put_rationale,
        max_profit="Strike - Premium",
        max_loss="Premium paid",
        ideal_conditions=["Low IV", "Strong downtrend", "30-60 DTE"],
    ))

    # ── Covered Call ───────────────────────────────────────────
    cc_score = 0.0
    cc_rationale = []
    if high_iv:
        cc_score += 40
        cc_rationale.append(f"High IV ({iv_rank:.0f}%) — collect elevated premium")
    if trend == "sideways":
        cc_score += 30
        cc_rationale.append("Sideways market — ideal for premium collection")
    if near_expiry:
        cc_score += 15
        cc_rationale.append("Near expiry — faster theta decay benefits seller")
    strategies.append(StrategyScore(
        name="Covered Call",
        direction="neutral/bullish",
        score=max(0, cc_score),
        rationale=cc_rationale,
        max_profit="Strike - Cost Basis + Premium",
        max_loss="Stock price - Premium",
        ideal_conditions=["High IV", "Sideways to slightly bullish", "Already long stock"],
    ))

    # ── Cash-Secured Put ───────────────────────────────────────
    csp_score = 0.0
    csp_rationale = []
    if high_iv:
        csp_score += 40
        csp_rationale.append(f"High IV ({iv_rank:.0f}%) — elevated premium")
    if trend in ("uptrend", "sideways"):
        csp_score += 25
        csp_rationale.append("Non-bearish trend reduces assignment risk")
    if oversold:
        csp_score += 20
        csp_rationale.append("Oversold — good entry for acquiring shares at discount")
    strategies.append(StrategyScore(
        name="Cash-Secured Put",
        direction="neutral/bullish",
        score=max(0, csp_score),
        rationale=csp_rationale,
        max_profit="Premium received",
        max_loss="Strike - Premium",
        ideal_conditions=["High IV", "Bullish/neutral bias", "Willing to own stock"],
    ))

    # ── Iron Condor ────────────────────────────────────────────
    ic_score = 0.0
    ic_rationale = []
    if high_iv:
        ic_score += 45
        ic_rationale.append(f"High IV ({iv_rank:.0f}%) — wide profitable range")
    if trend == "sideways":
        ic_score += 35
        ic_rationale.append("Sideways market — price likely stays in range")
    if near_expiry:
        ic_score += 10
        ic_rationale.append("Near expiry — faster theta decay")
    strategies.append(StrategyScore(
        name="Iron Condor",
        direction="neutral",
        score=max(0, ic_score),
        rationale=ic_rationale,
        max_profit="Net premium received",
        max_loss="Wing width - Premium",
        ideal_conditions=["High IV", "Low expected move", "Range-bound market"],
    ))

    # ── Long Straddle ──────────────────────────────────────────
    straddle_score = 0.0
    straddle_rationale = []
    if low_iv:
        straddle_score += 40
        straddle_rationale.append(f"Low IV ({iv_rank:.0f}%) — cheap to buy both sides")
    if trend == "sideways":
        straddle_score += 20
        straddle_rationale.append("Coiled price action — breakout expected")
    if not near_expiry:
        straddle_score += 15
        straddle_rationale.append("Sufficient time for move to develop")
    strategies.append(StrategyScore(
        name="Long Straddle",
        direction="neutral (volatility play)",
        score=max(0, straddle_score),
        rationale=straddle_rationale,
        max_profit="Unlimited",
        max_loss="Total premium paid",
        ideal_conditions=["Low IV", "Catalyst expected (earnings, FDA, etc.)", "45-60 DTE"],
    ))

    strategies.sort(key=lambda s: s.score, reverse=True)
    return strategies


# ── Options chain analysis ────────────────────────────────────────────────────

def analyze_options_chain(
    chain: List[Dict[str, Any]],
    underlying_price: float,
    risk_free_rate: float = 0.05,
) -> Dict[str, Any]:
    """
    Enrich an options chain with computed Greeks and moneyness labels.
    chain: list of option contract dicts with at least strike, expiration, type, bid, ask
    """
    enriched = []
    for contract in chain:
        strike = contract.get("strike", 0)
        option_type = contract.get("type", "call")
        bid = contract.get("bid", 0)
        ask = contract.get("ask", 0)
        mid = (bid + ask) / 2 if bid and ask else 0
        expiry_days = contract.get("expiry_days", 30)
        T = expiry_days / 365

        # Moneyness
        if underlying_price > 0 and strike > 0:
            moneyness_pct = (underlying_price - strike) / strike * 100
            if option_type == "call":
                if underlying_price > strike * 1.02:
                    moneyness = "ITM"
                elif underlying_price < strike * 0.98:
                    moneyness = "OTM"
                else:
                    moneyness = "ATM"
            else:
                if underlying_price < strike * 0.98:
                    moneyness = "ITM"
                elif underlying_price > strike * 1.02:
                    moneyness = "OTM"
                else:
                    moneyness = "ATM"
        else:
            moneyness = "unknown"
            moneyness_pct = 0

        # Compute Greeks if we have a mid price
        greeks = {}
        iv = contract.get("iv")
        if mid > 0 and T > 0:
            if not iv:
                iv = implied_volatility(mid, underlying_price, strike, T, risk_free_rate, option_type)
            if iv:
                greeks = black_scholes(underlying_price, strike, T, risk_free_rate, iv, option_type)

        enriched.append({
            **contract,
            "mid": round(mid, 4),
            "moneyness": moneyness,
            "moneyness_pct": round(moneyness_pct, 2),
            "iv": round(iv, 4) if iv else None,
            "greeks": greeks,
            "spread_pct": round((ask - bid) / ask * 100, 2) if ask > 0 else None,
        })

    # Separate calls and puts
    calls = sorted([c for c in enriched if c.get("type") == "call"], key=lambda x: x.get("strike", 0))
    puts = sorted([c for c in enriched if c.get("type") == "put"], key=lambda x: x.get("strike", 0))

    # Put/Call ratio
    total_call_oi = sum(c.get("open_interest", 0) or 0 for c in calls)
    total_put_oi = sum(c.get("open_interest", 0) or 0 for c in puts)
    pc_ratio = total_put_oi / total_call_oi if total_call_oi > 0 else None

    return {
        "calls": calls,
        "puts": puts,
        "put_call_ratio": round(pc_ratio, 3) if pc_ratio else None,
        "put_call_sentiment": (
            "bearish" if pc_ratio and pc_ratio > 1.2
            else "bullish" if pc_ratio and pc_ratio < 0.8
            else "neutral"
        ),
        "total_call_oi": total_call_oi,
        "total_put_oi": total_put_oi,
    }


# ── Simple options backtest ───────────────────────────────────────────────────

def backtest_long_option(
    bars: List[Dict[str, Any]],
    option_type: str,          # "call" or "put"
    strike_offset_pct: float,  # e.g. 0.05 = 5% OTM
    dte: int,                  # days to expiry at entry
    iv_assumption: float,      # constant IV assumption
    risk_free_rate: float = 0.05,
    entry_every_n_bars: int = 21,  # enter monthly
) -> Dict[str, Any]:
    """
    Backtest buying a call or put at regular intervals.
    Returns win rate, avg P&L, and trade log.
    """
    trades = []
    i = 0
    while i < len(bars) - dte:
        entry_bar = bars[i]
        exit_bar = bars[min(i + dte, len(bars) - 1)]

        S_entry = entry_bar["close"]
        S_exit = exit_bar["close"]

        if option_type == "call":
            K = S_entry * (1 + strike_offset_pct)
        else:
            K = S_entry * (1 - strike_offset_pct)

        T_entry = dte / 365
        entry_price = black_scholes(S_entry, K, T_entry, risk_free_rate, iv_assumption, option_type)["price"]

        # At expiry, intrinsic value only
        if option_type == "call":
            exit_price = max(S_exit - K, 0)
        else:
            exit_price = max(K - S_exit, 0)

        pnl = exit_price - entry_price
        pnl_pct = (pnl / entry_price * 100) if entry_price > 0 else 0

        trades.append({
            "entry_date": entry_bar.get("date", ""),
            "exit_date": exit_bar.get("date", ""),
            "entry_price": round(entry_price, 4),
            "exit_price": round(exit_price, 4),
            "strike": round(K, 2),
            "underlying_entry": round(S_entry, 2),
            "underlying_exit": round(S_exit, 2),
            "pnl": round(pnl, 4),
            "pnl_pct": round(pnl_pct, 2),
            "win": pnl > 0,
        })

        i += entry_every_n_bars

    if not trades:
        return {"error": "No trades generated"}

    wins = [t for t in trades if t["win"]]
    losses = [t for t in trades if not t["win"]]
    avg_win = sum(t["pnl_pct"] for t in wins) / len(wins) if wins else 0
    avg_loss = sum(t["pnl_pct"] for t in losses) / len(losses) if losses else 0
    total_pnl = sum(t["pnl"] for t in trades)

    return {
        "strategy": f"Long {option_type.capitalize()} ({strike_offset_pct*100:.0f}% OTM, {dte} DTE)",
        "total_trades": len(trades),
        "wins": len(wins),
        "losses": len(losses),
        "win_rate": round(len(wins) / len(trades) * 100, 1),
        "avg_win_pct": round(avg_win, 2),
        "avg_loss_pct": round(avg_loss, 2),
        "total_pnl_per_contract": round(total_pnl * 100, 2),  # per 100-share contract
        "expectancy_pct": round((len(wins) / len(trades)) * avg_win + (len(losses) / len(trades)) * avg_loss, 2),
        "trades": trades[-20:],  # last 20 for display
        "disclaimer": (
            "Backtest results are hypothetical and do not account for commissions, slippage, "
            "or real-world IV changes. Past performance does not guarantee future results."
        ),
    }


# Singleton
options_engine_instance = None  # instantiated on demand

class OptionsAnalysisEngine:
    def compute_greeks(self, S, K, T_days, r, sigma, option_type):
        return black_scholes(S, K, T_days / 365, r, sigma, option_type)

    def score_strategies(self, underlying_price, trend, iv_rank, dte, rsi=None):
        return [s.to_dict() for s in score_strategies(underlying_price, trend, iv_rank, dte, rsi)]

    def analyze_chain(self, chain, underlying_price, risk_free_rate=0.05):
        return analyze_options_chain(chain, underlying_price, risk_free_rate)

    def backtest(self, bars, option_type, strike_offset_pct, dte, iv_assumption):
        return backtest_long_option(bars, option_type, strike_offset_pct, dte, iv_assumption)

    def iv_rank(self, current_iv, iv_history):
        return compute_iv_rank(current_iv, iv_history)


options_engine = OptionsAnalysisEngine()
