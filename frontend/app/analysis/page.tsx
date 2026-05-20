"use client";

import { useState, useCallback, useMemo, useEffect, Suspense } from "react";
import { useSearchParams } from "next/navigation";
import {
  Play, RefreshCw, AlertTriangle, TrendingUp, TrendingDown, Minus,
  Globe, ChevronDown, ChevronUp, BrainCircuit, CheckCircle, XCircle,
  Clock, Zap, BarChart2, Activity, Target, BookOpen,
} from "lucide-react";
import {
  ComposedChart, AreaChart, Area, Bar, Line, XAxis, YAxis,
  CartesianGrid, Tooltip, ResponsiveContainer, ReferenceLine, Cell,
} from "recharts";
import {
  api,
  type SimulationResult,
  type SimulationPrediction,
  type WorldEvent,
  type PredictionHistoryResponse,
  type SignalStat,
  type UnifiedAnalysisResponse,
} from "@/lib/api";
import { cn, fmtPrice } from "@/lib/utils";

// ── constants ─────────────────────────────────────────────────────────────────

const QUICK = ["AAPL", "TSLA", "NVDA", "SPY", "MSFT", "AMZN", "QQQ", "META", "GOOGL"];
const YEAR_OPTS = [1, 2, 3, 5, 10, 20];
const HORIZON_OPTS = [10, 20, 30, 45];

const IMPACT_CFG = {
  bullish:    { dot: "bg-green-400",  color: "text-green-400",  border: "border-green-800/30",  bg: "bg-green-900/10"  },
  bearish:    { dot: "bg-red-400",    color: "text-red-400",    border: "border-red-800/30",    bg: "bg-red-900/10"    },
  volatility: { dot: "bg-yellow-400", color: "text-yellow-400", border: "border-yellow-800/30", bg: "bg-yellow-900/10" },
} as const;

const CAT_COLOR: Record<string, string> = {
  geopolitical: "text-red-400",
  macro:        "text-purple-400",
  weather:      "text-cyan-400",
  social:       "text-pink-400",
  regulatory:   "text-orange-400",
  pandemic:     "text-rose-400",
};

const SIGNAL_LABELS: Record<string, string> = {
  rsi_oversold:    "RSI Oversold → CALL",
  rsi_overbought:  "RSI Overbought → PUT",
  macd_bullish:    "MACD Bullish → CALL",
  macd_bearish:    "MACD Bearish → PUT",
  bb_lower:        "BB Lower Band → CALL",
  bb_upper:        "BB Upper Band → PUT",
  high_volume:     "High Volume Confirm",
};

// ── small shared components ───────────────────────────────────────────────────

function DirBadge({ d }: { d: string }) {
  if (d === "call") return (
    <span className="inline-flex items-center gap-1 text-[10px] px-2 py-0.5 rounded-full bg-green-900/20 border border-green-800/30 text-green-400 font-semibold">
      <TrendingUp size={9} />CALL
    </span>
  );
  if (d === "put") return (
    <span className="inline-flex items-center gap-1 text-[10px] px-2 py-0.5 rounded-full bg-red-900/20 border border-red-800/30 text-red-400 font-semibold">
      <TrendingDown size={9} />PUT
    </span>
  );
  return (
    <span className="inline-flex items-center gap-1 text-[10px] px-2 py-0.5 rounded-full bg-gray-900/20 border border-gray-800/30 text-gray-400 font-semibold">
      <Minus size={9} />NEUTRAL
    </span>
  );
}

function StatCard({ label, value, color = "text-white", sub }: {
  label: string; value: string | number; color?: string; sub?: string;
}) {
  return (
    <div className="bg-[#111827] border border-[#1f2937] rounded-xl p-4 text-center">
      <div className="text-[10px] text-gray-600 uppercase tracking-wide mb-1">{label}</div>
      <div className={cn("text-2xl font-bold font-mono", color)}>{value}</div>
      {sub && <div className="text-[10px] text-gray-600 mt-0.5">{sub}</div>}
    </div>
  );
}

function SectionHeader({ icon: Icon, title, badge }: {
  icon: React.ElementType; title: string; badge?: string | number;
}) {
  return (
    <div className="flex items-center gap-2 mb-3">
      <Icon size={14} className="text-blue-400 flex-shrink-0" />
      <span className="text-xs font-semibold text-gray-300">{title}</span>
      {badge != null && (
        <span className="text-[10px] text-gray-600 bg-[#1f2937] px-2 py-0.5 rounded-full ml-auto">{badge}</span>
      )}
    </div>
  );
}

// ── AccuracySummary ───────────────────────────────────────────────────────────

