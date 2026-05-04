"""
Market Data Service — multi-provider stock and options data.

Provider priority:
  1. Polygon.io  — real-time quotes, historical OHLCV, options chains
  2. Alpha Vantage — historical OHLCV fallback (free tier)
  3. Yahoo Finance chart API — last-resort free delayed stock data

All public methods return normalized dicts so callers are provider-agnostic.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from app.core.config import settings

log = logging.getLogger(__name__)

# ── Helpers ───────────────────────────────────────────────────────────────────

def _today() -> str:
    return date.today().isoformat()

def _n_years_ago(n: int) -> str:
    return (date.today() - timedelta(days=365 * n)).isoformat()


# ── Polygon.io client ─────────────────────────────────────────────────────────

class PolygonClient:
    BASE = "https://api.polygon.io"

    def __init__(self):
        self._client: Optional[httpx.AsyncClient] = None

    async def _get(self, path: str, params: Dict[str, Any] = None) -> Dict[str, Any]:
        if not settings.polygon_api_key:
            raise ValueError("POLYGON_API_KEY not configured")
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(timeout=30.0)
        p = params or {}
        p["apiKey"] = settings.polygon_api_key
        resp = await self._client.get(f"{self.BASE}{path}", params=p)
        resp.raise_for_status()
        return resp.json()

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=8))
    async def get_quote(self, symbol: str) -> Dict[str, Any]:
        data = await self._get(f"/v2/last/trade/{symbol.upper()}")
        result = data.get("results", {})
        return {
            "symbol": symbol.upper(),
            "price": result.get("p", 0),
            "size": result.get("s", 0),
            "timestamp": result.get("t", 0),
            "source": "polygon",
        }

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=8))
    async def get_snapshot(self, symbol: str) -> Dict[str, Any]:
        data = await self._get(f"/v2/snapshot/locale/us/markets/stocks/tickers/{symbol.upper()}")
        ticker = data.get("ticker", {})
        day = ticker.get("day", {})
        prev = ticker.get("prevDay", {})
        return {
            "symbol": symbol.upper(),
            "price": ticker.get("lastTrade", {}).get("p", day.get("c", 0)),
            "open": day.get("o", 0),
            "high": day.get("h", 0),
            "low": day.get("l", 0),
            "close": day.get("c", 0),
            "volume": day.get("v", 0),
            "vwap": day.get("vw", 0),
            "prev_close": prev.get("c", 0),
            "change": ticker.get("todaysChange", 0),
            "change_pct": ticker.get("todaysChangePerc", 0),
            "source": "polygon",
        }

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=8))
    async def get_ohlcv(
        self,
        symbol: str,
        from_date: str,
        to_date: str,
        timespan: str = "day",
        multiplier: int = 1,
    ) -> List[Dict[str, Any]]:
        data = await self._get(
            f"/v2/aggs/ticker/{symbol.upper()}/range/{multiplier}/{timespan}/{from_date}/{to_date}",
            params={"adjusted": "true", "sort": "asc", "limit": 50000},
        )
        bars = data.get("results", [])
        return [
            {
                "date": datetime.fromtimestamp(b["t"] / 1000).strftime("%Y-%m-%d"),
                "open": b.get("o", 0),
                "high": b.get("h", 0),
                "low": b.get("l", 0),
                "close": b.get("c", 0),
                "volume": b.get("v", 0),
                "vwap": b.get("vw", 0),
            }
            for b in bars
        ]

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=8))
    async def get_options_chain(
        self,
        symbol: str,
        expiration_date: Optional[str] = None,
        option_type: Optional[str] = None,  # "call" or "put"
        strike_price_gte: Optional[float] = None,
        strike_price_lte: Optional[float] = None,
    ) -> List[Dict[str, Any]]:
        params: Dict[str, Any] = {
            "underlying_ticker": symbol.upper(),
            "limit": 250,
            "sort": "strike_price",
        }
        if expiration_date:
            params["expiration_date"] = expiration_date
        if option_type:
            params["contract_type"] = option_type
        if strike_price_gte:
            params["strike_price.gte"] = strike_price_gte
        if strike_price_lte:
            params["strike_price.lte"] = strike_price_lte

        data = await self._get("/v3/reference/options/contracts", params=params)
        results = data.get("results", [])
        return [
            {
                "ticker": r.get("ticker"),
                "underlying": r.get("underlying_ticker"),
                "type": r.get("contract_type"),
                "strike": r.get("strike_price"),
                "expiration": r.get("expiration_date"),
                "shares_per_contract": r.get("shares_per_contract", 100),
            }
            for r in results
        ]

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=8))
    async def get_options_snapshot(self, option_ticker: str) -> Dict[str, Any]:
        data = await self._get(f"/v3/snapshot/options/{option_ticker}")
        r = data.get("results", {})
        greeks = r.get("greeks", {})
        details = r.get("details", {})
        day = r.get("day", {})
        return {
            "ticker": option_ticker,
            "underlying": details.get("underlying_ticker"),
            "type": details.get("contract_type"),
            "strike": details.get("strike_price"),
            "expiration": details.get("expiration_date"),
            "price": r.get("last_quote", {}).get("midpoint", 0),
            "bid": r.get("last_quote", {}).get("bid", 0),
            "ask": r.get("last_quote", {}).get("ask", 0),
            "volume": day.get("volume", 0),
            "open_interest": r.get("open_interest", 0),
            "iv": r.get("implied_volatility", 0),
            "delta": greeks.get("delta", 0),
            "gamma": greeks.get("gamma", 0),
            "theta": greeks.get("theta", 0),
            "vega": greeks.get("vega", 0),
            "source": "polygon",
        }

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=8))
    async def get_unusual_options_activity(self, symbol: str) -> List[Dict[str, Any]]:
        """Fetch options with unusually high volume relative to open interest."""
        # Get all options snapshots and filter for unusual activity
        data = await self._get(
            f"/v3/snapshot/options/{symbol.upper()}",
            params={"limit": 250},
        )
        results = data.get("results", [])
        unusual = []
        for r in results:
            day = r.get("day", {})
            oi = r.get("open_interest", 1) or 1
            vol = day.get("volume", 0)
            vol_oi_ratio = vol / oi
            if vol_oi_ratio >= 2.0 and vol >= 500:  # 2x OI and meaningful volume
                details = r.get("details", {})
                greeks = r.get("greeks", {})
                unusual.append({
                    "ticker": r.get("ticker"),
                    "type": details.get("contract_type"),
                    "strike": details.get("strike_price"),
                    "expiration": details.get("expiration_date"),
                    "volume": vol,
                    "open_interest": oi,
                    "vol_oi_ratio": round(vol_oi_ratio, 2),
                    "iv": r.get("implied_volatility", 0),
                    "delta": greeks.get("delta", 0),
                    "bid": r.get("last_quote", {}).get("bid", 0),
                    "ask": r.get("last_quote", {}).get("ask", 0),
                })
        unusual.sort(key=lambda x: x["vol_oi_ratio"], reverse=True)
        return unusual[:20]


# ── Alpha Vantage fallback ────────────────────────────────────────────────────

class AlphaVantageClient:
    BASE = "https://www.alphavantage.co/query"

    def __init__(self):
        self._client: Optional[httpx.AsyncClient] = None

    async def _get(self, params: Dict[str, Any]) -> Dict[str, Any]:
        if not settings.alpha_vantage_api_key:
            raise ValueError("ALPHA_VANTAGE_API_KEY not configured")
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(timeout=30.0)
        params["apikey"] = settings.alpha_vantage_api_key
        resp = await self._client.get(self.BASE, params=params)
        resp.raise_for_status()
        return resp.json()

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=2, max=10))
    async def get_daily_ohlcv(
        self, symbol: str, outputsize: str = "full"
    ) -> List[Dict[str, Any]]:
        data = await self._get({
            "function": "TIME_SERIES_DAILY_ADJUSTED",
            "symbol": symbol.upper(),
            "outputsize": outputsize,
        })
        ts = data.get("Time Series (Daily)", {})
        bars = []
        for date_str, values in sorted(ts.items()):
            bars.append({
                "date": date_str,
                "open": float(values.get("1. open", 0)),
                "high": float(values.get("2. high", 0)),
                "low": float(values.get("3. low", 0)),
                "close": float(values.get("5. adjusted close", values.get("4. close", 0))),
                "volume": int(values.get("6. volume", 0)),
                "vwap": None,
            })
        return bars

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=2, max=10))
    async def get_quote(self, symbol: str) -> Dict[str, Any]:
        data = await self._get({
            "function": "GLOBAL_QUOTE",
            "symbol": symbol.upper(),
        })
        q = data.get("Global Quote", {})
        price = float(q.get("05. price", 0))
        prev = float(q.get("08. previous close", 0))
        change_pct = float(q.get("10. change percent", "0%").replace("%", ""))
        return {
            "symbol": symbol.upper(),
            "price": price,
            "open": float(q.get("02. open", 0)),
            "high": float(q.get("03. high", 0)),
            "low": float(q.get("04. low", 0)),
            "prev_close": prev,
            "change": float(q.get("09. change", 0)),
            "change_pct": change_pct,
            "volume": int(q.get("06. volume", 0)),
            "source": "alpha_vantage",
        }

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=2, max=10))
    async def get_rsi(self, symbol: str, interval: str = "daily", period: int = 14) -> Optional[float]:
        data = await self._get({
            "function": "RSI",
            "symbol": symbol.upper(),
            "interval": interval,
            "time_period": period,
            "series_type": "close",
        })
        ts = data.get("Technical Analysis: RSI", {})
        if ts:
            latest_date = sorted(ts.keys())[-1]
            return float(ts[latest_date]["RSI"])
        return None

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=2, max=10))
    async def get_macd(self, symbol: str, interval: str = "daily") -> Dict[str, Optional[float]]:
        data = await self._get({
            "function": "MACD",
            "symbol": symbol.upper(),
            "interval": interval,
            "series_type": "close",
        })
        ts = data.get("Technical Analysis: MACD", {})
        if ts:
            latest_date = sorted(ts.keys())[-1]
            row = ts[latest_date]
            return {
                "macd": float(row.get("MACD", 0)),
                "signal": float(row.get("MACD_Signal", 0)),
                "hist": float(row.get("MACD_Hist", 0)),
            }
        return {"macd": None, "signal": None, "hist": None}

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=2, max=10))
    async def get_sma(self, symbol: str, period: int = 50, interval: str = "daily") -> Optional[float]:
        data = await self._get({
            "function": "SMA",
            "symbol": symbol.upper(),
            "interval": interval,
            "time_period": period,
            "series_type": "close",
        })
        ts = data.get(f"Technical Analysis: SMA", {})
        if ts:
            latest_date = sorted(ts.keys())[-1]
            return float(ts[latest_date]["SMA"])
        return None


# ── Yahoo Finance fallback ───────────────────────────────────────────────────

class YahooFinanceClient:
    """No-key delayed equities fallback using Yahoo's public chart endpoint."""

    BASE = "https://query1.finance.yahoo.com/v8/finance/chart"

    def __init__(self):
        self._client: Optional[httpx.AsyncClient] = None

    async def _get(self, symbol: str, params: Dict[str, Any]) -> Dict[str, Any]:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                timeout=30.0,
                headers={"User-Agent": "NexusTrader/1.0"},
            )
        resp = await self._client.get(f"{self.BASE}/{symbol.upper()}", params=params)
        resp.raise_for_status()
        return resp.json()

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=8))
    async def get_ohlcv(
        self,
        symbol: str,
        years: int = 5,
        interval: str = "1d",
    ) -> List[Dict[str, Any]]:
        period = f"{max(1, min(years, 10))}y"
        data = await self._get(symbol, {"range": period, "interval": interval, "events": "history"})
        result = (data.get("chart", {}).get("result") or [None])[0]
        if not result:
            return []

        timestamps = result.get("timestamp") or []
        quote = ((result.get("indicators") or {}).get("quote") or [{}])[0]
        adjclose = ((result.get("indicators") or {}).get("adjclose") or [{}])[0].get("adjclose") or []
        bars: List[Dict[str, Any]] = []
        for i, ts in enumerate(timestamps):
            close = self._at(adjclose, i) or self._at(quote.get("close"), i)
            open_ = self._at(quote.get("open"), i)
            high = self._at(quote.get("high"), i)
            low = self._at(quote.get("low"), i)
            volume = self._at(quote.get("volume"), i) or 0
            if close is None or open_ is None or high is None or low is None:
                continue
            bars.append({
                "date": datetime.fromtimestamp(ts).strftime("%Y-%m-%d"),
                "open": round(float(open_), 4),
                "high": round(float(high), 4),
                "low": round(float(low), 4),
                "close": round(float(close), 4),
                "volume": int(volume),
                "vwap": None,
            })
        return bars

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=8))
    async def get_quote(self, symbol: str) -> Dict[str, Any]:
        data = await self._get(symbol, {"range": "5d", "interval": "1d"})
        result = (data.get("chart", {}).get("result") or [None])[0]
        if not result:
            return {"symbol": symbol.upper(), "price": 0, "error": "No Yahoo Finance data returned"}

        meta = result.get("meta") or {}
        bars = await self.get_ohlcv(symbol, years=1)
        latest = bars[-1] if bars else {}
        prev = bars[-2]["close"] if len(bars) >= 2 else meta.get("previousClose", 0)
        price = float(meta.get("regularMarketPrice") or latest.get("close") or 0)
        change = price - float(prev or 0) if price and prev else 0
        change_pct = change / float(prev) * 100 if prev else 0

        return {
            "symbol": symbol.upper(),
            "price": round(price, 4),
            "open": latest.get("open", 0),
            "high": latest.get("high", 0),
            "low": latest.get("low", 0),
            "close": latest.get("close", price),
            "volume": latest.get("volume", 0),
            "prev_close": round(float(prev), 4) if prev else 0,
            "change": round(change, 4),
            "change_pct": round(change_pct, 4),
            "source": "yahoo_finance",
        }

    @staticmethod
    def _at(values: Optional[List[Any]], index: int) -> Optional[float]:
        if not values or index >= len(values):
            return None
        value = values[index]
        return None if value is None else float(value)


