"""News and social event intelligence for options-aware predictions.

This module ingests market-moving headlines, social sentiment shifts, and viral
trend signals through small source adapters. It classifies each event, compares
it with completed historical analogues, estimates whether calls/puts tended to
benefit, and records outcomes so the weights adapt over time.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import math
import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Dict, Iterable, List, Optional, Protocol

import aiosqlite
import httpx
from textblob import TextBlob

from app.core.config import settings
from app.db.database import get_db
from app.services.market_data import market_data_service

log = logging.getLogger(__name__)

DISCLAIMER = (
    "Event intelligence is a probabilistic research input. It is not financial "
    "advice, and historical reactions do not guarantee future options outcomes."
)

EVENT_CATEGORIES = {
    "earnings": ["earnings", "revenue", "guidance", "eps", "profit", "quarter"],
    "macro": ["fed", "inflation", "cpi", "ppi", "rates", "gdp", "jobs", "unemployment", "treasury"],
    "geopolitical": ["war", "sanction", "tariff", "election", "attack", "conflict", "china", "opec"],
    "regulatory": ["sec", "doj", "ftc", "fda", "lawsuit", "probe", "ban", "approval", "antitrust"],
    "product": ["launch", "product", "chip", "ai", "model", "delivery", "recall", "upgrade"],
    "analyst": ["upgrade", "downgrade", "price target", "initiates", "rating"],
    "social_trend": ["trending", "viral", "mentions", "short squeeze", "meme", "reddit", "twitter", "x.com"],
    "options_flow": ["calls", "puts", "sweep", "unusual options", "open interest", "volatility"],
}

BULLISH_TERMS = {
    "beat", "beats", "upgrade", "approval", "record", "surge", "rally", "strong",
    "buy", "growth", "partnership", "launch", "profit", "raises", "outperform",
}
BEARISH_TERMS = {
    "miss", "misses", "downgrade", "probe", "lawsuit", "recall", "cut", "cuts",
    "weak", "sell", "drop", "falls", "slump", "ban", "risk", "underperform",
}
VOLATILITY_TERMS = {"earnings", "cpi", "fed", "fda", "lawsuit", "merger", "squeeze", "war"}


@dataclass
class EventSignal:
    source: str
    source_event_id: str
    symbol: str
    event_time: datetime
    title: str
    summary: str = ""
    url: Optional[str] = None
    sentiment_score: float = 0.0
    virality_score: float = 0.0
    source_credibility: float = 0.5
    raw_payload: Dict[str, Any] = field(default_factory=dict)


class EventSource(Protocol):
    name: str

    async def fetch(self, symbol: str) -> List[EventSignal]:
        ...


def _utcnow() -> datetime:
    return datetime.utcnow()


def _parse_time(value: Any) -> datetime:
    if not value:
        return _utcnow()
    if isinstance(value, (int, float)):
        timestamp = value / 1000 if value > 10_000_000_000 else value
        return datetime.utcfromtimestamp(timestamp)
    text = str(value).replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(text).replace(tzinfo=None)
    except ValueError:
        return _utcnow()


def _stable_id(*parts: Any) -> str:
    raw = "|".join(str(p or "") for p in parts)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


class AlphaVantageNewsSentimentSource:
    name = "alpha_vantage_news_sentiment"

    async def fetch(self, symbol: str) -> List[EventSignal]:
        if not settings.alpha_vantage_api_key:
            return []
        async with httpx.AsyncClient(timeout=25.0) as client:
            resp = await client.get(
                settings.alpha_vantage_base_url,
                params={
                    "function": "NEWS_SENTIMENT",
                    "tickers": symbol.upper(),
                    "limit": 50,
                    "apikey": settings.alpha_vantage_api_key,
                },
            )
            resp.raise_for_status()
            data = resp.json()

        signals: List[EventSignal] = []
        for item in data.get("feed", []) or []:
            ticker_sentiment = item.get("ticker_sentiment") or []
            symbol_sentiment = next(
                (t for t in ticker_sentiment if t.get("ticker", "").upper() == symbol.upper()),
                {},
            )
            sentiment = float(symbol_sentiment.get("ticker_sentiment_score") or item.get("overall_sentiment_score") or 0)
            relevance = float(symbol_sentiment.get("relevance_score") or item.get("relevance_score") or 0.5)
            title = item.get("title") or "Untitled market news"
            url = item.get("url")
            signals.append(EventSignal(
                source=self.name,
                source_event_id=_stable_id(url, title, item.get("time_published")),
                symbol=symbol.upper(),
                event_time=_parse_time(item.get("time_published")),
                title=title,
                summary=item.get("summary") or "",
                url=url,
                sentiment_score=_clamp(sentiment, -1, 1),
                virality_score=_clamp(relevance, 0, 1),
                source_credibility=0.8,
                raw_payload=item,
            ))
        return signals


class NewsApiSource:
    name = "newsapi"

    async def fetch(self, symbol: str) -> List[EventSignal]:
        if not settings.news_api_key:
            return []
        query = f'({symbol.upper()} OR "{symbol.upper()} stock")'
        async with httpx.AsyncClient(timeout=25.0) as client:
            resp = await client.get(
                f"{settings.news_api_base_url}/everything",
                params={
                    "q": query,
                    "language": "en",
                    "sortBy": "publishedAt",
                    "pageSize": 50,
                    "apiKey": settings.news_api_key,
                },
            )
            resp.raise_for_status()
            data = resp.json()

        signals = []
        for item in data.get("articles", []) or []:
            title = item.get("title") or "Untitled market headline"
            summary = item.get("description") or item.get("content") or ""
            text_sentiment = TextBlob(f"{title}. {summary}").sentiment.polarity
            url = item.get("url")
            signals.append(EventSignal(
                source=self.name,
                source_event_id=_stable_id(url, title, item.get("publishedAt")),
                symbol=symbol.upper(),
                event_time=_parse_time(item.get("publishedAt")),
                title=title,
                summary=summary,
                url=url,
                sentiment_score=_clamp(text_sentiment, -1, 1),
                virality_score=0.35,
                source_credibility=0.65,
                raw_payload=item,
            ))
        return signals


class TwitterRecentSearchSource:
    name = "twitter_recent_search"

    async def fetch(self, symbol: str) -> List[EventSignal]:
        if not settings.twitter_bearer_token:
            return []
        query = f"(${symbol.upper()} OR {symbol.upper()} stock OR {symbol.upper()} calls OR {symbol.upper()} puts) lang:en -is:retweet"
        async with httpx.AsyncClient(timeout=25.0) as client:
            resp = await client.get(
                "https://api.twitter.com/2/tweets/search/recent",
                headers={"Authorization": f"Bearer {settings.twitter_bearer_token}"},
                params={
                    "query": query,
                    "max_results": 50,
                    "tweet.fields": "created_at,public_metrics,author_id",
                },
            )
            resp.raise_for_status()
            data = resp.json()

        signals = []
        for item in data.get("data", []) or []:
            text = item.get("text") or ""
            metrics = item.get("public_metrics") or {}
            engagement = sum(float(metrics.get(k) or 0) for k in ("retweet_count", "reply_count", "like_count", "quote_count"))
            virality = _clamp(math.log10(engagement + 1) / 5, 0, 1)
            signals.append(EventSignal(
                source=self.name,
                source_event_id=str(item.get("id") or _stable_id(text, item.get("created_at"))),
                symbol=symbol.upper(),
                event_time=_parse_time(item.get("created_at")),
                title=text[:240],
                summary=text,
                url=f"https://twitter.com/i/web/status/{item.get('id')}" if item.get("id") else None,
                sentiment_score=_clamp(TextBlob(text).sentiment.polarity, -1, 1),
                virality_score=virality,
                source_credibility=0.45,
                raw_payload=item,
            ))
        return signals


class GenericSocialSentimentSource:
    """Adapter for paid sentiment APIs that return normalized or near-normalized JSON."""

    name = "generic_social_sentiment"

    async def fetch(self, symbol: str) -> List[EventSignal]:
        if not settings.social_sentiment_api_url:
            return []
        headers = {}
        if settings.social_sentiment_api_key:
            headers["Authorization"] = f"Bearer {settings.social_sentiment_api_key}"
        async with httpx.AsyncClient(timeout=25.0) as client:
            resp = await client.get(settings.social_sentiment_api_url, params={"symbol": symbol.upper()}, headers=headers)
            resp.raise_for_status()
            data = resp.json()

        rows = data.get("events") or data.get("data") or data.get("results") or []
        if isinstance(rows, dict):
            rows = [rows]
        signals = []
        for item in rows:
            title = item.get("title") or item.get("text") or item.get("headline") or f"{symbol.upper()} sentiment shift"
            summary = item.get("summary") or item.get("description") or item.get("text") or ""
            sentiment = float(item.get("sentiment_score") or item.get("sentiment") or TextBlob(f"{title}. {summary}").sentiment.polarity)
            virality = float(item.get("virality_score") or item.get("mention_velocity") or item.get("volume_score") or 0.5)
            signals.append(EventSignal(
                source=item.get("source") or self.name,
                source_event_id=str(item.get("id") or _stable_id(title, item.get("timestamp"), symbol)),
                symbol=symbol.upper(),
                event_time=_parse_time(item.get("timestamp") or item.get("published_at") or item.get("created_at")),
                title=title,
                summary=summary,
                url=item.get("url"),
                sentiment_score=_clamp(sentiment, -1, 1),
                virality_score=_clamp(virality, 0, 1),
                source_credibility=_clamp(float(item.get("source_credibility") or 0.55), 0, 1),
                raw_payload=item,
            ))
        return signals


class EventIntelligenceService:
    horizon_days = 7
    min_option_move_pct = 0.012

    def __init__(self, sources: Optional[List[EventSource]] = None):
        self.sources = sources or [
            AlphaVantageNewsSentimentSource(),
            NewsApiSource(),
            TwitterRecentSearchSource(),
            GenericSocialSentimentSource(),
        ]

    async def ingest(self, symbols: Iterable[str]) -> Dict[str, Any]:
        symbols = [s.upper() for s in symbols if s]
        totals = {"symbols": symbols, "fetched": 0, "stored": 0, "errors": []}
        for symbol in symbols:
            await self.score_due_outcomes(symbol)
            fetched = await asyncio.gather(
                *(source.fetch(symbol) for source in self.sources),
                return_exceptions=True,
            )
            for result in fetched:
                if isinstance(result, Exception):
                    totals["errors"].append(str(result))
                    continue
                totals["fetched"] += len(result)
                for signal in result:
                    classified = await self.classify(signal)
                    stored = await self._store_event(signal, classified)
                    totals["stored"] += 1 if stored else 0
        return totals

    async def build_symbol_intelligence(self, symbol: str, fresh: bool = True) -> Dict[str, Any]:
        symbol = symbol.upper()
        if fresh:
            await self.ingest([symbol])
        else:
            await self.score_due_outcomes(symbol)

        events = await self._recent_events(symbol)
        top_events = []
        bullish = bearish = volatility = 0.0
        for event in events:
            analogues = await self._historical_analogues(
                symbol=symbol,
                category=event["category"],
                direction=event["direction"],
                source=event["source"],
            )
            enriched = {**event, "historical_analogues": analogues}
            top_events.append(enriched)
            score = float(event["impact_score"] or 0)
            if event["direction"] == "bullish":
                bullish += score
            elif event["direction"] == "bearish":
                bearish += score
            elif event["direction"] == "volatility":
                volatility += score

        composite = self._composite_signal(bullish, bearish, volatility, top_events)
        return {
            "symbol": symbol,
            "composite": composite,
            "events": top_events[:12],
            "source_status": self.source_status(),
            "disclaimer": DISCLAIMER,
        }

    async def classify(self, signal: EventSignal) -> Dict[str, Any]:
        text = f"{signal.title} {signal.summary}".lower()
        category = self._category(text)
        direction = self._direction(text, signal.sentiment_score)
        option_bias = self._option_bias(category, direction, text)
        learning = await self._learning_factor(signal.source, category, direction)
        recency = self._recency_score(signal.event_time)
        text_intensity = self._text_intensity(text)
        impact_score = (
            abs(signal.sentiment_score) * 30
            + signal.virality_score * 25
            + signal.source_credibility * 20
            + text_intensity * 15
            + recency * 10
        ) * learning
        confidence = _clamp(
            0.32
            + abs(signal.sentiment_score) * 0.24
            + signal.virality_score * 0.16
            + signal.source_credibility * 0.18
            + (learning - 1) * 0.12,
            0.2,
            0.9,
        )
        return {
            "category": category,
            "direction": direction,
            "option_bias": option_bias,
            "impact_score": round(_clamp(impact_score, 0, 100), 2),
            "confidence": round(confidence, 2),
            "learning_factor": round(learning, 2),
        }

    async def score_due_outcomes(self, symbol: str) -> None:
        async with get_db() as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                """
                SELECT * FROM market_events
                WHERE symbol = ? AND outcome_status = 'pending'
                ORDER BY event_time ASC
                """,
                (symbol.upper(),),
            )
            rows = await cursor.fetchall()
        if not rows:
            return

        bars = await market_data_service.get_historical_ohlcv(symbol, years=2)
        if not bars:
            return

        async with get_db() as db:
            for row in rows:
                event_time = datetime.fromisoformat(row["event_time"])
                due_at = event_time + timedelta(days=int(row["horizon_days"]))
                if _utcnow() < due_at:
                    continue
                entry_bar = self._first_bar_on_or_after(bars, event_time)
                exit_bar = self._first_bar_on_or_after(bars, due_at)
                if not entry_bar or not exit_bar:
                    continue
                entry_price = float(entry_bar["close"])
                exit_price = float(exit_bar["close"])
                move_pct = (exit_price - entry_price) / entry_price * 100 if entry_price else 0
                call_result = "win" if move_pct >= self.min_option_move_pct * 100 else "loss"
                put_result = "win" if move_pct <= -self.min_option_move_pct * 100 else "loss"
                await db.execute(
                    """
                    UPDATE market_events
                    SET outcome_status = 'scored', outcome_checked_at = ?, entry_price = ?,
                        exit_price = ?, underlying_move_pct = ?, call_result = ?, put_result = ?
                    WHERE id = ?
                    """,
                    (
                        _utcnow().isoformat(),
                        round(entry_price, 4),
                        round(exit_price, 4),
                        round(move_pct, 3),
                        call_result,
                        put_result,
                        row["id"],
                    ),
                )
                await self._update_learning(db, row, move_pct, call_result, put_result)
            await db.commit()

    def source_status(self) -> List[Dict[str, Any]]:
        return [
            {
                "name": "Alpha Vantage News Sentiment",
                "configured": bool(settings.alpha_vantage_api_key),
                "capabilities": ["news", "ticker_sentiment"],
            },
            {
                "name": "NewsAPI",
                "configured": bool(settings.news_api_key),
                "capabilities": ["global_news"],
            },
            {
                "name": "Twitter/X Recent Search",
                "configured": bool(settings.twitter_bearer_token),
                "capabilities": ["social_posts", "engagement_velocity"],
            },
            {
                "name": "Generic Social Sentiment API",
                "configured": bool(settings.social_sentiment_api_url),
                "capabilities": ["sentiment_shifts", "viral_trends"],
            },
        ]

    def _category(self, text: str) -> str:
        scores = {
            category: sum(1 for term in terms if term in text)
            for category, terms in EVENT_CATEGORIES.items()
        }
        best = max(scores, key=scores.get)
        return best if scores[best] > 0 else "general_news"

    def _direction(self, text: str, sentiment: float) -> str:
        bullish_hits = sum(1 for term in BULLISH_TERMS if re.search(rf"\b{re.escape(term)}\b", text))
        bearish_hits = sum(1 for term in BEARISH_TERMS if re.search(rf"\b{re.escape(term)}\b", text))
        volatility_hits = sum(1 for term in VOLATILITY_TERMS if term in text)
        if volatility_hits >= 2 and abs(sentiment) < 0.25:
            return "volatility"
        score = sentiment + (bullish_hits - bearish_hits) * 0.18
        if score > 0.12:
            return "bullish"
        if score < -0.12:
            return "bearish"
        return "neutral"

    def _option_bias(self, category: str, direction: str, text: str) -> str:
        if "puts" in text and "calls" not in text:
            return "put"
        if "calls" in text and "puts" not in text:
            return "call"
        if direction == "bullish":
            return "call"
        if direction == "bearish":
            return "put"
        if direction == "volatility" or category in {"earnings", "macro", "regulatory", "options_flow"}:
            return "straddle"
        return "neutral"

    def _text_intensity(self, text: str) -> float:
        intensity_terms = ["breaking", "surge", "plunge", "record", "unexpected", "massive", "halts", "urgent"]
        return _clamp(sum(1 for term in intensity_terms if term in text) / 3, 0, 1)

    def _recency_score(self, event_time: datetime) -> float:
        hours = max(0.0, (_utcnow() - event_time).total_seconds() / 3600)
        return _clamp(1 - hours / 72, 0, 1)

    async def _learning_factor(self, source: str, category: str, direction: str) -> float:
        async with get_db() as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                "SELECT impact_weight FROM event_learning WHERE learning_key = ?",
                (self._learning_key(source, category, direction),),
            )
            row = await cursor.fetchone()
        return float(row["impact_weight"]) if row else 1.0

    async def _store_event(self, signal: EventSignal, classified: Dict[str, Any]) -> bool:
        async with get_db() as db:
            try:
                await db.execute(
                    """
                    INSERT INTO market_events (
                        id, source, source_event_id, symbol, event_time, title, summary, url,
                        category, direction, sentiment_score, virality_score, source_credibility,
                        impact_score, confidence, option_bias, horizon_days, raw_payload, created_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        str(uuid.uuid4()),
                        signal.source,
                        signal.source_event_id,
                        signal.symbol.upper(),
                        signal.event_time.isoformat(),
                        signal.title[:500],
                        signal.summary[:2500],
                        signal.url,
                        classified["category"],
                        classified["direction"],
                        signal.sentiment_score,
                        signal.virality_score,
                        signal.source_credibility,
                        classified["impact_score"],
                        classified["confidence"],
                        classified["option_bias"],
                        self.horizon_days,
                        json.dumps(signal.raw_payload),
                        _utcnow().isoformat(),
                    ),
                )
                await db.commit()
                return True
            except aiosqlite.IntegrityError:
                return False

    async def _recent_events(self, symbol: str) -> List[Dict[str, Any]]:
        cutoff = (_utcnow() - timedelta(days=14)).isoformat()
        async with get_db() as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                """
                SELECT * FROM market_events
                WHERE symbol = ? AND event_time >= ?
                ORDER BY impact_score DESC, event_time DESC
                LIMIT 40
                """,
                (symbol.upper(), cutoff),
            )
            rows = await cursor.fetchall()
        return [self._row_to_event(row) for row in rows]

    async def _historical_analogues(self, symbol: str, category: str, direction: str, source: str) -> Dict[str, Any]:
        async with get_db() as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                """
                SELECT * FROM market_events
                WHERE outcome_status = 'scored'
                  AND category = ?
                  AND direction = ?
                  AND (symbol = ? OR source = ?)
                ORDER BY event_time DESC
                LIMIT 200
                """,
                (category, direction, symbol.upper(), source),
            )
            rows = await cursor.fetchall()

        if not rows:
            return {
                "sample_size": 0,
                "call_win_rate": None,
                "put_win_rate": None,
                "avg_underlying_move_pct": None,
                "summary": "No completed analogue set yet; Nexus will learn as outcomes mature.",
            }
        call_wins = sum(1 for r in rows if r["call_result"] == "win")
        put_wins = sum(1 for r in rows if r["put_result"] == "win")
        avg_move = sum(float(r["underlying_move_pct"] or 0) for r in rows) / len(rows)
        favored = "calls" if call_wins > put_wins else "puts" if put_wins > call_wins else "neither side"
        return {
            "sample_size": len(rows),
            "call_win_rate": round(call_wins / len(rows) * 100, 1),
            "put_win_rate": round(put_wins / len(rows) * 100, 1),
            "avg_underlying_move_pct": round(avg_move, 2),
            "summary": f"Similar completed events historically favored {favored}.",
        }

    def _composite_signal(self, bullish: float, bearish: float, volatility: float, events: List[Dict[str, Any]]) -> Dict[str, Any]:
        net = bullish - bearish
        total = max(bullish + bearish + volatility, 1)
        if abs(net) < max(8, total * 0.12) and volatility > total * 0.25:
            bias = "volatility"
            option_bias = "straddle"
        elif net > 6:
            bias = "bullish"
            option_bias = "call"
        elif net < -6:
            bias = "bearish"
            option_bias = "put"
        else:
            bias = "neutral"
            option_bias = "neutral"
        confidence = _clamp(0.35 + min(abs(net) / total, 1) * 0.35 + min(len(events), 8) * 0.025, 0.25, 0.86)
        return {
            "bias": bias,
            "option_bias": option_bias,
            "confidence": round(confidence, 2),
            "raw_scores": {
                "bullish": round(bullish, 2),
                "bearish": round(bearish, 2),
                "volatility": round(volatility, 2),
            },
            "top_rationale": [e["title"] for e in events[:3]],
        }

    async def _update_learning(
        self,
        db: aiosqlite.Connection,
        row: aiosqlite.Row,
        move_pct: float,
        call_result: str,
        put_result: str,
    ) -> None:
        key = self._learning_key(row["source"], row["category"], row["direction"])
        cursor = await db.execute("SELECT * FROM event_learning WHERE learning_key = ?", (key,))
        current = await cursor.fetchone()
        total = int(current["total"]) if current else 0
        call_wins = int(current["call_wins"]) if current else 0
        put_wins = int(current["put_wins"]) if current else 0
        avg_move = float(current["avg_underlying_move_pct"]) if current else 0.0
        total += 1
        call_wins += 1 if call_result == "win" else 0
        put_wins += 1 if put_result == "win" else 0
        avg_move = avg_move + (move_pct - avg_move) / total
        directional_wins = call_wins if row["direction"] == "bullish" else put_wins if row["direction"] == "bearish" else max(call_wins, put_wins)
        win_rate = directional_wins / total if total else 0.5
        impact_weight = 1.0
        if total >= 5:
            impact_weight = _clamp(0.75 + win_rate * 0.6, 0.75, 1.25)
        await db.execute(
            """
            INSERT INTO event_learning (
                learning_key, source, category, direction, total, call_wins, put_wins,
                avg_underlying_move_pct, impact_weight, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(learning_key) DO UPDATE SET
                total = excluded.total,
                call_wins = excluded.call_wins,
                put_wins = excluded.put_wins,
                avg_underlying_move_pct = excluded.avg_underlying_move_pct,
                impact_weight = excluded.impact_weight,
                updated_at = excluded.updated_at
            """,
            (
                key,
                row["source"],
                row["category"],
                row["direction"],
                total,
                call_wins,
                put_wins,
                round(avg_move, 4),
                round(impact_weight, 3),
                _utcnow().isoformat(),
            ),
        )

    def _first_bar_on_or_after(self, bars: List[Dict[str, Any]], dt: datetime) -> Optional[Dict[str, Any]]:
        target = dt.date().isoformat()
        for bar in bars:
            if bar.get("date", "") >= target:
                return bar
        return None

    def _learning_key(self, source: str, category: str, direction: str) -> str:
        return f"{source}:{category}:{direction}"

    def _row_to_event(self, row: aiosqlite.Row) -> Dict[str, Any]:
        return {
            "id": row["id"],
            "source": row["source"],
            "symbol": row["symbol"],
            "event_time": row["event_time"],
            "title": row["title"],
            "summary": row["summary"],
            "url": row["url"],
            "category": row["category"],
            "direction": row["direction"],
            "option_bias": row["option_bias"],
            "sentiment_score": row["sentiment_score"],
            "virality_score": row["virality_score"],
            "impact_score": row["impact_score"],
            "confidence": row["confidence"],
            "outcome_status": row["outcome_status"],
            "underlying_move_pct": row["underlying_move_pct"],
            "call_result": row["call_result"],
            "put_result": row["put_result"],
        }


event_intelligence_service = EventIntelligenceService()


async def run_event_intelligence_loop() -> None:
    while settings.event_intelligence_autostart:
        try:
            await event_intelligence_service.ingest(settings.event_intelligence_symbols)
        except Exception as exc:
            log.warning("event_intelligence_loop_failed", extra={"error": str(exc)})
        await asyncio.sleep(max(60, settings.event_intelligence_interval_seconds))
