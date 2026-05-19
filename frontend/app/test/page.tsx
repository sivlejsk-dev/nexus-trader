"use client";

import { useState, useCallback } from "react";
import {
  Activity, Zap, TrendingUp, TrendingDown, Minus,
  RefreshCw, CheckCircle, XCircle, Clock, ChevronDown, ChevronUp,
  BarChart2, Target, BookOpen, AlertTriangle,
} from "lucide-react";
import { api, type Quote, type FullAnalysis, type BacktestResult, type GreeksResult, type StrategyScore, type ChatResponse } from "@/lib/api";
import { PriceChart } from "@/components/charts/PriceChart";
import { StrategyRadarChart, BacktestEquityCurve, GreeksSensitivityChart } from "@/components/charts/OptionsChart";
import { cn, fmtPrice, fmtPct, fmtVolume, changeColor } from "@/lib/utils";

// ── Types ─────────────────────────────────────────────────────────────────────

type Status = "idle" | "loading" | "ok" | "error";

interface SectionState<T> {
  status: Status;
  data: T | null;
  error: string | null;
  ms: number | null;
}

function initSection<T>(): SectionState<T> {
  return { status: "idle", data: null, error: null, ms: null };
}

// ── Sub-components ────────────────────────────────────────────────────────────

function StatusBadge({ status, ms }: { status: Status; ms: number | null }) {
  if (status === "idle") return <span className="text-xs text-gray-600">not run</span>;
  if (status === "loading") return (
    <span className="flex items-center gap-1 text-xs text-blue-400">
      <RefreshCw size={11} className="animate-spin" /> running…
    </span>
  );
  if (status === "ok") return (
    <span className="flex items-center gap-1 text-xs text-green-400">
      <CheckCircle size={11} /> {ms}ms
    </span>
  );
  return (
    <span className="flex items-center gap-1 text-xs text-red-400">
      <XCircle size={11} /> error
    </span>
  );
}

function SectionCard({
  title, icon: Icon, status, ms, children, defaultOpen = false,
}: {
  title: string;
  icon: React.ElementType;
  status: Status;
  ms: number | null;
  children: React.ReactNode;
  defaultOpen?: boolean;
}) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <div className="bg-[#111827] border border-[#1f2937] rounded-xl overflow-hidden">
      <button
        onClick={() => setOpen((o) => !o)}
        className="w-full flex items-center gap-3 px-5 py-4 hover:bg-[#1a2235] transition-colors"
      >
        <Icon size={16} className="text-blue-400 flex-shrink-0" />
        <span className="flex-1 text-left text-sm font-semibold text-gray-200">{title}</span>
        <StatusBadge status={status} ms={ms} />
        {open ? <ChevronUp size={14} className="text-gray-500 ml-2" /> : <ChevronDown size={14} className="text-gray-500 ml-2" />}
      </button>
      {open && <div className="px-5 pb-5 border-t border-[#1f2937]">{children}</div>}
    </div>
  );
}

function StatPill({ label, value, color }: { label: string; value: string; color?: string }) {
  return (
    <div className="bg-[#0a0e1a] rounded-lg px-3 py-2 flex flex-col gap-0.5">
      <span className="text-[10px] text-gray-500 uppercase tracking-wider">{label}</span>
      <span className={cn("text-sm font-semibold", color ?? "text-gray-100")}>{value}</span>
    </div>
  );
}

function ErrorBox({ msg }: { msg: string }) {
  return (
    <div className="mt-3 flex items-start gap-2 bg-red-950/30 border border-red-900/40 rounded-lg p-3 text-xs text-red-400">
      <AlertTriangle size={13} className="flex-shrink-0 mt-0.5" />
      <span>{msg}</span>
    </div>
  );
}

// ── Quote Section ─────────────────────────────────────────────────────────────

