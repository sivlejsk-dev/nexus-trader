const BASE = process.env.NEXT_PUBLIC_API_URL
  ? `${process.env.NEXT_PUBLIC_API_URL}/api/v1`
  : "/api/v1";

async function req<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...init,
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || `HTTP ${res.status}`);
  }
  return res.json();
}

// ── Types ─────────────────────────────────────────────────────────────────────

export interface OHLCVBar {
  date: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
  vwap?: number;
}

export interface Quote {
  symbol: string;
  price: number;
  open?: number;
  high?: number;
  low?: number;
  close?: number;
  volume?: number;
  change?: number;
  change_pct?: number;
  prev_close?: number;
  source?: string;
  error?: string;
}

export interface Technicals {
  rsi?: number;
  macd?: number;
  macd_signal?: number;
  macd_hist?: number;
  sma_50?: number;
  sma_200?: number;
}

export interface PatternMatch {
  name: string;
  pattern_type: string;
  direction: "bullish" | "bearish" | "neutral";
  confidence: number;
  start_idx: number;
  end_idx: number;
  key_levels: Record<string, number>;
  evidence: string[];
  target_price?: number;
  stop_loss?: number;
  description: string;
}

export interface SupportResistance {
  support: number[];
  resistance: number[];
}

export interface PatternAnalysis {
  symbol: string;
  trend: { trend: string; slope_pct_per_bar: number; strength: number; lookback_bars: number };
  support_resistance: SupportResistance;
  patterns: PatternMatch[];
  volume_spikes: Array<{ idx: number; date: string; volume: number; ratio: number; close: number; direction: string }>;
  bollinger_squeeze: { squeeze: boolean; current_width_pct: number; description: string };
  rsi_divergences: Array<{ type: string; direction: string; description: string; confidence: number }>;
  summary: { bias: string; pattern_count: number; bullish_signals: number; bearish_signals: number; top_pattern: string | null };
}

export interface FullAnalysis {
  symbol: string;
  quote?: Quote;
  technicals?: Technicals;
  patterns?: PatternAnalysis;
  chart_bars?: OHLCVBar[];
  reasoning?: {
    conclusion: string;
    confidence: number;
    confidence_level: string;
    steps: Array<{ description: string; evidence: string[]; confidence: number }>;
    risks: string[];
    disclaimer: string;
  };
}

export interface ChatResponse {
  response: string;
  session_id: string;
  intent: string;
  symbols: string[];
  active_symbol?: string;
  reasoning?: Record<string, unknown>;
  market_context?: Record<string, unknown>;
}

export interface StrategyScore {
  name: string;
  direction: string;
  score: number;
  rationale: string[];
  max_profit: string;
  max_loss: string;
  ideal_conditions: string[];
}

export interface BacktestResult {
  strategy: string;
  total_trades: number;
  wins: number;
  losses: number;
  win_rate: number;
  avg_win_pct: number;
  avg_loss_pct: number;
  total_pnl_per_contract: number;
  expectancy_pct: number;
  trades: Array<{
    entry_date: string;
    exit_date: string;
    entry_price: number;
    exit_price: number;
    strike: number;
    underlying_entry: number;
    underlying_exit: number;
    pnl: number;
    pnl_pct: number;
    win: boolean;
  }>;
  disclaimer: string;
}

export interface GreeksResult {
  price: number;
  delta: number;
  gamma: number;
  theta: number;
  vega: number;
  rho: number;
}

export interface ChatSession {
  id: string;
  title: string;
  created_at: string;
  updated_at: string;
  turn_count: number;
}

export interface WatchlistResponse {
  session_id: string;
  symbols: string[];
  quotes: Quote[];
}

// ── API calls ─────────────────────────────────────────────────────────────────

export const api = {
  // Chat
  chat: (message: string, sessionId: string, symbol?: string) =>
    req<ChatResponse>("/chat", {
      method: "POST",
      body: JSON.stringify({ message, session_id: sessionId, symbol, include_reasoning: true }),
    }),

  clearHistory: (sessionId: string) =>
    req(`/chat/history/${sessionId}`, { method: "DELETE" }),

  // Sessions
  getSessions: () => req<{ sessions: ChatSession[]; count: number }>("/chat/sessions"),

  getSession: (sessionId: string) =>
    req<{ session_id: string; turns: unknown[]; preferences: Record<string, unknown> }>(
      `/chat/sessions/${sessionId}`
    ),

  renameSession: (sessionId: string, title: string) =>
    req(`/chat/sessions/${sessionId}`, {
      method: "PATCH",
      body: JSON.stringify({ title }),
    }),

  deleteSession: (sessionId: string) =>
    req(`/chat/sessions/${sessionId}`, { method: "DELETE" }),

  // Market
  quote: (symbol: string) => req<Quote>(`/market/quote/${symbol}`),

  history: (symbol: string, years = 5, timespan = "day") =>
    req<{ symbol: string; bars: OHLCVBar[] }>(`/market/history/${symbol}?years=${years}&timespan=${timespan}`),

  analysis: (symbol: string) => req<FullAnalysis>(`/market/analysis/${symbol}`),

  patterns: (symbol: string, years = 2) =>
    req<PatternAnalysis>(`/market/patterns/${symbol}?years=${years}`),

  // Options
  strategies: (symbol: string, dte = 30) =>
    req<{ strategies: StrategyScore[]; disclaimer: string }>(`/options/strategies/${symbol}?days_to_expiry=${dte}`),

  greeks: (params: {
    underlying_price: number;
    strike: number;
    days_to_expiry: number;
    implied_volatility: number;
    option_type: string;
  }) =>
    req<{ greeks: GreeksResult; disclaimer: string }>("/options/greeks", {
      method: "POST",
      body: JSON.stringify(params),
    }),

  unusualActivity: (symbol: string) =>
    req<{ unusual_contracts: unknown[]; count: number }>(`/options/unusual/${symbol}`),

  backtest: (params: {
    symbol: string;
    option_type: string;
    strike_offset_pct: number;
    days_to_expiry: number;
    iv_assumption: number;
    years: number;
  }) =>
    req<BacktestResult>("/options/backtest", { method: "POST", body: JSON.stringify(params) }),

  // Watchlist
  getWatchlist: (sessionId: string) => req<WatchlistResponse>(`/watchlist/${sessionId}`),
  addToWatchlist: (sessionId: string, symbol: string) =>
    req(`/watchlist/${sessionId}`, { method: "POST", body: JSON.stringify({ symbol }) }),
  removeFromWatchlist: (sessionId: string, symbol: string) =>
    req(`/watchlist/${sessionId}/${symbol}`, { method: "DELETE" }),
};
