"use client";

import { useState, useCallback, useMemo } from "react";
import {
  Play, RefreshCw, AlertTriangle, TrendingUp, TrendingDown,
  Minus, Globe, ChevronDown, ChevronUp, Zap, BarChart2,
  CheckCircle, XCircle, Brain, Target, Activity, Layers,
} from "lucide-react";
import {
  ComposedChart, Bar, Line, XAxis, YAxis, CartesianGrid,
  Tooltip, ResponsiveContainer, ReferenceLine, Cell, RadarChart,
  PolarGrid, PolarAngleAxis, Radar,
} from "recharts";
import { api, type SimulationResult, type SimulationPrediction, type WorldEvent } from "@/lib/api";
import { cn, fmtPrice } from "@/lib/utils";

// ── helpers ───────────────────────────────────────────────────────────────────

const IMPACT_CFG = {
  bullish:    { color: "text-green-400",  bg: "bg-green-900/20 border-green-800/30",  dot: "bg-green-400" },
  bearish:    { color: "text-red-400",    bg: "bg-red-900/20 border-red-800/30",      dot: "bg-red-400"   },
  volatility: { color: "text-yellow-400", bg: "bg-yellow-900/20 border-yellow-800/30", dot: "bg-yellow-400" },
};

const CAT_COLOR: Record<string, string> = {
  geopolitical: "text-red-400",
  macro:        "text-purple-400",
  weather:      "text-cyan-400",
  social:       "text-pink-400",
  regulatory:   "text-orange-400",
  pandemic:     "text-rose-400",
};

function DirectionBadge({ d }: { d: string }) {
  if (d === "call") return <span className="text-[10px] px-2 py-0.5 rounded-full bg-green-900/20 border border-green-800/30 text-green-400 font-semibold flex items-center gap-1"><TrendingUp size={9}/>CALL</span>;
  if (d === "put")  return <span className="text-[10px] px-2 py-0.5 rounded-full bg-red-900/20 border border-red-800/30 text-red-400 font-semibold flex items-center gap-1"><TrendingDown size={9}/>PUT</span>;
  return <span className="text-[10px] px-2 py-0.5 rounded-full bg-gray-900/20 border border-gray-800/30 text-gray-400 font-semibold flex items-center gap-1"><Minus size={9}/>NEUTRAL</span>;
}

// ── Regime breakdown panel ────────────────────────────────────────────────────

const REGIME_CFG: Record<string, { label: string; color: string; bg: string }> = {
  trending_up:   { label: "Trending Up",   color: "text-green-400",  bg: "bg-green-900/20 border-green-800/30" },
  trending_down: { label: "Trending Down", color: "text-red-400",    bg: "bg-red-900/20 border-red-800/30" },
  ranging:       { label: "Ranging",       color: "text-blue-400",   bg: "bg-blue-900/20 border-blue-800/30" },
  volatile:      { label: "Volatile",      color: "text-yellow-400", bg: "bg-yellow-900/20 border-yellow-800/30" },
};