function QuoteSection({ state, symbol, onRun }: { state: SectionState<Quote>; symbol: string; onRun: () => void }) {
  const q = state.data;
  const isUp = (q?.change ?? 0) >= 0;
  return (
    <SectionCard title="Market Quote" icon={Activity} status={state.status} ms={state.ms} defaultOpen>
      <div className="pt-4 space-y-4">
        <div className="flex items-center justify-between">
          <span className="text-xs text-gray-500">GET /api/v1/market/quote/{symbol}</span>
          <button onClick={onRun} className="flex items-center gap-1.5 px-3 py-1.5 bg-[#1f2937] hover:bg-[#374151] text-gray-300 text-xs rounded-lg transition-colors">
            <RefreshCw size={11} /> Run
          </button>
        </div>
        {state.error && <ErrorBox msg={state.error} />}
        {q && (
          <div className="space-y-3">
            <div className="flex items-baseline gap-3">
              <span className="text-3xl font-bold text-white">{fmtPrice(q.price)}</span>
              <span className={cn("flex items-center gap-1 text-sm font-medium", isUp ? "text-green-400" : "text-red-400")}>
                {isUp ? <TrendingUp size={14} /> : <TrendingDown size={14} />}
                {fmtPct(q.change_pct)}
              </span>
              <span className="text-xs text-gray-500 ml-auto">via {q.source}</span>
            </div>
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
              <StatPill label="Open" value={fmtPrice(q.open)} />
              <StatPill label="High" value={fmtPrice(q.high)} color="text-green-400" />
              <StatPill label="Low" value={fmtPrice(q.low)} color="text-red-400" />
              <StatPill label="Volume" value={fmtVolume(q.volume)} />
            </div>
          </div>
        )}
      </div>
    </SectionCard>
  );
}

// ── Analysis Section ──────────────────────────────────────────────────────────

function AnalysisSection({ state, symbol, onRun }: { state: SectionState<FullAnalysis>; symbol: string; onRun: () => void }) {
  const d = state.data;
  return (
    <SectionCard title="Full Market Analysis + Chart" icon={BarChart2} status={state.status} ms={state.ms}>
      <div className="pt-4 space-y-4">
        <div className="flex items-center justify-between">
          <span className="text-xs text-gray-500">GET /api/v1/market/analysis/{symbol}</span>
          <button onClick={onRun} className="flex items-center gap-1.5 px-3 py-1.5 bg-[#1f2937] hover:bg-[#374151] text-gray-300 text-xs rounded-lg transition-colors">
            <RefreshCw size={11} /> Run
          </button>
        </div>
        {state.error && <ErrorBox msg={state.error} />}
        {d && (
          <div className="space-y-4">
            {/* Technicals */}
            {d.technicals && (
              <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-2">
                <StatPill label="RSI" value={d.technicals.rsi?.toFixed(1) ?? "—"} color={d.technicals.rsi != null ? (d.technicals.rsi > 70 ? "text-red-400" : d.technicals.rsi < 30 ? "text-green-400" : "text-yellow-400") : undefined} />
                <StatPill label="MACD" value={d.technicals.macd?.toFixed(2) ?? "—"} color={(d.technicals.macd ?? 0) >= 0 ? "text-green-400" : "text-red-400"} />
                <StatPill label="Signal" value={d.technicals.macd_signal?.toFixed(2) ?? "—"} />
                <StatPill label="SMA 50" value={fmtPrice(d.technicals.sma_50)} />
                <StatPill label="SMA 200" value={fmtPrice(d.technicals.sma_200)} />
                <StatPill label="Bias" value={d.patterns?.summary?.bias ?? "—"} color={d.patterns?.summary?.bias === "bullish" ? "text-green-400" : d.patterns?.summary?.bias === "bearish" ? "text-red-400" : "text-yellow-400"} />
              </div>
            )}
            {/* Price chart */}
            {d.chart_bars && d.chart_bars.length > 0 && (
              <div className="bg-[#0a0e1a] rounded-xl p-3">
                <PriceChart
                  bars={d.chart_bars}
                  sr={d.patterns?.support_resistance}
                  sma50={d.technicals?.sma_50}
                  sma200={d.technicals?.sma_200}
                  height={380}
                />
              </div>
            )}
            {/* Reasoning */}
            {d.reasoning && (
              <div className="bg-[#0a0e1a] rounded-xl p-4 space-y-2">
                <div className="flex items-center justify-between">
                  <span className="text-xs font-semibold text-gray-300">AI Reasoning</span>
                  <span className={cn("text-xs font-medium px-2 py-0.5 rounded-full", d.reasoning.confidence >= 0.7 ? "bg-green-900/40 text-green-400" : d.reasoning.confidence >= 0.5 ? "bg-yellow-900/40 text-yellow-400" : "bg-red-900/40 text-red-400")}>
                    {(d.reasoning.confidence * 100).toFixed(0)}% {d.reasoning.confidence_level}
                  </span>
                </div>
                <p className="text-sm text-gray-200">{d.reasoning.conclusion}</p>
                {d.reasoning.steps?.slice(0, 3).map((step, i) => (
                  <div key={i} className="text-xs text-gray-400 flex gap-2">
                    <span className="text-blue-500 flex-shrink-0">›</span>
                    <span>{step.description}</span>
                  </div>
                ))}
              </div>
            )}
            {/* Adaptive prediction */}
            {d.adaptive_prediction?.prediction && (() => {
              const p = d.adaptive_prediction!.prediction;
              const isCall = p.direction === "call";
              const isNeutral = p.direction === "neutral";
              return (
                <div className="bg-[#0a0e1a] rounded-xl p-4 space-y-2">
                  <div className="flex items-center justify-between">
                    <span className="text-xs font-semibold text-gray-300">Adaptive Prediction</span>
                    <span className={cn("text-xs font-bold px-2 py-0.5 rounded-full uppercase", isCall ? "bg-green-900/40 text-green-400" : isNeutral ? "bg-yellow-900/40 text-yellow-400" : "bg-red-900/40 text-red-400")}>
                      {p.direction} · {(p.confidence * 100).toFixed(0)}%
                    </span>
                  </div>
                  <div className="grid grid-cols-3 gap-2">
                    <StatPill label="Entry" value={fmtPrice(p.entry_price)} />
                    <StatPill label="Target" value={fmtPrice(p.target_price)} color="text-green-400" />
                    <StatPill label="Stop" value={fmtPrice(p.stop_loss)} color="text-red-400" />
                  </div>
                  {p.rationale?.slice(0, 2).map((r, i) => (
                    <div key={i} className="text-xs text-gray-400 flex gap-2">
                      <span className="text-blue-500 flex-shrink-0">›</span><span>{r}</span>
                    </div>
                  ))}
                </div>
              );
            })()}
          </div>
        )}
      </div>
    </SectionCard>
  );
}

