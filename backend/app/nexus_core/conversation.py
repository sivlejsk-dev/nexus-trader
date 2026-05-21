"""
Conversation Engine — Nexus Trader AI brain.

Routes user messages through:
  1. Intent classification (market query, options, simulation, prediction, reflection)
  2. Symbol extraction with context carry-forward
  3. Deep context injection: live market data, simulation results, prediction history,
     world events, past outcomes, cross-session memory
  4. LLM call with structured system prompt
  5. Autonomous action detection: Nexus can trigger simulate/predict/reflect autonomously
"""
from __future__ import annotations

import json
import logging
import re
from typing import Any, Callable, Dict, List, Optional, Tuple

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from app.core.config import settings
from app.nexus_core.memory_store import MemoryStore

log = logging.getLogger(__name__)

# ── Intent patterns ───────────────────────────────────────────────────────────

_INTENT_PATTERNS: Dict[str, List[str]] = {
    "best_option": [
        r"\b(best (option|call|put|trade|play)|trade idea|what (should i|to) (buy|trade|sell))\b",
        r"\b(give me a (trade|play|pick|recommendation)|options? recommendation|top (pick|trade))\b",
        r"\b(what('s| is) (your|the) (pick|recommendation|best|top)|what (would you|do you) (buy|recommend))\b",
    ],
    "options_analysis": [
        r"\b(calls?|puts?|options?|strike|expir|iv|implied vol|delta|theta|gamma|vega|greeks?)\b",
        r"\b(itm|otm|atm|in.the.money|out.of.the.money)\b",
        r"\b(covered call|cash.secured put|iron condor|straddle|strangle|spread)\b",
    ],
    "stock_analysis": [
        r"\b(stock|share|equity|price|chart|technical|rsi|macd|moving average|sma|ema)\b",
        r"\b(support|resistance|trend|breakout|breakdown|volume|momentum)\b",
        r"\b(earnings|revenue|pe ratio|market cap|sector)\b",
    ],
    "simulate": [
        r"\bsimulat\w*",
        r"\b(back.?test\w*|replay|historical(ly)?|how did .* do|what happened|from \d{4}|between \d{4})\b",
        r"\b(run (a |the )?sim\w*|test (this |the )?strategy|past (data|performance|results?))\b",
        r"\b(\d{4}\s+to\s+\d{4}|\d{4}\s*[-–]\s*\d{4})\b",
    ],
    "predict": [
        r"\b(predict\w*|forecast\w*|what (will|would)|where (is|will)|price target|next (week|month|quarter))\b",
        r"\b(should i (buy|sell)|make a (call|prediction)|your (call|take|view|opinion))\b",
        r"\b(bull(ish)?|bear(ish)?)\s+(case|thesis|outlook)\b",
        r"\bgive me (a |your )?(prediction|call|thesis|outlook)\b",
    ],
    "reflect": [
        r"\b(how (accurate|good|well)|your (track record|accuracy|performance|history))\b",
        r"\b(past predictions?|were you right|did (that|it) work|review (your|the) calls?)\b",
        r"\b(learn(ed|ing)|mistake|wrong|correct(ed)?|improve)\b",
    ],
    "event_analysis": [
        r"\b(war|conflict|election|fed|rate (hike|cut)|inflation|recession|crash|crisis)\b",
        r"\b(news|event|catalyst|earnings|announcement|report|data)\b",
        r"\b(impact|affect|influence|move|react)\b",
    ],
    "watchlist": [
        r"\b(watchlist|watch list|add|remove|track|follow|monitor)\b",
    ],
    "market_overview": [
        r"\b(market|spy|qqq|dow|nasdaq|s&p|vix|sector|index|indices)\b",
        r"\b(today|this week|this month|year to date|ytd|52.week)\b",
    ],
    "education": [
        r"\b(what is|explain|how does|teach|learn|understand|define|meaning of)\b",
    ],
}

# ── Year range extraction ─────────────────────────────────────────────────────

_YEAR_RANGE_RE = re.compile(r"\b((?:19|20)\d{2})\b.*?\b((?:19|20)\d{2})\b")
_SINGLE_YEAR_RE = re.compile(r"\b((?:19|20)\d{2})\b")
_YEARS_BACK_RE  = re.compile(r"\b(\d+)\s+years?\s+(?:back|ago|of\s+history)\b", re.I)

