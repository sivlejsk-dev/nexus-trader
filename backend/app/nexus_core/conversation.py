"""
Conversation Engine — adapted from Nexus Wellness.

Routes user messages through:
  1. Intent classification (market query, options analysis, backtest, general)
  2. Symbol extraction
  3. Tone analysis (casual vs technical)
  4. Context enrichment with active symbol / recent analysis
  5. LLM call with structured system prompt
  6. Response post-processing (disclaimer injection, flow enhancement)
"""
from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional, Tuple

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from app.core.config import settings
from app.nexus_core.memory_store import MemoryStore

log = logging.getLogger(__name__)

# ── Intent patterns ───────────────────────────────────────────────────────────

_INTENT_PATTERNS: Dict[str, List[str]] = {
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
    "backtest": [
        r"\b(backtest|back.test|historical|history|past performance|simulate|simulation)\b",
        r"\b(how did|what happened|when did|pattern|recurring)\b",
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

_SYSTEM_PROMPT = """You are Nexus, an expert AI assistant specializing in stock market research and options trading analysis.

Your capabilities:
- Deep technical analysis: RSI, MACD, Bollinger Bands, moving averages, volume analysis
- Options expertise: calls, puts, Greeks (delta, gamma, theta, vega), IV rank, unusual options activity
- Pattern recognition: chart patterns (head & shoulders, cup & handle, flags, wedges), candlestick patterns
- Historical analysis: market cycles, sector rotation, earnings patterns, seasonal trends
- Backtesting: evaluate how strategies performed historically
- Risk management: position sizing, stop-loss placement, risk/reward ratios

Communication style:
- Converse naturally, like a sharp trading partner sitting beside the user.
- Be precise and data-driven. Cite specific numbers when available.
- Keep momentum: answer the question, explain the tradeoff, then offer the next useful angle.
- Ask one concise follow-up when the user's goal is ambiguous.
- Structure complex analysis with clear sections, but avoid sounding like a static report.
- Always distinguish between high-confidence signals and speculative observations.
- Use markdown formatting for readability (headers, bullet points, tables).

MANDATORY DISCLAIMER: Always end any trade suggestion or analysis with:
> ⚠️ **Disclaimer**: This analysis is for informational purposes only and does not constitute financial advice. Options trading involves substantial risk of loss and is not suitable for all investors. Past performance does not guarantee future results. Always conduct your own due diligence and consult a licensed financial advisor before trading.

Never guarantee profits. Never recommend specific position sizes in dollar terms. Always present both bull and bear cases."""


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
    ) -> List[Dict[str, str]]:
        """Build the full message list for the LLM."""
        messages = [{"role": "system", "content": _SYSTEM_PROMPT}]

        # Inject active market context if available
        if market_context:
            ctx_lines = ["**Current Market Context:**"]
            symbol = market_context.get("symbol")
            if symbol:
                ctx_lines.append(f"- Symbol: {symbol}")
            price = market_context.get("price")
            if price:
                ctx_lines.append(f"- Last Price: ${price:.2f}")
            change_pct = market_context.get("change_pct")
            if change_pct is not None:
                ctx_lines.append(f"- Change: {change_pct:+.2f}%")
            technicals = market_context.get("technicals", {})
            if technicals:
                rsi = technicals.get("rsi")
                if rsi:
                    ctx_lines.append(f"- RSI(14): {rsi:.1f}")
                macd = technicals.get("macd")
                if macd is not None:
                    ctx_lines.append(f"- MACD: {macd:.4f}")

            messages.append({
                "role": "system",
                "content": "\n".join(ctx_lines),
            })

        # Inject recent conversation history (last 16 turns from DB)
        history = await memory.get_conversation_messages(n=16)
        messages.extend(history)

        # Add current user message
        messages.append({"role": "user", "content": user_message})
        return messages

    @retry(
        stop=stop_after_attempt(2),
        wait=wait_exponential(multiplier=1, min=1, max=4),
        reraise=True,
    )
    async def _call_llm(
        self,
        messages: List[Dict[str, str]],
        use_groq: bool = False,
    ) -> str:
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
            return self._fallback_response(messages[-1]["content"])

        resp = await client.post(
            url,
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={"model": model, "messages": messages, "temperature": 0.3, "max_tokens": 2048},
        )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"]

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
    ) -> Tuple[str, Dict[str, Any]]:
        """
        Process a user message and return (response_text, metadata).

        Stores the turn in memory automatically.
        """
        intent = classify_intent(user_message)
        symbols = extract_symbols(user_message)

        # Update active symbol if one was mentioned
        if symbols:
            await memory.set_active_symbol(symbols[0])

        messages = await self._build_messages(user_message, memory, market_context)

        try:
            if not settings.nexus_api_key and not settings.groq_api_key:
                response = self._fallback_response(user_message, market_context)
            else:
                response = await self._call_llm(messages)
        except Exception as exc:
            log.warning("nexus_trader.llm_primary_failed", error=str(exc))
            try:
                response = await self._call_llm(messages, use_groq=True)
            except Exception as exc2:
                log.error("nexus_trader.llm_all_failed", error=str(exc2))
                response = self._fallback_response(user_message, market_context)

        # Persist both turns to SQLite
        await memory.add_turn("user", user_message, metadata={"intent": intent, "symbols": symbols})
        await memory.add_turn("assistant", response)

        metadata = {
            "intent": intent,
            "symbols": symbols,
            "active_symbol": await memory.get_active_symbol(),
        }
        return response, metadata


# Singleton
conversation_engine = NexusConversationEngine()