// ── Strategies Section ────────────────────────────────────────────────────────

function StrategiesSection({ state, symbol, onRun }: { state: SectionState<{ strategies: StrategyScore[]; disclaimer: string }>; symbol: string; onRun: () => void }) {
  const d = state.data;
  return (
    <SectionCard title="Options Strategy Scoring" icon={Target} status={state.status} ms={state.ms}>
      <div className="pt-4 space-y-4">
        <div className="flex items-center justify-between">
          <span className="text-xs text-gray-500">GET /api/v1/options/strategies/{symbol}</span>
          <button onClick={onRun} className="flex items-center gap-1.5 px-3 py-1.5 bg-[#1f2937] hover:bg-[#374151] text-gray-300 text-xs rounded-lg transition-colors">
            <RefreshCw size={11} /> Run
          </button>
        </div>
        {state.error && <ErrorBox msg={state.error} />}
        {d && (
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            <div className="space-y-2">
              {d.strategies.slice(0, 6).map((s) => (
                <div key={s.name} className="bg-[#0a0e1a] rounded-lg p-3 flex items-center gap-3">
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                      <span className="text-sm font-medium text-gray-200">{s.name}</span>
                      <span className={cn("text-[10px] px-1.5 py-0.5 rounded uppercase font-semibold", s.direction === "bullish" ? "bg-green-900/40 text-green-400" : s.direction === "bearish" ? "bg-red-900/40 text-red-400" : "bg-yellow-900/40 text-yellow-400")}>
                        {s.direction}
                      </span>
                    </div>
                    <div className="text-[10px] text-gray-500 mt-0.5">{s.rationale[0]}</div>
                  </div>
                  <div className="flex-shrink-0 text-right">
                    <div className="text-lg font-bold text-blue-400">{s.score}</div>
                    <div className="text-[9px] text-gray-600">score</div>
                  </div>
                </div>
              ))}
            </div>
            <div className="bg-[#0a0e1a] rounded-xl p-3">
              <StrategyRadarChart strategies={d.strategies} />
            </div>
          </div>
        )}
      </div>
    </SectionCard>
  );
}

// ── Backtest Section ──────────────────────────────────────────────────────────