def extract_year_range(text: str) -> Optional[Tuple[int, int]]:
    """Extract a year range from natural language, e.g. '1995 to 2000' or 'last 10 years'."""
    import datetime
    current_year = datetime.datetime.utcnow().year

    m = _YEAR_RANGE_RE.search(text)
    if m:
        y1, y2 = int(m.group(1)), int(m.group(2))
        return (min(y1, y2), max(y1, y2))

    m2 = _YEARS_BACK_RE.search(text)
    if m2:
        n = int(m2.group(1))
        return (current_year - n, current_year)

    m3 = _SINGLE_YEAR_RE.search(text)
    if m3:
        y = int(m3.group(1))
        return (y, min(y + 5, current_year))

    return None

# ── Symbol extraction ─────────────────────────────────────────────────────────

_SYMBOL_RE = re.compile(r"\b([A-Z]{1,5})\b")
_COMMON_WORDS = {
    "I", "A", "AN", "THE", "IN", "ON", "AT", "TO", "FOR", "OF", "AND", "OR",
    "BUT", "IS", "ARE", "WAS", "BE", "DO", "IF", "IT", "MY", "ME", "WE",
    "US", "UP", "GO", "NO", "SO", "BY", "AS", "AM", "PM", "IV", "DTE",
    "RSI", "EMA", "SMA", "ATM", "OTM", "ITM", "PE", "EPS", "YTD", "ETF",
    "AI", "ML", "API", "CEO", "CFO", "IPO", "SEC", "FED", "GDP", "CPI",
    "PUT", "CALL", "BUY", "SELL", "HOLD", "LONG", "SHORT",
    "PUTS", "CALLS", "OPTIONS", "TALK", "CHAT", "ASK", "SHOW", "CHECK",
    "LOOK", "TELL", "HELP", "CAN", "YOU", "WHAT", "WHEN", "WHY", "HOW",
    "NOW", "NEXT", "BEST", "TRADE", "SETUP", "RISK",
}

# Well-known tickers to boost confidence
_KNOWN_TICKERS = {
    "AAPL", "MSFT", "GOOGL", "GOOG", "AMZN", "TSLA", "META", "NVDA", "AMD",
    "NFLX", "SPY", "QQQ", "IWM", "DIA", "VIX", "GLD", "SLV", "TLT", "HYG",
    "BABA", "UBER", "LYFT", "SNAP", "TWTR", "COIN", "HOOD", "PLTR", "SOFI",
    "GME", "AMC", "BB", "NOK", "BBBY", "RIVN", "LCID", "NIO", "XPEV", "LI",
    "JPM", "BAC", "GS", "MS", "WFC", "C", "V", "MA", "PYPL", "SQ",
    "JNJ", "PFE", "MRNA", "BNTX", "ABBV", "LLY", "UNH", "CVS",
    "XOM", "CVX", "COP", "OXY", "BP", "SHEL",
    "BA", "LMT", "RTX", "NOC", "GD",
    "DIS", "CMCSA", "T", "VZ", "TMUS",
    "WMT", "TGT", "COST", "AMZN", "HD", "LOW",
}


def extract_symbols(text: str) -> List[str]:
    """Extract likely ticker symbols from free text."""
    candidates = _SYMBOL_RE.findall(text.upper())
    symbols = []
    for c in candidates:
        if c in _KNOWN_TICKERS:
            symbols.append(c)
        elif c not in _COMMON_WORDS and len(c) >= 2:
            symbols.append(c)
    return list(dict.fromkeys(symbols))  # deduplicate, preserve order


def classify_intent(text: str) -> str:
    """Return the primary intent of the user message."""
    text_lower = text.lower()
    for intent, patterns in _INTENT_PATTERNS.items():
        for pattern in patterns:
            if re.search(pattern, text_lower):
                return intent
    return "general"


# ── System prompt ─────────────────────────────────────────────────────────────