function RegimePanel({ result }: { result: SimulationResult }) {
  const stats = result.regime_stats;
  if (!stats || Object.keys(stats).length === 0) return null;
  return (
    <div className="bg-[#111827] border border-[#1f2937] rounded-xl p-4">
      <div className="flex items-center gap-2 mb-3">
        <Activity size={13} className="text-purple-400" />
        <span className="text-xs font-semibold text-gray-400">Win Rate by Market Regime</span>
      </div>
      <div className="space-y-2">
        {Object.entries(stats).map(([regime, s]) => {
          const cfg = REGIME_CFG[regime] || { label: regime, color: "text-gray-400", bg: "bg-gray-900/20 border-gray-800/30" };
          const wr = s.win_rate ?? 0;
          return (
            <div key={regime} className={cn("border rounded-lg px-3 py-2", cfg.bg)}>
              <div className="flex items-center justify-between mb-1">
                <span className={cn("text-[10px] font-semibold", cfg.color)}>{cfg.label}</span>
                <span className={cn("text-xs font-mono font-bold", wr >= 55 ? "text-green-400" : "text-red-400")}>{wr}%</span>
              </div>
              <div className="flex items-center gap-3">
                <div className="flex-1 h-1.5 bg-[#1f2937] rounded-full overflow-hidden">
                  <div className={cn("h-full rounded-full", wr >= 55 ? "bg-green-500" : "bg-red-500")} style={{ width: `${wr}%` }} />
                </div>
                <span className="text-[10px] text-gray-600">{s.total} trades</span>
                <span className={cn("text-[10px] font-mono", s.avg_pnl >= 0 ? "text-green-400" : "text-red-400")}>
                  {s.avg_pnl >= 0 ? "+" : ""}{s.avg_pnl}%
                </span>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

// ── Multi-timeframe alignment panel ──────────────────────────────────────────

function MTFPanel({ result }: { result: SimulationResult }) {
  const mtf = result.mtf_stats;
  if (!mtf) return null;
  const alignedWR = mtf.aligned.win_rate;
  const unalignedWR = mtf.unaligned.win_rate;
  const lift = alignedWR != null && unalignedWR != null ? +(alignedWR - unalignedWR).toFixed(1) : null;
  return (
    <div className="bg-[#111827] border border-[#1f2937] rounded-xl p-4">
      <div className="flex items-center gap-2 mb-3">
        <Layers size={13} className="text-cyan-400" />
        <span className="text-xs font-semibold text-gray-400">Multi-Timeframe Alignment</span>
        {lift != null && (
          <span className={cn("text-[10px] px-2 py-0.5 rounded-full border ml-auto",
            lift > 0 ? "text-green-400 bg-green-900/20 border-green-800/30" : "text-gray-500 bg-gray-900/20 border-gray-800/30")}>
            {lift > 0 ? `+${lift}% lift when aligned` : "No alignment lift"}
          </span>
        )}
      </div>
      <div className="grid grid-cols-2 gap-3">
        {[
          { label: "Aligned", data: mtf.aligned, color: "text-green-400", bar: "bg-green-500" },
          { label: "Not Aligned", data: mtf.unaligned, color: "text-red-400", bar: "bg-red-500" },
        ].map(({ label, data, color, bar }) => {
          const wr = data.win_rate ?? 0;
          return (
            <div key={label} className="bg-[#0d1117] rounded-lg p-3">
              <div className="text-[10px] text-gray-500 mb-1">{label}</div>
              <div className={cn("text-xl font-bold font-mono", color)}>{wr != null ? `${wr}%` : "—"}</div>
              <div className="mt-1.5 h-1.5 bg-[#1f2937] rounded-full overflow-hidden">
                <div className={cn("h-full rounded-full", bar)} style={{ width: `${wr}%` }} />
              </div>
              <div className="text-[10px] text-gray-600 mt-1">{data.total} trades</div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

// ── Confidence calibration panel ──────────────────────────────────────────────

function CalibrationPanel({ result }: { result: SimulationResult }) {
  const cal = result.calibration;
  if (!cal || cal.length === 0) return null;
  return (
    <div className="bg-[#111827] border border-[#1f2937] rounded-xl p-4">
      <div className="flex items-center gap-2 mb-3">
        <Target size={13} className="text-orange-400" />
        <span className="text-xs font-semibold text-gray-400">Confidence Calibration</span>
        <span className="text-[10px] text-gray-600 ml-auto">Does high confidence = higher win rate?</span>
      </div>
      <ResponsiveContainer width="100%" height={120}>
        <ComposedChart data={cal} margin={{ top: 4, right: 8, left: 0, bottom: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#1a2235" vertical={false} />
          <XAxis dataKey="bucket" tick={{ fill: "#4b5563", fontSize: 9 }} tickLine={false} axisLine={false} />
          <YAxis tick={{ fill: "#4b5563", fontSize: 9 }} tickLine={false} axisLine={false} width={32}
            tickFormatter={(v) => `${v}%`} domain={[0, 100]} />
          <Tooltip contentStyle={{ background: "#1a2235", border: "1px solid #374151", borderRadius: 8, fontSize: 11 }}
            formatter={(v: number, name: string) => [`${v}%`, name === "actual_win_rate" ? "Actual Win Rate" : "Predicted"]} />
          <ReferenceLine y={50} stroke="#374151" strokeDasharray="3 2" />
          <Bar dataKey="actual_win_rate" name="actual_win_rate" radius={[3, 3, 0, 0]}>
            {cal.map((b, i) => (
              <Cell key={i} fill={b.actual_win_rate >= 55 ? "#22c55e" : b.actual_win_rate >= 45 ? "#f59e0b" : "#ef4444"} />
            ))}
          </Bar>
          <Line type="monotone" dataKey="predicted_confidence" stroke="#6366f1" strokeWidth={1.5}
            strokeDasharray="4 2" dot={false} name="predicted_confidence" />
        </ComposedChart>
      </ResponsiveContainer>
      <div className="flex gap-3 mt-2">
        <div className="flex items-center gap-1.5 text-[10px] text-gray-500">
          <div className="w-3 h-2 rounded-sm bg-green-500" /> Actual win rate
        </div>
        <div className="flex items-center gap-1.5 text-[10px] text-gray-500">
          <div className="w-4 h-px bg-indigo-400" style={{ borderTop: "2px dashed #6366f1" }} /> Predicted confidence
        </div>
      </div>
    </div>
  );
}

// ── Signal quality radar ──────────────────────────────────────────────────────

function SignalRadar({ result }: { result: SimulationResult }) {
  const stats = result.signal_stats;
  if (!stats) return null;
  const data = Object.entries(stats)
    .filter(([, s]) => s.total >= 5)
    .map(([key, s]) => ({
      signal: key.replace(/_/g, " ").replace(/\b\w/g, c => c.toUpperCase()),
      win_rate: s.win_rate ?? 0,
      total: s.total,
    }));
  if (data.length < 3) return null;
  return (
    <div className="bg-[#111827] border border-[#1f2937] rounded-xl p-4">
      <div className="flex items-center gap-2 mb-3">
        <Brain size={13} className="text-blue-400" />
        <span className="text-xs font-semibold text-gray-400">Signal Win Rates</span>
      </div>
      <ResponsiveContainer width="100%" height={180}>
        <RadarChart data={data} margin={{ top: 8, right: 24, left: 24, bottom: 8 }}>
          <PolarGrid stroke="#1f2937" />
          <PolarAngleAxis dataKey="signal" tick={{ fill: "#6b7280", fontSize: 9 }} />
          <Radar dataKey="win_rate" stroke="#3b82f6" fill="#3b82f6" fillOpacity={0.25} strokeWidth={1.5} />
          <Tooltip contentStyle={{ background: "#1a2235", border: "1px solid #374151", borderRadius: 8, fontSize: 11 }}
            formatter={(v: number) => [`${v}%`, "Win Rate"]} />
        </RadarChart>
      </ResponsiveContainer>
    </div>
  );
}

// ── Learning factors panel ────────────────────────────────────────────────────

function LearningPanel({ result }: { result: SimulationResult }) {
  const factors = result.learning_factors;
  if (!factors) return null;
  const entries = Object.entries(factors).filter(([d]) => d !== "neutral");
  return (
    <div className="bg-[#111827] border border-[#1f2937] rounded-xl p-4">
      <div className="flex items-center gap-2 mb-3">
        <Brain size={13} className="text-cyan-400" />
        <span className="text-xs font-semibold text-gray-400">Live Learning Factors</span>
        <span className="text-[10px] text-gray-600 ml-auto">Applied from past predictions</span>
      </div>
      <div className="grid grid-cols-2 gap-3">
        {entries.map(([dir, factor]) => {
          const boosted = factor > 1.0;
          const reduced = factor < 1.0;
          return (
            <div key={dir} className={cn("rounded-lg border p-3",
              boosted ? "bg-green-900/15 border-green-800/30" :
              reduced ? "bg-red-900/15 border-red-800/30" :
              "bg-[#0d1117] border-[#1f2937]")}>
              <div className="text-[10px] text-gray-500 uppercase mb-1">{dir}</div>
              <div className={cn("text-xl font-bold font-mono",
                boosted ? "text-green-400" : reduced ? "text-red-400" : "text-gray-400")}>
                {factor.toFixed(2)}×
              </div>
              <div className="text-[10px] mt-1">
                {boosted ? <span className="text-green-500">Confidence boosted</span> :
                 reduced ? <span className="text-red-500">Confidence reduced</span> :
                 <span className="text-gray-600">No adjustment</span>}
              </div>
            </div>
          );
        })}
      </div>
      {result.using_learned_weights && (
        <div className="mt-3 flex items-center gap-1.5 text-[10px] text-cyan-500">
          <Zap size={10} /> Using optimized signal weights for this symbol
        </div>
      )}
    </div>
  );
}

// ── Accuracy summary cards ────────────────────────────────────────────────────

function AccuracySummary({ result }: { result: SimulationResult }) {
  const wr = result.win_rate ?? 0;
  return (
    <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
      {[
        { label: "Predictions", value: result.total_predictions, color: "text-white" },
        { label: "Win Rate",    value: wr != null ? `${wr}%` : "—", color: wr >= 55 ? "text-green-400" : "text-red-400" },
        { label: "Avg P&L",    value: result.avg_pnl_pct != null ? `${result.avg_pnl_pct > 0 ? "+" : ""}${result.avg_pnl_pct}%` : "—",
          color: (result.avg_pnl_pct ?? 0) >= 0 ? "text-green-400" : "text-red-400" },
        { label: "World Events", value: result.events.length, color: "text-blue-400" },
      ].map(({ label, value, color }) => (
        <div key={label} className="bg-[#111827] border border-[#1f2937] rounded-xl p-4 text-center">
          <div className="text-[10px] text-gray-600 uppercase tracking-wide mb-1">{label}</div>
          <div className={cn("text-2xl font-bold font-mono", color)}>{value}</div>
        </div>
      ))}
    </div>
  );
}

// ── Direction breakdown ───────────────────────────────────────────────────────

function DirectionBreakdown({ byDir }: { byDir: SimulationResult["by_direction"] }) {
  return (
    <div className="bg-[#111827] border border-[#1f2937] rounded-xl p-4">
      <div className="text-xs font-semibold text-gray-400 mb-3">Accuracy by Direction</div>
      <div className="space-y-3">
        {(["call", "put", "neutral"] as const).map((dir) => {
          const s = byDir[dir];
          if (!s || s.total === 0) return null;
          const wr = s.win_rate ?? 0;
          return (
            <div key={dir} className="flex items-center gap-3">
              <DirectionBadge d={dir} />
              <div className="flex-1">
                <div className="flex justify-between text-[10px] text-gray-500 mb-1">
                  <span>{s.wins}W / {s.total - s.wins}L</span>
                  <span className={cn("font-mono", wr >= 55 ? "text-green-400" : "text-red-400")}>{wr}%</span>
                </div>
                <div className="h-1.5 bg-[#1f2937] rounded-full overflow-hidden">
                  <div className={cn("h-full rounded-full", wr >= 55 ? "bg-green-500" : "bg-red-500")} style={{ width: `${wr}%` }} />
                </div>
              </div>
              {s.avg_pnl != null && (
                <span className={cn("text-[10px] font-mono w-14 text-right", s.avg_pnl >= 0 ? "text-green-400" : "text-red-400")}>
                  {s.avg_pnl >= 0 ? "+" : ""}{s.avg_pnl}%
                </span>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}

// ── Equity curve chart ────────────────────────────────────────────────────────

function EquityCurve({ predictions }: { predictions: SimulationPrediction[] }) {
  const data = useMemo(() => {
    let equity = 100;
    return predictions
      .filter((p) => p.direction !== "neutral")
      .map((p) => {
        equity += p.pnl_pct;
        return { date: p.entry_date.slice(5), equity: +equity.toFixed(2), win: p.outcome === "win" };
      });
  }, [predictions]);

  return (
    <div className="bg-[#111827] border border-[#1f2937] rounded-xl p-4">
      <div className="text-xs font-semibold text-gray-400 mb-3">Cumulative P&L (starting $100)</div>
      <ResponsiveContainer width="100%" height={160}>
        <ComposedChart data={data} margin={{ top: 4, right: 8, left: 0, bottom: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#1a2235" vertical={false} />
          <XAxis dataKey="date" tick={{ fill: "#4b5563", fontSize: 9 }} tickLine={false} axisLine={false}
            interval={Math.max(1, Math.floor(data.length / 8))} />
          <YAxis tick={{ fill: "#4b5563", fontSize: 9 }} tickLine={false} axisLine={false} width={44}
            tickFormatter={(v) => `$${v.toFixed(0)}`} />
          <Tooltip contentStyle={{ background: "#1a2235", border: "1px solid #374151", borderRadius: 8, fontSize: 11 }}
            formatter={(v: number) => [`$${v.toFixed(2)}`, "Equity"]} />
          <ReferenceLine y={100} stroke="#374151" strokeDasharray="3 2" />
          <Line type="monotone" dataKey="equity" stroke="#3b82f6" strokeWidth={2} dot={false} />
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  );
}

// ── World events panel ────────────────────────────────────────────────────────

function WorldEventsPanel({ events }: { events: WorldEvent[] }) {
  const [expanded, setExpanded] = useState<number | null>(null);
  if (!events.length) return null;
  return (
    <div className="bg-[#111827] border border-[#1f2937] rounded-xl p-4">
      <div className="flex items-center gap-2 mb-3">
        <Globe size={14} className="text-blue-400" />
        <span className="text-xs font-semibold text-gray-400">World Events in This Period</span>
        <span className="text-[10px] text-gray-600 bg-[#1f2937] px-2 py-0.5 rounded-full">{events.length}</span>
      </div>
      <div className="space-y-1.5 max-h-72 overflow-y-auto pr-1">
        {events.map((ev, i) => {
          const cfg = IMPACT_CFG[ev.impact] || IMPACT_CFG.volatility;
          return (
            <div key={i} className={cn("border rounded-lg overflow-hidden", cfg.bg)}>
              <button onClick={() => setExpanded(expanded === i ? null : i)}
                className="w-full flex items-center gap-2 px-3 py-2 text-left">
                <span className={cn("w-2 h-2 rounded-full flex-shrink-0", cfg.dot)} />
                <span className={cn("text-[10px] font-medium flex-shrink-0", CAT_COLOR[ev.category] || "text-gray-400")}>{ev.category}</span>
                <span className="text-xs text-gray-300 flex-1 truncate">{ev.title}</span>
                <span className="text-[10px] text-gray-600 flex-shrink-0">{ev.date.slice(0, 7)}</span>
                {expanded === i ? <ChevronUp size={11} className="text-gray-500 flex-shrink-0" /> : <ChevronDown size={11} className="text-gray-500 flex-shrink-0" />}
              </button>
              {expanded === i && (
                <div className="px-3 pb-3">
                  <p className="text-xs text-gray-400 leading-relaxed">{ev.description}</p>
                  <div className={cn("mt-1.5 text-[10px] font-semibold", cfg.color)}>
                    Historical impact: {ev.impact}
                  </div>
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}

// ── Prediction table ──────────────────────────────────────────────────────────

function PredictionTable({ predictions }: { predictions: SimulationPrediction[] }) {
  const [expanded, setExpanded] = useState<number | null>(null);
  const [filter, setFilter] = useState<"all" | "win" | "loss">("all");
  const filtered = predictions.filter((p) => filter === "all" || p.outcome === filter);

  return (
    <div className="bg-[#111827] border border-[#1f2937] rounded-xl p-4">
      <div className="flex items-center gap-3 mb-3">
        <span className="text-xs font-semibold text-gray-400">Prediction Log</span>
        <div className="flex gap-1 bg-[#1f2937] rounded-lg p-0.5">
          {(["all", "win", "loss"] as const).map((f) => (
            <button key={f} onClick={() => setFilter(f)}
              className={cn("text-[10px] px-2.5 py-1 rounded-md font-medium capitalize transition-colors",
                filter === f ? "bg-blue-600 text-white" : "text-gray-500 hover:text-gray-300")}>
              {f}
            </button>
          ))}
        </div>
        <span className="text-[10px] text-gray-600 ml-auto">{filtered.length} entries</span>
      </div>
      <div className="space-y-1 max-h-96 overflow-y-auto pr-1">
        {filtered.slice(0, 100).map((p, i) => (
          <div key={i} className="border border-[#1f2937] rounded-lg overflow-hidden">
            <button onClick={() => setExpanded(expanded === i ? null : i)}
              className="w-full flex items-center gap-2 px-3 py-2 hover:bg-[#1f2937]/50 transition-colors text-left">
              <DirectionBadge d={p.direction} />
              <span className="text-[10px] text-gray-500 w-20 flex-shrink-0">{p.entry_date.slice(0, 10)}</span>
              <span className="text-xs font-mono text-gray-300 flex-shrink-0">{fmtPrice(p.entry_price)}</span>
              <span className="text-[10px] text-gray-600 flex-shrink-0">→</span>
              <span className="text-xs font-mono text-gray-300 flex-shrink-0">{fmtPrice(p.exit_price)}</span>
              <span className={cn("text-xs font-mono font-semibold flex-shrink-0 w-14 text-right",
                p.actual_move_pct >= 0 ? "text-green-400" : "text-red-400")}>
                {p.actual_move_pct >= 0 ? "+" : ""}{p.actual_move_pct.toFixed(1)}%
              </span>
              <div className="flex-1" />
              {p.outcome === "win"
                ? <CheckCircle size={13} className="text-green-400 flex-shrink-0" />
                : <XCircle size={13} className="text-red-400 flex-shrink-0" />}
              {expanded === i ? <ChevronUp size={11} className="text-gray-500" /> : <ChevronDown size={11} className="text-gray-500" />}
            </button>
            {expanded === i && (
              <div className="px-3 pb-3 border-t border-[#1f2937] bg-[#0d1117]/40 pt-2 space-y-1">
                {p.rationale.map((r, j) => (
                  <div key={j} className="text-xs text-gray-400 flex gap-1.5">
                    <span className="text-blue-500">›</span>{r}
                  </div>
                ))}
                <div className="flex flex-wrap gap-3 text-[10px] text-gray-600 mt-1.5">
                  {p.rsi != null && <span>RSI {p.rsi}</span>}
                  {p.sma20 != null && <span>SMA20 {fmtPrice(p.sma20)}</span>}
                  <span>Confidence {Math.round(p.confidence * 100)}%</span>
                  {p.regime && (
                    <span className={cn("px-1.5 py-0.5 rounded text-[9px] font-medium",
                      p.regime === "trending_up" ? "bg-green-900/30 text-green-400" :
                      p.regime === "trending_down" ? "bg-red-900/30 text-red-400" :
                      p.regime === "volatile" ? "bg-yellow-900/30 text-yellow-400" :
                      "bg-blue-900/30 text-blue-400")}>
                      {p.regime.replace("_", " ")}
                    </span>
                  )}
                  {p.mtf_aligned != null && (
                    <span className={cn("px-1.5 py-0.5 rounded text-[9px]",
                      p.mtf_aligned ? "bg-cyan-900/30 text-cyan-400" : "bg-gray-900/30 text-gray-500")}>
                      MTF {p.mtf_aligned ? "aligned" : "unaligned"}
                    </span>
                  )}
                </div>
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}

// ── Main page ─────────────────────────────────────────────────────────────────

const QUICK = ["AAPL", "TSLA", "NVDA", "SPY", "MSFT", "AMZN"];
const YEAR_OPTS = [1, 2, 3, 5, 10, 20, 30];

export default function SimulatePage() {
  const [symbol, setSymbol] = useState("AAPL");
  const [input, setInput] = useState("AAPL");
  const [years, setYears] = useState(5);
  const [horizon, setHorizon] = useState(20);
  const [result, setResult] = useState<SimulationResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const run = useCallback(async (sym: string, yr: number, hz: number) => {
    const s = sym.trim().toUpperCase();
    if (!s) return;
    setLoading(true);
    setError(null);
    setSymbol(s);
    try {
      const res = await api.simulate(s, yr, hz);
      setResult(res);
    } catch (e: any) {
      setError(e.message || "Simulation failed");
    } finally {
      setLoading(false);
    }
  }, []);

  return (
    <div className="flex flex-col h-full bg-[#0a0e1a] overflow-auto">
      {/* Header */}
      <div className="flex items-center gap-3 px-5 py-3 border-b border-[#1f2937] bg-[#111827] flex-shrink-0">
        <BarChart2 size={16} className="text-blue-400" />
        <span className="text-sm font-semibold text-white">Historical Simulation</span>
        <span className="text-[10px] text-gray-600 bg-[#1f2937] px-2 py-0.5 rounded-full">Nexus predictions vs actual outcomes</span>
        <div className="flex-1" />
        {loading && <RefreshCw size={13} className="animate-spin text-blue-400" />}
      </div>

      {/* Config bar */}
      <div className="flex items-center gap-3 px-5 py-3 border-b border-[#1f2937] bg-[#0d1117] flex-wrap flex-shrink-0">
        {/* Symbol */}
        <form onSubmit={(e) => { e.preventDefault(); run(input, years, horizon); }} className="flex items-center gap-2">
          <input value={input} onChange={(e) => setInput(e.target.value.toUpperCase())}
            placeholder="Symbol…"
            className="bg-[#1f2937] border border-[#374151] rounded-lg px-3 py-1.5 text-sm text-white placeholder-gray-600 w-24 focus:outline-none focus:border-blue-500" />
          <button type="submit" disabled={loading}
            className="bg-blue-600 hover:bg-blue-500 disabled:opacity-50 text-white text-xs px-3 py-1.5 rounded-lg transition-colors flex items-center gap-1.5">
            <Play size={11} /> Run
          </button>
        </form>

        {/* Quick symbols */}
        <div className="flex gap-1">
          {QUICK.map((s) => (
            <button key={s} onClick={() => { setInput(s); run(s, years, horizon); }}
              className={cn("text-[10px] px-2 py-1 rounded font-mono transition-colors border",
                symbol === s ? "bg-blue-600/20 text-blue-400 border-blue-600/30" : "text-gray-500 border-[#374151] hover:text-gray-300 hover:bg-[#1f2937]")}>
              {s}
            </button>
          ))}
        </div>

        <div className="w-px h-4 bg-[#374151]" />

        {/* Years */}
        <div className="flex items-center gap-2">
          <span className="text-[10px] text-gray-500">History:</span>
          <div className="flex gap-1">
            {YEAR_OPTS.map((y) => (
              <button key={y} onClick={() => setYears(y)}
                className={cn("text-[10px] px-2 py-1 rounded font-mono transition-colors",
                  years === y ? "bg-blue-600 text-white" : "text-gray-500 hover:text-gray-300 hover:bg-[#1f2937]")}>
                {y}Y
              </button>
            ))}
          </div>
        </div>

        <div className="w-px h-4 bg-[#374151]" />

        {/* Horizon */}
        <div className="flex items-center gap-2">
          <span className="text-[10px] text-gray-500">Horizon:</span>
          {[10, 20, 30].map((h) => (
            <button key={h} onClick={() => setHorizon(h)}
              className={cn("text-[10px] px-2 py-1 rounded font-mono transition-colors",
                horizon === h ? "bg-blue-600 text-white" : "text-gray-500 hover:text-gray-300 hover:bg-[#1f2937]")}>
              {h}d
            </button>
          ))}
        </div>
      </div>

      {/* Content */}
      <div className="flex-1 overflow-auto p-5 space-y-5">
        {!result && !loading && !error && (
          <div className="flex flex-col items-center justify-center h-64 text-center gap-4">
            <BarChart2 size={40} className="text-gray-700" />
            <div className="text-gray-500 text-sm">Select a symbol and click Run to replay Nexus predictions against history</div>
            <button onClick={() => run("AAPL", years, horizon)}
              className="bg-blue-600 hover:bg-blue-500 text-white text-sm px-5 py-2 rounded-lg transition-colors flex items-center gap-2">
              <Play size={13} /> Try AAPL {years}Y
            </button>
          </div>
        )}

        {error && (
          <div className="flex items-center gap-2 bg-red-900/20 border border-red-800/40 rounded-xl px-4 py-3 text-sm text-red-400">
            <AlertTriangle size={14} /> {error}
          </div>
        )}

        {loading && (
          <div className="flex flex-col items-center justify-center h-64 gap-3 text-gray-500">
            <RefreshCw size={28} className="animate-spin text-blue-500" />
            <span className="text-sm">Replaying {symbol} history…</span>
          </div>
        )}

        {result && !loading && (
          <>
            <div className="flex items-center gap-2 flex-wrap">
              <span className="text-lg font-bold text-white font-mono">{result.symbol}</span>
              <span className="text-sm text-gray-500">{result.date_range.start} → {result.date_range.end}</span>
              <span className="text-[10px] text-gray-600 bg-[#1f2937] px-2 py-0.5 rounded-full">{result.horizon_days}-day prediction window</span>
              {result.using_learned_weights && (
                <span className="text-[10px] text-cyan-400 bg-cyan-900/20 border border-cyan-800/30 px-2 py-0.5 rounded-full flex items-center gap-1">
                  <Zap size={9} /> Optimized weights active
                </span>
              )}
            </div>

            <AccuracySummary result={result} />

            <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
              <DirectionBreakdown byDir={result.by_direction} />
              <EquityCurve predictions={result.predictions} />
            </div>

            {/* New intelligence panels */}
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
              <RegimePanel result={result} />
              <MTFPanel result={result} />
            </div>

            <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
              <CalibrationPanel result={result} />
              <SignalRadar result={result} />
            </div>

            <LearningPanel result={result} />

            <WorldEventsPanel events={result.events} />
            <PredictionTable predictions={result.predictions} />

            <div className="flex items-start gap-2 bg-yellow-900/10 border border-yellow-800/20 rounded-xl p-3 text-xs text-yellow-700">
              <AlertTriangle size={12} className="flex-shrink-0 mt-0.5" />
              Simulated results use simplified technical signals and do not account for slippage, commissions, or real options pricing. Past simulated accuracy does not predict future results.
            </div>
          </>
        )}
      </div>
    </div>
  );
}
