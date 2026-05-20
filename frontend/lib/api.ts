// Keep browser requests same-origin so Next.js can proxy them to FastAPI.
// Calling a localhost backend directly from the browser breaks in Codespaces,
// forwarded ports, and any origin that FastAPI CORS has not explicitly allowed.
const BASE = "/api/v1";

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
  adaptive_prediction?: AdaptivePredictionResponse;
}

export interface AdaptivePredictionResponse {
  symbol: string;
  prediction: {
    direction: "call" | "put" | "neutral";
    option_type?: "call" | "put" | null;
    confidence: number;
    horizon_days: number;
    entry_price: number;
    target_price?: number | null;
    stop_loss?: number | null;
    raw_scores: { bullish: number; bearish: number };
    rationale: string[];
    risks: string[];
    learning_adjustment: { factor: number; reason: string };
  };
  review: {
    completed: number;
    pending: number;
    wins: number;
    losses: number;
    win_rate?: number | null;
    by_direction: Record<string, {
      total: number;
      wins: number;
      losses: number;
      win_rate?: number | null;
      learning_factor: number;
    }>;
    recent_mistakes: Array<{
      created_at: string;
      direction: string;
      confidence: number;
      entry_price: number;
      exit_price?: number | null;
      pnl_pct?: number | null;
      notes: string[];
    }>;
    recent_predictions: Array<{
      created_at: string;
      direction: string;
      confidence: number;
      entry_price: number;
      target_price?: number | null;
      stop_loss?: number | null;
      outcome_status: string;
      exit_price?: number | null;
      pnl_pct?: number | null;
    }>;
  };
  disclaimer: string;
}

export interface AppCommand {
  type: string;
  path?: string;
  symbol?: string;
  years?: number;
  label?: string;
  _source?: string;
}

export interface PendingConfirmation extends AppCommand {
  id: string;
  created_at?: string;
}

export interface SessionInsight {
  id: string;
  session_id?: string;
  symbol?: string;
  insight_type: string;
  content: string;
  confidence: number;
  created_at: string;
}

export interface ChatResponse {
  response: string;
  session_id: string;
  intent: string;
  symbols: string[];
  active_symbol?: string;
  reasoning?: Record<string, unknown>;
  market_context?: Record<string, unknown>;
  triggered_actions?: string[];
  simulation?: SimulationResult;
  prediction_history?: PredictionHistoryResponse;
  // New fields
  app_commands?: AppCommand[];
  pending_confirmations?: PendingConfirmation[];
  voice_reasoning?: string;
  new_insights?: SessionInsight[];
  tool_log?: ToolCall[];
}

