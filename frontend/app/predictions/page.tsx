"use client";

/**
 * Prediction Tracker — shows Nexus's prediction history, win/loss outcomes,
 * learning adjustments, and accuracy metrics per symbol.
 */

import { useState, useCallback } from "react";
import {
  BrainCircuit, RefreshCw, TrendingUp, TrendingDown, Minus,
  AlertTriangle, CheckCircle, Clock, Target, ChevronDown, ChevronUp,
  BarChart2, Zap, Activity, Flame, TrendingUp as StreakIcon,
} from "lucide-react";
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, Cell,
} from "recharts";
import { api, type PredictionHistoryResponse } from "@/lib/api";
import { cn, fmtPrice } from "@/lib/utils";

const QUICK_SYMBOLS = ["AAPL", "TSLA", "NVDA", "SPY", "QQQ", "MSFT", "AMZN", "META"];

function StatusBadge({ status }: { status: string }) {
  const cfg = {
    win:     { icon: <CheckCircle size={10} />, label: "Win",     cls: "text-green-400 bg-green-900/20 border-green-800/30" },
    loss:    { icon: <AlertTriangle size={10} />, label: "Loss",  cls: "text-red-400 bg-red-900/20 border-red-800/30" },
    pending: { icon: <Clock size={10} />, label: "Pending",       cls: "text-yellow-400 bg-yellow-900/20 border-yellow-800/30" },
    flat:    { icon: <Minus size={10} />, label: "Flat",          cls: "text-gray-400 bg-gray-900/20 border-gray-800/30" },
  }[status] || { icon: <Minus size={10} />, label: status, cls: "text-gray-400 bg-gray-900/20 border-gray-800/30" };

  return (
    <span className={cn("flex items-center gap-1 text-[10px] px-2 py-0.5 rounded-full border font-medium", cfg.cls)}>
      {cfg.icon} {cfg.label}
    </span>
  );
}

function DirectionBadge({ direction }: { direction: string }) {
  if (direction === "call") return (
    <span className="flex items-center gap-1 text-[10px] px-2 py-0.5 rounded-full bg-green-900/20 border border-green-800/30 text-green-400 font-semibold">
      <TrendingUp size={10} /> CALL
    </span>
  );
  if (direction === "put") return (
    <span className="flex items-center gap-1 text-[10px] px-2 py-0.5 rounded-full bg-red-900/20 border border-red-800/30 text-red-400 font-semibold">
      <TrendingDown size={10} /> PUT
    </span>
  );
  return (
    <span className="flex items-center gap-1 text-[10px] px-2 py-0.5 rounded-full bg-gray-900/20 border border-gray-800/30 text-gray-400 font-semibold">
      <Minus size={10} /> NEUTRAL
    </span>
  );
}

function ConfidenceBar({ value }: { value: number }) {
  const pct = Math.round(value * 100);
  const color = pct >= 70 ? "bg-green-500" : pct >= 55 ? "bg-yellow-500" : "bg-gray-500";
  return (
    <div className="flex items-center gap-2">
      <div className="flex-1 h-1.5 bg-[#1f2937] rounded-full overflow-hidden">
        <div className={cn("h-full rounded-full", color)} style={{ width: `${pct}%` }} />
      </div>
      <span className="text-[10px] font-mono text-gray-400 w-8 text-right">{pct}%</span>
    </div>
  );
}

// ── Streak banner ─────────────────────────────────────────────────────────────

function StreakBanner({ perf }: { perf: any }) {
  const streak = perf.current_streak;
  if (!streak || streak.length < 2) return null;
  const isWin = streak.type === "win";
  return (
    <div className={cn(
      "flex items-center gap-3 rounded-xl border px-4 py-3",
      isWin ? "bg-green-900/20 border-green-800/30" : "bg-red-900/20 border-red-800/30"
    )}>
      <Flame size={18} className={isWin ? "text-green-400" : "text-red-400"} />
      <div>
        <div className={cn("text-sm font-bold", isWin ? "text-green-400" : "text-red-400")}>
          {streak.length}-prediction {streak.type} streak on {streak.direction}s
        </div>
        <div className="text-[10px] text-gray-500 mt-0.5">
          {isWin
            ? "Model is hot — confidence is being nudged up for this direction."
            : "Model is struggling — confidence is being reduced for this direction."}
        </div>
      </div>
    </div>
  );
}

// ── Confidence calibration chart ──────────────────────────────────────────────

