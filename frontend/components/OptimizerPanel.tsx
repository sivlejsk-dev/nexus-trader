"use client";

/**
 * OptimizerPanel — iterative signal weight optimizer UI.
 *
 * Runs the backend optimizer (N generations of hill-climbing), shows a live
 * convergence chart, compares baseline vs optimized win rate, and displays
 * which signals changed the most. Learned weights are auto-saved and used
 * for all future simulations on that symbol.
 */

import { useState, useCallback } from "react";
import {
  Play, RefreshCw, RotateCcw, CheckCircle, AlertTriangle,
  TrendingUp, TrendingDown, Minus, Zap, BarChart2, ChevronDown, ChevronUp,
} from "lucide-react";
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, ReferenceLine, Legend,
} from "recharts";
import { api, type OptimizationResult } from "@/lib/api";
import { cn } from "@/lib/utils";

// ── constants ─────────────────────────────────────────────────────────────────

const SIGNAL_LABELS: Record<string, string> = {
  sma20:          "SMA20 trend",
  sma_cross:      "SMA20/50 cross",
  sma200:         "SMA200 trend",
  rsi_extreme:    "RSI extreme (30/70)",
  rsi_mild:       "RSI mild (40/60)",
  macd_cross:     "MACD cross",
  macd_accel:     "MACD acceleration",
  bb_band:        "Bollinger Band touch",
  volume_confirm: "Volume confirmation",
  momentum_5bar:  "5-bar momentum",
  edge_threshold: "Edge threshold",
};

const GEN_OPTS = [10, 20, 40, 60, 100];
const YEAR_OPTS = [1, 2, 3, 5, 10];

// ── WeightBar ─────────────────────────────────────────────────────────────────

function WeightBar({
  label, baseline, optimized, maxVal = 4,
}: {
  label: string; baseline: number; optimized: number; maxVal?: number;
}) {
  const delta = optimized - baseline;
  const increased = delta > 0.05;
  const decreased = delta < -0.05;
  const unchanged = !increased && !decreased;

  return (
    <div className="space-y-1">
      <div className="flex items-center justify-between text-[10px]">
        <span className="text-gray-400 truncate max-w-[140px]">{label}</span>
        <div className="flex items-center gap-2 flex-shrink-0">
          <span className="text-gray-600 font-mono">{baseline.toFixed(2)}</span>
          <span className="text-gray-600">→</span>
          <span className={cn("font-mono font-semibold",
            increased ? "text-green-400" : decreased ? "text-red-400" : "text-gray-400")}>
            {optimized.toFixed(2)}
          </span>
          {!unchanged && (
            <span className={cn("text-[9px] font-mono",
              increased ? "text-green-500" : "text-red-500")}>
              {delta > 0 ? "+" : ""}{delta.toFixed(2)}
            </span>
          )}
        </div>
      </div>
      {/* Stacked bar: baseline (gray) + optimized (colored) */}
      <div className="relative h-2 bg-[#1f2937] rounded-full overflow-hidden">
        {/* Baseline */}
        <div className="absolute inset-y-0 left-0 bg-gray-700 rounded-full"
          style={{ width: `${(baseline / maxVal) * 100}%` }} />
        {/* Optimized overlay */}
        <div className={cn("absolute inset-y-0 left-0 rounded-full opacity-80",
          increased ? "bg-green-500" : decreased ? "bg-red-500" : "bg-blue-500")}
          style={{ width: `${(optimized / maxVal) * 100}%` }} />
      </div>
    </div>
  );
}

// ── ConvergenceChart ──────────────────────────────────────────────────────────

