"""Nexus tool definitions and agentic execution loop.

Defines every tool Nexus can call, the JSON schema the LLM sees, and the
dispatcher that executes tool calls and feeds results back into the loop.

The agentic loop:
  1. Send messages + tool schemas to LLM
  2. If LLM returns tool_calls → execute each tool, append results
  3. Send updated messages back to LLM
  4. Repeat until LLM returns a plain text response (no more tool calls)
  5. Cap at MAX_TOOL_ROUNDS to prevent infinite loops

Tools available to Nexus:
  web_search          — search the internet
  fetch_page          — read any URL
  get_stock_price     — current quote + technicals
  run_simulation      — historical simulation on a symbol
  optimize_weights    — run the signal optimizer
  research_symbol     — deep symbol research (news + filings)
  research_strategy   — look up trading strategies / academic papers
  research_event      — research a market event or macro development
  get_model_stats     — Nexus's own accuracy stats for a symbol
  remember_finding    — store a research finding to memory
"""
from __future__ import annotations

import json
import time
from typing import Any, Dict, List, Optional, Tuple

# ── Tool schemas (OpenAI function-calling format) ─────────────────────────────

TOOL_SCHEMAS: List[Dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": (
                "Search the internet for any information. Use this to research "
                "trading strategies, market news, company fundamentals, economic data, "
                "academic papers, or anything else you need to answer the user's question. "
                "Always search before claiming you don't know something."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "The search query. Be specific. Include ticker symbols, dates, or technical terms as needed.",
                    },
                    "prefer_financial": {
                        "type": "boolean",
                        "description": "Set true to bias results toward financial news sites (Reuters, Bloomberg, WSJ, SEC).",
                        "default": False,
                    },
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "fetch_page",
            "description": (
                "Read the full content of any web page or URL. Use after web_search "
                "to get the complete article, SEC filing, research paper, or documentation. "
                "Works on any public URL including arxiv.org, SEC EDGAR, GitHub, news sites."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "The full URL to fetch.",
                    },
                },
                "required": ["url"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_stock_price",
            "description": "Get the current price, technicals (RSI, MACD, Bollinger Bands), and Nexus's current prediction for a stock symbol.",
            "parameters": {
                "type": "object",
                "properties": {
                    "symbol": {
                        "type": "string",
                        "description": "Stock ticker symbol, e.g. AAPL, TSLA, SPY.",
                    },
                },
                "required": ["symbol"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "run_simulation",
            "description": (
                "Run Nexus's historical simulation on a symbol to see how its prediction "
                "logic would have performed. Returns win rate, avg P&L, and signal breakdown."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "symbol": {"type": "string", "description": "Stock ticker symbol."},
                    "years": {"type": "integer", "description": "Years of history to simulate (1-20).", "default": 5},
                    "horizon_days": {"type": "integer", "description": "Prediction horizon in days (5-60).", "default": 20},
                },
                "required": ["symbol"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "optimize_weights",
            "description": (
                "Run the iterative signal weight optimizer on a symbol. Nexus will run "
                "the simulation many times, mutating signal weights each time, to find "
                "the combination that maximises win rate. Saves the best weights for future use."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "symbol": {"type": "string"},
                    "years": {"type": "integer", "default": 5},
                    "generations": {"type": "integer", "description": "Number of optimization generations (5-100).", "default": 20},
                },
                "required": ["symbol"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "research_symbol",
            "description": "Deep research on a stock: recent news, analyst targets, earnings, SEC filings, options flow.",
            "parameters": {
                "type": "object",
                "properties": {
                    "symbol": {"type": "string"},
                },
                "required": ["symbol"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "research_strategy",
            "description": (
                "Research a trading strategy, technical indicator, or quantitative concept. "
                "Searches academic papers (arxiv, SSRN), quant blogs, and documentation. "
                "Use this to learn about new approaches and improve Nexus's models."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "topic": {
                        "type": "string",
                        "description": "The strategy or concept to research, e.g. 'mean reversion RSI', 'VWAP options strategy', 'Kelly criterion position sizing'.",
                    },
                },
                "required": ["topic"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "research_event",
            "description": "Research a market event, macro development, earnings release, or geopolitical situation and its market impact.",
            "parameters": {
                "type": "object",
                "properties": {
                    "event": {
                        "type": "string",
                        "description": "The event to research, e.g. 'Fed rate decision June 2025', 'NVDA earnings Q1 2025'.",
                    },
                },
                "required": ["event"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_model_stats",
            "description": "Get Nexus's own rolling accuracy stats for a symbol — win rates per signal, confidence adjustments, and learning factors.",
            "parameters": {
                "type": "object",
                "properties": {
                    "symbol": {"type": "string"},
                },
                "required": ["symbol"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_best_option",
            "description": (
                "Run the full Nexus best-option engine on one or more symbols. "
                "Analyses technicals, runs the historical simulation, scores the options chain "
                "(delta, IV, DTE, liquidity), and returns the single best call or put to buy "
                "right now — with strike, expiry, premium estimate, breakeven, risk/reward, "
                "and a full spoken rationale. "
                "Use this whenever the user asks: 'what's the best option to buy?', "
                "'give me a trade idea', 'what should I trade today?', "
                "'best call/put for X', or any variant."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "symbols": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": (
                            "List of ticker symbols to analyse, e.g. ['AAPL', 'TSLA', 'SPY']. "
                            "If the user mentions a single symbol, pass it as a one-element list. "
                            "If no symbol is specified, use ['SPY', 'QQQ', 'AAPL'] as defaults."
                        ),
                    },
                    "include_research": {
                        "type": "boolean",
                        "description": "Whether to fetch recent news for context. Default true.",
                        "default": True,
                    },
                },
                "required": ["symbols"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "remember_finding",
            "description": (
                "Store an important research finding, insight, or learned fact to Nexus's "
                "long-term memory. Use this when you discover something useful about a symbol, "
                "strategy, or market condition that should influence future analysis."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "content": {"type": "string", "description": "The finding to remember."},
                    "symbol": {"type": "string", "description": "Related symbol if applicable."},
                    "category": {
                        "type": "string",
                        "enum": ["strategy", "symbol_insight", "market_condition", "model_improvement", "research"],
                        "description": "Category of the finding.",
                    },
                },
                "required": ["content", "category"],
            },
        },
    },
]


# ── Tool dispatcher ───────────────────────────────────────────────────────────

MAX_TOOL_ROUNDS = 6   # max LLM ↔ tool iterations per request
TOOL_TIMEOUT = 15.0   # seconds per tool call


async def dispatch_tool(
    name: str,
    args: Dict[str, Any],
    session_id: str = "console",
) -> Tuple[Any, str]:
    """
    Execute a tool call and return (result_dict, display_label).
    All tools return JSON-serialisable dicts.
    """
    from app.services.web_research import (
        search_web, fetch_page,
        research_symbol, research_strategy, research_market_event,
    )
    from app.services.market_data import market_data_service
    from app.services.historical_simulation import run_simulation
    from app.services.signal_optimizer import signal_optimizer
    from app.services.model_refinement import get_model_stats
    from app.services.research_memory import research_memory_service

    t0 = time.time()

    try:
        if name == "web_search":
            result = await search_web(
                args["query"],
                prefer_financial=args.get("prefer_financial", False),
            )
            label = f"🔍 Searched: {args['query'][:60]}"

        elif name == "fetch_page":
            result = await fetch_page(args["url"])
            label = f"📄 Read: {args['url'][:60]}"

        elif name == "get_stock_price":
            sym = args["symbol"].upper()
            data = await market_data_service.get_full_analysis(sym)
            result = {
                "symbol": sym,
                "price": data.get("quote", {}).get("price"),
                "change_pct": data.get("quote", {}).get("change_pct"),
                "rsi": data.get("technicals", {}).get("rsi"),
                "macd": data.get("technicals", {}).get("macd"),
                "direction": data.get("adaptive_prediction", {}).get("direction"),
                "confidence": data.get("adaptive_prediction", {}).get("confidence"),
            }
            label = f"📈 Got price: {sym}"

        elif name == "run_simulation":
            sym = args["symbol"].upper()
            years = min(int(args.get("years", 5)), 20)
            hz = min(int(args.get("horizon_days", 20)), 60)
            bars = await market_data_service.get_historical_ohlcv(sym, years=years)
            weights = await signal_optimizer.load_weights(sym)
            sim = run_simulation(bars, sym, horizon_days=hz, sample_every=10, weights=weights)
            result = {
                "symbol": sym,
                "win_rate": sim.get("win_rate"),
                "avg_pnl_pct": sim.get("avg_pnl_pct"),
                "total_predictions": sim.get("total_predictions"),
                "by_direction": sim.get("by_direction"),
                "signal_stats": sim.get("signal_stats"),
                "using_learned_weights": sim.get("using_learned_weights"),
                "date_range": sim.get("date_range"),
            }
            label = f"⚙️ Simulated: {sym} {years}Y"

        elif name == "optimize_weights":
            sym = args["symbol"].upper()
            years = min(int(args.get("years", 5)), 20)
            gens = min(int(args.get("generations", 20)), 100)
            bars = await market_data_service.get_historical_ohlcv(sym, years=years)
            opt = await signal_optimizer.optimize(
                bars=bars, symbol=sym,
                horizon_days=20, sample_every=10,
                max_generations=gens,
            )
            if opt["optimized"]["win_rate"] is not None:
                await signal_optimizer.save_weights(
                    sym, opt["optimized"]["weights"],
                    opt["optimized"]["win_rate"],
                    opt["optimized"]["avg_pnl_pct"],
                    opt["optimized"]["total_predictions"] or 0,
                    opt["generations_run"],
                )
            result = {
                "symbol": sym,
                "baseline_win_rate": opt["baseline"]["win_rate"],
                "optimized_win_rate": opt["optimized"]["win_rate"],
                "improvement_pct": opt.get("improvement_pct"),
                "generations_run": opt["generations_run"],
                "top_changed_signals": opt.get("top_changed_signals", []),
                "weights_saved": True,
            }
            label = f"🧬 Optimized: {sym} ({gens} generations)"

        elif name == "research_symbol":
            result = await research_symbol(args["symbol"].upper())
            label = f"🔬 Researched: {args['symbol'].upper()}"

        elif name == "research_strategy":
            result = await research_strategy(args["topic"])
            label = f"📚 Researched strategy: {args['topic'][:50]}"

        elif name == "research_event":
            result = await research_market_event(args["event"])
            label = f"🌐 Researched event: {args['event'][:50]}"

        elif name == "get_model_stats":
            result = await get_model_stats(args["symbol"].upper())
            label = f"📊 Model stats: {args['symbol'].upper()}"

        elif name == "get_best_option":
            from app.services.best_option import get_best_option
            import asyncio
            symbols = [s.upper() for s in args.get("symbols", ["SPY"])]
            include_research = args.get("include_research", True)

            # Run all symbols concurrently
            tasks = [
                get_best_option(sym, include_research=include_research, session_id=session_id)
                for sym in symbols[:5]  # cap at 5 symbols
            ]
            results = await asyncio.gather(*tasks, return_exceptions=True)

            recs = []
            for sym, r in zip(symbols, results):
                if isinstance(r, Exception):
                    recs.append({"symbol": sym, "error": str(r)})
                else:
                    recs.append(r)

            # If multiple symbols, pick the one with highest confidence
            valid = [r for r in recs if not r.get("error") and r.get("direction") != "neutral"]
            if valid:
                best = max(valid, key=lambda r: r.get("confidence", 0))
            else:
                best = recs[0] if recs else {"error": "No results"}

            result = {
                "best": best,
                "all_symbols": recs if len(recs) > 1 else None,
                "symbol_count": len(symbols),
            }
            sym_list = ", ".join(symbols)
            label = f"🎯 Best option: {sym_list}"

        elif name == "remember_finding":
            finding_id = await research_memory_service.store_finding(
                content=args["content"],
                symbol=args.get("symbol"),
                category=args["category"],
                session_id=session_id,
            )
            result = {"stored": True, "id": finding_id, "content": args["content"][:100]}
            label = f"💾 Remembered: {args['content'][:50]}"

        else:
            result = {"error": f"Unknown tool: {name}"}
            label = f"❓ Unknown tool: {name}"

    except Exception as e:
        result = {"error": str(e), "tool": name}
        label = f"⚠️ Tool error: {name}: {e}"

    elapsed = round(time.time() - t0, 2)
    return result, label, elapsed


# ── Agentic loop ──────────────────────────────────────────────────────────────

async def run_agentic_loop(
    messages: List[Dict[str, Any]],
    call_llm_fn,          # async (messages, tools) -> (content, tool_calls)
    session_id: str = "console",
    on_tool_call=None,    # optional async callback(name, args, label, result)
) -> Tuple[str, List[Dict[str, Any]]]:
    """
    Run the full agentic loop: LLM → tools → LLM → tools → … → final response.

    Returns (final_text_response, tool_call_log).
    tool_call_log: list of {name, args, label, result, elapsed} for UI display.
    """
    tool_log: List[Dict[str, Any]] = []
    current_messages = list(messages)

    for round_num in range(MAX_TOOL_ROUNDS):
        content, tool_calls = await call_llm_fn(current_messages, TOOL_SCHEMAS)

        # No tool calls → final answer
        if not tool_calls:
            return content or "", tool_log

        # Append assistant message with tool_calls
        current_messages.append({
            "role": "assistant",
            "content": content or "",
            "tool_calls": tool_calls,
        })

        # Execute each tool call
        for tc in tool_calls:
            fn = tc.get("function", {})
            name = fn.get("name", "")
            try:
                args = json.loads(fn.get("arguments", "{}"))
            except json.JSONDecodeError:
                args = {}

            result, label, elapsed = await dispatch_tool(name, args, session_id)

            entry = {
                "tool_call_id": tc.get("id", f"call_{round_num}"),
                "name": name,
                "args": args,
                "label": label,
                "result": result,
                "elapsed": elapsed,
                "round": round_num + 1,
            }
            tool_log.append(entry)

            if on_tool_call:
                await on_tool_call(entry)

            # Feed result back to LLM
            current_messages.append({
                "role": "tool",
                "tool_call_id": tc.get("id", f"call_{round_num}"),
                "content": json.dumps(result, default=str)[:6000],  # cap tool result size
            })

    # Hit max rounds — ask LLM to summarise what it found
    current_messages.append({
        "role": "user",
        "content": "Please summarise your findings and give your final answer based on the research above.",
    })
    content, _ = await call_llm_fn(current_messages, [])  # no tools on final pass
    return content or "", tool_log