function ConfidenceCalibration({ perf }: { perf: any }) {
  const bands = perf.confidence_analysis;
  if (!bands || bands.length === 0) return null;
  return (
    <div className="bg-[#111827] border border-[#1f2937] rounded-xl p-4">
      <div className="flex items-center gap-2 mb-3">
        <Target size={13} className="text-orange-400" />
        <span className="text-xs font-semibold text-gray-400">Confidence Calibration</span>
        <span className="text-[10px] text-gray-600 ml-auto">Predicted vs actual win rate</span>
      </div>
      <div className="space-y-2">
        {bands.map((band: any, i: number) => (
          <div key={i} className="flex items-center gap-3">
            <span className="text-[10px] text-gray-500 w-14 flex-shrink-0">{band.band}</span>
            <div className="flex-1 relative h-5 bg-[#1f2937] rounded overflow-hidden">
              <div
                className={cn("h-full rounded transition-all",
                  band.actual_win_rate >= 60 ? "bg-green-600/70" :
                  band.actual_win_rate >= 45 ? "bg-yellow-600/70" : "bg-red-600/70")}
                style={{ width: `${band.actual_win_rate}%` }}
              />
              <span className="absolute inset-0 flex items-center px-2 text-[10px] font-mono text-white">
                {band.actual_win_rate}% actual
              </span>
            </div>
            <span className="text-[10px] text-gray-600 w-12 text-right">{band.total} trades</span>
            {band.calibrated
              ? <CheckCircle size={11} className="text-green-500 flex-shrink-0" />
              : <AlertTriangle size={11} className="text-yellow-500 flex-shrink-0" />}
          </div>
        ))}
      </div>
      <div className="mt-2 text-[10px] text-gray-600">
        ✓ = well-calibrated (actual win rate close to predicted confidence)
      </div>
    </div>
  );
}

// ── P&L by direction bar chart ────────────────────────────────────────────────