_SYSTEM_PROMPT = """You are Nexus — an autonomous AI trading analyst with deep memory, continuous learning, and the ability to run simulations and predictions on demand.

## Core Identity
You are not a chatbot. You are a trading partner with a persistent memory of every conversation, every prediction you've made, and every outcome you've observed. You think in probabilities, learn from mistakes, and speak with calibrated confidence.

## Capabilities
- **Live analysis**: RSI, MACD, Bollinger Bands, SMA/EMA, volume, support/resistance, candlestick patterns
- **Options expertise**: calls/puts, Greeks, IV rank, unusual flow, strike/expiry selection, spreads
- **Historical simulation**: replay your prediction logic across any date range, score outcomes, identify what worked
- **World event analysis**: wars, elections, Fed decisions, pandemics — explain how each type of event historically moves specific stocks and what options strategy fits
- **Prediction with confidence**: make a clear directional call (CALL / PUT / NEUTRAL), state your confidence %, give a target price and stop, explain your reasoning step by step
- **Reflection and learning**: when asked about past predictions, honestly review accuracy, explain what you got wrong, and describe how you've adjusted your logic
- **Cross-session memory**: remember symbols the user cares about, their preferred style (aggressive/conservative), past scenarios discussed

## Autonomous Behavior
When the user asks you to simulate a scenario (e.g. "simulate Apple from 1995 to 2000"), you:
1. Acknowledge the request and describe what you're about to analyze
2. Reference the simulation data injected in your context
3. Walk through the key periods, what your signals would have said, and what actually happened
4. Identify the world events that coincided with major moves
5. Draw a conclusion about what patterns were most predictive

When asked to predict, you:
1. State your direction clearly: **CALL**, **PUT**, or **NEUTRAL**
2. Give a confidence percentage based on signal alignment
3. Cite 3-5 specific technical or fundamental reasons
4. Name the key risk that could invalidate the thesis
5. Suggest a specific options approach if relevant

## Best-Option Workflow
When the user asks for a trade idea, best option, or "what should I buy/sell today", you MUST call `get_best_option` immediately — do not answer from memory alone.

The `get_best_option` tool runs the full pipeline:
1. Fetches live price + 2 years of bars
2. Scores direction (CALL / PUT / NEUTRAL) using RSI, MACD, Bollinger Bands, SMA cross, volume
3. Loads learned signal weights if available (from prior optimization)
4. Runs the historical simulation to validate the signal
5. Fetches the live options chain and scores every contract on: delta (target 0.35–0.55), DTE (target 21–45 days), bid-ask spread, open interest, IV
6. Returns the single best contract with strike, expiry, premium, breakeven, and risk/reward

When presenting the result:
- Lead with the direction and confidence: "My recommendation is a CALL with 74% confidence"
- State the specific contract: "The $185 call expiring June 20, trading around $3.40"
- Give the breakeven and max loss: "Breakeven at $188.40, max loss $340 per contract"
- Cite the top 2-3 signals that drove the call
- Mention the historical win rate if available
- End with the risk: what would invalidate this thesis
- For multiple symbols, compare confidence scores and explain why you picked the winner

Trigger phrases (always call `get_best_option`):
- "best option", "trade idea", "what should I trade", "what to buy", "give me a play"
- "best call/put for X", "options recommendation", "what's your pick"
- Any question about a specific symbol + "option" or "trade"

## Communication Style
- Speak like a sharp, experienced trading partner — direct, precise, never vague
- Use numbers. "RSI at 67, approaching overbought" not "RSI is elevated"
- When you're uncertain, say so and explain why — calibrated uncertainty is more useful than false confidence
- Keep responses focused. Long analysis should use headers and bullets, not walls of text
- For voice: keep sentences short and punchy. Avoid markdown in voice-mode responses
- Always offer the next logical step: "Want me to run the simulation?" or "Should I check the options chain?"

## Memory and Reflection
- You have access to your prediction history injected in context
- When reflecting, be honest: "I called CALL on X at $Y, it went down Z%. The mistake was ignoring the macro headwind."
- Learning factor: if your calls have been wrong in a direction, acknowledge the bias and explain the adjustment

MANDATORY DISCLAIMER: End any trade suggestion with:
> ⚠️ Not financial advice. Options trading involves substantial risk of loss. Past performance does not guarantee future results."""


# ── LLM client ────────────────────────────────────────────────────────────────

