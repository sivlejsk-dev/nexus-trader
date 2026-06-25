"""Global symbol resolution helpers.

The app uses Yahoo Finance as its no-key fallback, and Yahoo represents most
non-US listings with exchange suffixes such as 7203.T, VOD.L, SHOP.TO, or
RELIANCE.NS. These helpers keep that mapping in one place so chat, voice, and
market endpoints resolve symbols consistently.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional


GLOBAL_MARKETS: Dict[str, Dict[str, str]] = {
    "usa": {"suffix": "", "exchange": "US exchanges", "example": "AAPL"},
    "us": {"suffix": "", "exchange": "US exchanges", "example": "AAPL"},
    "japan": {"suffix": ".T", "exchange": "Tokyo Stock Exchange", "example": "7203.T"},
    "tokyo": {"suffix": ".T", "exchange": "Tokyo Stock Exchange", "example": "7203.T"},
    "uk": {"suffix": ".L", "exchange": "London Stock Exchange", "example": "VOD.L"},
    "london": {"suffix": ".L", "exchange": "London Stock Exchange", "example": "VOD.L"},
    "canada": {"suffix": ".TO", "exchange": "Toronto Stock Exchange", "example": "SHOP.TO"},
    "toronto": {"suffix": ".TO", "exchange": "Toronto Stock Exchange", "example": "SHOP.TO"},
    "germany": {"suffix": ".DE", "exchange": "Xetra", "example": "SAP.DE"},
    "frankfurt": {"suffix": ".DE", "exchange": "Xetra", "example": "SAP.DE"},
    "france": {"suffix": ".PA", "exchange": "Euronext Paris", "example": "MC.PA"},
    "paris": {"suffix": ".PA", "exchange": "Euronext Paris", "example": "MC.PA"},
    "netherlands": {"suffix": ".AS", "exchange": "Euronext Amsterdam", "example": "ASML.AS"},
    "amsterdam": {"suffix": ".AS", "exchange": "Euronext Amsterdam", "example": "ASML.AS"},
    "switzerland": {"suffix": ".SW", "exchange": "SIX Swiss Exchange", "example": "NESN.SW"},
    "zurich": {"suffix": ".SW", "exchange": "SIX Swiss Exchange", "example": "NESN.SW"},
    "italy": {"suffix": ".MI", "exchange": "Borsa Italiana", "example": "ENEL.MI"},
    "milan": {"suffix": ".MI", "exchange": "Borsa Italiana", "example": "ENEL.MI"},
    "spain": {"suffix": ".MC", "exchange": "Bolsa de Madrid", "example": "SAN.MC"},
    "madrid": {"suffix": ".MC", "exchange": "Bolsa de Madrid", "example": "SAN.MC"},
    "sweden": {"suffix": ".ST", "exchange": "Nasdaq Stockholm", "example": "VOLV-B.ST"},
    "stockholm": {"suffix": ".ST", "exchange": "Nasdaq Stockholm", "example": "VOLV-B.ST"},
    "hong kong": {"suffix": ".HK", "exchange": "Hong Kong Stock Exchange", "example": "0700.HK"},
    "hk": {"suffix": ".HK", "exchange": "Hong Kong Stock Exchange", "example": "0700.HK"},
    "india": {"suffix": ".NS", "exchange": "National Stock Exchange of India", "example": "RELIANCE.NS"},
    "nse": {"suffix": ".NS", "exchange": "National Stock Exchange of India", "example": "RELIANCE.NS"},
    "australia": {"suffix": ".AX", "exchange": "Australian Securities Exchange", "example": "BHP.AX"},
    "asx": {"suffix": ".AX", "exchange": "Australian Securities Exchange", "example": "BHP.AX"},
    "brazil": {"suffix": ".SA", "exchange": "B3", "example": "PETR4.SA"},
    "sao paulo": {"suffix": ".SA", "exchange": "B3", "example": "PETR4.SA"},
    "mexico": {"suffix": ".MX", "exchange": "Mexican Stock Exchange", "example": "AMXL.MX"},
    "south africa": {"suffix": ".JO", "exchange": "Johannesburg Stock Exchange", "example": "NPN.JO"},
    "korea": {"suffix": ".KS", "exchange": "Korea Exchange", "example": "005930.KS"},
    "south korea": {"suffix": ".KS", "exchange": "Korea Exchange", "example": "005930.KS"},
    "taiwan": {"suffix": ".TW", "exchange": "Taiwan Stock Exchange", "example": "2330.TW"},
    "singapore": {"suffix": ".SI", "exchange": "Singapore Exchange", "example": "D05.SI"},
}


COMPANY_ALIASES: Dict[str, str] = {
    "toyota": "7203.T",
    "samsung": "005930.KS",
    "taiwan semiconductor": "2330.TW",
    "tsmc taiwan": "2330.TW",
    "tsmc": "TSM",
    "tencent": "0700.HK",
    "alibaba hong kong": "9988.HK",
    "alibaba": "BABA",
    "reliance": "RELIANCE.NS",
    "infosys india": "INFY.NS",
    "infosys": "INFY",
    "vodafone": "VOD.L",
    "shell london": "SHEL.L",
    "shell": "SHEL",
    "bp london": "BP.L",
    "bp": "BP",
    "asml amsterdam": "ASML.AS",
    "asml": "ASML.AS",
    "sap germany": "SAP.DE",
    "sap": "SAP.DE",
    "lvmh": "MC.PA",
    "nestle": "NESN.SW",
    "novartis": "NOVN.SW",
    "bhp australia": "BHP.AX",
    "bhp": "BHP.AX",
    "rio tinto london": "RIO.L",
    "rio tinto": "RIO",
    "petrobras brazil": "PETR4.SA",
    "petrobras": "PBR",
    "shopify canada": "SHOP.TO",
    "shopify": "SHOP",
}


_YAHOO_SYMBOL_RE = re.compile(r"\b([A-Z0-9]{1,8}(?:[-.][A-Z0-9]{1,5})?)\b")
_COMMON_WORDS = {
    "ADD", "ANALYZE", "ANALYSE", "AMSTERDAM", "AUSTRALIA", "BRAZIL", "CANADA",
    "A", "AN", "AND", "ARE", "ASK", "AT", "BE", "BEST", "BUY", "CALL", "CALLS",
    "CAN", "CHECK", "DO", "FOR", "FROM", "GO", "GOES", "HELP", "HIT", "HITS", "HOW", "I", "IF", "IN", "IS",
    "INDIA", "IT", "JAPAN", "KOREA", "LONDON", "LOOK", "ME", "MY", "NEXUS",
    "OF", "ON", "OPTION", "OPTIONS", "OR",
    "PUT", "PUTS", "SELL", "SHOW", "SIMULATE", "START", "STOCK", "STOP", "TELL", "THE", "TO",
    "TOKYO", "TRADE", "UK", "UP", "US", "USA", "VOICE", "WHAT", "WHEN",
    "WHY", "WORLD", "YEAR", "YEARS", "ONE", "TWO", "THREE", "FOUR", "FIVE",
    "SIX", "SEVEN", "EIGHT", "NINE", "TEN", "TUTORIAL", "MODE", "WITH", "YOU",
}


def market_hint(text: str) -> Optional[Dict[str, str]]:
    lower = text.lower()
    for key in sorted(GLOBAL_MARKETS, key=len, reverse=True):
        if re.search(rf"\b{re.escape(key)}\b", lower):
            return GLOBAL_MARKETS[key]
    return None


def alias_symbol(text: str) -> Optional[str]:
    lower = text.lower()
    for alias in sorted(COMPANY_ALIASES, key=len, reverse=True):
        if re.search(rf"\b{re.escape(alias)}\b", lower):
            return COMPANY_ALIASES[alias]
    return None


def resolve_symbol(symbol: str, context: str = "") -> Dict[str, Any]:
    raw = (symbol or "").strip().replace("$", "")
    raw = re.sub(r"\s+", " ", raw)
    if not raw:
        return {"symbol": "", "input": symbol, "market": None, "resolved": False}

    alias = alias_symbol(raw) or alias_symbol(context)
    if alias:
        raw = alias

    normalized = raw.upper()
    hint = market_hint(context)
    if "." not in normalized and "-" not in normalized and hint and hint["suffix"]:
        normalized = f"{normalized}{hint['suffix']}"

    market = None
    for info in GLOBAL_MARKETS.values():
        suffix = info["suffix"]
        if suffix and normalized.endswith(suffix):
            market = info
            break
    if market is None:
        market = GLOBAL_MARKETS["usa"] if "." not in normalized else None

    return {
        "symbol": normalized,
        "input": symbol,
        "market": market,
        "resolved": normalized != (symbol or "").upper(),
        "source": "alias" if alias else "market_hint" if hint else "direct",
    }


def extract_global_symbols(text: str) -> List[str]:
    symbols: List[str] = []

    alias = alias_symbol(text)
    if alias:
        symbols.append(alias)

    hint = market_hint(text)
    for candidate in _YAHOO_SYMBOL_RE.findall(text.upper()):
        if candidate in _COMMON_WORDS:
            continue
        if candidate.isdigit() and not hint:
            continue
        if len(candidate) == 1 and not candidate.isdigit():
            continue
        resolved = resolve_symbol(candidate, context=text)["symbol"]
        if resolved:
            symbols.append(resolved)

    return list(dict.fromkeys(symbols))


def supported_markets() -> List[Dict[str, str]]:
    seen = set()
    rows = []
    for key, info in GLOBAL_MARKETS.items():
        marker = (info["suffix"], info["exchange"])
        if marker in seen:
            continue
        seen.add(marker)
        rows.append({
            "region": key,
            "exchange": info["exchange"],
            "suffix": info["suffix"],
            "example": info["example"],
        })
    return rows