function PnLByDirection({ perf }: { perf: any }) {
  const pnlMap = perf.avg_pnl_by_direction;
  if (!pnlMap) return null;
  const data = Object.entries(pnlMap)
    .filter(([d]) => d !== "neutral")
    .map(([dir, pnl]) => ({ dir: dir.toUpperCase(), pnl: pnl as number }));
  if (data.length === 0) return null;
  return (
    <div className="bg-[#111827] border border-[#1f2937] rounded-xl p-4">
      <div className="flex items-center gap-2 mb-3">
        <Activity size={13} className="text-blue-400" />
        <span className="text-xs font-semibold text-gray-400">Avg P&L by Direction</span>
      </div>
      <ResponsiveContainer width="100%" height={100}>
        <BarChart data={data} margin={{ top: 4, right: 8, left: 0, bottom: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#1a2235" vertical={false} />
          <XAxis dataKey="dir" tick={{ fill: "#6b7280", fontSize: 10 }} tickLine={false} axisLine={false} />
          <YAxis tick={{ fill: "#6b7280", fontSize: 9 }} tickLine={false} axisLine={false} width={36}
            tickFormatter={(v) => `${v > 0 ? "+" : ""}${v}%`} />
          <Tooltip contentStyle={{ background: "#1a2235", border: "1px solid #374151", borderRadius: 8, fontSize: 11 }}
            formatter={(v: number) => [`${v >= 0 ? "+" : ""}${v.toFixed(2)}%`, "Avg P&L"]} />
          <Bar dataKey="pnl" radius={[4, 4, 0, 0]}>
            {data.map((d, i) => (
              <Cell key={i} fill={d.pnl >= 0 ? "#22c55e" : "#ef4444"} />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

function PerformanceSummary({ perf }: { perf: PredictionHistoryResponse["performance"] }) {
  return (
    <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
      {[
        { label: "Total", value: perf.total, color: "text-white" },
        { label: "Win Rate", value: perf.win_rate != null ? `${perf.win_rate}%` : "—", color: (perf.win_rate ?? 0) >= 55 ? "text-green-400" : "text-red-400" },
        { label: "Wins", value: perf.wins, color: "text-green-400" },
        { label: "Losses", value: perf.losses, color: "text-red-400" },
      ].map(({ label, value, color }) => (
        <div key={label} className="bg-[#111827] border border-[#1f2937] rounded-xl p-4 text-center">
          <div className="text-[10px] text-gray-600 uppercase tracking-wide mb-1">{label}</div>
          <div className={cn("text-2xl font-bold font-mono", color)}>{value}</div>
        </div>
      ))}
    </div>
  );
}

function DirectionBreakdown({ byDir }: { byDir: PredictionHistoryResponse["performance"]["by_direction"] }) {
  return (
    <div className="bg-[#111827] border border-[#1f2937] rounded-xl p-4">
      <div className="text-xs font-semibold text-gray-400 mb-3">Performance by Direction</div>
      <div className="space-y-3">
        {(["call", "put", "neutral"] as const).map((dir) => {
          const s = byDir[dir];
          if (!s || s.total === 0) return null;
          const wr = s.win_rate ?? 0;
          return (
            <div key={dir} className="flex items-center gap-3">
              <DirectionBadge direction={dir} />
              <div className="flex-1">
                <div className="flex justify-between text-[10px] text-gray-500 mb-1">
                  <span>{s.wins}W / {s.losses}L / {s.total - s.wins - s.losses}P</span>
                  <span className={cn("font-mono", wr >= 55 ? "text-green-400" : "text-red-400")}>{wr}%</span>
                </div>
                <div className="h-1.5 bg-[#1f2937] rounded-full overflow-hidden">
                  <div
                    className={cn("h-full rounded-full", wr >= 55 ? "bg-green-500" : "bg-red-500")}
                    style={{ width: `${wr}%` }}
                  />
                </div>
              </div>
              <div className={cn(
                "text-[10px] px-2 py-0.5 rounded font-mono",
                s.learning_factor > 1 ? "text-green-400 bg-green-900/20" :
                s.learning_factor < 1 ? "text-red-400 bg-red-900/20" : "text-gray-500 bg-gray-900/20"
              )}>
                ×{s.learning_factor.toFixed(2)}
              </div>
            </div>
          );
        })}
      </div>
      <div className="mt-3 text-[10px] text-gray-600">
        Learning factor adjusts future confidence based on past accuracy per direction.
      </div>
    </div>
  );
}

function PredictionRow({ pred, expanded, onToggle }: {
  pred: PredictionHistoryResponse["predictions"][0];
  expanded: boolean;
  onToggle: () => void;
}) {
  const pnl = pred.pnl_pct;
  return (
    <div className="border border-[#1f2937] rounded-xl overflow-hidden">
      <button
        onClick={onToggle}
        className="w-full flex items-center gap-3 px-4 py-3 hover:bg-[#111827]/50 transition-colors text-left"
      >
        <DirectionBadge direction={pred.direction} />
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <span className="text-xs text-gray-300 font-mono">{fmtPrice(pred.entry_price)}</span>
            {pred.target_price && (
              <span className="text-[10px] text-green-400 font-mono">→ {fmtPrice(pred.target_price)}</span>
            )}
          </div>
          <div className="text-[10px] text-gray-600 mt-0.5">
            {new Date(pred.created_at).toLocaleDateString()}
          </div>
        </div>
        <ConfidenceBar value={pred.confidence} />
        <StatusBadge status={pred.outcome_status} />
        {pnl != null && (
          <span className={cn("text-xs font-mono font-semibold w-14 text-right", pnl >= 0 ? "text-green-400" : "text-red-400")}>
            {pnl >= 0 ? "+" : ""}{pnl.toFixed(1)}%
          </span>
        )}
        {expanded ? <ChevronUp size={13} className="text-gray-500" /> : <ChevronDown size={13} className="text-gray-500" />}
      </button>

      {expanded && (
        <div className="px-4 pb-4 border-t border-[#1f2937] bg-[#0d1117]/40 space-y-3 pt-3">
          {pred.rationale.length > 0 && (
            <div>
              <div className="text-[10px] text-gray-600 uppercase tracking-wide mb-1.5">Nexus Rationale</div>
              <ul className="space-y-1">
                {pred.rationale.map((r, i) => (
                  <li key={i} className="text-xs text-gray-400 flex gap-1.5">
                    <span className="text-blue-500 mt-0.5">›</span>{r}
                  </li>
                ))}
              </ul>
            </div>
          )}
          {pred.outcome_status !== "pending" && pred.exit_price && (
            <div className="grid grid-cols-3 gap-3 text-center">
              <div className="bg-[#111827] rounded-lg p-2">
                <div className="text-[10px] text-gray-600">Entry</div>
                <div className="text-xs font-mono text-white">{fmtPrice(pred.entry_price)}</div>
              </div>
              <div className="bg-[#111827] rounded-lg p-2">
                <div className="text-[10px] text-gray-600">Exit</div>
                <div className="text-xs font-mono text-white">{fmtPrice(pred.exit_price)}</div>
              </div>
              <div className="bg-[#111827] rounded-lg p-2">
                <div className="text-[10px] text-gray-600">P&L</div>
                <div className={cn("text-xs font-mono font-semibold", (pnl ?? 0) >= 0 ? "text-green-400" : "text-red-400")}>
                  {pnl != null ? `${pnl >= 0 ? "+" : ""}${pnl.toFixed(1)}%` : "—"}
                </div>
              </div>
            </div>
          )}
          {pred.mistake_notes && pred.mistake_notes.length > 0 && (
            <div className="bg-red-900/10 border border-red-800/20 rounded-lg p-3">
              <div className="text-[10px] text-red-400 font-semibold mb-1.5 flex items-center gap-1">
                <Zap size={10} /> What Nexus learned
              </div>
              <ul className="space-y-1">
                {pred.mistake_notes.map((n, i) => (
                  <li key={i} className="text-xs text-gray-400 flex gap-1.5">
                    <span className="text-red-500 mt-0.5">›</span>{n}
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

export default function PredictionsPage() {
  const [symbol, setSymbol] = useState("AAPL");
  const [input, setInput] = useState("AAPL");
  const [data, setData] = useState<PredictionHistoryResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [scoring, setScoring] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [expanded, setExpanded] = useState<number | null>(null);

  const load = useCallback(async (sym: string) => {
    const s = sym.trim().toUpperCase();
    if (!s) return;
    setLoading(true);
    setError(null);
    setSymbol(s);
    setInput(s);
    setExpanded(null);
    try {
      const res = await api.predictionHistory(s);
      setData(res);
    } catch (e: any) {
      setError(e.message || "Failed to load predictions");
    } finally {
      setLoading(false);
    }
  }, []);

  const scoreNow = async () => {
    if (!symbol) return;
    setScoring(true);
    try {
      await api.scorePredictions(symbol);
      await load(symbol);
    } catch {}
    finally { setScoring(false); }
  };

  return (
    <div className="flex flex-col h-full bg-[#0a0e1a] overflow-auto">
      {/* Header */}
      <div className="flex items-center gap-3 px-5 py-3 border-b border-[#1f2937] bg-[#111827] flex-shrink-0">
        <BrainCircuit size={16} className="text-blue-400" />
        <span className="text-sm font-semibold text-white">Prediction Tracker</span>
        <div className="flex-1" />
        <form onSubmit={(e) => { e.preventDefault(); load(input); }} className="flex items-center gap-2">
          <input
            value={input}
            onChange={(e) => setInput(e.target.value.toUpperCase())}
            placeholder="Symbol…"
            className="bg-[#1f2937] border border-[#374151] rounded-lg px-3 py-1.5 text-sm text-white placeholder-gray-600 w-24 focus:outline-none focus:border-blue-500"
          />
          <button type="submit" disabled={loading}
            className="bg-blue-600 hover:bg-blue-500 disabled:opacity-50 text-white text-xs px-3 py-1.5 rounded-lg transition-colors">
            {loading ? <RefreshCw size={12} className="animate-spin" /> : "Load"}
          </button>
        </form>
        {data && (
          <button onClick={scoreNow} disabled={scoring}
            className="flex items-center gap-1.5 bg-[#1f2937] hover:bg-[#374151] text-gray-300 text-xs px-3 py-1.5 rounded-lg transition-colors border border-[#374151]">
            {scoring ? <RefreshCw size={11} className="animate-spin" /> : <Target size={11} />}
            Score pending
          </button>
        )}
      </div>

      <div className="p-5 space-y-5">
        {/* Quick symbols */}
        <div className="flex gap-1.5 flex-wrap">
          {QUICK_SYMBOLS.map((s) => (
            <button key={s} onClick={() => load(s)}
              className={cn(
                "text-[10px] px-2.5 py-1 rounded-lg font-mono font-medium transition-colors border",
                symbol === s
                  ? "bg-blue-600/20 text-blue-400 border-blue-600/30"
                  : "bg-[#1f2937] text-gray-500 border-[#374151] hover:text-gray-300"
              )}>
              {s}
            </button>
          ))}
        </div>

        {error && (
          <div className="flex items-center gap-2 bg-red-900/20 border border-red-800/40 rounded-xl px-4 py-3 text-sm text-red-400">
            <AlertTriangle size={14} /> {error}
          </div>
        )}

        {data && (
          <>
            <StreakBanner perf={data.performance} />
            <PerformanceSummary perf={data.performance} />

            <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
              <DirectionBreakdown byDir={data.performance.by_direction} />
              <PnLByDirection perf={data.performance} />
            </div>

            <ConfidenceCalibration perf={data.performance} />

            {data.predictions.length > 0 ? (
              <div className="space-y-2">
                <div className="text-xs font-semibold text-gray-500 uppercase tracking-wide">
                  {data.predictions.length} Predictions for {data.symbol}
                </div>
                {data.predictions.map((pred, i) => (
                  <PredictionRow
                    key={pred.id}
                    pred={pred}
                    expanded={expanded === i}
                    onToggle={() => setExpanded(expanded === i ? null : i)}
                  />
                ))}
              </div>
            ) : (
              <div className="flex flex-col items-center justify-center py-16 text-center">
                <BrainCircuit size={36} className="text-gray-700 mb-3" />
                <div className="text-gray-500 text-sm">No predictions yet for {data.symbol}</div>
                <div className="text-gray-600 text-xs mt-1">Run an analysis on the Console to generate predictions</div>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}
