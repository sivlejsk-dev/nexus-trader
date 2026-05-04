"use client";

import { useState, useCallback, useEffect } from "react";
import {
  Search, RefreshCw, TrendingUp, TrendingDown, Minus,
  AlertTriangle, ChevronDown, ChevronUp, Zap, BarChart2,
  BrainCircuit, Target, History,
} from "lucide-react";
import { api, type FullAnalysis } from "@/lib/api";
import { PriceChart } from "@/components/charts/PriceChart";
import { StrategyRadarChart } from "@/components/charts/OptionsChart";
import { cn, fmtPrice, fmtPct, fmtVolume, changeColor, confidenceColor, directionColor } from "@/lib/utils";

const QUICK_SYMBOLS = ["AAPL", "TSLA", "NVDA", "SPY", "QQQ", "MSFT", "AMZN", "META"];

export default function ConsolePage() {
  const [symbol, setSymbol] = useState("AAPL");
  const [input, setInput] = useState("AAPL");
  const [data, setData] = useState<FullAnalysis | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [showAllPatterns, setShowAllPatterns] = useState(false);
  const [providerSummary, setProviderSummary] = useState<string>("Checking data sources...");

  useEffect(() => {
    api.providers()
      .then((res) => {
        const active = res.providers.filter((p) => p.configured).map((p) => p.name).join(" -> ");
        setProviderSummary(active || "No market providers configured");
      })
      .catch(() => setProviderSummary("Provider status unavailable"));
  }, []);

  const load = useCallback(async (sym: string) => {
    const s = sym.trim().toUpperCase();
    if (!s) return;
    setLoading(true);
    setError(null);
    setSymbol(s);
    setInput(s);
    try {
      const result = await api.analysis(s);
      setData(result);
    } catch (e: any) {
      setError(e.message || "Failed to load data");
    } finally {
      setLoading(false);
    }
  }, []);

  const quote = data?.quote;
  const tech = data?.technicals;
  const patterns = data?.patterns;
  const reasoning = data?.reasoning;
  const adaptive = data?.adaptive_prediction;
  const bars = data?.chart_bars || [];

  const changePct = quote?.change_pct ?? 0;
  const TrendIcon = patterns?.summary.bias === "bullish" ? TrendingUp
    : patterns?.summary.bias === "bearish" ? TrendingDown : Minus;

  return (
    <div className="flex flex-col h-full bg-[#0a0e1a]">
      {/* Header bar */}
      <div className="flex items-center gap-3 px-5 py-3 border-b border-[#1f2937] bg-[#111827]">
        <BarChart2 size={18} className="text-blue-400" />
        <span className="text-sm font-semibold text-white">Visual Console</span>
        <div className="flex-1" />

        {/* Symbol search */}
        <form
          onSubmit={(e) => { e.preventDefault(); load(input); }}
          className="flex items-center gap-2"
        >
          <div className="relative">
            <Search size={13} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-gray-500" />
            <input
              value={input}
              onChange={(e) => setInput(e.target.value.toUpperCase())}
              placeholder="Symbol…"
              className="bg-[#1f2937] border border-[#374151] rounded-lg pl-8 pr-3 py-1.5 text-sm text-white placeholder-gray-600 w-28 focus:outline-none focus:border-blue-500"
            />
          </div>
          <button
            type="submit"
            disabled={loading}
            className="bg-blue-600 hover:bg-blue-500 disabled:opacity-50 text-white text-xs font-medium px-3 py-1.5 rounded-lg transition-colors"
          >
            {loading ? <RefreshCw size={12} className="animate-spin" /> : "Analyze"}
          </button>
        </form>

        {/* Quick symbols */}
        <div className="flex gap-1">
          {QUICK_SYMBOLS.map((s) => (
            <button
              key={s}
              onClick={() => load(s)}
              className={cn(
                "text-[10px] px-2 py-1 rounded font-mono transition-colors",
                symbol === s
                  ? "bg-blue-600/30 text-blue-300 border border-blue-600/40"
                  : "text-gray-500 hover:text-gray-300 hover:bg-[#1f2937]"
              )}
            >
              {s}
            </button>
          ))}
        </div>
      </div>

      {/* Error */}
      {error && (
        <div className="mx-5 mt-4 flex items-center gap-2 bg-red-900/20 border border-red-800/40 rounded-lg px-4 py-3 text-sm text-red-400">
          <AlertTriangle size={14} /> {error}
        </div>
      )}

      {/* Empty state */}
      {!data && !loading && !error && (
        <div className="flex-1 flex flex-col items-center justify-center gap-4 text-gray-600">
          <Zap size={40} className="text-blue-600/40" />
          <p className="text-sm">Enter a symbol above to begin analysis</p>
        </div>
      )}

      {/* Loading skeleton */}
      {loading && (
        <div className="flex-1 flex items-center justify-center">
          <div className="flex flex-col items-center gap-3 text-gray-500">
            <RefreshCw size={24} className="animate-spin text-blue-500" />
            <span className="text-sm">Fetching {symbol}…</span>
          </div>
        </div>
      )}

      {/* Main content */}
      {data && !loading && (
        <div className="flex-1 overflow-auto p-5 space-y-5">

          {/* ── Quote strip ── */}
          <div className="flex items-center gap-6 bg-[#111827] border border-[#1f2937] rounded-xl px-5 py-4">
            <div>
              <div className="text-2xl font-bold text-white font-mono">{symbol}</div>
              <div className="text-xs text-gray-500 mt-0.5">
                {quote?.source === "polygon" ? "Polygon.io" : quote?.source === "alpha_vantage" ? "Alpha Vantage" : quote?.source === "yahoo_finance" ? "Yahoo Finance delayed" : "Market Data"}
              </div>
            </div>
            <div className="text-3xl font-bold font-mono text-white">{fmtPrice(quote?.price)}</div>
            <div className={cn("text-lg font-semibold font-mono", changeColor(changePct))}>
              {fmtPct(changePct)}
            </div>
            <div className="flex-1" />
            {/* Key stats */}
            {[
              { label: "Open",   value: fmtPrice(quote?.open) },
              { label: "High",   value: fmtPrice(quote?.high) },
              { label: "Low",    value: fmtPrice(quote?.low) },
              { label: "Volume", value: fmtVolume(quote?.volume) },
              { label: "RSI",    value: tech?.rsi ? tech.rsi.toFixed(1) : "—" },
              { label: "MACD",   value: tech?.macd != null ? tech.macd.toFixed(3) : "—" },
            ].map(({ label, value }) => (
              <div key={label} className="text-center">
                <div className="text-[10px] text-gray-500 uppercase tracking-wide">{label}</div>
                <div className="text-sm font-mono text-gray-200 mt-0.5">{value}</div>
              </div>
            ))}
          </div>

          <div className="flex items-start gap-2 bg-[#111827] border border-[#1f2937] rounded-xl px-4 py-3 text-xs text-gray-500">
            <Zap size={13} className="mt-0.5 flex-shrink-0 text-blue-400" />
            <span>Data sources: {providerSummary}. Options chains still require a configured Polygon or Tradier integration.</span>
          </div>

          {adaptive && (
            <div className="grid grid-cols-3 gap-5">
              <div className="col-span-2 bg-[#111827] border border-[#1f2937] rounded-xl p-4">
                <div className="flex items-center justify-between mb-3">
                  <div className="flex items-center gap-2 text-sm font-semibold text-white">
                    <BrainCircuit size={15} className="text-cyan-400" />
                    Adaptive Options Thesis
                  </div>
                  <span className="text-[10px] uppercase tracking-wide text-gray-500">
                    {adaptive.prediction.horizon_days} day review window
                  </span>
                </div>
                <div className="grid grid-cols-4 gap-3">
                  <div className={cn(
                    "rounded-lg border p-3",
                    adaptive.prediction.direction === "call"
                      ? "bg-green-900/15 border-green-800/40"
                      : adaptive.prediction.direction === "put"
                        ? "bg-red-900/15 border-red-800/40"
                        : "bg-gray-800/60 border-gray-700"
                  )}>
                    <div className="text-[10px] text-gray-500 uppercase tracking-wide">Prediction</div>
                    <div className={cn("mt-1 text-xl font-bold uppercase", directionColor(
                      adaptive.prediction.direction === "call" ? "bullish" : adaptive.prediction.direction === "put" ? "bearish" : "neutral"
                    ))}>
                      {adaptive.prediction.direction}
                    </div>
                  </div>
                  <div className="bg-[#1f2937] rounded-lg p-3">
                    <div className="text-[10px] text-gray-500 uppercase tracking-wide">Confidence</div>
                    <div className={cn("mt-1 text-xl font-bold font-mono", confidenceColor(adaptive.prediction.confidence))}>
                      {(adaptive.prediction.confidence * 100).toFixed(0)}%
                    </div>
                  </div>
                  <div className="bg-[#1f2937] rounded-lg p-3">
                    <div className="text-[10px] text-gray-500 uppercase tracking-wide">Target</div>
                    <div className="mt-1 text-xl font-bold font-mono text-gray-100">
                      {fmtPrice(adaptive.prediction.target_price)}
                    </div>
                  </div>
                  <div className="bg-[#1f2937] rounded-lg p-3">
                    <div className="text-[10px] text-gray-500 uppercase tracking-wide">Stop</div>
                    <div className="mt-1 text-xl font-bold font-mono text-gray-100">
                      {fmtPrice(adaptive.prediction.stop_loss)}
                    </div>
                  </div>
                </div>
                <div className="mt-4 grid grid-cols-2 gap-4">
                  <div>
                    <div className="flex items-center gap-2 text-xs font-semibold text-gray-300 mb-2">
                      <Target size={12} className="text-blue-400" />
                      Current Evidence
                    </div>
                    <div className="space-y-1.5">
                      {adaptive.prediction.rationale.slice(0, 4).map((item, i) => (
                        <div key={i} className="flex gap-2 text-xs text-gray-400">
                          <span className="text-cyan-500 mt-0.5">›</span>
                          <span>{item}</span>
                        </div>
                      ))}
                    </div>
                  </div>
                  <div>
                    <div className="text-xs font-semibold text-gray-300 mb-2">Learning Adjustment</div>
                    <div className="text-xs text-gray-400 leading-relaxed">
                      {adaptive.prediction.learning_adjustment.reason}
                    </div>
                    <div className="mt-2 flex gap-3 text-[11px] text-gray-500">
                      <span>Bull: {adaptive.prediction.raw_scores.bullish.toFixed(1)}</span>
                      <span>Bear: {adaptive.prediction.raw_scores.bearish.toFixed(1)}</span>
                      <span>Factor: {adaptive.prediction.learning_adjustment.factor.toFixed(2)}x</span>
                    </div>
                  </div>
                </div>
                {adaptive.prediction.risks.length > 0 && (
                  <div className="mt-3 border-t border-[#1f2937] pt-3 space-y-1">
                    {adaptive.prediction.risks.map((risk, i) => (
                      <div key={i} className="flex gap-2 text-xs text-yellow-600">
                        <AlertTriangle size={11} className="mt-0.5 flex-shrink-0" />
                        <span>{risk}</span>
                      </div>
                    ))}
                  </div>
                )}
              </div>

              <div className="bg-[#111827] border border-[#1f2937] rounded-xl p-4">
                <div className="flex items-center gap-2 text-sm font-semibold text-white mb-3">
                  <History size={14} className="text-blue-400" />
                  Past Analysis
                </div>
                <div className="grid grid-cols-2 gap-2 mb-3">
                  <div className="bg-[#1f2937] rounded-lg p-2 text-center">
                    <div className="text-[10px] text-gray-500 uppercase tracking-wide">Win Rate</div>
                    <div className={cn("text-lg font-bold font-mono", (adaptive.review.win_rate ?? 0) >= 50 ? "text-green-400" : "text-red-400")}>
                      {adaptive.review.win_rate == null ? "—" : `${adaptive.review.win_rate}%`}
                    </div>
                  </div>
                  <div className="bg-[#1f2937] rounded-lg p-2 text-center">
                    <div className="text-[10px] text-gray-500 uppercase tracking-wide">Journal</div>
                    <div className="text-lg font-bold font-mono text-gray-200">
                      {adaptive.review.completed}/{adaptive.review.pending}
                    </div>
                  </div>
                </div>
                <div className="space-y-2">
                  {adaptive.review.recent_predictions.slice(0, 4).map((p, i) => (
                    <div key={i} className="flex items-center justify-between border border-[#1f2937] rounded-lg px-2.5 py-2 text-xs">
                      <div>
                        <div className={cn("font-semibold uppercase", directionColor(p.direction === "call" ? "bullish" : p.direction === "put" ? "bearish" : "neutral"))}>
                          {p.direction}
                        </div>
                        <div className="text-gray-600">{new Date(p.created_at).toLocaleDateString()}</div>
                      </div>
                      <div className="text-right">
                        <div className={cn("font-mono", p.outcome_status === "win" ? "text-green-400" : p.outcome_status === "loss" ? "text-red-400" : "text-gray-400")}>
                          {p.outcome_status}
                        </div>
                        <div className="text-gray-600">{p.pnl_pct == null ? `${(p.confidence * 100).toFixed(0)}% conf` : `${p.pnl_pct.toFixed(1)}%`}</div>
                      </div>
                    </div>
                  ))}
                  {adaptive.review.recent_predictions.length === 0 && (
                    <p className="text-xs text-gray-600">No completed prediction history yet. Nexus will score predictions after their review window closes.</p>
                  )}
                </div>
                {adaptive.review.recent_mistakes[0]?.notes?.[0] && (
                  <div className="mt-3 border-t border-[#1f2937] pt-3 text-xs text-gray-500 leading-relaxed">
                    Last lesson: {adaptive.review.recent_mistakes[0].notes[0]}
                  </div>
                )}
              </div>
            </div>
          )}

          {/* ── Two-column layout ── */}
          <div className="grid grid-cols-3 gap-5">

            {/* Price chart — 2/3 width */}
            <div className="col-span-2 bg-[#111827] border border-[#1f2937] rounded-xl p-4">
              <div className="flex items-center justify-between mb-3">
                <div className="text-sm font-semibold text-white">Price Chart</div>
                <div className="flex items-center gap-3 text-[10px] text-gray-500">
                  <span className="flex items-center gap-1"><span className="w-3 h-0.5 bg-yellow-400 inline-block" /> SMA50</span>
                  <span className="flex items-center gap-1"><span className="w-3 h-0.5 bg-purple-400 inline-block" /> SMA200</span>
                  <span className="flex items-center gap-1"><span className="w-2 h-2 rounded-sm bg-green-500 inline-block" /> Support</span>
                  <span className="flex items-center gap-1"><span className="w-2 h-2 rounded-sm bg-red-500 inline-block" /> Resistance</span>
                </div>
              </div>
              {bars.length > 0 ? (
                <PriceChart
                  bars={bars}
                  sr={patterns?.support_resistance}
                  sma50={tech?.sma_50}
                  sma200={tech?.sma_200}
                  height={400}
                />
              ) : (
                <div className="h-64 flex items-center justify-center text-gray-600 text-sm">
                  No chart data — configure a market data API key
                </div>
              )}
            </div>

            {/* Right column */}
            <div className="space-y-4">

              {/* Trend & bias */}
              <div className="bg-[#111827] border border-[#1f2937] rounded-xl p-4">
                <div className="text-xs text-gray-500 uppercase tracking-wide mb-3">Market Bias</div>
                <div className="flex items-center gap-3">
                  <div className={cn(
                    "w-10 h-10 rounded-lg flex items-center justify-center",
                    patterns?.summary.bias === "bullish" ? "bg-green-900/40" :
                    patterns?.summary.bias === "bearish" ? "bg-red-900/40" : "bg-gray-800"
                  )}>
                    <TrendIcon size={20} className={directionColor(patterns?.summary.bias || "neutral")} />
                  </div>
                  <div>
                    <div className={cn("text-lg font-bold capitalize", directionColor(patterns?.summary.bias || "neutral"))}>
                      {patterns?.summary.bias || "—"}
                    </div>
                    <div className="text-xs text-gray-500 capitalize">
                      {patterns?.trend.trend} · strength {((patterns?.trend.strength || 0) * 100).toFixed(0)}%
                    </div>
                  </div>
                </div>
                <div className="mt-3 grid grid-cols-2 gap-2 text-xs">
                  <div className="bg-green-900/20 rounded-lg p-2 text-center">
                    <div className="text-green-400 font-bold text-lg">{patterns?.summary.bullish_signals ?? 0}</div>
                    <div className="text-gray-500">Bullish signals</div>
                  </div>
                  <div className="bg-red-900/20 rounded-lg p-2 text-center">
                    <div className="text-red-400 font-bold text-lg">{patterns?.summary.bearish_signals ?? 0}</div>
                    <div className="text-gray-500">Bearish signals</div>
                  </div>
                </div>
              </div>

              {/* Bollinger squeeze */}
              {patterns?.bollinger_squeeze && (
                <div className={cn(
                  "border rounded-xl p-3 text-xs",
                  patterns.bollinger_squeeze.squeeze
                    ? "bg-yellow-900/20 border-yellow-700/40"
                    : "bg-[#111827] border-[#1f2937]"
                )}>
                  <div className="flex items-center gap-2 mb-1">
                    {patterns.bollinger_squeeze.squeeze && <Zap size={12} className="text-yellow-400" />}
                    <span className="font-semibold text-gray-300">
                      {patterns.bollinger_squeeze.squeeze ? "⚡ BB Squeeze Active" : "Bollinger Bands"}
                    </span>
                  </div>
                  <p className="text-gray-500 leading-relaxed">{patterns.bollinger_squeeze.description}</p>
                  <div className="mt-1 text-gray-600">
                    Width: {patterns.bollinger_squeeze.current_width_pct.toFixed(2)}%
                  </div>
                </div>
              )}

              {/* Support / Resistance */}
              <div className="bg-[#111827] border border-[#1f2937] rounded-xl p-4">
                <div className="text-xs text-gray-500 uppercase tracking-wide mb-3">Key Levels</div>
                <div className="space-y-1.5">
                  {patterns?.support_resistance.resistance.slice(0, 3).map((lvl) => (
                    <div key={lvl} className="flex items-center justify-between text-xs">
                      <span className="text-red-400">Resistance</span>
                      <span className="font-mono text-gray-200">{fmtPrice(lvl)}</span>
                    </div>
                  ))}
                  <div className="border-t border-[#1f2937] my-1" />
                  {patterns?.support_resistance.support.slice(0, 3).map((lvl) => (
                    <div key={lvl} className="flex items-center justify-between text-xs">
                      <span className="text-green-400">Support</span>
                      <span className="font-mono text-gray-200">{fmtPrice(lvl)}</span>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          </div>

          {/* ── Patterns + Reasoning row ── */}
          <div className="grid grid-cols-2 gap-5">

            {/* Detected patterns */}
            <div className="bg-[#111827] border border-[#1f2937] rounded-xl p-4">
              <div className="flex items-center justify-between mb-3">
                <div className="text-sm font-semibold text-white">
                  Detected Patterns
                  {patterns?.patterns.length ? (
                    <span className="ml-2 text-xs bg-blue-600/20 text-blue-400 px-2 py-0.5 rounded-full">
                      {patterns.patterns.length}
                    </span>
                  ) : null}
                </div>
              </div>
              {!patterns?.patterns.length ? (
                <p className="text-xs text-gray-600">No significant patterns detected in current data.</p>
              ) : (
                <div className="space-y-2">
                  {(showAllPatterns ? patterns.patterns : patterns.patterns.slice(0, 4)).map((p, i) => (
                    <div key={i} className="border border-[#1f2937] rounded-lg p-3">
                      <div className="flex items-center justify-between mb-1">
                        <span className="text-sm font-medium text-white">{p.name}</span>
                        <div className="flex items-center gap-2">
                          <span className={cn("text-xs font-medium capitalize", directionColor(p.direction))}>
                            {p.direction}
                          </span>
                          <span className={cn("text-xs font-mono", confidenceColor(p.confidence))}>
                            {(p.confidence * 100).toFixed(0)}%
                          </span>
                        </div>
                      </div>
                      <p className="text-xs text-gray-500 leading-relaxed">{p.description}</p>
                      {p.target_price && (
                        <div className="mt-1.5 flex gap-3 text-xs">
                          <span className="text-green-400">Target: {fmtPrice(p.target_price)}</span>
                          {p.stop_loss && <span className="text-red-400">Stop: {fmtPrice(p.stop_loss)}</span>}
                        </div>
                      )}
                    </div>
                  ))}
                  {patterns.patterns.length > 4 && (
                    <button
                      onClick={() => setShowAllPatterns(!showAllPatterns)}
                      className="flex items-center gap-1 text-xs text-blue-400 hover:text-blue-300 mt-1"
                    >
                      {showAllPatterns ? <ChevronUp size={12} /> : <ChevronDown size={12} />}
                      {showAllPatterns ? "Show less" : `Show ${patterns.patterns.length - 4} more`}
                    </button>
                  )}
                </div>
              )}
            </div>

            {/* AI Reasoning */}
            <div className="bg-[#111827] border border-[#1f2937] rounded-xl p-4">
              <div className="text-sm font-semibold text-white mb-3">AI Reasoning</div>
              {!reasoning ? (
                <p className="text-xs text-gray-600">Configure an API key to enable AI reasoning.</p>
              ) : (
                <div className="space-y-3">
                  <div className={cn(
                    "rounded-lg p-3 text-sm font-medium",
                    reasoning.confidence >= 0.65 ? "bg-blue-900/20 text-blue-300" : "bg-gray-800 text-gray-300"
                  )}>
                    {reasoning.conclusion}
                  </div>
                  <div className="flex items-center gap-2 text-xs">
                    <span className="text-gray-500">Confidence:</span>
                    <div className="flex-1 bg-[#1f2937] rounded-full h-1.5">
                      <div
                        className={cn("h-1.5 rounded-full", reasoning.confidence >= 0.65 ? "bg-blue-500" : "bg-yellow-500")}
                        style={{ width: `${reasoning.confidence * 100}%` }}
                      />
                    </div>
                    <span className={cn("font-mono", confidenceColor(reasoning.confidence))}>
                      {(reasoning.confidence * 100).toFixed(0)}%
                    </span>
                  </div>
                  {reasoning.steps.slice(0, 4).map((step, i) => (
                    <div key={i} className="text-xs text-gray-400 flex gap-2">
                      <span className="text-blue-500 mt-0.5">›</span>
                      <span>{step.description}</span>
                    </div>
                  ))}
                  {reasoning.risks.length > 0 && (
                    <div className="border-t border-[#1f2937] pt-2 space-y-1">
                      {reasoning.risks.map((r, i) => (
                        <div key={i} className="flex gap-2 text-xs text-yellow-600">
                          <AlertTriangle size={11} className="mt-0.5 flex-shrink-0" />
                          <span>{r}</span>
                        </div>
                      ))}
                    </div>
                  )}
                  <p className="text-[10px] text-gray-600 border-t border-[#1f2937] pt-2 leading-relaxed">
                    {reasoning.disclaimer}
                  </p>
                </div>
              )}
            </div>
          </div>

          {/* ── RSI Divergences ── */}
          {patterns?.rsi_divergences && patterns.rsi_divergences.length > 0 && (
            <div className="bg-[#111827] border border-[#1f2937] rounded-xl p-4">
              <div className="text-sm font-semibold text-white mb-3">RSI Divergences</div>
              <div className="grid grid-cols-2 gap-3">
                {patterns.rsi_divergences.map((d, i) => (
                  <div key={i} className={cn(
                    "border rounded-lg p-3 text-xs",
                    d.direction === "bullish" ? "border-green-800/40 bg-green-900/10" : "border-red-800/40 bg-red-900/10"
                  )}>
                    <div className={cn("font-semibold mb-1 capitalize", directionColor(d.direction))}>
                      {d.type.replace(/_/g, " ")}
                    </div>
                    <p className="text-gray-400">{d.description}</p>
                    <div className="mt-1 text-gray-600">Confidence: {(d.confidence * 100).toFixed(0)}%</div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Disclaimer */}
          <div className="flex items-start gap-2 bg-yellow-900/10 border border-yellow-800/30 rounded-xl p-4 text-xs text-yellow-700">
            <AlertTriangle size={14} className="flex-shrink-0 mt-0.5" />
            <p>
              All analysis is for informational purposes only and does not constitute financial advice.
              Options trading involves substantial risk of loss. Past performance does not guarantee future results.
              Always conduct your own due diligence and consult a licensed financial advisor before trading.
            </p>
          </div>
        </div>
      )}
    </div>
  );
}