export interface ToolCall {
  tool_call_id: string;
  name: string;
  args: Record<string, unknown>;
  label: string;
  result: Record<string, unknown>;
  elapsed: number;
  round: number;
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

export interface MarketProvidersResponse {
  providers: Array<{
    name: string;
    configured: boolean;
    capabilities: string[];
    note?: string;
  }>;
  active_fallback_order: string[];
}

// ── Historical Simulation ─────────────────────────────────────────────────────

export interface SimulationPrediction {
  entry_date: string;
  exit_date: string;
  entry_price: number;
  exit_price: number;
  direction: "call" | "put" | "neutral";
  confidence: number;
  raw_confidence?: number;
  learning_factor?: number;
  actual_move_pct: number;
  pnl_pct: number;
  outcome: "win" | "loss";
  rationale: string[];
  rsi?: number;
  sma20?: number;
  macd?: number;
  bb_pct_b?: number;
  vol_ratio?: number;
  bullish_score?: number;
  bearish_score?: number;
}

export interface WorldEvent {
  date: string;
  end_date: string;
  title: string;
  category: string;
  impact: "bullish" | "bearish" | "volatility";
  description: string;
}

export interface SignalStat {
  total: number;
  wins: number;
  win_rate?: number | null;
}

export interface SimulationResult {
  symbol: string;
  total_predictions: number;
  wins: number;
  losses: number;
  win_rate?: number;
  avg_pnl_pct?: number;
  by_direction: Record<string, {
    total: number;
    wins: number;
    win_rate?: number;
    avg_pnl?: number;
    learning_factor?: number;
  }>;
  signal_stats?: Record<string, SignalStat>;
  learning_factors?: Record<string, number>;
  weights_used?: Record<string, number>;
  using_learned_weights?: boolean;
  predictions: SimulationPrediction[];
  events: WorldEvent[];
  horizon_days: number;
  date_range: { start: string; end: string };
}

export interface UnifiedAnalysisResponse {
  symbol: string;
  simulation: SimulationResult;
  live_predictions: PredictionHistoryResponse;
}

export interface WeightChange {
  baseline: number;
  optimized: number;
  delta: number;
}

export interface OptimizationConvergencePoint {
  generation: number;
  win_rate: number | null;
  avg_pnl: number | null;
  fitness: number;
  temperature?: number;
  improved: boolean;
}

export interface OptimizationResult {
  symbol: string;
  generations_run: number;
  baseline: { win_rate: number | null; avg_pnl_pct: number | null; total_predictions: number; weights: Record<string, number> };
  optimized: { win_rate: number | null; avg_pnl_pct: number | null; total_predictions: number; weights: Record<string, number> };
  improvement_pct: number | null;
  weight_changes: Record<string, WeightChange>;
  top_changed_signals: string[];
  convergence: OptimizationConvergencePoint[];
  weights_saved: boolean;
  full_simulation?: Partial<SimulationResult>;
}

// ── Event Intelligence ────────────────────────────────────────────────────────

export interface EventIntelligenceResponse {
  symbol: string;
  events: Array<{
    source: string;
    source_event_id: string;
    symbol: string;
    event_time: string;
    title: string;
    summary?: string;
    url?: string;
    sentiment_score?: number;
    virality_score?: number;
    category?: string;
    direction?: string;
    option_bias?: string;
    nexus_analysis?: string;
    historical_analogues?: {
      count: number;
      call_win_rate?: number;
      put_win_rate?: number;
    };
  }>;
  composite?: {
    bias: string;
    confidence: number;
    raw_scores?: Record<string, number>;
    top_events?: string[];
  };
  source_status?: Array<{ name: string; configured: boolean }>;
  disclaimer?: string;
}

export interface PredictionHistoryResponse {
  symbol: string;
  predictions: Array<{
    id: string;
    created_at: string;
    direction: string;
    confidence: number;
    entry_price: number;
    target_price?: number;
    stop_loss?: number;
    outcome_status: string;
    exit_price?: number;
    pnl_pct?: number;
    rationale: string[];
    mistake_notes?: string[];
  }>;
  performance: {
    total: number;
    wins: number;
    losses: number;
    pending: number;
    win_rate?: number;
    by_direction: Record<string, {
      total: number; wins: number; losses: number;
      win_rate?: number; learning_factor: number;
    }>;
  };
}

// ── Best Option ───────────────────────────────────────────────────────────────

export interface BestOptionContract {
  symbol: string;
  type: "call" | "put";
  strike: number;
  expiry?: string;
  expiration_date?: string;
  days_to_expiry?: number;
  dte?: number;
  bid?: number;
  ask?: number;
  estimated_premium?: number;
  delta?: number;
  gamma?: number;
  theta?: number;
  vega?: number;
  implied_volatility?: number;
  iv?: number;
  open_interest?: number;
  volume?: number;
  is_synthetic?: boolean;
  note?: string;
  _nexus_score?: number;
}

export interface BestOptionSignal {
  name: string;
  value: string;
  signal: "bullish" | "bearish" | "neutral";
  detail: string;
}

export interface BestOptionRiskReward {
  premium: number;
  cost_per_contract: number;
  breakeven: number;
  target_price: number;
  max_loss: number;
  expected_value: number;
  risk_reward_ratio?: number;
  dte: number;
}

export interface BestOptionResult {
  symbol: string;
  price: number;
  direction: "call" | "put" | "neutral";
  confidence: number;
  direction_score: {
    direction: string;
    confidence: number;
    bull_score: number;
    bear_score: number;
    edge: number;
    signals: BestOptionSignal[];
    rsi?: number;
    macd?: number;
    sma20?: number;
    sma50?: number;
    bb_pct_b?: number;
    vol_ratio?: number;
  };
  simulation: {
    win_rate?: number;
    avg_pnl_pct?: number;
    total_predictions?: number;
    direction_stats?: { total: number; wins: number; win_rate?: number };
  };
  contract?: BestOptionContract;
  risk_reward?: BestOptionRiskReward;
  news_snippets: string[];
  rationale: string[];
  voice_script: string;
  using_learned_weights: boolean;
  chain_available: boolean;
  generated_at: string;
  error?: string;
}

export interface BestOptionMultiResult {
  best: BestOptionResult;
  all?: BestOptionResult[];
  symbol_count: number;
}

// ── API calls ─────────────────────────────────────────────────────────────────

export const api = {
  // Chat
  chat: (message: string, sessionId: string, voiceModeOrSymbol?: boolean | string) =>
    req<ChatResponse>("/chat", {
      method: "POST",
      body: JSON.stringify({
        message,
        session_id: sessionId,
        symbol: typeof voiceModeOrSymbol === "string" ? voiceModeOrSymbol : undefined,
        voice_mode: typeof voiceModeOrSymbol === "boolean" ? voiceModeOrSymbol : false,
        include_reasoning: true,
      }),
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
  providers: () => req<MarketProvidersResponse>("/market/providers"),

  quote: (symbol: string) => req<Quote>(`/market/quote/${symbol}`),

  history: (symbol: string, years = 5, timespan = "day") =>
    req<{ symbol: string; bars: OHLCVBar[] }>(`/market/history/${symbol}?years=${years}&timespan=${timespan}`),

  analysis: (symbol: string, sessionId = "console") =>
    req<FullAnalysis>(`/market/analysis/${symbol}?session_id=${encodeURIComponent(sessionId)}`),

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
  // Cross-session memory summary
  memorySummary: () =>
    req<{
      top_symbols: Array<{ symbol: string; mentions: number }>;
      recent_scenarios: Array<{ query: string; timestamp: string; session_id: string }>;
      recent_predictions: Array<{ symbol: string; direction: string; outcome: string; pnl_pct?: number; date: string }>;
    }>("/chat/memory/summary"),

  // Historical simulation
  simulate: (symbol: string, years = 5, horizonDays = 20) =>
    req<SimulationResult>(`/market/simulate/${symbol}?years=${years}&horizon_days=${horizonDays}&sample_every=10`),

  worldEvents: (start: string, end: string) =>
    req<{ events: WorldEvent[] }>(`/market/events/world?start=${start}&end=${end}`),

  // Event Intelligence
  eventIntelligence: (symbol: string) =>
    req<EventIntelligenceResponse>(`/market/events/${symbol}`),

  // Prediction history
  predictionHistory: (symbol: string) =>
    req<PredictionHistoryResponse>(`/market/predictions/${symbol}`),

  // Force score pending predictions
  scorePredictions: (symbol: string) =>
    req<{ scored: number }>(`/market/predictions/${symbol}/score`, { method: "POST" }),

  // Unified analysis — simulation + live predictions in one call
  unifiedAnalysis: (symbol: string, years = 5, horizonDays = 20, sampleEvery = 10) =>
    req<UnifiedAnalysisResponse>(
      `/market/unified/${symbol}?years=${years}&horizon_days=${horizonDays}&sample_every=${sampleEvery}`
    ),

  // Model accuracy stats
  modelStats: (symbol: string) =>
    req<Record<string, unknown>>(`/market/model-stats/${symbol}`),

  globalModelStats: () =>
    req<Record<string, unknown>>(`/market/model-stats`),

  // App control
  confirmCommand: (cmdId: string, confirmed: boolean) =>
    req<{ cmd_id: string; confirmed: boolean }>(`/chat/commands/${cmdId}/confirm`, {
      method: "POST",
      body: JSON.stringify({ confirmed }),
    }),

  pendingCommands: (sessionId: string) =>
    req<{ commands: PendingConfirmation[] }>(`/chat/commands/${sessionId}/pending`),

  commandHistory: (sessionId: string) =>
    req<{ commands: PendingConfirmation[] }>(`/chat/commands/${sessionId}/history`),

  // Session insights
  sessionInsights: (sessionId: string) =>
    req<{ insights: SessionInsight[]; summary: Record<string, unknown> }>(`/chat/insights/${sessionId}`),

  // Signal weight optimizer
  optimizeWeights: (symbol: string, years = 5, horizonDays = 20, generations = 40, save = true) =>
    req<OptimizationResult>(
      `/market/optimize/${symbol}?years=${years}&horizon_days=${horizonDays}&generations=${generations}&save=${save}`,
      { method: "POST" }
    ),

  getActiveWeights: (symbol: string) =>
    req<{ symbol: string; weights: Record<string, number>; is_default: boolean; default_weights: Record<string, number> }>(
      `/market/optimize/${symbol}/weights`
    ),

  resetWeights: (symbol: string) =>
    req<{ symbol: string; reset: boolean }>(`/market/optimize/${symbol}/weights`, { method: "DELETE" }),

  optimizationHistory: (symbol: string) =>
    req<{ symbol: string; runs: Array<Record<string, unknown>> }>(`/market/optimize/${symbol}/history`),

  // Best-option engine
  bestOption: (symbol: string, includeResearch = true) =>
    req<BestOptionResult>(
      `/market/best-option/${symbol}?include_research=${includeResearch}`
    ),

  bestOptionMulti: (symbols: string[], includeResearch = true) =>
    req<BestOptionMultiResult>(
      `/market/best-option?${symbols.map(s => `symbols=${s}`).join("&")}&include_research=${includeResearch}`,
      { method: "POST" }
    ),
};