function BacktestSection({ state, symbol, onRun }: { state: SectionState<BacktestResult>; symbol: string; onRun: () => void }) {
  const d = state.data;
  return (
    <SectionCard title="Strategy Backtest" icon={TrendingUp} status={state.status} ms={state.ms}>
      <div className="pt-4 space-y-4">
        <div className="flex items-center justify-between">
          <span className="text-xs text-gray-500">POST /api/v1/options/backtest · Long Call · 5% OTM · 30 DTE · 3yr</span>
          <button onClick={onRun} className="flex items-center gap-1.5 px-3 py-1.5 bg-[#1f2937] hover:bg-[#374151] text-gray-300 text-xs rounded-lg transition-colors">
            <RefreshCw size={11} /> Run
          </button>
        </div>
        {state.error && <ErrorBox msg={state.error} />}
        {d && (
          <div className="space-y-4">
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
              <StatPill label="Trades" value={String(d.total_trades)} />
              <StatPill label="Win Rate" value={`${(d.win_rate * 100).toFixed(1)}%`} color={d.win_rate >= 0.5 ? "text-green-400" : "text-red-400"} />
              <StatPill label="Avg Win" value={`+${d.avg_win_pct.toFixed(1)}%`} color="text-green-400" />
              <StatPill label="Avg Loss" value={`${d.avg_loss_pct.toFixed(1)}%`} color="text-red-400" />
              <StatPill label="Total P&L" value={`$${d.total_pnl_per_contract.toFixed(0)}`} color={d.total_pnl_per_contract >= 0 ? "text-green-400" : "text-red-400"} />
              <StatPill label="Expectancy" value={`${d.expectancy_pct.toFixed(2)}%`} color={d.expectancy_pct >= 0 ? "text-green-400" : "text-red-400"} />
              <StatPill label="Wins" value={String(d.wins)} color="text-green-400" />
              <StatPill label="Losses" value={String(d.losses)} color="text-red-400" />
            </div>
            {d.trades?.length > 0 && (
              <div className="bg-[#0a0e1a] rounded-xl p-3">
                <BacktestEquityCurve trades={d.trades} />
              </div>
            )}
          </div>
        )}
      </div>
    </SectionCard>
  );
}

// ── Greeks Section ────────────────────────────────────────────────────────────

function GreeksSection({ state, form, setForm, onRun, underlyingPrice }: {
  state: SectionState<{ greeks: GreeksResult; disclaimer: string }>;
  form: { strike: number; dte: number; iv: number; type: "call" | "put" };
  setForm: React.Dispatch<React.SetStateAction<{ strike: number; dte: number; iv: number; type: "call" | "put" }>>;
  onRun: () => void;
  underlyingPrice: number;
}) {
  const g = state.data?.greeks;
  return (
    <SectionCard title="Black-Scholes Greeks Calculator" icon={BookOpen} status={state.status} ms={state.ms}>
      <div className="pt-4 space-y-4">
        <div className="flex items-center justify-between">
          <span className="text-xs text-gray-500">POST /api/v1/options/greeks</span>
          <button onClick={onRun} className="flex items-center gap-1.5 px-3 py-1.5 bg-[#1f2937] hover:bg-[#374151] text-gray-300 text-xs rounded-lg transition-colors">
            <RefreshCw size={11} /> Run
          </button>
        </div>
        {/* Inputs */}
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
          <label className="flex flex-col gap-1">
            <span className="text-[10px] text-gray-500 uppercase tracking-wider">Strike ($)</span>
            <input type="number" value={form.strike} onChange={(e) => setForm((f) => ({ ...f, strike: Number(e.target.value) }))}
              className="bg-[#0a0e1a] border border-[#374151] rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-blue-500" />
          </label>
          <label className="flex flex-col gap-1">
            <span className="text-[10px] text-gray-500 uppercase tracking-wider">DTE (days)</span>
            <input type="number" value={form.dte} onChange={(e) => setForm((f) => ({ ...f, dte: Number(e.target.value) }))}
              className="bg-[#0a0e1a] border border-[#374151] rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-blue-500" />
          </label>
          <label className="flex flex-col gap-1">
            <span className="text-[10px] text-gray-500 uppercase tracking-wider">IV (e.g. 0.30)</span>
            <input type="number" step="0.01" value={form.iv} onChange={(e) => setForm((f) => ({ ...f, iv: Number(e.target.value) }))}
              className="bg-[#0a0e1a] border border-[#374151] rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-blue-500" />
          </label>
          <label className="flex flex-col gap-1">
            <span className="text-[10px] text-gray-500 uppercase tracking-wider">Type</span>
            <select value={form.type} onChange={(e) => setForm((f) => ({ ...f, type: e.target.value as "call" | "put" }))}
              className="bg-[#0a0e1a] border border-[#374151] rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-blue-500">
              <option value="call">Call</option>
              <option value="put">Put</option>
            </select>
          </label>
        </div>
        {state.error && <ErrorBox msg={state.error} />}
        {g && (
          <div className="space-y-4">
            <div className="grid grid-cols-3 sm:grid-cols-6 gap-2">
              <StatPill label="Price" value={`$${g.price.toFixed(3)}`} color="text-blue-400" />
              <StatPill label="Delta" value={g.delta.toFixed(3)} color={g.delta >= 0 ? "text-green-400" : "text-red-400"} />
              <StatPill label="Gamma" value={g.gamma.toFixed(4)} />
              <StatPill label="Theta" value={g.theta.toFixed(4)} color="text-red-400" />
              <StatPill label="Vega" value={g.vega.toFixed(4)} color="text-yellow-400" />
              <StatPill label="Rho" value={g.rho.toFixed(4)} />
            </div>
            <div className="bg-[#0a0e1a] rounded-xl p-3">
              <GreeksSensitivityChart
                underlyingPrice={underlyingPrice || 200}
                strike={form.strike}
                dte={form.dte}
                iv={form.iv}
                optionType={form.type}
              />
            </div>
          </div>
        )}
      </div>
    </SectionCard>
  );
}