function ConvergenceChart({
  convergence, baselineWr,
}: {
  convergence: OptimizationResult["convergence"];
  baselineWr: number | null;
}) {
  const data = convergence.map(c => ({
    gen: c.generation,
    win_rate: c.win_rate ?? 0,
    fitness: +(c.fitness * 100).toFixed(1),
  }));

  return (
    <div className="bg-[#111827] border border-[#1f2937] rounded-xl p-4">
      <div className="text-xs font-semibold text-gray-400 mb-3">Convergence — Win Rate per Generation</div>
      <ResponsiveContainer width="100%" height={180}>
        <LineChart data={data} margin={{ top: 4, right: 8, left: 0, bottom: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#1a2235" vertical={false} />
          <XAxis dataKey="gen" tick={{ fill: "#4b5563", fontSize: 9 }} tickLine={false} axisLine={false}
            label={{ value: "Generation", position: "insideBottom", offset: -2, fill: "#4b5563", fontSize: 9 }} />
          <YAxis tick={{ fill: "#4b5563", fontSize: 9 }} tickLine={false} axisLine={false} width={36}
            tickFormatter={(v: number) => `${v}%`} domain={["auto", "auto"]} />
          <Tooltip
            contentStyle={{ background: "#1a2235", border: "1px solid #374151", borderRadius: 8, fontSize: 11 }}
            formatter={(v: number, name: string) => [
              name === "win_rate" ? `${v}%` : `${v}`,
              name === "win_rate" ? "Win Rate" : "Fitness",
            ]}
          />
          {baselineWr != null && (
            <ReferenceLine y={baselineWr} stroke="#6b7280" strokeDasharray="4 2"
              label={{ value: `Baseline ${baselineWr}%`, fill: "#6b7280", fontSize: 9, position: "right" }} />
          )}
          <Line type="monotone" dataKey="win_rate" stroke="#3b82f6" strokeWidth={2}
            dot={(p: any) => p.payload.improved
              ? <circle key={p.key} cx={p.cx} cy={p.cy} r={3} fill="#22c55e" />
              : <circle key={p.key} cx={p.cx} cy={p.cy} r={1.5} fill="#3b82f6" />}
          />
        </LineChart>
      </ResponsiveContainer>
      <div className="flex items-center gap-4 mt-2 text-[9px] text-gray-600">
        <span className="flex items-center gap-1"><span className="w-2 h-2 rounded-full bg-green-500 inline-block" /> Improvement</span>
        <span className="flex items-center gap-1"><span className="w-2 h-2 rounded-full bg-blue-500 inline-block" /> No change</span>
        <span className="flex items-center gap-1"><span className="w-3 border-t border-dashed border-gray-600 inline-block" /> Baseline</span>
      </div>
    </div>
  );
}

// ── ComparisonCard ────────────────────────────────────────────────────────────

function ComparisonCard({ result }: { result: OptimizationResult }) {
  const bwr = result.baseline.win_rate ?? 0;
  const owr = result.optimized.win_rate ?? 0;
  const bpnl = result.baseline.avg_pnl_pct ?? 0;
  const opnl = result.optimized.avg_pnl_pct ?? 0;
  const imp = result.improvement_pct;

  return (
    <div className="grid grid-cols-2 gap-3">
      {/* Baseline */}
      <div className="bg-[#111827] border border-[#1f2937] rounded-xl p-4">
        <div className="text-[10px] text-gray-600 uppercase tracking-wide mb-2">Baseline (defaults)</div>
        <div className={cn("text-2xl font-bold font-mono", bwr >= 55 ? "text-green-400" : "text-red-400")}>
          {bwr}%
        </div>
        <div className="text-[10px] text-gray-500 mt-0.5">win rate</div>
        <div className={cn("text-sm font-mono mt-2", bpnl >= 0 ? "text-green-400" : "text-red-400")}>
          {bpnl >= 0 ? "+" : ""}{bpnl}%
        </div>
        <div className="text-[10px] text-gray-500">avg P&L</div>
      </div>

      {/* Optimized */}
      <div className={cn("border rounded-xl p-4",
        owr > bwr ? "bg-green-900/10 border-green-800/30" : "bg-[#111827] border-[#1f2937]")}>
        <div className="text-[10px] text-gray-600 uppercase tracking-wide mb-2 flex items-center gap-1">
          Optimized
          {result.weights_saved && <CheckCircle size={9} className="text-green-400" />}
        </div>
        <div className={cn("text-2xl font-bold font-mono", owr >= 55 ? "text-green-400" : "text-red-400")}>
          {owr}%
        </div>
        <div className="text-[10px] text-gray-500 mt-0.5">win rate</div>
        <div className={cn("text-sm font-mono mt-2", opnl >= 0 ? "text-green-400" : "text-red-400")}>
          {opnl >= 0 ? "+" : ""}{opnl}%
        </div>
        <div className="text-[10px] text-gray-500">avg P&L</div>
        {imp != null && (
          <div className={cn("text-[10px] font-semibold mt-2",
            imp > 0 ? "text-green-400" : imp < 0 ? "text-red-400" : "text-gray-500")}>
            {imp > 0 ? "+" : ""}{imp}% vs baseline
          </div>
        )}
      </div>
    </div>
  );
}

// ── Main component ────────────────────────────────────────────────────────────

export function OptimizerPanel({ symbol }: { symbol: string }) {
  const [result, setResult]       = useState<OptimizationResult | null>(null);
  const [loading, setLoading]     = useState(false);
  const [error, setError]         = useState<string | null>(null);
  const [generations, setGens]    = useState(40);
  const [years, setYears]         = useState(5);
  const [showWeights, setShowWeights] = useState(true);
  const [resetting, setResetting] = useState(false);

  const run = useCallback(async () => {
    if (!symbol || loading) return;
    setLoading(true);
    setError(null);
    setResult(null);
    try {
      const res = await api.optimizeWeights(symbol, years, 20, generations, true);
      setResult(res);
    } catch (e: any) {
      setError(e.message || "Optimization failed");
    } finally {
      setLoading(false);
    }
  }, [symbol, years, generations, loading]);

  const reset = useCallback(async () => {
    if (!symbol || resetting) return;
    setResetting(true);
    try {
      await api.resetWeights(symbol);
      setResult(null);
      setError(null);
    } catch (e: any) {
      setError(e.message || "Reset failed");
    } finally {
      setResetting(false);
    }
  }, [symbol, resetting]);

  return (
    <div className="bg-[#111827] border border-[#1f2937] rounded-xl overflow-hidden">
      {/* Header */}
      <div className="flex items-center gap-2 px-4 py-3 border-b border-[#1f2937] bg-[#0d1117]">
        <Zap size={14} className="text-yellow-400" />
        <span className="text-xs font-semibold text-gray-200">Signal Weight Optimizer</span>
        <span className="text-[10px] text-gray-600 bg-[#1f2937] px-2 py-0.5 rounded-full">
          {symbol}
        </span>
        <div className="flex-1" />
        {loading && <RefreshCw size={12} className="animate-spin text-blue-400" />}
      </div>

      <div className="p-4 space-y-4">
        {/* Controls */}
        <div className="flex items-center gap-3 flex-wrap">
          <div className="flex items-center gap-1.5">
            <span className="text-[10px] text-gray-500">Generations:</span>
            {GEN_OPTS.map(g => (
              <button key={g} onClick={() => setGens(g)}
                className={cn("text-[10px] px-2 py-1 rounded font-mono transition-colors",
                  generations === g ? "bg-blue-600 text-white" : "text-gray-500 hover:text-gray-300 hover:bg-[#1f2937]")}>
                {g}
              </button>
            ))}
          </div>
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
          <div className="flex gap-2 ml-auto">
            <button onClick={reset} disabled={resetting || loading}
              className="text-[10px] text-gray-500 hover:text-red-400 flex items-center gap-1 transition-colors disabled:opacity-40">
              <RotateCcw size={10} /> Reset to defaults
            </button>
            <button onClick={run} disabled={loading}
              className="bg-yellow-600 hover:bg-yellow-500 disabled:opacity-50 text-white text-xs px-3 py-1.5 rounded-lg transition-colors flex items-center gap-1.5">
              {loading ? <RefreshCw size={11} className="animate-spin" /> : <Play size={11} />}
              {loading ? "Optimizing…" : "Run Optimizer"}
            </button>
          </div>
        </div>

        {/* Description */}
        {!result && !loading && !error && (
          <div className="text-xs text-gray-600 leading-relaxed bg-[#0d1117] rounded-lg p-3 border border-[#1f2937]">
            The optimizer runs the simulation <strong className="text-gray-400">{generations} times</strong>, each time
            mutating the signal weights (RSI, MACD, Bollinger, volume, SMA) and keeping the best-performing combination.
            It forgets the fixed defaults and learns which signals actually predict {symbol} price moves.
            Best weights are saved and used automatically for all future simulations.
          </div>
        )}

        {error && (
          <div className="flex items-center gap-2 bg-red-900/20 border border-red-800/40 rounded-lg px-3 py-2 text-xs text-red-400">
            <AlertTriangle size={12} /> {error}
          </div>
        )}

        {loading && (
          <div className="flex flex-col items-center justify-center py-10 gap-3">
            <RefreshCw size={24} className="animate-spin text-yellow-400" />
            <div className="text-sm text-gray-400">Running {generations} generations…</div>
            <div className="text-xs text-gray-600">Nexus is forgetting the defaults and learning from scratch</div>
          </div>
        )}

        {result && !loading && (
          <>
            {/* Comparison */}
            <ComparisonCard result={result} />

            {/* Convergence chart */}
            <ConvergenceChart
              convergence={result.convergence}
              baselineWr={result.baseline.win_rate}
            />

            {/* Weight changes */}
            <div className="bg-[#0d1117] border border-[#1f2937] rounded-xl p-4">
              <button
                onClick={() => setShowWeights(s => !s)}
                className="w-full flex items-center gap-2 text-left">
                <BarChart2 size={13} className="text-blue-400" />
                <span className="text-xs font-semibold text-gray-300">Signal Weight Changes</span>
                <span className="text-[10px] text-gray-600 ml-2">
                  {result.generations_run} generations · {result.top_changed_signals.length} signals changed
                </span>
                <div className="flex-1" />
                {showWeights
                  ? <ChevronUp size={12} className="text-gray-500" />
                  : <ChevronDown size={12} className="text-gray-500" />}
              </button>

              {showWeights && (
                <div className="mt-4 space-y-3">
                  {/* Sort by absolute delta — biggest changes first */}
                  {Object.entries(result.weight_changes)
                    .sort(([, a], [, b]) => Math.abs(b.delta) - Math.abs(a.delta))
                    .map(([key, change]) => (
                      <WeightBar
                        key={key}
                        label={SIGNAL_LABELS[key] ?? key}
                        baseline={change.baseline}
                        optimized={change.optimized}
                      />
                    ))}
                  <div className="pt-2 border-t border-[#1f2937] text-[10px] text-gray-600 space-y-0.5">
                    <div>Gray bar = baseline weight · Colored bar = optimized weight</div>
                    <div className="flex gap-3">
                      <span className="text-green-500">Green = increased</span>
                      <span className="text-red-500">Red = decreased</span>
                      <span className="text-blue-500">Blue = unchanged</span>
                    </div>
                  </div>
                </div>
              )}
            </div>

            {/* What Nexus learned */}
            <div className="bg-yellow-900/10 border border-yellow-800/20 rounded-xl p-4 space-y-2">
              <div className="flex items-center gap-2">
                <Zap size={12} className="text-yellow-400" />
                <span className="text-xs font-semibold text-gray-300">What Nexus learned</span>
              </div>
              <div className="text-xs text-gray-400 leading-relaxed space-y-1.5">
                <p>
                  After {result.generations_run} generations on {symbol} ({years}Y history),
                  win rate moved from{" "}
                  <strong className={cn(result.baseline.win_rate != null && result.baseline.win_rate >= 55 ? "text-green-400" : "text-red-400")}>
                    {result.baseline.win_rate}%
                  </strong>{" "}
                  to{" "}
                  <strong className={cn(result.optimized.win_rate != null && result.optimized.win_rate >= 55 ? "text-green-400" : "text-red-400")}>
                    {result.optimized.win_rate}%
                  </strong>
                  {result.improvement_pct != null && result.improvement_pct > 0 && (
                    <span className="text-green-400"> (+{result.improvement_pct}%)</span>
                  )}
                  {result.improvement_pct != null && result.improvement_pct <= 0 && (
                    <span className="text-gray-500"> — defaults were already near-optimal for this symbol</span>
                  )}.
                </p>
                {result.top_changed_signals.length > 0 && (
                  <p>
                    Most impactful changes:{" "}
                    {result.top_changed_signals.slice(0, 3).map((s, i) => {
                      const ch = result.weight_changes[s];
                      return (
                        <span key={s}>
                          <strong className="text-white">{SIGNAL_LABELS[s] ?? s}</strong>
                          {ch && (
                            <span className={cn("ml-1", ch.delta > 0 ? "text-green-400" : "text-red-400")}>
                              ({ch.delta > 0 ? "+" : ""}{ch.delta.toFixed(2)})
                            </span>
                          )}
                          {i < 2 ? ", " : ""}
                        </span>
                      );
                    })}
                    .
                  </p>
                )}
                {result.weights_saved && (
                  <p className="text-green-400/80">
                    ✅ Learned weights saved — all future {symbol} simulations will use these weights automatically.
                  </p>
                )}
              </div>
            </div>

            {/* Stats */}
            <div className="flex items-center gap-4 text-[10px] text-gray-600 px-1">
              <span>{result.optimized.total_predictions} trades evaluated</span>
              <span>{result.generations_run} generations completed</span>
              <span>Weights {result.weights_saved ? "saved ✓" : "not saved"}</span>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