function AccuracySummary({ sim, live }: { sim: SimulationResult; live: PredictionHistoryResponse }) {
  const wr = sim.win_rate ?? 0;
  const liveWr = live.performance.win_rate;
  return (
    <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-8 gap-3">
      <div className="col-span-2 sm:col-span-2 lg:col-span-2">
        <StatCard label="Sim Win Rate" value={wr != null ? `${wr}%` : "—"}
          color={wr >= 55 ? "text-green-400" : wr >= 45 ? "text-yellow-400" : "text-red-400"}
          sub={`${sim.total_predictions} trades`} />
      </div>
      <div className="col-span-2 sm:col-span-2 lg:col-span-2">
        <StatCard label="Live Win Rate" value={liveWr != null ? `${liveWr}%` : "—"}
          color={liveWr != null ? (liveWr >= 55 ? "text-green-400" : liveWr >= 45 ? "text-yellow-400" : "text-red-400") : "text-gray-600"}
          sub={`${live.performance.total} completed`} />
      </div>
      <div className="col-span-1 lg:col-span-2">
        <StatCard label="Avg P&L" value={sim.avg_pnl_pct != null ? `${sim.avg_pnl_pct > 0 ? "+" : ""}${sim.avg_pnl_pct}%` : "—"}
          color={(sim.avg_pnl_pct ?? 0) >= 0 ? "text-green-400" : "text-red-400"} />
      </div>
      <div className="col-span-1 lg:col-span-2">
        <StatCard label="World Events" value={sim.events.length} color="text-blue-400"
          sub={`${sim.date_range.start?.slice(0,4)}–${sim.date_range.end?.slice(0,4)}`} />
      </div>
    </div>
  );
}

// ── Direction breakdown ───────────────────────────────────────────────────────