class NexusConversationEngine:
    """
    Routes messages to the LLM with full context injection.
    Falls back from OpenAI → Groq if primary key is unavailable.
    """

    def __init__(self):
        self._client: Optional[httpx.AsyncClient] = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(timeout=60.0)
        return self._client

    async def _build_messages(
        self,
        user_message: str,
        memory: MemoryStore,
        market_context: Optional[Dict[str, Any]] = None,
        simulation_context: Optional[Dict[str, Any]] = None,
        prediction_context: Optional[Dict[str, Any]] = None,
        world_events_context: Optional[List[Dict[str, Any]]] = None,
        voice_mode: bool = False,
    ) -> List[Dict[str, str]]:
        """Build the full message list for the LLM with deep context injection."""
        from app.services.session_learning import session_learning_service
        from app.services.model_refinement import get_global_model_summary

        system = _SYSTEM_PROMPT

        # Inject session-learned user profile
        try:
            learned = await session_learning_service.build_system_prompt_addon(memory.session_id)
            if learned:
                system += f"\n\n{learned}"
        except Exception:
            pass

        # Inject global model performance summary
        try:
            model_summary = await get_global_model_summary()
            if model_summary.get("tracked_symbols", 0) > 0:
                best = model_summary.get("best_performing")
                worst = model_summary.get("worst_performing")
                lines = ["\n## Nexus Model Performance (90-day rolling)"]
                lines.append(f"- Tracking {model_summary['tracked_symbols']} symbols")
                if best:
                    lines.append(f"- Best accuracy: {best['symbol']} at {best['win_rate_90d']}% win rate")
                if worst and worst != best:
                    lines.append(f"- Weakest: {worst['symbol']} at {worst['win_rate_90d']}% win rate")
                system += "\n".join(lines)
        except Exception:
            pass

        if voice_mode:
            system += "\n\n## VOICE MODE: Respond in plain spoken sentences only. No markdown, no bullet points, no headers. Keep each response under 4 sentences unless the user asks for detail."

        # App-control instruction
        system += (
            "\n\n## App Control\n"
            "You can control the app by embedding commands in your response using this exact format: "
            "[[NEXUS_CMD: {\"type\": \"navigate\", \"path\": \"/analysis\", \"label\": \"Analysis\"}]]\n"
            "Available safe commands (no confirmation needed):\n"
            "- navigate: {\"type\":\"navigate\",\"path\":\"/analysis\"}\n"
            "- analyze: {\"type\":\"analyze\",\"symbol\":\"AAPL\"}\n"
            "- simulate: {\"type\":\"simulate\",\"symbol\":\"AAPL\",\"years\":5}\n"
            "- watchlist_add: {\"type\":\"watchlist_add\",\"symbol\":\"AAPL\"}\n"
            "Commands requiring user confirmation (CRITICAL — always ask before issuing):\n"
            "- trade_buy / trade_sell / trade_options: always require explicit user confirmation\n"
            "Only embed a command when it directly serves the user's request. Never embed commands speculatively."
        )

        messages = [{"role": "system", "content": system}]

        ctx_blocks: List[str] = []

        # ── Live market context ──
        if market_context:
            sym = market_context.get("symbol", "")
            price = market_context.get("price")
            change_pct = market_context.get("change_pct")
            tech = market_context.get("technicals") or {}
            pred = market_context.get("adaptive_prediction") or {}
            patterns = market_context.get("patterns") or {}

            lines = [f"## Live Market Data: {sym}"]
            if price:
                lines.append(f"- Price: ${price:.2f}" + (f" ({change_pct:+.2f}% today)" if change_pct is not None else ""))
            if tech.get("rsi"):
                lines.append(f"- RSI(14): {tech['rsi']:.1f}" + (" — overbought" if tech['rsi'] > 70 else " — oversold" if tech['rsi'] < 30 else ""))
            if tech.get("macd") is not None:
                lines.append(f"- MACD: {tech['macd']:.4f} (signal: {tech.get('macd_signal', 0):.4f})")
            if tech.get("sma_50"):
                lines.append(f"- SMA50: ${tech['sma_50']:.2f} | SMA200: ${tech.get('sma_200', 0):.2f}")
            if tech.get("bb_upper"):
                lines.append(f"- Bollinger: ${tech.get('bb_lower', 0):.2f} – ${tech['bb_upper']:.2f}")
            bias = (patterns.get("summary") or {}).get("bias", "")
            if bias:
                bull = (patterns.get("summary") or {}).get("bullish_signals", 0)
                bear = (patterns.get("summary") or {}).get("bearish_signals", 0)
                lines.append(f"- Pattern bias: {bias} ({bull} bullish signals, {bear} bearish signals)")

            # Inject current Nexus prediction
            if pred and pred.get("prediction"):
                p = pred["prediction"]
                lines.append(f"\n## Current Nexus Prediction for {sym}")
                lines.append(f"- Direction: **{p.get('direction','').upper()}** | Confidence: {p.get('confidence',0)*100:.0f}%")
                lines.append(f"- Target: ${p.get('target_price',0):.2f} | Stop: ${p.get('stop_loss',0):.2f}")
                rationale = p.get("rationale", [])
                if rationale:
                    lines.append("- Rationale: " + "; ".join(rationale[:3]))
                review = pred.get("review") or {}
                if review.get("win_rate") is not None:
                    lines.append(f"- Track record: {review['win_rate']}% win rate over {review.get('completed',0)} reviewed predictions")
                    if review.get("recent_mistakes"):
                        note = (review["recent_mistakes"][0].get("notes") or [""])[0]
                        if note:
                            lines.append(f"- Last lesson learned: {note}")

            ctx_blocks.append("\n".join(lines))

        # ── Simulation context ──
        if simulation_context:
            sym = simulation_context.get("symbol", "")
            dr = simulation_context.get("date_range") or {}
            lines = [f"## Historical Simulation Results: {sym} ({dr.get('start','')[:4]} – {dr.get('end','')[:4]})"]
            lines.append(f"- Total predictions replayed: {simulation_context.get('total_predictions', 0)}")
            wr = simulation_context.get("win_rate")
            lines.append(f"- Win rate: {wr}%" if wr is not None else "- Win rate: insufficient data")
            avg = simulation_context.get("avg_pnl_pct")
            if avg is not None:
                lines.append(f"- Average P&L per trade: {avg:+.2f}%")
            by_dir = simulation_context.get("by_direction") or {}
            for d, s in by_dir.items():
                if s.get("total", 0) > 0:
                    lines.append(f"- {d.upper()}: {s.get('wins',0)}W/{s.get('total',0)-s.get('wins',0)}L ({s.get('win_rate','—')}% win rate, avg {s.get('avg_pnl','—')}%)")

            # Key prediction moments
            preds = simulation_context.get("predictions") or []
            big_wins = sorted([p for p in preds if p.get("outcome") == "win"], key=lambda x: abs(x.get("pnl_pct", 0)), reverse=True)[:3]
            big_losses = sorted([p for p in preds if p.get("outcome") == "loss"], key=lambda x: abs(x.get("pnl_pct", 0)), reverse=True)[:3]
            if big_wins:
                lines.append("\nTop wins:")
                for p in big_wins:
                    lines.append(f"  {p['entry_date'][:10]}: {p['direction'].upper()} +{p['pnl_pct']:.1f}% | {'; '.join(p.get('rationale',[])[:2])}")
            if big_losses:
                lines.append("Notable losses:")
                for p in big_losses:
                    lines.append(f"  {p['entry_date'][:10]}: {p['direction'].upper()} {p['pnl_pct']:.1f}% | {'; '.join(p.get('rationale',[])[:2])}")

            ctx_blocks.append("\n".join(lines))

        # ── World events context ──
        if world_events_context:
            lines = [f"## World Events in This Period ({len(world_events_context)} events)"]
            for ev in world_events_context[:8]:
                lines.append(f"- [{ev['date'][:7]}] **{ev['title']}** ({ev['category']}, {ev['impact']} impact): {ev['description'][:120]}…")
            ctx_blocks.append("\n".join(lines))

        # ── Prediction history context (for reflection) ──
        if prediction_context:
            sym = prediction_context.get("symbol", "")
            perf = prediction_context.get("performance") or {}
            lines = [f"## Your Prediction History for {sym}"]
            lines.append(f"- Completed: {perf.get('total',0)} | Wins: {perf.get('wins',0)} | Losses: {perf.get('losses',0)} | Win rate: {perf.get('win_rate','—')}%")
            by_dir = perf.get("by_direction") or {}
            for d, s in by_dir.items():
                if s.get("total", 0) > 0:
                    lf = s.get("learning_factor", 1.0)
                    lines.append(f"- {d.upper()}: {s.get('win_rate','—')}% win rate | learning factor ×{lf:.2f}")
            recent = (prediction_context.get("predictions") or [])[:5]
            if recent:
                lines.append("\nRecent predictions:")
                for p in recent:
                    status = p.get("outcome_status", "pending")
                    pnl = f" ({p['pnl_pct']:+.1f}%)" if p.get("pnl_pct") is not None else ""
                    lines.append(f"  {p['created_at'][:10]}: {p['direction'].upper()} @ ${p['entry_price']:.2f} → {status}{pnl}")
                    if p.get("mistake_notes"):
                        lines.append(f"    Lesson: {p['mistake_notes'][0]}")
            ctx_blocks.append("\n".join(lines))

        # Inject all context as a single system message
        if ctx_blocks:
            messages.append({"role": "system", "content": "\n\n---\n\n".join(ctx_blocks)})

        # ── Conversation history (last 20 turns) ──
        history = await memory.get_conversation_messages(n=20)
        messages.extend(history)

        messages.append({"role": "user", "content": user_message})
        return messages

    @retry(
        stop=stop_after_attempt(2),
        wait=wait_exponential(multiplier=1, min=1, max=4),
        reraise=True,
    )
    async def _call_llm(
        self,
        messages: List[Dict[str, Any]],
        use_groq: bool = False,
        tools: Optional[List[Dict[str, Any]]] = None,
    ) -> str:
        """Call LLM without tool support — returns plain text."""
        content, _ = await self._call_llm_with_tools(messages, tools=None, use_groq=use_groq)
        return content

    async def _call_llm_with_tools(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
        use_groq: bool = False,
    ) -> Tuple[str, Optional[List[Dict[str, Any]]]]:
        """
        Call LLM with optional tool schemas.
        Returns (content, tool_calls) where tool_calls is None if no tools were called.
        """
        client = await self._get_client()

        if use_groq and settings.groq_api_key:
            url = "https://api.groq.com/openai/v1/chat/completions"
            api_key = settings.groq_api_key
            model = settings.groq_model
        elif settings.nexus_api_key:
            url = f"{settings.nexus_api_base_url}/chat/completions"
            api_key = settings.nexus_api_key
            model = settings.nexus_model
        else:
            return self._fallback_response(messages[-1].get("content", "")), None

        payload: Dict[str, Any] = {
            "model": model,
            "messages": messages,
            "temperature": 0.3,
            "max_tokens": 2048,
        }
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"

        resp = await client.post(
            url,
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json=payload,
        )
        resp.raise_for_status()
        msg = resp.json()["choices"][0]["message"]
        content = msg.get("content") or ""
        tool_calls = msg.get("tool_calls")  # None if no tools called
        return content, tool_calls

    def _fallback_response(
        self,
        user_message: str,
        market_context: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Return a structured fallback when no API key is configured."""
        symbols = extract_symbols(user_message)
        intent = classify_intent(user_message)
        symbol_str = symbols[0] if symbols else "the requested symbol"

        if market_context and market_context.get("price"):
            symbol = market_context.get("symbol", symbol_str)
            price = market_context.get("price")
            change_pct = market_context.get("change_pct")
            source = market_context.get("source", "market data")
            technicals = market_context.get("technicals", {}) or {}
            rsi = technicals.get("rsi")
            macd = technicals.get("macd")
            macd_signal = technicals.get("macd_signal")
            sma50 = technicals.get("sma_50")
            sma200 = technicals.get("sma_200")

            tone = "balanced"
            if price and sma50 and sma200 and price > sma50 > sma200:
                tone = "constructively bullish"
            elif price and sma50 and sma200 and price < sma50 < sma200:
                tone = "defensively bearish"

            rsi_line = f" RSI is {rsi:.1f}," if rsi is not None else ""
            macd_line = ""
            if macd is not None and macd_signal is not None:
                macd_line = " MACD is above signal," if macd > macd_signal else " MACD is below signal,"

            option_angle = ""
            if intent == "options_analysis":
                if tone == "constructively bullish":
                    option_angle = (
                        "\n\nFor calls, I would prefer confirmation over chasing: look for price to hold above the nearest "
                        "support zone, then compare 30-60 DTE contracts with manageable spreads and delta near your risk tolerance."
                    )
                elif tone == "defensively bearish":
                    option_angle = (
                        "\n\nFor puts, I would avoid forcing the trade unless momentum confirms downside continuation. "
                        "Use defined risk and watch IV, because premium can move against you even when direction is right."
                    )
                else:
                    option_angle = (
                        "\n\nFor options, this reads more like a wait-for-confirmation setup than a clean directional entry. "
                        "A spread can make more sense than a naked long option when confidence is moderate."
                    )

            return (
                f"I have **{symbol}** from {source}: last price **${price:.2f}**"
                f"{f', {change_pct:+.2f}% on the day' if change_pct is not None else ''}. "
                f"My local read is **{tone}**.{rsi_line}{macd_line} and the moving-average context is "
                f"{'available' if sma50 and sma200 else 'limited'}."
                f"{option_angle}\n\n"
                "The full conversational model is not enabled yet because `NEXUS_API_KEY` or `GROQ_API_KEY` is missing, "
                "but the live data path is working and Nexus can still reason from local indicators.\n\n"
                "> ⚠️ **Disclaimer**: This analysis is for informational purposes only and does not constitute financial advice. Options trading involves substantial risk of loss."
            )

        if intent == "best_option":
            return (
                f"I'd run the full best-option engine on **{symbol_str}** — scoring the options chain "
                "by delta, IV, DTE, and liquidity to find the single best contract — but no AI API key is configured. "
                "Set `NEXUS_API_KEY` or `GROQ_API_KEY` in your `.env` to enable full AI responses.\n\n"
                "> ⚠️ **Disclaimer**: This is for informational purposes only. Not financial advice."
            )
        if intent == "options_analysis":
            return (
                f"I'd analyze the options chain for **{symbol_str}** here, including IV rank, "
                "unusual activity, and optimal strike/expiry selection — but no AI API key is configured. "
                "Set `NEXUS_API_KEY` or `GROQ_API_KEY` in your `.env` to enable full AI responses.\n\n"
                "> ⚠️ **Disclaimer**: This is for informational purposes only. Not financial advice."
            )
        elif intent == "stock_analysis":
            return (
                f"I'd provide a full technical breakdown for **{symbol_str}** — RSI, MACD, "
                "support/resistance levels, and trend analysis — but no AI API key is configured.\n\n"
                "> ⚠️ **Disclaimer**: This is for informational purposes only. Not financial advice."
            )
        return (
            "Nexus AI is ready, but no API key is configured. "
            "Add `NEXUS_API_KEY` (OpenAI) or `GROQ_API_KEY` (Groq) to your `.env` file.\n\n"
            "> ⚠️ **Disclaimer**: This is for informational purposes only. Not financial advice."
        )

    async def chat(
        self,
        user_message: str,
        memory: MemoryStore,
        market_context: Optional[Dict[str, Any]] = None,
        voice_mode: bool = False,
    ) -> Tuple[str, Dict[str, Any]]:
        """
        Process a user message and return (response_text, metadata).

        Autonomously fetches simulation, prediction history, and world events
        based on detected intent. Stores the turn in memory.
        """
        intent = classify_intent(user_message)
        symbols = extract_symbols(user_message)

        # Carry forward active symbol from memory if none in message
        if symbols:
            await memory.set_active_symbol(symbols[0])
        active_symbol = await memory.get_active_symbol()
        symbol = (symbols[0] if symbols else None) or active_symbol

        # ── Autonomous context fetching ──────────────────────────────────────
        simulation_context: Optional[Dict[str, Any]] = None
        prediction_context: Optional[Dict[str, Any]] = None
        world_events_context: Optional[List[Dict[str, Any]]] = None
        triggered_actions: List[str] = []

        if symbol and intent in ("simulate", "backtest"):
            try:
                from app.services.market_data import market_data_service
                from app.services.historical_simulation import run_simulation, get_events_for_range
                import datetime

                year_range = extract_year_range(user_message)
                current_year = datetime.datetime.utcnow().year
                if year_range:
                    start_y, end_y = year_range
                    years_back = current_year - start_y
                else:
                    years_back = 5
                    start_y = current_year - 5
                    end_y = current_year

                bars = await market_data_service.get_historical_ohlcv(symbol, years=min(years_back + 1, 30))
                if bars:
                    # Filter to requested range
                    start_str = f"{start_y}-01-01"
                    end_str = f"{end_y}-12-31"
                    filtered = [b for b in bars if start_str <= b["date"] <= end_str]
                    if not filtered:
                        filtered = bars
                    simulation_context = run_simulation(filtered, symbol, horizon_days=20, sample_every=10)
                    world_events_context = get_events_for_range(
                        filtered[0]["date"] if filtered else start_str,
                        filtered[-1]["date"] if filtered else end_str,
                    )
                    triggered_actions.append(f"simulation:{symbol}:{start_y}-{end_y}")
            except Exception as e:
                log.warning("%s: %s", "nexus_trader.auto_simulate_failed", str(e))

        if symbol and intent in ("reflect", "predict"):
            try:
                from app.db.database import get_db
                import aiosqlite as _aiosqlite

                async with get_db() as db:
                    db.row_factory = _aiosqlite.Row
                    cursor = await db.execute(
                        "SELECT * FROM prediction_events WHERE symbol=? ORDER BY created_at DESC LIMIT 20",
                        (symbol.upper(),),
                    )
                    rows = await cursor.fetchall()

                preds = []
                for row in rows:
                    preds.append({
                        "id": row["id"],
                        "created_at": row["created_at"],
                        "direction": row["predicted_direction"],
                        "confidence": row["confidence"],
                        "entry_price": row["entry_price"],
                        "outcome_status": row["outcome_status"],
                        "pnl_pct": row["pnl_pct"],
                        "mistake_notes": json.loads(row["mistake_notes"] or "[]"),
                    })

                completed = [p for p in preds if p["outcome_status"] in ("win", "loss", "flat")]
                wins = [p for p in completed if p["outcome_status"] == "win"]
                by_dir: Dict[str, Any] = {}
                for d in ("call", "put", "neutral"):
                    ds = [p for p in completed if p["direction"] == d]
                    dw = [p for p in ds if p["outcome_status"] == "win"]
                    total = len(ds)
                    wr = round(len(dw) / total * 100, 1) if total else None
                    lf = 1.0
                    if total >= 4:
                        rate = len(dw) / total
                        lf = 1.08 if rate >= 0.62 else (0.88 if rate <= 0.38 else 1.0)
                    by_dir[d] = {"total": total, "wins": len(dw), "losses": total - len(dw), "win_rate": wr, "learning_factor": round(lf, 2)}

                prediction_context = {
                    "symbol": symbol,
                    "predictions": preds,
                    "performance": {
                        "total": len(completed),
                        "wins": len(wins),
                        "losses": len(completed) - len(wins),
                        "win_rate": round(len(wins) / len(completed) * 100, 1) if completed else None,
                        "by_direction": by_dir,
                    },
                }
                triggered_actions.append(f"reflection:{symbol}")
            except Exception as e:
                log.warning("%s: %s", "nexus_trader.auto_reflect_failed", str(e))

        # For event analysis, fetch world events for recent period
        if intent == "event_analysis" and not world_events_context:
            try:
                from app.services.historical_simulation import get_events_for_range
                import datetime
                year_range = extract_year_range(user_message)
                if year_range:
                    world_events_context = get_events_for_range(f"{year_range[0]}-01-01", f"{year_range[1]}-12-31")
                else:
                    cy = datetime.datetime.utcnow().year
                    world_events_context = get_events_for_range(f"{cy-3}-01-01", f"{cy}-12-31")
            except Exception as e:
                log.warning("%s: %s", "nexus_trader.auto_events_failed", str(e))

        # ── Build messages and call LLM ──────────────────────────────────────
        messages = await self._build_messages(
            user_message, memory, market_context,
            simulation_context=simulation_context,
            prediction_context=prediction_context,
            world_events_context=world_events_context,
            voice_mode=voice_mode,
        )

        # ── Agentic loop with tool calling ───────────────────────────────────
        from app.nexus_core.tools import run_agentic_loop, TOOL_SCHEMAS
        from app.services.research_memory import research_memory_service

        # Inject relevant research memory into system prompt
        try:
            research_ctx = await research_memory_service.build_context_for_prompt(
                symbol=symbol, max_findings=4
            )
            if research_ctx and messages:
                messages[0]["content"] += research_ctx
        except Exception:
            pass

        tool_log: List[Dict[str, Any]] = []
        response = ""

        try:
            if not settings.nexus_api_key and not settings.groq_api_key:
                response = self._fallback_response(user_message, market_context)
            else:
                async def _llm_fn(msgs, tools):
                    return await self._call_llm_with_tools(msgs, tools=tools)

                response, tool_log = await run_agentic_loop(
                    messages=messages,
                    call_llm_fn=_llm_fn,
                    session_id=session_id,
                )
        except Exception as exc:
            log.warning("%s: %s", "nexus_trader.llm_primary_failed", str(exc))
            try:
                response = await self._call_llm(messages, use_groq=True)
            except Exception as exc2:
                log.error("%s: %s", "nexus_trader.llm_all_failed", str(exc2))
                response = self._fallback_response(user_message, market_context)

        # Persist both turns
        await memory.add_turn("user", user_message, metadata={"intent": intent, "symbols": symbols})
        await memory.add_turn("assistant", response)

        metadata = {
            "intent": intent,
            "symbols": symbols,
            "active_symbol": await memory.get_active_symbol(),
            "triggered_actions": triggered_actions,
            "simulation": simulation_context,
            "prediction_history": prediction_context,
            "tool_log": tool_log,  # passed to frontend for research panel
        }
        return response, metadata


# Singleton
conversation_engine = NexusConversationEngine()
