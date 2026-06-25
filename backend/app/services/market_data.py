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
from app.services.symbol_resolver import resolve_symbol

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

    @staticmethod
    def resolve_symbol(symbol: str, context: str = "") -> Dict[str, Any]:
        return resolve_symbol(symbol, context=context)

    async def get_quote(self, symbol: str) -> Dict[str, Any]:
        """Get current quote for a symbol."""
        resolved = resolve_symbol(symbol)
        sym = resolved["symbol"]
        is_global = "." in sym or sym[:1].isdigit()
        if settings.polygon_api_key and not is_global:
            try:
                data = await self.polygon.get_snapshot(sym)
                data["resolved_symbol"] = resolved
                return data
            except Exception as e:
                log.warning("polygon_snapshot_failed symbol=%s error=%s", sym, str(e))
        if settings.alpha_vantage_api_key and not is_global:
            try:
                data = await self.alpha_vantage.get_quote(sym)
                data["resolved_symbol"] = resolved
                return data
            except Exception as e:
                log.warning("alpha_vantage_quote_failed symbol=%s error=%s", sym, str(e))
        try:
            data = await self.yahoo.get_quote(sym)
            data["resolved_symbol"] = resolved
            return data
        except Exception as e:
            log.warning("yahoo_quote_failed symbol=%s error=%s", sym, str(e))
        return {"symbol": sym, "price": 0, "resolved_symbol": resolved, "error": "No market data provider configured or reachable"}

    async def get_historical_ohlcv(
        self,
        symbol: str,
        years: int = 5,
        timespan: str = "day",
    ) -> List[Dict[str, Any]]:
        """Get historical OHLCV bars going back `years` years."""
        resolved = resolve_symbol(symbol)
        sym = resolved["symbol"]
        is_global = "." in sym or sym[:1].isdigit()
        from_date = _n_years_ago(years)
        to_date = _today()

        if settings.polygon_api_key and not is_global:
            try:
                return await self.polygon.get_ohlcv(sym, from_date, to_date, timespan)
            except Exception as e:
                log.warning("polygon_ohlcv_failed symbol=%s error=%s", sym, str(e))

        if settings.alpha_vantage_api_key and not is_global:
            try:
                bars = await self.alpha_vantage.get_daily_ohlcv(sym, outputsize="full")
                cutoff = from_date
                return [b for b in bars if b["date"] >= cutoff]
            except Exception as e:
                log.warning("alpha_vantage_ohlcv_failed symbol=%s error=%s", sym, str(e))

        try:
            return await self.yahoo.get_ohlcv(sym, years=years)
        except Exception as e:
            log.warning("yahoo_ohlcv_failed symbol=%s error=%s", sym, str(e))

        return []

    async def get_technicals(self, symbol: str) -> Dict[str, Any]:
        """Fetch key technical indicators for a symbol."""
        resolved = resolve_symbol(symbol)
        sym = resolved["symbol"]
        is_global = "." in sym or sym[:1].isdigit()
        technicals: Dict[str, Any] = {}

        if settings.alpha_vantage_api_key and not is_global:
            try:
                rsi_task = self.alpha_vantage.get_rsi(sym)
                macd_task = self.alpha_vantage.get_macd(sym)
                sma50_task = self.alpha_vantage.get_sma(sym, 50)
                sma200_task = self.alpha_vantage.get_sma(sym, 200)
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
                log.warning("technicals_fetch_failed symbol=%s error=%s", sym, str(e))

        if not {"rsi", "macd", "sma_50", "sma_200"}.issubset(technicals):
            try:
                bars = await self.get_historical_ohlcv(sym, years=2)
                local = compute_local_technicals(bars)
                for key, value in local.items():
                    technicals.setdefault(key, value)
            except Exception as e:
                log.warning("local_technicals_failed symbol=%s error=%s", sym, str(e))

        return technicals

    async def get_options_chain(
        self,
        symbol: str,
        expiration_date: Optional[str] = None,
        option_type: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        sym = resolve_symbol(symbol)["symbol"]
        if "." in sym or sym[:1].isdigit():
            return []
        if settings.polygon_api_key:
            try:
                return await self.polygon.get_options_chain(
                    sym, expiration_date, option_type
                )
            except Exception as e:
                log.warning("polygon_options_chain_failed symbol=%s error=%s", symbol, str(e))
        if settings.tradier_api_key:
            try:
                return await self.tradier.get_options_chain(
                    sym, expiration_date, option_type
                )
            except Exception as e:
                log.warning("tradier_options_chain_failed symbol=%s error=%s", symbol, str(e))
        return []

    async def get_unusual_options_activity(self, symbol: str) -> List[Dict[str, Any]]:
        sym = resolve_symbol(symbol)["symbol"]
        if "." in sym or sym[:1].isdigit():
            return []
        if settings.polygon_api_key:
            try:
                return await self.polygon.get_unusual_options_activity(sym)
            except Exception as e:
                log.warning("polygon_unusual_options_failed symbol=%s error=%s", symbol, str(e))
        return []

    async def get_full_market_context(self, symbol: str) -> Dict[str, Any]:
        """Fetch quote + technicals in parallel for AI context injection."""
        resolved = resolve_symbol(symbol)
        sym = resolved["symbol"]
        quote_task = self.get_quote(sym)
        tech_task = self.get_technicals(sym)
        quote, technicals = await asyncio.gather(quote_task, tech_task, return_exceptions=True)

        ctx: Dict[str, Any] = {"symbol": sym, "resolved_symbol": resolved}
        if not isinstance(quote, Exception):
            ctx.update(quote)
        if not isinstance(technicals, Exception):
            ctx["technicals"] = technicals

        return ctx

    async def get_full_analysis(
        self,
        symbol: str,
        session_id: str = "nexus",
    ) -> Dict[str, Any]:
        """Shared market analysis pipeline for chat tools and API routes."""
        from app.nexus_core.reasoning import reasoning_engine
        from app.services.adaptive_predictions import adaptive_prediction_service
        from app.services.decision_engine import nexus_decision_engine
        from app.services.event_intelligence import event_intelligence_service
        from app.services.pattern_recognition import pattern_engine

        resolved = resolve_symbol(symbol)
        sym = resolved["symbol"]

        quote_task = self.get_quote(sym)
        tech_task = self.get_technicals(sym)
        hist_task = self.get_historical_ohlcv(sym, years=2)
        intelligence_task = event_intelligence_service.build_symbol_intelligence(sym, fresh=True)
        quote, technicals, bars, event_intelligence = await asyncio.gather(
            quote_task, tech_task, hist_task, intelligence_task, return_exceptions=True
        )

        result: Dict[str, Any] = {"symbol": sym, "resolved_symbol": resolved}
        if not isinstance(quote, Exception):
            result["quote"] = quote
        if not isinstance(technicals, Exception):
            result["technicals"] = technicals
        if not isinstance(event_intelligence, Exception):
            result["event_intelligence"] = event_intelligence

        patterns_data: Dict[str, Any] = {}
        participation_data: Dict[str, Any] = {}
        if not isinstance(bars, Exception) and bars:
            patterns_data = pattern_engine.analyze(bars, symbol=sym)
            participation_data = await self.get_market_participation(sym, bars=bars)
            result["patterns"] = patterns_data
            result["participation"] = participation_data
            result["chart_bars"] = bars[-252:]

        if isinstance(technicals, dict) and technicals:
            reasoning = reasoning_engine.analyze_technicals({
                **technicals,
                "price": result.get("quote", {}).get("price", 0),
                "volume": result.get("quote", {}).get("volume", 0),
                "participation": participation_data,
            })
            result["reasoning"] = reasoning.to_dict()

        if (
            result.get("quote")
            and result["quote"].get("price")
            and isinstance(technicals, dict)
            and not isinstance(bars, Exception)
            and bars
        ):
            result["adaptive_prediction"] = await adaptive_prediction_service.build_prediction(
                symbol=sym,
                quote=result["quote"],
                technicals=technicals,
                patterns=patterns_data,
                bars=bars,
                session_id=session_id,
                event_intelligence=event_intelligence if isinstance(event_intelligence, dict) else None,
                participation=participation_data,
            )
        result["decision"] = nexus_decision_engine.build_decision(result)
        return result

    async def get_market_participation(
        self,
        symbol: str,
        bars: Optional[List[Dict[str, Any]]] = None,
        lookback: int = 20,
    ) -> Dict[str, Any]:
        """Estimate recent buy/sell participation from OHLCV bars."""
        if bars is None:
            bars = await self.get_historical_ohlcv(symbol, years=1)
        return compute_market_participation(symbol, bars, lookback=lookback)


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


def compute_market_participation(
    symbol: str,
    bars: List[Dict[str, Any]],
    lookback: int = 20,
) -> Dict[str, Any]:
    """
    Estimate buy/sell pressure from OHLCV data.

    Public equity feeds expose traded share volume, not a literal count of
    unique buyers and sellers. This uses each candle's close location and body
    direction to estimate how much volume behaved like buying versus selling.
    """
    usable = [
        b for b in bars
        if b.get("open") is not None
        and b.get("high") is not None
        and b.get("low") is not None
        and b.get("close") is not None
        and b.get("volume") is not None
    ]
    if not usable:
        return {
            "symbol": symbol.upper(),
            "window_bars": 0,
            "method": "ohlcv_close_location_estimate",
            "available": False,
            "description": "No OHLCV volume data available for participation analysis.",
        }

    window = usable[-lookback:] if len(usable) >= lookback else usable
    prior = usable[-lookback * 2:-lookback] if len(usable) >= lookback * 2 else []

    def clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
        return max(low, min(high, value))

    def estimate(rows: List[Dict[str, Any]]) -> Dict[str, float]:
        buy_volume = 0.0
        sell_volume = 0.0
        total_volume = 0.0
        close_position_total = 0.0
        weighted_close_position = 0.0

        for row in rows:
            open_ = float(row.get("open") or 0)
            high = float(row.get("high") or 0)
            low = float(row.get("low") or 0)
            close = float(row.get("close") or 0)
            volume = float(row.get("volume") or 0)
            if volume <= 0:
                continue

            candle_range = high - low
            if candle_range > 0:
                close_location = clamp((close - low) / candle_range)
                body_score = clamp(0.5 + ((close - open_) / candle_range) / 2)
            else:
                close_location = 0.5
                body_score = 0.5

            buy_ratio = clamp(close_location * 0.65 + body_score * 0.35)
            buy_volume += volume * buy_ratio
            sell_volume += volume * (1 - buy_ratio)
            total_volume += volume
            close_position_total += close_location
            weighted_close_position += close_location * volume

        buy_share = buy_volume / total_volume if total_volume else 0.0
        sell_share = sell_volume / total_volume if total_volume else 0.0
        return {
            "buy_volume": buy_volume,
            "sell_volume": sell_volume,
            "total_volume": total_volume,
            "buy_share": buy_share,
            "sell_share": sell_share,
            "pressure": buy_share - sell_share,
            "avg_volume": total_volume / len(rows) if rows else 0.0,
            "avg_close_position": close_position_total / len(rows) if rows else 0.5,
            "weighted_close_position": weighted_close_position / total_volume if total_volume else 0.5,
        }

    current = estimate(window)
    previous = estimate(prior)
    pressure = current["pressure"]
    acceleration = pressure - previous["pressure"] if prior else 0.0
    relative_volume = (
        current["avg_volume"] / previous["avg_volume"]
        if previous.get("avg_volume", 0) > 0 else 1.0
    )
    conviction = min(1.0, abs(pressure) * 1.35 + min(max(relative_volume - 1.0, 0), 1.5) * 0.25)

    if pressure >= 0.35:
        label = "heavy_buying"
        direction = "bullish"
        description = "Estimated participation shows aggressive buying pressure; upside outcomes get a stronger tailwind if price confirms."
    elif pressure >= 0.12:
        label = "buying"
        direction = "bullish"
        description = "Estimated buying pressure is stronger than selling; call outcomes receive a modest tailwind."
    elif pressure <= -0.35:
        label = "heavy_selling"
        direction = "bearish"
        description = "Estimated participation shows aggressive selling pressure; downside outcomes get a stronger tailwind if support fails."
    elif pressure <= -0.12:
        label = "selling"
        direction = "bearish"
        description = "Estimated selling pressure is stronger than buying; put outcomes receive a modest tailwind."
    else:
        label = "balanced"
        direction = "neutral"
        description = "Estimated buying and selling pressure is balanced; participation does not materially change the directional outcome."

    risks = [
        "Participation is estimated from traded share volume, not a unique buyer/seller headcount.",
    ]
    if relative_volume < 0.75:
        risks.append("Below-normal volume weakens the signal.")
    if abs(acceleration) >= 0.2:
        risks.append("Participation pressure is shifting quickly, so confirmation matters.")

    bias_delta = round(pressure * (0.8 + conviction * 0.7), 3)
    ratio = (
        current["buy_volume"] / current["sell_volume"]
        if current["sell_volume"] > 0 else None
    )

    return {
        "symbol": symbol.upper(),
        "available": True,
        "window_bars": len(window),
        "method": "ohlcv_close_location_estimate",
        "estimated_buy_volume": round(current["buy_volume"]),
        "estimated_sell_volume": round(current["sell_volume"]),
        "total_volume": round(current["total_volume"]),
        "buy_volume_pct": round(current["buy_share"] * 100, 1),
        "sell_volume_pct": round(current["sell_share"] * 100, 1),
        "net_volume": round(current["buy_volume"] - current["sell_volume"]),
        "pressure_score": round(pressure, 3),
        "pressure_label": label,
        "conviction": round(conviction, 3),
        "buyer_seller_ratio": round(ratio, 2) if ratio is not None else None,
        "relative_volume": round(relative_volume, 2),
        "acceleration": round(acceleration, 3),
        "latest_close_position": round(current["weighted_close_position"], 3),
        "outcome_impact": {
            "direction": direction,
            "bias_delta": bias_delta,
            "description": description,
            "risks": risks,
        },
    }


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