# ── Tradier options client ───────────────────────────────────────────────────

class TradierClient:
    """Tradier market-data client for options expirations and chains."""

    def __init__(self):
        self._client: Optional[httpx.AsyncClient] = None

    async def _get(self, path: str, params: Dict[str, Any] = None) -> Dict[str, Any]:
        if not settings.tradier_api_key:
            raise ValueError("TRADIER_API_KEY not configured")
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(timeout=30.0)
        resp = await self._client.get(
            f"{settings.tradier_base_url}{path}",
            headers={
                "Authorization": f"Bearer {settings.tradier_api_key}",
                "Accept": "application/json",
            },
            params=params or {},
        )
        resp.raise_for_status()
        return resp.json()

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=8))
    async def get_expirations(self, symbol: str) -> List[str]:
        data = await self._get("/markets/options/expirations", {"symbol": symbol.upper()})
        dates = data.get("expirations", {}).get("date", [])
        if isinstance(dates, str):
            return [dates]
        return dates or []

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=8))
    async def get_options_chain(
        self,
        symbol: str,
        expiration_date: Optional[str] = None,
        option_type: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        expiration = expiration_date
        if not expiration:
            expirations = await self.get_expirations(symbol)
            if not expirations:
                return []
            expiration = expirations[0]

        data = await self._get(
            "/markets/options/chains",
            {"symbol": symbol.upper(), "expiration": expiration, "greeks": "true"},
        )
        options = data.get("options", {}).get("option", [])
        if isinstance(options, dict):
            options = [options]

        normalized = []
        for contract in options:
            contract_type = contract.get("option_type") or contract.get("type")
            if option_type and contract_type != option_type:
                continue
            greeks = contract.get("greeks") or {}
            normalized.append({
                "ticker": contract.get("symbol"),
                "underlying": contract.get("root_symbol") or symbol.upper(),
                "type": contract_type,
                "strike": contract.get("strike"),
                "expiration": contract.get("expiration_date") or expiration,
                "bid": contract.get("bid") or 0,
                "ask": contract.get("ask") or 0,
                "last": contract.get("last") or 0,
                "volume": contract.get("volume") or 0,
                "open_interest": contract.get("open_interest") or 0,
                "iv": greeks.get("mid_iv") or greeks.get("smv_vol") or greeks.get("iv"),
                "delta": greeks.get("delta"),
                "gamma": greeks.get("gamma"),
                "theta": greeks.get("theta"),
                "vega": greeks.get("vega"),
                "source": "tradier",
            })
        return normalized


# ── Unified facade ────────────────────────────────────────────────────────────

class MarketDataService:
    """
    Provider-agnostic market data facade.

    Tries Polygon first, falls back to Alpha Vantage.
    """

    def __init__(self):
        self.polygon = PolygonClient()
        self.alpha_vantage = AlphaVantageClient()
        self.yahoo = YahooFinanceClient()
        self.tradier = TradierClient()

    async def get_quote(self, symbol: str) -> Dict[str, Any]:
        """Get current quote for a symbol."""
        if settings.polygon_api_key:
            try:
                return await self.polygon.get_snapshot(symbol)
            except Exception as e:
                log.warning("polygon_snapshot_failed", symbol=symbol, error=str(e))
        if settings.alpha_vantage_api_key:
            try:
                return await self.alpha_vantage.get_quote(symbol)
            except Exception as e:
                log.warning("alpha_vantage_quote_failed", symbol=symbol, error=str(e))
        try:
            return await self.yahoo.get_quote(symbol)
        except Exception as e:
            log.warning("yahoo_quote_failed", symbol=symbol, error=str(e))
        return {"symbol": symbol.upper(), "price": 0, "error": "No market data provider configured or reachable"}

    async def get_historical_ohlcv(
        self,
        symbol: str,
        years: int = 5,
        timespan: str = "day",
    ) -> List[Dict[str, Any]]:
        """Get historical OHLCV bars going back `years` years."""
        from_date = _n_years_ago(years)
        to_date = _today()

        if settings.polygon_api_key:
            try:
                return await self.polygon.get_ohlcv(symbol, from_date, to_date, timespan)
            except Exception as e:
                log.warning("polygon_ohlcv_failed", symbol=symbol, error=str(e))

        if settings.alpha_vantage_api_key:
            try:
                bars = await self.alpha_vantage.get_daily_ohlcv(symbol, outputsize="full")
                cutoff = from_date
                return [b for b in bars if b["date"] >= cutoff]
            except Exception as e:
                log.warning("alpha_vantage_ohlcv_failed", symbol=symbol, error=str(e))

        try:
            return await self.yahoo.get_ohlcv(symbol, years=years)
        except Exception as e:
            log.warning("yahoo_ohlcv_failed", symbol=symbol, error=str(e))

        return []

    async def get_technicals(self, symbol: str) -> Dict[str, Any]:
        """Fetch key technical indicators for a symbol."""
        technicals: Dict[str, Any] = {}

        if settings.alpha_vantage_api_key:
            try:
                rsi_task = self.alpha_vantage.get_rsi(symbol)
                macd_task = self.alpha_vantage.get_macd(symbol)
                sma50_task = self.alpha_vantage.get_sma(symbol, 50)
                sma200_task = self.alpha_vantage.get_sma(symbol, 200)
                rsi, macd, sma50, sma200 = await asyncio.gather(
                    rsi_task, macd_task, sma50_task, sma200_task,
                    return_exceptions=True,
                )
                if not isinstance(rsi, Exception):
                    technicals["rsi"] = rsi
                if not isinstance(macd, Exception) and isinstance(macd, dict):
                    technicals["macd"] = macd.get("macd")
                    technicals["macd_signal"] = macd.get("signal")
                    technicals["macd_hist"] = macd.get("hist")
                if not isinstance(sma50, Exception):
                    technicals["sma_50"] = sma50
                if not isinstance(sma200, Exception):
                    technicals["sma_200"] = sma200
            except Exception as e:
                log.warning("technicals_fetch_failed", symbol=symbol, error=str(e))

        if not {"rsi", "macd", "sma_50", "sma_200"}.issubset(technicals):
            try:
                bars = await self.get_historical_ohlcv(symbol, years=2)
                local = compute_local_technicals(bars)
                for key, value in local.items():
                    technicals.setdefault(key, value)
            except Exception as e:
                log.warning("local_technicals_failed", symbol=symbol, error=str(e))

        return technicals

    async def get_options_chain(
        self,
        symbol: str,
        expiration_date: Optional[str] = None,
        option_type: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        if settings.polygon_api_key:
            try:
                return await self.polygon.get_options_chain(
                    symbol, expiration_date, option_type
                )
            except Exception as e:
                log.warning("polygon_options_chain_failed", symbol=symbol, error=str(e))
        if settings.tradier_api_key:
            try:
                return await self.tradier.get_options_chain(
                    symbol, expiration_date, option_type
                )
            except Exception as e:
                log.warning("tradier_options_chain_failed", symbol=symbol, error=str(e))
        return []

    async def get_unusual_options_activity(self, symbol: str) -> List[Dict[str, Any]]:
        if settings.polygon_api_key:
            try:
                return await self.polygon.get_unusual_options_activity(symbol)
            except Exception as e:
                log.warning("polygon_unusual_options_failed", symbol=symbol, error=str(e))
        return []

    async def get_full_market_context(self, symbol: str) -> Dict[str, Any]:
        """Fetch quote + technicals in parallel for AI context injection."""
        quote_task = self.get_quote(symbol)
        tech_task = self.get_technicals(symbol)
        quote, technicals = await asyncio.gather(quote_task, tech_task, return_exceptions=True)

        ctx: Dict[str, Any] = {"symbol": symbol.upper()}
        if not isinstance(quote, Exception):
            ctx.update(quote)
        if not isinstance(technicals, Exception):
            ctx["technicals"] = technicals

        return ctx


# Singleton
market_data_service = MarketDataService()


# ── Local technical indicators ────────────────────────────────────────────────

def compute_local_technicals(bars: List[Dict[str, Any]]) -> Dict[str, Any]:
    closes = [float(b["close"]) for b in bars if b.get("close") is not None]
    if len(closes) < 20:
        return {}

    macd_line, signal_line = _macd(closes)
    result: Dict[str, Any] = {
        "rsi": _rsi(closes, 14),
        "sma_50": _sma(closes, 50),
        "sma_200": _sma(closes, 200),
    }
    if macd_line is not None and signal_line is not None:
        result["macd"] = round(macd_line, 4)
        result["macd_signal"] = round(signal_line, 4)
        result["macd_hist"] = round(macd_line - signal_line, 4)
    return {k: v for k, v in result.items() if v is not None}


def _sma(values: List[float], period: int) -> Optional[float]:
    if len(values) < period:
        return None
    return round(sum(values[-period:]) / period, 4)


def _ema_series(values: List[float], period: int) -> List[float]:
    if not values:
        return []
    multiplier = 2 / (period + 1)
    ema = values[0]
    series = [ema]
    for value in values[1:]:
        ema = (value - ema) * multiplier + ema
        series.append(ema)
    return series


def _macd(values: List[float]) -> tuple[Optional[float], Optional[float]]:
    if len(values) < 35:
        return None, None
    ema12 = _ema_series(values, 12)
    ema26 = _ema_series(values, 26)
    macd_values = [a - b for a, b in zip(ema12, ema26)]
    signal = _ema_series(macd_values, 9)
    return macd_values[-1], signal[-1] if signal else None


def _rsi(values: List[float], period: int = 14) -> Optional[float]:
    if len(values) <= period:
        return None
    gains = []
    losses = []
    for prev, current in zip(values[-period - 1:-1], values[-period:]):
        change = current - prev
        gains.append(max(change, 0))
        losses.append(abs(min(change, 0)))
    avg_gain = sum(gains) / period
    avg_loss = sum(losses) / period
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return round(100 - (100 / (1 + rs)), 2)
