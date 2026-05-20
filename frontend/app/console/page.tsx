"use client";

import { useState, useCallback, useEffect, Suspense } from "react";
import { useSearchParams } from "next/navigation";
import {
  Search, RefreshCw, TrendingUp, TrendingDown, Minus,
  AlertTriangle, ChevronDown, ChevronUp, Zap, BarChart2,
  BrainCircuit, Target, History, Globe, ExternalLink,
} from "lucide-react";
import { api, type FullAnalysis } from "@/lib/api";
import { AdvancedChart } from "@/components/charts/AdvancedChart";
import { StrategyRadarChart } from "@/components/charts/OptionsChart";
import { cn, fmtPrice, fmtPct, fmtVolume, changeColor, confidenceColor, directionColor } from "@/lib/utils";

const QUICK_SYMBOLS = ["AAPL", "TSLA", "NVDA", "SPY", "QQQ", "MSFT", "AMZN", "META"];

function ConsolePageInner() {
  const searchParams = useSearchParams();
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
        const active = res.providers.filter((p) => p.configured).map((p) => p.name).join(" → ");
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

  // Auto-load when Nexus navigates here with ?symbol=AAPL
  useEffect(() => {
    const sym = searchParams.get("symbol");
    if (sym) load(sym);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [searchParams]);

  const quote = data?.quote;
  const tech = data?.technicals;
  const patterns = data?.patterns;
  const reasoning = data?.reasoning;
  const adaptive = data?.adaptive_prediction;
  const bars = data?.chart_bars || [];
  const eventIntel = (data as any)?.event_intelligence;

  const changePct = quote?.change_pct ?? 0;
  const TrendIcon = patterns?.summary.bias === "bullish" ? TrendingUp
    : patterns?.summary.bias === "bearish" ? TrendingDown : Minus;

  // Build AI pattern explanation from reasoning
  const patternExplanation = reasoning?.conclusion
    ? `${reasoning.conclusion} (${reasoning.confidence_level} confidence, ${(reasoning.confidence * 100).toFixed(0)}%)`
    : undefined;

  return (
    <div className="flex flex-col h-full bg-[#0a0e1a]">
      {/* Header */}
      <div className="flex items-center gap-3 px-5 py-3 border-b border-[#1f2937] bg-[#111827] flex-shrink-0">
        <BarChart2 size={18} className="text-blue-400" />
        <span className="text-sm font-semibold text-white">Visual Console</span>
        <div className="flex-1" />
        <form onSubmit={(e) => { e.preventDefault(); load(input); }} className="flex items-center gap-2">
          <div className="relative">
            <Search size={13} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-gray-500" />
            <input
              value={input}
              onChange={(e) => setInput(e.target.value.toUpperCase())}
              placeholder="Symbol…"
              className="bg-[#1f2937] border border-[#374151] rounded-lg pl-8 pr-3 py-1.5 text-sm text-white placeholder-gray-600 w-28 focus:outline-none focus:border-blue-500"
            />
          </div>
          <button type="submit" disabled={loading}
            className="bg-blue-600 hover:bg-blue-500 disabled:opacity-50 text-white text-xs font-medium px-3 py-1.5 rounded-lg transition-colors">
            {loading ? <RefreshCw size={12} className="animate-spin" /> : "Analyze"}
          </button>
        </form>
        <div className="flex gap-1">
          {QUICK_SYMBOLS.map((s) => (
            <button key={s} onClick={() => load(s)}
              className={cn(
                "text-[10px] px-2 py-1 rounded font-mono transition-colors",
                symbol === s ? "bg-blue-600/30 text-blue-300 border border-blue-600/40" : "text-gray-500 hover:text-gray-300 hover:bg-[#1f2937]"
              )}>
              {s}
            </button>
          ))}
        </div>
      </div>

      {error && (
        <div className="mx-5 mt-4 flex items-center gap-2 bg-red-900/20 border border-red-800/40 rounded-xl px-4 py-3 text-sm text-red-400">
          <AlertTriangle size={14} /> {error}
        </div>
      )}

      {!data && !loading && !error && (
        <div className="flex-1 flex flex-col items-center justify-center gap-4 text-gray-600">
          <Zap size={40} className="text-blue-600/40" />
          <p className="text-sm">Enter a symbol above to begin analysis</p>
        </div>
      )}

      {loading && (
        <div className="flex-1 flex items-center justify-center">
          <div className="flex flex-col items-center gap-3 text-gray-500">
            <RefreshCw size={24} className="animate-spin text-blue-500" />
            <span className="text-sm">Fetching {symbol}…</span>
          </div>
        </div>
      )}

      {data && !loading && (
        <div className="flex-1 overflow-auto p-5 space-y-5">

          {/* Quote strip */}
          <div className="flex items-center gap-6 bg-[#111827] border border-[#1f2937] rounded-xl px-5 py-4">
            <div>
              <div className="text-2xl font-bold text-white font-mono">{symbol}</div>
              <div className="text-xs text-gray-500 mt-0.5">
                {quote?.source === "polygon" ? "Polygon.io" : quote?.source === "alpha_vantage" ? "Alpha Vantage" : "Yahoo Finance (delayed)"}
              </div>
            </div>
            <div className="text-3xl font-bold font-mono text-white">{fmtPrice(quote?.price)}</div>
            <div className={cn("text-lg font-semibold font-mono", changeColor(changePct))}>{fmtPct(changePct)}</div>
            <div className="flex-1" />
            {[
              { label: "Open",   value: fmtPrice(quote?.open) },
              { label: "High",   value: fmtPrice(quote?.high) },
              { label: "Low",    value: fmtPrice(quote?.low) },
              { label: "Volume", value: fmtVolume(quote?.volume) },
              { label: "RSI",    value: tech?.rsi ? tech.rsi.toFixed(1) : "—" },
              { label: "MACD",   value: tech?.macd != null ? tech.macd.toFixed(3) : "—" },
              { label: "SMA50",  value: fmtPrice(tech?.sma_50) },
              { label: "SMA200", value: fmtPrice(tech?.sma_200) },
            ].map(({ label, value }) => (
              <div key={label} className="text-center">
                <div className="text-[10px] text-gray-500 uppercase tracking-wide">{label}</div>
                <div className="text-sm font-mono text-gray-200 mt-0.5">{value}</div>
              </div>
            ))}
          </div>

          {/* Data source notice */}
          <div className="flex items-center gap-2 bg-[#111827] border border-[#1f2937] rounded-xl px-4 py-2.5 text-xs text-gray-500">
            <Zap size={12} className="text-blue-400 flex-shrink-0" />
            <span>Data: {providerSummary}</span>
          </div>

          {/* Adaptive prediction + review */}
          {adaptive && (
            <div className="grid grid-cols-3 gap-5">
              <div className="col-span-2 bg-[#111827] border border-[#1f2937] rounded-xl p-4">
                <div className="flex items-center justify-between mb-3">
                  <div className="flex items-center gap-2 text-sm font-semibold text-white">
                    <BrainCircuit size={15} className="text-cyan-400" />
                    Nexus Prediction
                  </div>
                  <span className="text-[10px] text-gray-500">{adaptive.prediction.horizon_days}-day window</span>
                </div>
                <div className="grid grid-cols-4 gap-3 mb-4">
                  {[
                    {
                      label: "Direction",
                      value: adaptive.prediction.direction.toUpperCase(),
                      color: adaptive.prediction.direction === "call" ? "text-green-400" : adaptive.prediction.direction === "put" ? "text-red-400" : "text-gray-400",
                      bg: adaptive.prediction.direction === "call" ? "bg-green-900/15 border-green-800/40" : adaptive.prediction.direction === "put" ? "bg-red-900/15 border-red-800/40" : "bg-gray-800/60 border-gray-700",
                    },
                    { label: "Confidence", value: `${(adaptive.prediction.confidence * 100).toFixed(0)}%`, color: confidenceColor(adaptive.prediction.confidence), bg: "bg-[#1f2937] border-[#374151]" },
                    { label: "Target",     value: fmtPrice(adaptive.prediction.target_price),  color: "text-green-400", bg: "bg-[#1f2937] border-[#374151]" },
                    { label: "Stop",       value: fmtPrice(adaptive.prediction.stop_loss),     color: "text-red-400",   bg: "bg-[#1f2937] border-[#374151]" },
                  ].map(({ label, value, color, bg }) => (
                    <div key={label} className={cn("rounded-xl border p-3", bg)}>
                      <div className="text-[10px] text-gray-500 uppercase tracking-wide">{label}</div>
                      <div className={cn("mt-1 text-xl font-bold font-mono", color)}>{value}</div>
                    </div>
                  ))}
                </div>
                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <div className="text-xs font-semibold text-gray-400 mb-2 flex items-center gap-1.5">
                      <Target size={11} className="text-blue-400" /> Evidence
                    </div>
                    <ul className="space-y-1.5">
                      {adaptive.prediction.rationale.slice(0, 5).map((r, i) => (
                        <li key={i} className="flex gap-2 text-xs text-gray-400">
                          <span className="text-cyan-500 mt-0.5 flex-shrink-0">›</span>{r}
                        </li>
                      ))}
                    </ul>
                  </div>
                  <div>
                    <div className="text-xs font-semibold text-gray-400 mb-2">Learning Adjustment</div>
                    <p className="text-xs text-gray-400 leading-relaxed">{adaptive.prediction.learning_adjustment.reason}</p>
                    <div className="mt-2 flex gap-3 text-[10px] text-gray-600">
                      <span>Bull {adaptive.prediction.raw_scores.bullish.toFixed(1)}</span>
                      <span>Bear {adaptive.prediction.raw_scores.bearish.toFixed(1)}</span>
                      <span>×{adaptive.prediction.learning_adjustment.factor.toFixed(2)}</span>
                    </div>
                  </div>
                </div>
                {adaptive.prediction.risks.length > 0 && (
                  <div className="mt-3 pt-3 border-t border-[#1f2937] space-y-1">
                    {adaptive.prediction.risks.map((r, i) => (
                      <div key={i} className="flex gap-2 text-xs text-yellow-600">
                        <AlertTriangle size={10} className="mt-0.5 flex-shrink-0" />{r}
                      </div>
                    ))}
                  </div>
                )}
              </div>

              {/* Prediction history mini */}
              <div className="bg-[#111827] border border-[#1f2937] rounded-xl p-4">
                <div className="flex items-center gap-2 text-sm font-semibold text-white mb-3">
                  <History size={14} className="text-blue-400" /> Track Record
                </div>
                <div className="grid grid-cols-2 gap-2 mb-3">
                  <div className="bg-[#1f2937] rounded-xl p-2 text-center">
                    <div className="text-[10px] text-gray-500">Win Rate</div>
                    <div className={cn("text-xl font-bold font-mono", (adaptive.review.win_rate ?? 0) >= 50 ? "text-green-400" : "text-red-400")}>
                      {adaptive.review.win_rate == null ? "—" : `${adaptive.review.win_rate}%`}
                    </div>
                  </div>
                  <div className="bg-[#1f2937] rounded-xl p-2 text-center">
                    <div className="text-[10px] text-gray-500">Reviewed</div>
                    <div className="text-xl font-bold font-mono text-gray-200">{adaptive.review.completed}</div>
                  </div>
                </div>
                <div className="space-y-1.5">
                  {adaptive.review.recent_predictions.slice(0, 5).map((p, i) => (
                    <div key={i} className="flex items-center justify-between border border-[#1f2937] rounded-lg px-2.5 py-1.5 text-xs">
                      <div>
                        <span className={cn("font-semibold uppercase text-[10px]",
                          p.direction === "call" ? "text-green-400" : p.direction === "put" ? "text-red-400" : "text-gray-400")}>
                          {p.direction}
                        </span>
                        <div className="text-gray-600 text-[9px]">{new Date(p.created_at).toLocaleDateString()}</div>
                      </div>
                      <div className="text-right">
                        <div className={cn("font-mono text-[10px]",
                          p.outcome_status === "win" ? "text-green-400" : p.outcome_status === "loss" ? "text-red-400" : "text-gray-500")}>
                          {p.outcome_status}
                        </div>
                        <div className="text-gray-600 text-[9px]">
                          {p.pnl_pct != null ? `${p.pnl_pct >= 0 ? "+" : ""}${p.pnl_pct.toFixed(1)}%` : `${(p.confidence * 100).toFixed(0)}% conf`}
                        </div>
                      </div>
                    </div>
                  ))}
                  {adaptive.review.recent_predictions.length === 0 && (
                    <p className="text-xs text-gray-600 leading-relaxed">No completed predictions yet. Nexus scores each prediction after its review window closes.</p>
                  )}
                </div>
                {adaptive.review.recent_mistakes[0]?.notes?.[0] && (
                  <div className="mt-3 pt-3 border-t border-[#1f2937] text-xs text-gray-500 leading-relaxed">
                    <span className="text-yellow-600 font-medium">Last lesson: </span>
                    {adaptive.review.recent_mistakes[0].notes[0]}
                  </div>
                )}
              </div>
            </div>
          )}

          {/* Advanced chart + right column */}
          <div className="grid grid-cols-3 gap-5">
            <div className="col-span-2 bg-[#111827] border border-[#1f2937] rounded-xl p-4">
              <div className="text-sm font-semibold text-white mb-3">Advanced Chart — {symbol}</div>
              {bars.length > 0 ? (
                <AdvancedChart
                  bars={bars}
                  sr={patterns?.support_resistance}
                  patterns={patterns?.patterns}
                  sma50={tech?.sma_50}
                  sma200={tech?.sma_200}
                  symbol={symbol}
                  patternExplanation={patternExplanation}
                />
              ) : (
                <div className="h-64 flex items-center justify-center text-gray-600 text-sm">
                  No chart data — configure a market data API key
                </div>
              )}
            </div>

            {/* Right column */}
            <div className="space-y-4">
              {/* Bias */}
              <div className="bg-[#111827] border border-[#1f2937] rounded-xl p-4">
                <div className="text-xs text-gray-500 uppercase tracking-wide mb-3">Market Bias</div>
                <div className="flex items-center gap-3">
                  <div className={cn("w-10 h-10 rounded-xl flex items-center justify-center",
                    patterns?.summary.bias === "bullish" ? "bg-green-900/40" : patterns?.summary.bias === "bearish" ? "bg-red-900/40" : "bg-gray-800")}>
                    <TrendIcon size={20} className={directionColor(patterns?.summary.bias || "neutral")} />
                  </div>
                  <div>
                    <div className={cn("text-lg font-bold capitalize", directionColor(patterns?.summary.bias || "neutral"))}>
                      {patterns?.summary.bias || "—"}
                    </div>
                    <div className="text-xs text-gray-500 capitalize">
                      {patterns?.trend.trend} · {((patterns?.trend.strength || 0) * 100).toFixed(0)}% strength
                    </div>
                  </div>
                </div>
                <div className="mt-3 grid grid-cols-2 gap-2 text-xs">
                  <div className="bg-green-900/20 rounded-xl p-2 text-center">
                    <div className="text-green-400 font-bold text-lg">{patterns?.summary.bullish_signals ?? 0}</div>
                    <div className="text-gray-500">Bullish</div>
                  </div>
                  <div className="bg-red-900/20 rounded-xl p-2 text-center">
                    <div className="text-red-400 font-bold text-lg">{patterns?.summary.bearish_signals ?? 0}</div>
                    <div className="text-gray-500">Bearish</div>
                  </div>
                </div>
              </div>

              {/* Bollinger squeeze */}
              {patterns?.bollinger_squeeze && (
                <div className={cn("border rounded-xl p-3 text-xs",
                  patterns.bollinger_squeeze.squeeze ? "bg-yellow-900/20 border-yellow-700/40" : "bg-[#111827] border-[#1f2937]")}>
                  <div className="flex items-center gap-2 mb-1">
                    {patterns.bollinger_squeeze.squeeze && <Zap size={12} className="text-yellow-400" />}
                    <span className="font-semibold text-gray-300">
                      {patterns.bollinger_squeeze.squeeze ? "BB Squeeze Active" : "Bollinger Bands"}
                    </span>
                  </div>
                  <p className="text-gray-500 leading-relaxed">{patterns.bollinger_squeeze.description}</p>
                  <div className="mt-1 text-gray-600">Width: {patterns.bollinger_squeeze.current_width_pct.toFixed(2)}%</div>
                </div>
              )}

              {/* Event intelligence mini */}
              {eventIntel?.composite && (
                <div className={cn("border rounded-xl p-3",
                  eventIntel.composite.bias === "bullish" ? "bg-green-900/10 border-green-800/30" :
                  eventIntel.composite.bias === "bearish" ? "bg-red-900/10 border-red-800/30" :
                  "bg-yellow-900/10 border-yellow-800/30")}>
                  <div className="flex items-center gap-2 mb-2">
                    <Globe size={12} className="text-blue-400" />
                    <span className="text-xs font-semibold text-gray-300">Event Intelligence</span>
                    <a href="/events" className="ml-auto text-[10px] text-blue-400 hover:text-blue-300 flex items-center gap-0.5">
                      <ExternalLink size={9} /> Details
                    </a>
                  </div>
                  <div className={cn("text-sm font-bold capitalize",
                    eventIntel.composite.bias === "bullish" ? "text-green-400" :
                    eventIntel.composite.bias === "bearish" ? "text-red-400" : "text-yellow-400")}>
                    {eventIntel.composite.bias === "bullish" ? "Call bias" :
                     eventIntel.composite.bias === "bearish" ? "Put bias" : "Volatility"}
                  </div>
                  <div className="text-[10px] text-gray-500 mt-0.5">
                    {Math.round((eventIntel.composite.confidence || 0) * 100)}% confidence · {eventIntel.events?.length ?? 0} events
                  </div>
                </div>
              )}

              {/* RSI divergences */}
              {patterns?.rsi_divergences && patterns.rsi_divergences.length > 0 && (
                <div className="bg-[#111827] border border-[#1f2937] rounded-xl p-3">
                  <div className="text-xs font-semibold text-gray-400 mb-2">RSI Divergences</div>
                  {patterns.rsi_divergences.slice(0, 2).map((d, i) => (
                    <div key={i} className="text-xs text-gray-400 flex gap-2 mb-1">
                      <span className={cn("font-medium", d.direction === "bullish" ? "text-green-400" : "text-red-400")}>{d.type}</span>
                      <span>{d.description}</span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>

          {/* Reasoning */}
          {reasoning && (
            <div className="bg-[#111827] border border-[#1f2937] rounded-xl p-4">
              <div className="flex items-center justify-between mb-3">
                <div className="flex items-center gap-2 text-sm font-semibold text-white">
                  <BrainCircuit size={14} className="text-purple-400" /> Structured Reasoning
                </div>
                <span className={cn("text-xs font-semibold px-2 py-0.5 rounded-full border",
                  reasoning.confidence >= 0.65 ? "text-green-400 bg-green-900/20 border-green-800/30" :
                  reasoning.confidence >= 0.4 ? "text-yellow-400 bg-yellow-900/20 border-yellow-800/30" :
                  "text-gray-400 bg-gray-900/20 border-gray-800/30")}>
                  {reasoning.confidence_level} · {(reasoning.confidence * 100).toFixed(0)}%
                </span>
              </div>
              <p className="text-sm text-gray-300 mb-3 leading-relaxed">{reasoning.conclusion}</p>
              <div className="grid grid-cols-2 gap-4">
                <div className="space-y-2">
                  {reasoning.steps.slice(0, 3).map((step: any, i: number) => (
                    <div key={i} className="border border-[#1f2937] rounded-lg p-2.5">
                      <div className="text-xs font-medium text-gray-300 mb-1">{step.description}</div>
                      {step.evidence.slice(0, 2).map((e: string, j: number) => (
                        <div key={j} className="text-[11px] text-gray-500 flex gap-1.5">
                          <span className="text-blue-500">›</span>{e}
                        </div>
                      ))}
                    </div>
                  ))}
                </div>
                <div className="space-y-1.5">
                  {reasoning.risks.slice(0, 4).map((r: string, i: number) => (
                    <div key={i} className="flex gap-2 text-xs text-yellow-600">
                      <AlertTriangle size={10} className="mt-0.5 flex-shrink-0" />{r}
                    </div>
                  ))}
                </div>
              </div>
            </div>
          )}

          {/* Disclaimer */}
          <div className="flex items-start gap-2 bg-yellow-900/10 border border-yellow-800/20 rounded-xl p-4 text-xs text-yellow-700">
            <AlertTriangle size={13} className="flex-shrink-0 mt-0.5" />
            <p>All analysis is for informational purposes only and does not constitute financial advice.
              Options trading involves substantial risk of loss. Past performance does not guarantee future results.
              Always conduct your own due diligence and consult a licensed financial advisor before trading.</p>
          </div>
        </div>
      )}
    </div>
  );
}

export default function ConsolePage() {
  return (
    <Suspense fallback={
      <div className="flex items-center justify-center h-full bg-[#0a0e1a]">
        <div className="text-gray-500 text-sm">Loading…</div>
      </div>
    }>
      <ConsolePageInner />
    </Suspense>
  );
}