// ── Chat Section ──────────────────────────────────────────────────────────────

function ChatSection({ state, msg, setMsg, symbol, onRun }: {
  state: SectionState<ChatResponse>;
  msg: string;
  setMsg: (m: string) => void;
  symbol: string;
  onRun: () => void;
}) {
  return (
    <SectionCard title="Nexus AI Chat" icon={Zap} status={state.status} ms={state.ms}>
      <div className="pt-4 space-y-4">
        <div className="flex items-center justify-between">
          <span className="text-xs text-gray-500">POST /api/v1/chat · symbol: {symbol}</span>
          <button onClick={onRun} className="flex items-center gap-1.5 px-3 py-1.5 bg-[#1f2937] hover:bg-[#374151] text-gray-300 text-xs rounded-lg transition-colors">
            <RefreshCw size={11} /> Run
          </button>
        </div>
        <div className="flex gap-2">
          <input
            value={msg}
            onChange={(e) => setMsg(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && onRun()}
            placeholder="Ask Nexus AI…"
            className="flex-1 bg-[#0a0e1a] border border-[#374151] rounded-lg px-3 py-2 text-sm text-white placeholder-gray-600 focus:outline-none focus:border-blue-500"
          />
          <button onClick={onRun} className="px-4 py-2 bg-blue-600 hover:bg-blue-500 text-white text-sm rounded-lg transition-colors">
            Send
          </button>
        </div>
        {state.error && <ErrorBox msg={state.error} />}
        {state.data?.response && (
          <div className="bg-[#0a0e1a] rounded-xl p-4 text-sm text-gray-200 leading-relaxed border border-[#1f2937]">
            {state.data.response}
          </div>
        )}
      </div>
    </SectionCard>
  );
}

// ── Main page ─────────────────────────────────────────────────────────────────

const SYMBOLS = ["AAPL", "TSLA", "NVDA", "SPY", "MSFT", "AMZN", "META", "QQQ"];

export default function TestPage() {
  const [symbol, setSymbol] = useState("AAPL");
  const [input, setInput] = useState("AAPL");

  // Section states
  const [quote, setQuote] = useState<SectionState<Quote>>(initSection());
  const [analysis, setAnalysis] = useState<SectionState<FullAnalysis>>(initSection());
  const [strategies, setStrategies] = useState<SectionState<{ strategies: StrategyScore[]; disclaimer: string }>>(initSection());
  const [backtest, setBacktest] = useState<SectionState<BacktestResult>>(initSection());
  const [greeks, setGreeks] = useState<SectionState<{ greeks: GreeksResult; disclaimer: string }>>(initSection());
  const [chat, setChat] = useState<SectionState<ChatResponse>>(initSection());

  // Greeks inputs
  const [greeksForm, setGreeksForm] = useState({
    strike: 200, dte: 30, iv: 0.30, type: "call" as "call" | "put",
  });
  const [chatMsg, setChatMsg] = useState("What is the current trend for this stock?");

  const applySymbol = () => {
    const s = input.trim().toUpperCase();
    if (s) setSymbol(s);
  };

  async function run<T>(
    setter: React.Dispatch<React.SetStateAction<SectionState<T>>>,
    fn: () => Promise<T>,
  ) {
    setter((p) => ({ ...p, status: "loading", error: null }));
    const t0 = Date.now();
    try {
      const data = await fn();
      setter({ status: "ok", data, error: null, ms: Date.now() - t0 });
    } catch (e: any) {
      setter({ status: "error", data: null, error: e.message ?? "Unknown error", ms: Date.now() - t0 });
    }
  }

  const runAll = useCallback(async () => {
    const s = symbol;
    run(setQuote, () => api.quote(s));
    run(setAnalysis, () => api.analysis(s));
    run(setStrategies, () => api.strategies(s, 30));
    run(setBacktest, () => api.backtest({ symbol: s, option_type: "call", strike_offset_pct: 0.05, days_to_expiry: 30, iv_assumption: 0.30, years: 3 }));
    run(setGreeks, () => api.greeks({ underlying_price: 200, strike: greeksForm.strike, days_to_expiry: greeksForm.dte, implied_volatility: greeksForm.iv, option_type: greeksForm.type }));
    run(setChat, () => api.chat(chatMsg, "test-session", s));
  }, [symbol, greeksForm, chatMsg]);

  return (
    <div className="min-h-screen bg-[#0a0e1a] p-6 space-y-5">
      {/* Header */}
      <div className="flex items-center gap-3 mb-2">
        <div className="w-9 h-9 rounded-xl bg-blue-600/20 border border-blue-600/30 flex items-center justify-center">
          <Activity size={18} className="text-blue-400" />
        </div>
        <div>
          <h1 className="text-lg font-bold text-white">API Test Suite</h1>
          <p className="text-xs text-gray-500">Live endpoint verification for all Nexus Trader APIs</p>
        </div>
      </div>

      {/* Symbol picker */}
      <div className="bg-[#111827] border border-[#1f2937] rounded-xl p-4 flex flex-wrap items-center gap-3">
        <div className="flex items-center gap-2 flex-1 min-w-[200px]">
          <input
            value={input}
            onChange={(e) => setInput(e.target.value.toUpperCase())}
            onKeyDown={(e) => e.key === "Enter" && applySymbol()}
            placeholder="Symbol…"
            className="flex-1 bg-[#0a0e1a] border border-[#374151] rounded-lg px-3 py-2 text-sm text-white placeholder-gray-600 focus:outline-none focus:border-blue-500"
          />
          <button
            onClick={applySymbol}
            className="px-3 py-2 bg-[#1f2937] hover:bg-[#374151] text-gray-300 text-sm rounded-lg transition-colors"
          >
            Set
          </button>
        </div>
        <div className="flex flex-wrap gap-1.5">
          {SYMBOLS.map((s) => (
            <button
              key={s}
              onClick={() => { setSymbol(s); setInput(s); }}
              className={cn(
                "px-2.5 py-1 rounded-md text-xs font-medium transition-colors",
                symbol === s
                  ? "bg-blue-600 text-white"
                  : "bg-[#1f2937] text-gray-400 hover:text-gray-200 hover:bg-[#374151]"
              )}
            >{s}</button>
          ))}
        </div>
        <button
          onClick={runAll}
          className="flex items-center gap-2 px-4 py-2 bg-blue-600 hover:bg-blue-500 text-white text-sm font-semibold rounded-lg transition-colors ml-auto"
        >
          <Zap size={14} /> Run All Tests
        </button>
      </div>

      {/* Sections */}
      <QuoteSection state={quote} symbol={symbol} onRun={() => run(setQuote, () => api.quote(symbol))} />
      <AnalysisSection state={analysis} symbol={symbol} onRun={() => run(setAnalysis, () => api.analysis(symbol))} />
      <StrategiesSection state={strategies} symbol={symbol} onRun={() => run(setStrategies, () => api.strategies(symbol, 30))} />
      <BacktestSection state={backtest} symbol={symbol} onRun={() => run(setBacktest, () => api.backtest({ symbol, option_type: "call", strike_offset_pct: 0.05, days_to_expiry: 30, iv_assumption: 0.30, years: 3 }))} />
      <GreeksSection
        state={greeks} form={greeksForm} setForm={setGreeksForm}
        onRun={() => run(setGreeks, () => api.greeks({ underlying_price: analysis.data?.quote?.price ?? 200, strike: greeksForm.strike, days_to_expiry: greeksForm.dte, implied_volatility: greeksForm.iv, option_type: greeksForm.type }))}
        underlyingPrice={analysis.data?.quote?.price ?? 200}
      />
      <ChatSection state={chat} msg={chatMsg} setMsg={setChatMsg} symbol={symbol} onRun={() => run(setChat, () => api.chat(chatMsg, "test-session", symbol))} />

      <p className="text-[10px] text-gray-700 text-center pb-4">
        All data is for informational purposes only and does not constitute financial advice.
      </p>
    </div>
  );
}
