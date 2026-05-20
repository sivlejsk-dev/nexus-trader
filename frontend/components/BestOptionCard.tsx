"use client";

/**
 * BestOptionCard — displays the output of the best-option engine.
 *
 * Shows: direction badge, confidence bar, contract details, risk/reward,
 * signal breakdown, simulation win rate, news snippets, and a speak button.
 */

import { useState, useCallback } from "react";
import {
  TrendingUp, TrendingDown, Minus, Target, AlertTriangle,
  Volume2, VolumeX, Zap, BarChart2, Clock, DollarSign,
  Activity, ChevronDown, ChevronUp, Newspaper, Brain,
} from "lucide-react";
import { cn } from "@/lib/utils";
import type { BestOptionResult, BestOptionSignal } from "@/lib/api";

// ── helpers ───────────────────────────────────────────────────────────────────

function fmt$(n?: number | null, decimals = 2) {
  if (n == null) return "—";
  return `$${n.toFixed(decimals)}`;
}

function fmtPct(n?: number | null, decimals = 1) {
  if (n == null) return "—";
  return `${(n * 100).toFixed(decimals)}%`;
}

function fmtConf(n: number) {
  return `${Math.round(n * 100)}%`;
}

function ttsSpeak(text: string) {
  if (typeof window === "undefined" || !window.speechSynthesis) return;
  window.speechSynthesis.cancel();
  const clean = text.replace(/[*_`#>]/g, "").replace(/\s+/g, " ").trim();
  const utt = new SpeechSynthesisUtterance(clean);
  utt.rate = 0.95;
  utt.pitch = 1.0;
  window.speechSynthesis.speak(utt);
}

// ── sub-components ────────────────────────────────────────────────────────────

function DirectionBadge({ direction, confidence }: { direction: string; confidence: number }) {
  const isCall = direction === "call";
  const isNeutral = direction === "neutral";

  return (
    <div className={cn(
      "flex items-center gap-2 px-3 py-1.5 rounded-lg font-bold text-sm",
      isCall ? "bg-green-900/40 border border-green-700/50 text-green-400"
        : isNeutral ? "bg-gray-800 border border-gray-700 text-gray-400"
          : "bg-red-900/40 border border-red-700/50 text-red-400"
    )}>
      {isCall ? <TrendingUp size={14} /> : isNeutral ? <Minus size={14} /> : <TrendingDown size={14} />}
      <span>{direction.toUpperCase()}</span>
      <span className="ml-1 font-mono text-xs opacity-80">{fmtConf(confidence)}</span>
    </div>
  );
}

function ConfidenceBar({ confidence }: { confidence: number }) {
  const pct = Math.round(confidence * 100);
  const color = pct >= 70 ? "bg-green-500" : pct >= 55 ? "bg-yellow-500" : "bg-red-500";
  return (
    <div className="space-y-1">
      <div className="flex justify-between text-[10px] text-gray-500">
        <span>Confidence</span>
        <span className="font-mono text-gray-300">{pct}%</span>
      </div>
      <div className="h-1.5 bg-gray-800 rounded-full overflow-hidden">
        <div className={cn("h-full rounded-full transition-all", color)} style={{ width: `${pct}%` }} />
      </div>
    </div>
  );
}

function SignalRow({ signal }: { signal: BestOptionSignal }) {
  const isBull = signal.signal === "bullish";
  const isBear = signal.signal === "bearish";
  return (
    <div className="flex items-start gap-2 text-xs py-1 border-b border-gray-800/50 last:border-0">
      <span className={cn(
        "mt-0.5 shrink-0 font-bold",
        isBull ? "text-green-400" : isBear ? "text-red-400" : "text-gray-500"
      )}>
        {isBull ? "↑" : isBear ? "↓" : "→"}
      </span>
      <div className="flex-1 min-w-0">
        <span className="text-gray-400 font-medium">{signal.name}</span>
        <span className="text-gray-600 mx-1">·</span>
        <span className="text-gray-500">{signal.detail}</span>
      </div>
      <span className="shrink-0 font-mono text-[10px] text-gray-600">{signal.value}</span>
    </div>
  );
}

function ContractBlock({ result }: { result: BestOptionResult }) {
  const c = result.contract;
  const rr = result.risk_reward;
  if (!c) return null;

  const expiry = c.expiry || c.expiration_date;
  const dte = c.days_to_expiry || c.dte;
  const premium = c.ask || c.estimated_premium;
  const iv = c.implied_volatility || c.iv;
  const isCall = c.type === "call";

  return (
    <div className={cn(
      "rounded-lg border p-3 space-y-2",
      isCall ? "bg-green-950/20 border-green-800/30" : "bg-red-950/20 border-red-800/30"
    )}>
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Target size={13} className={isCall ? "text-green-400" : "text-red-400"} />
          <span className="font-bold text-white text-sm">
            {c.symbol} {fmt$(c.strike, 0)} {c.type.toUpperCase()}
          </span>
          {c.is_synthetic && (
            <span className="text-[9px] px-1.5 py-0.5 rounded bg-yellow-900/30 border border-yellow-700/40 text-yellow-500">
              MODEL EST.
            </span>
          )}
        </div>
        {c._nexus_score != null && (
          <span className="text-[10px] font-mono text-gray-500">
            score {c._nexus_score}
          </span>
        )}
      </div>

      {/* Grid */}
      <div className="grid grid-cols-3 gap-2 text-xs">
        {expiry && (
          <div className="space-y-0.5">
            <div className="text-gray-600 flex items-center gap-1"><Clock size={9} /> Expiry</div>
            <div className="font-mono text-gray-300">{expiry}</div>
          </div>
        )}
        {dte != null && (
          <div className="space-y-0.5">
            <div className="text-gray-600">DTE</div>
            <div className={cn("font-mono font-bold", dte <= 7 ? "text-red-400" : dte <= 21 ? "text-yellow-400" : "text-green-400")}>
              {dte}d
            </div>
          </div>
        )}
        {premium != null && (
          <div className="space-y-0.5">
            <div className="text-gray-600 flex items-center gap-1"><DollarSign size={9} /> Premium</div>
            <div className="font-mono text-gray-300">{fmt$(premium)}</div>
          </div>
        )}
        {c.delta != null && (
          <div className="space-y-0.5">
            <div className="text-gray-600">Delta</div>
            <div className="font-mono text-gray-300">{c.delta.toFixed(2)}</div>
          </div>
        )}
        {iv != null && (
          <div className="space-y-0.5">
            <div className="text-gray-600">IV</div>
            <div className="font-mono text-gray-300">{fmtPct(iv)}</div>
          </div>
        )}
        {c.open_interest != null && (
          <div className="space-y-0.5">
            <div className="text-gray-600">OI</div>
            <div className="font-mono text-gray-300">{c.open_interest.toLocaleString()}</div>
          </div>
        )}
      </div>

      {/* Risk/reward */}
      {rr && (
        <div className="pt-1 border-t border-gray-800/50 grid grid-cols-2 gap-2 text-xs">
          <div className="space-y-0.5">
            <div className="text-gray-600">Breakeven</div>
            <div className="font-mono text-white font-bold">{fmt$(rr.breakeven)}</div>
          </div>
          <div className="space-y-0.5">
            <div className="text-gray-600">Max loss</div>
            <div className="font-mono text-red-400 font-bold">{fmt$(rr.max_loss)}</div>
          </div>
          <div className="space-y-0.5">
            <div className="text-gray-600">Cost / contract</div>
            <div className="font-mono text-gray-300">{fmt$(rr.cost_per_contract)}</div>
          </div>
          {rr.risk_reward_ratio != null && (
            <div className="space-y-0.5">
              <div className="text-gray-600">R/R ratio</div>
              <div className="font-mono text-gray-300">{rr.risk_reward_ratio.toFixed(2)}×</div>
            </div>
          )}
        </div>
      )}

      {c.is_synthetic && c.note && (
        <p className="text-[10px] text-yellow-600/80 italic">{c.note}</p>
      )}
    </div>
  );
}

// ── Main component ────────────────────────────────────────────────────────────

interface Props {
  result: BestOptionResult;
  /** If true, auto-speak the voice_script on mount */
  autoSpeak?: boolean;
  className?: string;
}

export default function BestOptionCard({ result, autoSpeak = false, className }: Props) {
  const [showSignals, setShowSignals] = useState(false);
  const [showNews, setShowNews] = useState(false);
  const [speaking, setSpeaking] = useState(false);

  // Auto-speak on first render if requested
  const didAutoSpeak = useState(false);
  if (autoSpeak && !didAutoSpeak[0] && result.voice_script) {
    didAutoSpeak[1](true);
    // defer to avoid calling during render
    setTimeout(() => ttsSpeak(result.voice_script), 100);
  }

  const handleSpeak = useCallback(() => {
    if (speaking) {
      window.speechSynthesis?.cancel();
      setSpeaking(false);
      return;
    }
    setSpeaking(true);
    ttsSpeak(result.voice_script);
    // Estimate duration and reset state
    const words = result.voice_script.split(" ").length;
    setTimeout(() => setSpeaking(false), words * 380);
  }, [speaking, result.voice_script]);

  const ds = result.direction_score;
  const sim = result.simulation;
  const signals = ds?.signals ?? [];
  const bullSignals = signals.filter(s => s.signal === "bullish");
  const bearSignals = signals.filter(s => s.signal === "bearish");

  return (
    <div className={cn(
      "bg-[#0d1117] border border-[#1f2937] rounded-xl p-4 space-y-3 text-sm",
      className
    )}>
      {/* ── Header ── */}
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <Zap size={14} className="text-yellow-400" />
          <span className="font-bold text-white">{result.symbol}</span>
          <span className="text-gray-600 text-xs font-mono">{fmt$(result.price)}</span>
        </div>
        <div className="flex items-center gap-2">
          <DirectionBadge direction={result.direction} confidence={result.confidence} />
          {result.voice_script && (
            <button
              onClick={handleSpeak}
              title={speaking ? "Stop" : "Speak recommendation"}
              className={cn(
                "p-1.5 rounded-lg border transition-colors",
                speaking
                  ? "bg-blue-900/40 border-blue-700/50 text-blue-400"
                  : "bg-gray-800 border-gray-700 text-gray-400 hover:text-white hover:border-gray-600"
              )}
            >
              {speaking ? <VolumeX size={13} /> : <Volume2 size={13} />}
            </button>
          )}
        </div>
      </div>

      {/* ── Confidence bar ── */}
      <ConfidenceBar confidence={result.confidence} />

      {/* ── Contract ── */}
      {result.contract && <ContractBlock result={result} />}

      {/* ── Simulation stats ── */}
      {sim?.win_rate != null && (
        <div className="flex items-center gap-3 text-xs bg-gray-900/50 rounded-lg px-3 py-2">
          <BarChart2 size={12} className="text-blue-400 shrink-0" />
          <span className="text-gray-500">Historical win rate:</span>
          <span className={cn("font-mono font-bold", sim.win_rate >= 55 ? "text-green-400" : "text-red-400")}>
            {sim.win_rate}%
          </span>
          {sim.direction_stats?.win_rate != null && (
            <>
              <span className="text-gray-700">·</span>
              <span className="text-gray-500">{result.direction.toUpperCase()} signals:</span>
              <span className={cn("font-mono font-bold", sim.direction_stats.win_rate >= 55 ? "text-green-400" : "text-red-400")}>
                {sim.direction_stats.win_rate}%
              </span>
            </>
          )}
          {sim.total_predictions != null && (
            <span className="ml-auto text-gray-700 font-mono">{sim.total_predictions} trades</span>
          )}
        </div>
      )}

      {/* ── Signal breakdown (collapsible) ── */}
      {signals.length > 0 && (
        <div className="space-y-1">
          <button
            onClick={() => setShowSignals(v => !v)}
            className="flex items-center gap-1.5 text-xs text-gray-500 hover:text-gray-300 transition-colors w-full"
          >
            <Activity size={11} />
            <span>
              {bullSignals.length} bullish · {bearSignals.length} bearish signals
            </span>
            {showSignals ? <ChevronUp size={11} className="ml-auto" /> : <ChevronDown size={11} className="ml-auto" />}
          </button>
          {showSignals && (
            <div className="bg-gray-900/40 rounded-lg px-3 py-2 space-y-0">
              {signals.map((s, i) => <SignalRow key={i} signal={s} />)}
            </div>
          )}
        </div>
      )}

      {/* ── News snippets (collapsible) ── */}
      {result.news_snippets?.length > 0 && (
        <div className="space-y-1">
          <button
            onClick={() => setShowNews(v => !v)}
            className="flex items-center gap-1.5 text-xs text-gray-500 hover:text-gray-300 transition-colors w-full"
          >
            <Newspaper size={11} />
            <span>{result.news_snippets.length} news snippets</span>
            {showNews ? <ChevronUp size={11} className="ml-auto" /> : <ChevronDown size={11} className="ml-auto" />}
          </button>
          {showNews && (
            <div className="space-y-1.5">
              {result.news_snippets.map((n, i) => (
                <p key={i} className="text-[11px] text-gray-500 bg-gray-900/40 rounded px-2.5 py-1.5 leading-relaxed">
                  {n}
                </p>
              ))}
            </div>
          )}
        </div>
      )}

      {/* ── Learned weights badge ── */}
      {result.using_learned_weights && (
        <div className="flex items-center gap-1.5 text-[10px] text-purple-400/70">
          <Brain size={10} />
          <span>Using optimized signal weights</span>
        </div>
      )}

      {/* ── Disclaimer ── */}
      <div className="flex items-start gap-1.5 text-[10px] text-gray-600 border-t border-gray-800/50 pt-2">
        <AlertTriangle size={10} className="shrink-0 mt-0.5 text-yellow-700" />
        <span>Not financial advice. Options trading involves substantial risk of loss. Past performance does not guarantee future results.</span>
      </div>
    </div>
  );
}