function DirBreakdown({ byDir, title }: {
  byDir: SimulationResult["by_direction"] | PredictionHistoryResponse["performance"]["by_direction"];
  title: string;
}) {
  return (
    <div className="bg-[#111827] border border-[#1f2937] rounded-xl p-4">
      <div className="text-xs font-semibold text-gray-400 mb-3">{title}</div>
      <div className="space-y-3">
        {(["call", "put", "neutral"] as const).map((dir) => {
          const s = byDir[dir];
          if (!s || s.total === 0) return null;
          const wr = s.win_rate ?? 0;
          const lf = (s as any).learning_factor;
          return (
            <div key={dir} className="flex items-center gap-3">
              <DirBadge d={dir} />
              <div className="flex-1">
                <div className="flex justify-between text-[10px] text-gray-500 mb-1">
                  <span>{s.wins}W / {s.total - s.wins}L</span>
                  <span className={cn("font-mono", wr >= 55 ? "text-green-400" : wr >= 45 ? "text-yellow-400" : "text-red-400")}>{wr}%</span>
                </div>
                <div className="h-1.5 bg-[#1f2937] rounded-full overflow-hidden">
                  <div className={cn("h-full rounded-full transition-all", wr >= 55 ? "bg-green-500" : wr >= 45 ? "bg-yellow-500" : "bg-red-500")}
                    style={{ width: `${wr}%` }} />
                </div>
              </div>
              {(s as any).avg_pnl != null && (
                <span className={cn("text-[10px] font-mono w-14 text-right flex-shrink-0",
                  (s as any).avg_pnl >= 0 ? "text-green-400" : "text-red-400")}>
                  {(s as any).avg_pnl >= 0 ? "+" : ""}{(s as any).avg_pnl}%
                </span>
              )}
              {lf != null && lf !== 1.0 && (
                <span className={cn("text-[10px] font-mono flex-shrink-0", lf > 1 ? "text-green-400" : "text-red-400")}>
                  ×{lf}
                </span>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}

// ── Equity curve ──────────────────────────────────────────────────────────────

function EquityCurve({ predictions }: { predictions: SimulationPrediction[] }) {
  const data = useMemo(() => {
    let equity = 100;
    return predictions
      .filter(p => p.direction !== "neutral")
      .map(p => {
        equity += p.pnl_pct;
        return {
          date: p.entry_date.slice(5),
          equity: +equity.toFixed(2),
          win: p.outcome === "win",
        };
      });
  }, [predictions]);

  const final = data[data.length - 1]?.equity ?? 100;
  const isUp = final >= 100;

  return (
    <div className="bg-[#111827] border border-[#1f2937] rounded-xl p-4">
      <div className="flex items-center justify-between mb-3">
        <span className="text-xs font-semibold text-gray-400">Cumulative P&L</span>
        <span className={cn("text-sm font-bold font-mono", isUp ? "text-green-400" : "text-red-400")}>
          ${final.toFixed(2)} <span className="text-[10px] text-gray-600">from $100</span>
        </span>
      </div>
      <ResponsiveContainer width="100%" height={160}>
        <AreaChart data={data} margin={{ top: 4, right: 8, left: 0, bottom: 0 }}>
          <defs>
            <linearGradient id="eqGrad" x1="0" y1="0" x2="0" y2="1">
              <stop offset="5%" stopColor={isUp ? "#22c55e" : "#ef4444"} stopOpacity={0.3} />
              <stop offset="95%" stopColor={isUp ? "#22c55e" : "#ef4444"} stopOpacity={0} />
            </linearGradient>
          </defs>
          <CartesianGrid strokeDasharray="3 3" stroke="#1a2235" vertical={false} />
          <XAxis dataKey="date" tick={{ fill: "#4b5563", fontSize: 9 }} tickLine={false} axisLine={false}
            interval={Math.max(1, Math.floor(data.length / 8))} />
          <YAxis tick={{ fill: "#4b5563", fontSize: 9 }} tickLine={false} axisLine={false} width={44}
            tickFormatter={(v: number) => `$${v.toFixed(0)}`} />
          <Tooltip contentStyle={{ background: "#1a2235", border: "1px solid #374151", borderRadius: 8, fontSize: 11 }}
            formatter={(v: number) => [`$${v.toFixed(2)}`, "Equity"]} />
          <ReferenceLine y={100} stroke="#374151" strokeDasharray="3 2" />
          <Area type="monotone" dataKey="equity" stroke={isUp ? "#22c55e" : "#ef4444"}
            strokeWidth={2} fill="url(#eqGrad)" dot={false} />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}

// ── Signal quality heatmap ────────────────────────────────────────────────────

function SignalHeatmap({ stats }: { stats: Record<string, SignalStat> }) {
  const rows = Object.entries(stats)
    .filter(([, s]) => s.total > 0)
    .sort(([, a], [, b]) => (b.win_rate ?? 0) - (a.win_rate ?? 0));

  if (!rows.length) return null;

  return (
    <div className="bg-[#111827] border border-[#1f2937] rounded-xl p-4">
      <SectionHeader icon={Activity} title="Signal Quality Breakdown" />
      <div className="space-y-2">
        {rows.map(([key, s]) => {
          const wr = s.win_rate ?? 0;
          const barColor = wr >= 60 ? "bg-green-500" : wr >= 50 ? "bg-yellow-500" : "bg-red-500";
          return (
            <div key={key} className="flex items-center gap-3">
              <span className="text-[10px] text-gray-400 w-44 flex-shrink-0">{SIGNAL_LABELS[key] ?? key}</span>
              <div className="flex-1 h-2 bg-[#1f2937] rounded-full overflow-hidden">
                <div className={cn("h-full rounded-full", barColor)} style={{ width: `${wr}%` }} />
              </div>
              <span className={cn("text-[10px] font-mono w-10 text-right flex-shrink-0",
                wr >= 60 ? "text-green-400" : wr >= 50 ? "text-yellow-400" : "text-red-400")}>
                {wr}%
              </span>
              <span className="text-[10px] text-gray-600 w-12 text-right flex-shrink-0">{s.total} trades</span>
            </div>
          );
        })}
      </div>
    </div>
  );
}

// ── World events panel ────────────────────────────────────────────────────────

function WorldEventsPanel({ events }: { events: WorldEvent[] }) {
  const [expanded, setExpanded] = useState<number | null>(null);

  if (!events.length) return (
    <div className="flex flex-col items-center justify-center py-12 text-center">
      <Globe size={32} className="text-gray-700 mb-3" />
      <div className="text-gray-500 text-sm">No world events found for this period</div>
    </div>
  );

  return (
    <div className="space-y-1.5 max-h-[520px] overflow-y-auto pr-1">
      {events.map((ev, i) => {
        const cfg = IMPACT_CFG[ev.impact] ?? IMPACT_CFG.volatility;
        return (
          <div key={i} className={cn("border rounded-lg overflow-hidden", cfg.border, cfg.bg)}>
            <button onClick={() => setExpanded(expanded === i ? null : i)}
              className="w-full flex items-center gap-2 px-3 py-2.5 text-left">
              <span className={cn("w-2 h-2 rounded-full flex-shrink-0", cfg.dot)} />
              <span className={cn("text-[10px] font-semibold uppercase tracking-wide flex-shrink-0 w-20",
                CAT_COLOR[ev.category] ?? "text-gray-400")}>{ev.category}</span>
              <span className="text-xs text-gray-200 flex-1 truncate font-medium">{ev.title}</span>
              <span className="text-[10px] text-gray-500 flex-shrink-0">{ev.date.slice(0, 7)}</span>
              <span className={cn("text-[10px] font-semibold flex-shrink-0 w-16 text-right", cfg.color)}>
                {ev.impact}
              </span>
              {expanded === i
                ? <ChevronUp size={11} className="text-gray-500 flex-shrink-0" />
                : <ChevronDown size={11} className="text-gray-500 flex-shrink-0" />}
            </button>
            {expanded === i && (
              <div className="px-4 pb-3 pt-1 border-t border-white/5">
                <p className="text-xs text-gray-400 leading-relaxed">{ev.description}</p>
                <div className="flex gap-3 mt-2 text-[10px] text-gray-600">
                  <span>{ev.date} → {ev.end_date}</span>
                </div>
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}

// ── Prediction log ────────────────────────────────────────────────────────────

function PredictionLog({ predictions }: { predictions: SimulationPrediction[] }) {
  const [expanded, setExpanded] = useState<number | null>(null);
  const [filter, setFilter] = useState<"all" | "win" | "loss" | "call" | "put">("all");

  const filtered = useMemo(() => predictions.filter(p => {
    if (filter === "win") return p.outcome === "win";
    if (filter === "loss") return p.outcome === "loss";
    if (filter === "call") return p.direction === "call";
    if (filter === "put") return p.direction === "put";
    return true;
  }), [predictions, filter]);

  return (
    <div className="bg-[#111827] border border-[#1f2937] rounded-xl p-4">
      <div className="flex items-center gap-3 mb-3 flex-wrap">
        <span className="text-xs font-semibold text-gray-400">Simulation Log</span>
        <div className="flex gap-1 bg-[#1f2937] rounded-lg p-0.5">
          {(["all", "win", "loss", "call", "put"] as const).map(f => (
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
        {filtered.slice(0, 150).map((p, i) => (
          <div key={i} className="border border-[#1f2937] rounded-lg overflow-hidden">
            <button onClick={() => setExpanded(expanded === i ? null : i)}
              className="w-full flex items-center gap-2 px-3 py-2 hover:bg-[#1f2937]/50 transition-colors text-left">
              <DirBadge d={p.direction} />
              <span className="text-[10px] text-gray-500 w-20 flex-shrink-0">{p.entry_date.slice(0, 10)}</span>
              <span className="text-xs font-mono text-gray-300 flex-shrink-0">{fmtPrice(p.entry_price)}</span>
              <span className="text-[10px] text-gray-600 flex-shrink-0">→</span>
              <span className="text-xs font-mono text-gray-300 flex-shrink-0">{fmtPrice(p.exit_price)}</span>
              <span className={cn("text-xs font-mono font-semibold flex-shrink-0 w-14 text-right",
                p.actual_move_pct >= 0 ? "text-green-400" : "text-red-400")}>
                {p.actual_move_pct >= 0 ? "+" : ""}{p.actual_move_pct.toFixed(1)}%
              </span>
              <div className="flex-1" />
              {p.learning_factor != null && p.learning_factor !== 1.0 && (
                <span className={cn("text-[10px] font-mono flex-shrink-0",
                  p.learning_factor > 1 ? "text-green-500" : "text-red-500")}>
                  ×{p.learning_factor}
                </span>
              )}
              {p.outcome === "win"
                ? <CheckCircle size={13} className="text-green-400 flex-shrink-0" />
                : <XCircle size={13} className="text-red-400 flex-shrink-0" />}
              {expanded === i
                ? <ChevronUp size={11} className="text-gray-500 flex-shrink-0" />
                : <ChevronDown size={11} className="text-gray-500 flex-shrink-0" />}
            </button>
            {expanded === i && (
              <div className="px-3 pb-3 border-t border-[#1f2937] bg-[#0d1117]/40 pt-2 space-y-1.5">
                {p.rationale.map((r, j) => (
                  <div key={j} className="text-xs text-gray-400 flex gap-1.5">
                    <span className="text-blue-500 flex-shrink-0">›</span>{r}
                  </div>
                ))}
                <div className="flex flex-wrap gap-3 text-[10px] text-gray-600 mt-1 pt-1 border-t border-[#1f2937]">
                  {p.rsi != null && <span>RSI {p.rsi}</span>}
                  {p.sma20 != null && <span>SMA20 {fmtPrice(p.sma20)}</span>}
                  {p.macd != null && <span>MACD {p.macd.toFixed(3)}</span>}
                  {p.bb_pct_b != null && <span>%B {p.bb_pct_b.toFixed(2)}</span>}
                  {p.vol_ratio != null && <span>Vol {p.vol_ratio}×</span>}
                  <span>Conf {Math.round(p.confidence * 100)}%</span>
                  {p.bullish_score != null && <span className="text-green-600">Bull {p.bullish_score}</span>}
                  {p.bearish_score != null && <span className="text-red-600">Bear {p.bearish_score}</span>}
                </div>
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}

// ── Live predictions panel ────────────────────────────────────────────────────

function LivePredictionsPanel({ data }: { data: PredictionHistoryResponse }) {
  const [expanded, setExpanded] = useState<number | null>(null);
  const perf = data.performance;
  const wr = perf.win_rate ?? 0;

  return (
    <div className="space-y-4">
      {/* Stats row */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <StatCard label="Completed" value={perf.total} color="text-white" />
        <StatCard label="Win Rate" value={perf.total > 0 ? `${wr}%` : "—"}
          color={perf.total > 0 ? (wr >= 55 ? "text-green-400" : wr >= 45 ? "text-yellow-400" : "text-red-400") : "text-gray-600"} />
        <StatCard label="Wins" value={perf.wins} color="text-green-400" />
        <StatCard label="Pending" value={perf.pending} color="text-yellow-400" />
      </div>

      {/* Direction breakdown */}
      <DirBreakdown byDir={perf.by_direction} title="Live Accuracy by Direction" />

      {/* Prediction list */}
      {data.predictions.length > 0 ? (
        <div className="bg-[#111827] border border-[#1f2937] rounded-xl p-4">
          <SectionHeader icon={Target} title="Live Prediction History" badge={data.predictions.length} />
          <div className="space-y-1.5 max-h-96 overflow-y-auto pr-1">
            {data.predictions.map((p, i) => (
              <div key={i} className="border border-[#1f2937] rounded-lg overflow-hidden">
                <button onClick={() => setExpanded(expanded === i ? null : i)}
                  className="w-full flex items-center gap-2 px-3 py-2 hover:bg-[#1f2937]/50 transition-colors text-left">
                  <DirBadge d={p.direction} />
                  <span className="text-[10px] text-gray-500 w-20 flex-shrink-0">{p.created_at.slice(0, 10)}</span>
                  <span className="text-xs font-mono text-gray-300 flex-shrink-0">{fmtPrice(p.entry_price)}</span>
                  <div className="flex-1" />
                  <span className={cn("text-[10px] font-semibold px-2 py-0.5 rounded flex-shrink-0",
                    p.outcome_status === "win"  ? "text-green-400 bg-green-900/20" :
                    p.outcome_status === "loss" ? "text-red-400 bg-red-900/20" :
                    p.outcome_status === "pending" ? "text-yellow-400 bg-yellow-900/20" :
                    "text-gray-500 bg-gray-900/20")}>
                    {p.outcome_status}
                  </span>
                  {p.pnl_pct != null && (
                    <span className={cn("text-[10px] font-mono w-12 text-right flex-shrink-0",
                      p.pnl_pct >= 0 ? "text-green-400" : "text-red-400")}>
                      {p.pnl_pct >= 0 ? "+" : ""}{p.pnl_pct.toFixed(1)}%
                    </span>
                  )}
                  {expanded === i
                    ? <ChevronUp size={11} className="text-gray-500 flex-shrink-0" />
                    : <ChevronDown size={11} className="text-gray-500 flex-shrink-0" />}
                </button>
                {expanded === i && (
                  <div className="px-3 pb-3 border-t border-[#1f2937] bg-[#0d1117]/40 pt-2 space-y-1">
                    {p.rationale.map((r, j) => (
                      <div key={j} className="text-xs text-gray-400 flex gap-1.5">
                        <span className="text-blue-500 flex-shrink-0">›</span>{r}
                      </div>
                    ))}
                    {p.mistake_notes && p.mistake_notes.length > 0 && (
                      <div className="mt-2 pt-2 border-t border-[#1f2937] space-y-1">
                        {p.mistake_notes.map((n, j) => (
                          <div key={j} className="text-xs text-red-400/70 flex gap-1.5">
                            <span className="text-red-600 flex-shrink-0">!</span>{n}
                          </div>
                        ))}
                      </div>
                    )}
                    <div className="flex gap-3 text-[10px] text-gray-600 mt-1">
                      {p.target_price && <span>Target {fmtPrice(p.target_price)}</span>}
                      {p.stop_loss && <span>Stop {fmtPrice(p.stop_loss)}</span>}
                      <span>Conf {Math.round(p.confidence * 100)}%</span>
                    </div>
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
      ) : (
        <div className="flex flex-col items-center justify-center py-12 text-center bg-[#111827] border border-[#1f2937] rounded-xl">
          <Clock size={32} className="text-gray-700 mb-3" />
          <div className="text-gray-500 text-sm">No live predictions yet for this symbol</div>
          <div className="text-gray-600 text-xs mt-1">Run an analysis on the Console to generate live predictions</div>
        </div>
      )}
    </div>
  );
}

// ── Nexus Insight panel ───────────────────────────────────────────────────────

function NexusInsight({ sim, live }: { sim: SimulationResult; live: PredictionHistoryResponse }) {
  const wr = sim.win_rate ?? 0;
  const liveWr = live.performance.win_rate;
  const liveTotal = live.performance.total;

  const bestDir = Object.entries(sim.by_direction)
    .filter(([, s]) => s.total >= 5)
    .sort(([, a], [, b]) => (b.win_rate ?? 0) - (a.win_rate ?? 0))[0];

  const worstDir = Object.entries(sim.by_direction)
    .filter(([, s]) => s.total >= 5)
    .sort(([, a], [, b]) => (a.win_rate ?? 0) - (b.win_rate ?? 0))[0];

  const bestSignal = sim.signal_stats
    ? Object.entries(sim.signal_stats)
        .filter(([, s]) => s.total >= 5)
        .sort(([, a], [, b]) => (b.win_rate ?? 0) - (a.win_rate ?? 0))[0]
    : null;

  const bearishEvent = sim.events.find(e => e.impact === "bearish");
  const bullishEvent = sim.events.find(e => e.impact === "bullish");

  const lf = sim.learning_factors;
  const learningActive = lf && Object.values(lf).some(v => v !== 1.0);

  return (
    <div className="bg-blue-900/10 border border-blue-800/30 rounded-xl p-4 space-y-3">
      <div className="flex items-center gap-2">
        <Zap size={14} className="text-blue-400" />
        <span className="text-xs font-semibold text-gray-200">Nexus Analysis</span>
        {learningActive && (
          <span className="text-[10px] text-cyan-400 bg-cyan-900/20 border border-cyan-800/30 px-2 py-0.5 rounded-full ml-auto">
            Adaptive learning active
          </span>
        )}
      </div>
      <div className="space-y-2 text-xs text-gray-400 leading-relaxed">
        <p>
          Over {sim.date_range.start?.slice(0,4)}–{sim.date_range.end?.slice(0,4)}, Nexus achieved a{" "}
          <strong className={cn(wr >= 55 ? "text-green-400" : wr >= 45 ? "text-yellow-400" : "text-red-400")}>{wr}% win rate</strong>{" "}
          across {sim.total_predictions} simulated {sim.horizon_days}-day trades.
          {wr >= 60 && " Signals were well-aligned with actual price action."}
          {wr < 45 && " Signals underperformed — likely due to trending conditions that overwhelmed mean-reversion logic."}
          {wr >= 45 && wr < 60 && " Performance was moderate — signals had edge but not consistently."}
        </p>

        {bestDir && (
          <p>
            Strongest direction: <strong className="text-white">{bestDir[0].toUpperCase()}</strong> at{" "}
            <strong className={cn((bestDir[1].win_rate ?? 0) >= 55 ? "text-green-400" : "text-yellow-400")}>
              {bestDir[1].win_rate}%
            </strong>{" "}
            win rate ({bestDir[1].total} trades).
            {(bestDir[1].win_rate ?? 0) >= 65 && " Strong signal alignment — this direction has the most reliable edge."}
          </p>
        )}

        {worstDir && worstDir[0] !== bestDir?.[0] && (worstDir[1].win_rate ?? 100) < 45 && (
          <p>
            Weakest direction: <strong className="text-white">{worstDir[0].toUpperCase()}</strong> at{" "}
            <strong className="text-red-400">{worstDir[1].win_rate}%</strong> — signals here are unreliable in this period.
          </p>
        )}

        {bestSignal && (bestSignal[1].win_rate ?? 0) >= 60 && (
          <p>
            Best signal: <strong className="text-cyan-400">{SIGNAL_LABELS[bestSignal[0]] ?? bestSignal[0]}</strong>{" "}
            hit <strong className="text-green-400">{bestSignal[1].win_rate}%</strong> win rate over {bestSignal[1].total} occurrences.
          </p>
        )}

        {bearishEvent && (
          <p>
            Notable headwind: <strong className="text-red-400">{bearishEvent.title}</strong> ({bearishEvent.date.slice(0, 7)}) —{" "}
            {bearishEvent.description.slice(0, 110)}{bearishEvent.description.length > 110 ? "…" : ""}
          </p>
        )}

        {bullishEvent && (
          <p>
            Notable tailwind: <strong className="text-green-400">{bullishEvent.title}</strong> ({bullishEvent.date.slice(0, 7)}) —{" "}
            {bullishEvent.description.slice(0, 110)}{bullishEvent.description.length > 110 ? "…" : ""}
          </p>
        )}

        {liveTotal > 0 && liveWr != null ? (
          <p>
            Live track record: <strong className={cn(liveWr >= 55 ? "text-green-400" : liveWr >= 45 ? "text-yellow-400" : "text-red-400")}>
              {liveWr}%
            </strong>{" "}
            win rate on {liveTotal} completed predictions.
            {Math.abs(wr - liveWr) > 12 && (
              " There is a notable gap between simulated and live accuracy — live market conditions may differ from the historical period."
            )}
            {Math.abs(wr - liveWr) <= 5 && " Live accuracy closely tracks the simulation — a good sign of signal consistency."}
          </p>
        ) : (
          <p className="text-gray-600">No live predictions completed yet — run an analysis on the Console to start building a live track record.</p>
        )}

        {learningActive && lf && (
          <p>
            Adaptive learning is adjusting confidence:{" "}
            {Object.entries(lf).filter(([, v]) => v !== 1.0).map(([dir, v]) => (
              <span key={dir} className={cn("font-semibold", v > 1 ? "text-green-400" : "text-red-400")}>
                {dir} ×{v}{" "}
              </span>
            ))}.
            These multipliers are derived from live prediction outcomes.
          </p>
        )}
      </div>
    </div>
  );
}

// ── Main page ─────────────────────────────────────────────────────────────────

type Tab = "simulation" | "live" | "events";

function AnalysisPageInner() {
  const searchParams = useSearchParams();
  const [symbol, setSymbol]   = useState("AAPL");
  const [input, setInput]     = useState("AAPL");
  const [years, setYears]     = useState(5);
  const [horizon, setHorizon] = useState(20);
  const [data, setData]       = useState<UnifiedAnalysisResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError]     = useState<string | null>(null);
  const [tab, setTab]         = useState<Tab>("simulation");

  const run = useCallback(async (sym: string, yr: number, hz: number) => {
    const s = sym.trim().toUpperCase();
    if (!s) return;
    setLoading(true);
    setError(null);
    setSymbol(s);
    try {
      const res = await api.unifiedAnalysis(s, yr, hz);
      setData(res);
      setTab("simulation");
    } catch (e: any) {
      setError(e.message || "Analysis failed");
    } finally {
      setLoading(false);
    }
  }, []);

  // Auto-run when Nexus navigates here with ?symbol=AAPL&years=5
  useEffect(() => {
    const sym = searchParams.get("symbol");
    const yr  = parseInt(searchParams.get("years") ?? "5", 10);
    const hz  = parseInt(searchParams.get("horizon") ?? "20", 10);
    if (sym) {
      setInput(sym.toUpperCase());
      setYears(isNaN(yr) ? 5 : yr);
      setHorizon(isNaN(hz) ? 20 : hz);
      run(sym, isNaN(yr) ? 5 : yr, isNaN(hz) ? 20 : hz);
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [searchParams]);

  const sim  = data?.simulation ?? null;
  const live = data?.live_predictions ?? null;

  return (
    <div className="flex flex-col h-full bg-[#0a0e1a] overflow-hidden">

      {/* ── Header ── */}
      <div className="flex items-center gap-3 px-5 py-3 border-b border-[#1f2937] bg-[#111827] flex-shrink-0">
        <BrainCircuit size={16} className="text-blue-400" />
        <span className="text-sm font-semibold text-white">Nexus Analysis</span>
        <span className="text-[10px] text-gray-600 bg-[#1f2937] px-2 py-0.5 rounded-full hidden sm:inline">
          Simulation · Live predictions · Signal quality · World events
        </span>
        <div className="flex-1" />
        {loading && <RefreshCw size={13} className="animate-spin text-blue-400" />}
        {sim && !loading && (
          <button onClick={() => run(symbol, years, horizon)}
            className="text-[10px] text-gray-500 hover:text-gray-300 flex items-center gap-1 transition-colors">
            <RefreshCw size={11} /> Refresh
          </button>
        )}
      </div>

      {/* ── Config bar ── */}
      <div className="flex items-center gap-2 px-5 py-2.5 border-b border-[#1f2937] bg-[#0d1117] flex-wrap flex-shrink-0">
        <form onSubmit={e => { e.preventDefault(); run(input, years, horizon); }}
          className="flex items-center gap-2">
          <input value={input} onChange={e => setInput(e.target.value.toUpperCase())}
            placeholder="Symbol…"
            className="bg-[#1f2937] border border-[#374151] rounded-lg px-3 py-1.5 text-sm text-white placeholder-gray-600 w-24 focus:outline-none focus:border-blue-500" />
          <button type="submit" disabled={loading}
            className="bg-blue-600 hover:bg-blue-500 disabled:opacity-50 text-white text-xs px-3 py-1.5 rounded-lg transition-colors flex items-center gap-1.5 flex-shrink-0">
            <Play size={11} /> Analyze
          </button>
        </form>

        <div className="flex gap-1 flex-wrap">
          {QUICK.map(s => (
            <button key={s} onClick={() => { setInput(s); run(s, years, horizon); }}
              className={cn("text-[10px] px-2 py-1 rounded font-mono transition-colors border",
                symbol === s && data
                  ? "bg-blue-600/20 text-blue-400 border-blue-600/30"
                  : "text-gray-500 border-[#374151] hover:text-gray-300 hover:bg-[#1f2937]")}>
              {s}
            </button>
          ))}
        </div>

        <div className="w-px h-4 bg-[#374151] hidden sm:block" />

        <div className="flex items-center gap-1.5">
          <span className="text-[10px] text-gray-500">History:</span>
          {YEAR_OPTS.map(y => (
            <button key={y} onClick={() => setYears(y)}
              className={cn("text-[10px] px-2 py-1 rounded font-mono transition-colors",
                years === y ? "bg-blue-600 text-white" : "text-gray-500 hover:text-gray-300 hover:bg-[#1f2937]")}>
              {y}Y
            </button>
          ))}
        </div>

        <div className="w-px h-4 bg-[#374151] hidden sm:block" />

        <div className="flex items-center gap-1.5">
          <span className="text-[10px] text-gray-500">Horizon:</span>
          {HORIZON_OPTS.map(h => (
            <button key={h} onClick={() => setHorizon(h)}
              className={cn("text-[10px] px-2 py-1 rounded font-mono transition-colors",
                horizon === h ? "bg-blue-600 text-white" : "text-gray-500 hover:text-gray-300 hover:bg-[#1f2937]")}>
              {h}d
            </button>
          ))}
        </div>
      </div>

      {/* ── Content ── */}
      <div className="flex-1 overflow-auto p-5 space-y-5">

        {/* Empty state */}
        {!data && !loading && !error && (
          <div className="flex flex-col items-center justify-center h-64 text-center gap-4">
            <BrainCircuit size={44} className="text-gray-700" />
            <div className="text-gray-500 text-sm max-w-sm">
              Select a symbol and click <strong className="text-gray-400">Analyze</strong> to run the unified
              simulation + prediction review with adaptive learning.
            </div>
            <div className="flex gap-2">
              {["AAPL", "NVDA", "SPY"].map(s => (
                <button key={s} onClick={() => { setInput(s); run(s, years, horizon); }}
                  className="bg-blue-600 hover:bg-blue-500 text-white text-sm px-4 py-2 rounded-lg transition-colors flex items-center gap-1.5">
                  <Play size={12} /> {s}
                </button>
              ))}
            </div>
          </div>
        )}

        {/* Error */}
        {error && (
          <div className="flex items-center gap-2 bg-red-900/20 border border-red-800/40 rounded-xl px-4 py-3 text-sm text-red-400">
            <AlertTriangle size={14} className="flex-shrink-0" /> {error}
          </div>
        )}

        {/* Loading */}
        {loading && (
          <div className="flex flex-col items-center justify-center h-64 gap-3 text-gray-500">
            <RefreshCw size={28} className="animate-spin text-blue-500" />
            <span className="text-sm">Analyzing {symbol}…</span>
            <span className="text-xs text-gray-600">Running simulation + loading live predictions</span>
          </div>
        )}

        {/* Results */}
        {sim && live && !loading && (
          <>
            {/* Title row + tab switcher */}
            <div className="flex items-center gap-3 flex-wrap">
              <span className="text-xl font-bold text-white font-mono">{sim.symbol}</span>
              <span className="text-sm text-gray-500">
                {sim.date_range.start} → {sim.date_range.end}
              </span>
              <span className="text-[10px] text-gray-600 bg-[#1f2937] px-2 py-0.5 rounded-full">
                {sim.horizon_days}d window · {sim.total_predictions} trades
              </span>
              <div className="ml-auto flex gap-1 bg-[#1f2937] rounded-lg p-0.5">
                {([
                  { id: "simulation", label: "Simulation",  icon: BarChart2 },
                  { id: "live",       label: "Live",        icon: Target },
                  { id: "events",     label: "Events",      icon: Globe },
                ] as { id: Tab; label: string; icon: React.ElementType }[]).map(({ id, label, icon: Icon }) => (
                  <button key={id} onClick={() => setTab(id)}
                    className={cn("text-[10px] px-3 py-1.5 rounded-md font-medium transition-colors flex items-center gap-1.5",
                      tab === id ? "bg-blue-600 text-white" : "text-gray-500 hover:text-gray-300")}>
                    <Icon size={10} />{label}
                  </button>
                ))}
              </div>
            </div>

            {/* Nexus insight — always visible */}
            <NexusInsight sim={sim} live={live} />

            {/* Summary stats — always visible */}
            <AccuracySummary sim={sim} live={live} />

            {/* ── Simulation tab ── */}
            {tab === "simulation" && (
              <>
                <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
                  <DirBreakdown byDir={sim.by_direction} title="Simulated Accuracy by Direction" />
                  <EquityCurve predictions={sim.predictions} />
                </div>
                {sim.signal_stats && <SignalHeatmap stats={sim.signal_stats} />}
                <PredictionLog predictions={sim.predictions} />
              </>
            )}

            {/* ── Live tab ── */}
            {tab === "live" && <LivePredictionsPanel data={live} />}

            {/* ── Events tab ── */}
            {tab === "events" && (
              <div className="bg-[#111827] border border-[#1f2937] rounded-xl p-4">
                <SectionHeader icon={Globe} title="World Events in This Period" badge={sim.events.length} />
                <WorldEventsPanel events={sim.events} />
              </div>
            )}

            {/* Disclaimer */}
            <div className="flex items-start gap-2 bg-yellow-900/10 border border-yellow-800/20 rounded-xl p-3 text-xs text-yellow-700">
              <AlertTriangle size={12} className="flex-shrink-0 mt-0.5" />
              Simulated results use simplified technical signals and do not account for slippage, commissions, or real
              options pricing. Past simulated accuracy does not predict future results.
            </div>
          </>
        )}
      </div>
    </div>
  );
}

export default function AnalysisPage() {
  return (
    <Suspense fallback={
      <div className="flex items-center justify-center h-full bg-[#0a0e1a]">
        <div className="text-gray-500 text-sm">Loading…</div>
      </div>
    }>
      <AnalysisPageInner />
    </Suspense>
  );
}
