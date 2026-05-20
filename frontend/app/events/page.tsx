"use client";

/**
 * Event Monitor — real-world news, geopolitical, macro, and social events
 * that could influence specific stocks, with Nexus call/put analysis.
 */

import { useState, useCallback } from "react";
import {
  Globe, RefreshCw, AlertTriangle, TrendingUp, TrendingDown,
  Zap, Newspaper, Activity, ChevronDown, ChevronUp, ExternalLink,
  Search, Plus, X,
} from "lucide-react";
import { api, type EventIntelligenceResponse } from "@/lib/api";
import { cn } from "@/lib/utils";

const CATEGORY_ICONS: Record<string, React.ReactNode> = {
  earnings:      <Activity size={12} />,
  macro:         <Globe size={12} />,
  geopolitical:  <AlertTriangle size={12} />,
  regulatory:    <AlertTriangle size={12} />,
  product:       <Zap size={12} />,
  analyst:       <TrendingUp size={12} />,
  social_trend:  <Activity size={12} />,
  options_flow:  <TrendingUp size={12} />,
  unknown:       <Newspaper size={12} />,
};

const CATEGORY_COLORS: Record<string, string> = {
  earnings:     "text-blue-400 bg-blue-900/30 border-blue-800/40",
  macro:        "text-purple-400 bg-purple-900/30 border-purple-800/40",
  geopolitical: "text-red-400 bg-red-900/30 border-red-800/40",
  regulatory:   "text-orange-400 bg-orange-900/30 border-orange-800/40",
  product:      "text-cyan-400 bg-cyan-900/30 border-cyan-800/40",
  analyst:      "text-green-400 bg-green-900/30 border-green-800/40",
  social_trend: "text-pink-400 bg-pink-900/30 border-pink-800/40",
  options_flow: "text-yellow-400 bg-yellow-900/30 border-yellow-800/40",
  unknown:      "text-gray-400 bg-gray-900/30 border-gray-800/40",
};

const BIAS_CONFIG = {
  bullish:    { label: "CALL bias", color: "text-green-400", bg: "bg-green-900/20 border-green-800/30", icon: <TrendingUp size={12} /> },
  bearish:    { label: "PUT bias",  color: "text-red-400",   bg: "bg-red-900/20 border-red-800/30",   icon: <TrendingDown size={12} /> },
  volatility: { label: "Vol spike", color: "text-yellow-400", bg: "bg-yellow-900/20 border-yellow-800/30", icon: <Activity size={12} /> },
  neutral:    { label: "Neutral",   color: "text-gray-400",  bg: "bg-gray-900/20 border-gray-800/30",  icon: <Activity size={12} /> },
};

const DEFAULT_SYMBOLS = ["AAPL", "TSLA", "NVDA", "SPY", "QQQ"];

function EventCard({ event, expanded, onToggle }: {
  event: any;
  expanded: boolean;
  onToggle: () => void;
}) {
  const catColor = CATEGORY_COLORS[event.category] || CATEGORY_COLORS.unknown;
  const biasConf = BIAS_CONFIG[event.option_bias as keyof typeof BIAS_CONFIG] || BIAS_CONFIG.neutral;

  return (
    <div className="border border-[#1f2937] rounded-xl overflow-hidden hover:border-[#374151] transition-colors">
      <button
        onClick={onToggle}
        className="w-full flex items-start gap-3 px-4 py-3 text-left hover:bg-[#111827]/50 transition-colors"
      >
        {/* Category badge */}
        <span className={cn("flex items-center gap-1 text-[10px] px-2 py-0.5 rounded-full border font-medium flex-shrink-0 mt-0.5", catColor)}>
          {CATEGORY_ICONS[event.category] || CATEGORY_ICONS.unknown}
          {event.category}
        </span>

        <div className="flex-1 min-w-0">
          <div className="text-sm text-gray-200 font-medium leading-snug line-clamp-2">{event.title}</div>
          <div className="flex items-center gap-3 mt-1">
            <span className="text-[10px] text-gray-600">{event.source} · {new Date(event.event_time).toLocaleDateString()}</span>
            {event.sentiment_score !== undefined && (
              <span className={cn("text-[10px] font-mono", event.sentiment_score > 0.1 ? "text-green-400" : event.sentiment_score < -0.1 ? "text-red-400" : "text-gray-500")}>
                sentiment {event.sentiment_score > 0 ? "+" : ""}{event.sentiment_score?.toFixed(2)}
              </span>
            )}
          </div>
        </div>

        {/* Option bias */}
        <div className={cn("flex items-center gap-1 text-[10px] px-2 py-1 rounded-lg border font-semibold flex-shrink-0", biasConf.bg, biasConf.color)}>
          {biasConf.icon}
          {biasConf.label}
        </div>

        {expanded ? <ChevronUp size={14} className="text-gray-500 flex-shrink-0 mt-0.5" /> : <ChevronDown size={14} className="text-gray-500 flex-shrink-0 mt-0.5" />}
      </button>

      {expanded && (
        <div className="px-4 pb-4 space-y-3 border-t border-[#1f2937] bg-[#0d1117]/40">
          {event.summary && (
            <p className="text-xs text-gray-400 leading-relaxed pt-3">{event.summary}</p>
          )}

          {/* Nexus analysis */}
          {event.nexus_analysis && (
            <div className="bg-blue-900/10 border border-blue-800/20 rounded-lg p-3">
              <div className="flex items-center gap-1.5 text-[10px] text-blue-400 font-semibold mb-1.5">
                <Zap size={10} /> Nexus Analysis
              </div>
              <p className="text-xs text-gray-300 leading-relaxed">{event.nexus_analysis}</p>
            </div>
          )}

          {/* Historical analogues */}
          {event.historical_analogues?.count > 0 && (
            <div className="bg-[#111827] rounded-lg p-3">
              <div className="text-[10px] text-gray-500 font-semibold mb-2 uppercase tracking-wide">Historical Analogues</div>
              <div className="grid grid-cols-3 gap-3 text-center">
                <div>
                  <div className="text-lg font-bold text-white font-mono">{event.historical_analogues.count}</div>
                  <div className="text-[10px] text-gray-600">Similar events</div>
                </div>
                <div>
                  <div className={cn("text-lg font-bold font-mono", event.historical_analogues.call_win_rate >= 55 ? "text-green-400" : "text-red-400")}>
                    {event.historical_analogues.call_win_rate?.toFixed(0) ?? "—"}%
                  </div>
                  <div className="text-[10px] text-gray-600">Call win rate</div>
                </div>
                <div>
                  <div className={cn("text-lg font-bold font-mono", event.historical_analogues.put_win_rate >= 55 ? "text-green-400" : "text-red-400")}>
                    {event.historical_analogues.put_win_rate?.toFixed(0) ?? "—"}%
                  </div>
                  <div className="text-[10px] text-gray-600">Put win rate</div>
                </div>
              </div>
            </div>
          )}

          {event.url && (
            <a href={event.url} target="_blank" rel="noopener noreferrer"
              className="inline-flex items-center gap-1 text-[10px] text-blue-400 hover:text-blue-300 transition-colors">
              <ExternalLink size={10} /> Read source
            </a>
          )}
        </div>
      )}
    </div>
  );
}

function CompositeSignalBar({ intel }: { intel: EventIntelligenceResponse }) {
  const composite = intel.composite;
  if (!composite) return null;
  const biasConf = BIAS_CONFIG[composite.bias as keyof typeof BIAS_CONFIG] || BIAS_CONFIG.neutral;
  const pct = Math.round((composite.confidence || 0) * 100);

  return (
    <div className={cn("flex items-center gap-4 rounded-xl border p-4", biasConf.bg)}>
      <div className={cn("flex items-center gap-2 text-sm font-bold", biasConf.color)}>
        {biasConf.icon}
        {biasConf.label}
      </div>
      <div className="flex-1">
        <div className="flex items-center justify-between mb-1">
          <span className="text-[10px] text-gray-500">Composite confidence</span>
          <span className={cn("text-xs font-mono font-semibold", biasConf.color)}>{pct}%</span>
        </div>
        <div className="h-1.5 bg-[#1f2937] rounded-full overflow-hidden">
          <div
            className={cn("h-full rounded-full transition-all", composite.bias === "bullish" ? "bg-green-500" : composite.bias === "bearish" ? "bg-red-500" : "bg-yellow-500")}
            style={{ width: `${pct}%` }}
          />
        </div>
      </div>
      <div className="text-right">
        <div className="text-xs text-gray-400">{intel.events?.length ?? 0} events</div>
        <div className="text-[10px] text-gray-600">{intel.symbol}</div>
      </div>
    </div>
  );
}

export default function EventsPage() {
  const [symbols, setSymbols] = useState<string[]>(DEFAULT_SYMBOLS);
  const [newSymbol, setNewSymbol] = useState("");
  const [selected, setSelected] = useState("AAPL");
  const [intel, setIntel] = useState<EventIntelligenceResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [expanded, setExpanded] = useState<number | null>(null);

  const load = useCallback(async (sym: string) => {
    setSelected(sym);
    setLoading(true);
    setError(null);
    setExpanded(null);
    try {
      const res = await api.eventIntelligence(sym);
      setIntel(res);
    } catch (e: any) {
      setError(e.message || "Failed to load event intelligence");
    } finally {
      setLoading(false);
    }
  }, []);

  const addSymbol = () => {
    const s = newSymbol.trim().toUpperCase();
    if (s && !symbols.includes(s)) {
      setSymbols((prev) => [...prev, s]);
      setNewSymbol("");
      load(s);
    }
  };

  const removeSymbol = (s: string) => {
    setSymbols((prev) => prev.filter((x) => x !== s));
    if (selected === s && symbols.length > 1) {
      const next = symbols.find((x) => x !== s) || symbols[0];
      setSelected(next);
    }
  };

  return (
    <div className="flex flex-col h-full bg-[#0a0e1a] overflow-auto">
      {/* Header */}
      <div className="flex items-center gap-3 px-5 py-3 border-b border-[#1f2937] bg-[#111827] flex-shrink-0">
        <Globe size={16} className="text-blue-400" />
        <span className="text-sm font-semibold text-white">Event Monitor</span>
        <span className="text-[10px] text-gray-600 bg-[#1f2937] px-2 py-0.5 rounded-full">
          News · Geopolitical · Macro · Social
        </span>
        <div className="flex-1" />
        {loading && <RefreshCw size={13} className="animate-spin text-blue-400" />}
      </div>

      <div className="flex flex-1 overflow-hidden">
        {/* Symbol sidebar */}
        <div className="w-40 flex-shrink-0 border-r border-[#1f2937] bg-[#0d1117] flex flex-col">
          <div className="p-2 border-b border-[#1f2937]">
            <div className="flex gap-1">
              <input
                value={newSymbol}
                onChange={(e) => setNewSymbol(e.target.value.toUpperCase())}
                onKeyDown={(e) => e.key === "Enter" && addSymbol()}
                placeholder="Add symbol"
                className="flex-1 bg-[#1f2937] border border-[#374151] rounded px-2 py-1 text-xs text-white placeholder-gray-600 focus:outline-none focus:border-blue-500 min-w-0"
              />
              <button onClick={addSymbol} className="bg-blue-600 hover:bg-blue-500 text-white rounded p-1 transition-colors">
                <Plus size={12} />
              </button>
            </div>
          </div>
          <div className="flex-1 overflow-y-auto py-1">
            {symbols.map((s) => (
              <div key={s} className={cn(
                "flex items-center group px-3 py-2 cursor-pointer transition-colors",
                selected === s ? "bg-blue-600/20 text-blue-400" : "text-gray-400 hover:bg-[#1f2937] hover:text-gray-200"
              )}>
                <span className="flex-1 text-sm font-mono font-medium" onClick={() => load(s)}>{s}</span>
                <button
                  onClick={() => removeSymbol(s)}
                  className="opacity-0 group-hover:opacity-100 text-gray-600 hover:text-red-400 transition-all"
                >
                  <X size={10} />
                </button>
              </div>
            ))}
          </div>
        </div>

        {/* Main content */}
        <div className="flex-1 overflow-y-auto p-5 space-y-4">
          {!intel && !loading && !error && (
            <div className="flex flex-col items-center justify-center h-64 text-center">
              <Globe size={40} className="text-gray-700 mb-3" />
              <div className="text-gray-500 text-sm">Select a symbol to load event intelligence</div>
              <button
                onClick={() => load(selected)}
                className="mt-4 bg-blue-600 hover:bg-blue-500 text-white text-sm px-4 py-2 rounded-lg transition-colors"
              >
                Load {selected}
              </button>
            </div>
          )}

          {error && (
            <div className="flex items-center gap-2 bg-red-900/20 border border-red-800/40 rounded-xl px-4 py-3 text-sm text-red-400">
              <AlertTriangle size={14} /> {error}
            </div>
          )}

          {intel && (
            <>
              {/* Composite signal */}
              <CompositeSignalBar intel={intel} />

              {/* Source status */}
              {intel.source_status && intel.source_status.length > 0 && (
                <div className="flex gap-2 flex-wrap">
                  {intel.source_status.map((src: any) => (
                    <span key={src.name} className={cn(
                      "text-[10px] px-2 py-0.5 rounded-full border font-medium",
                      src.configured
                        ? "text-green-400 bg-green-900/20 border-green-800/30"
                        : "text-gray-600 bg-gray-900/20 border-gray-800/30"
                    )}>
                      {src.name} {src.configured ? "✓" : "—"}
                    </span>
                  ))}
                </div>
              )}

              {/* Events list */}
              {intel.events && intel.events.length > 0 ? (
                <div className="space-y-2">
                  <div className="text-xs font-semibold text-gray-500 uppercase tracking-wide">
                    {intel.events.length} Events for {intel.symbol}
                  </div>
                  {intel.events.map((event: any, i: number) => (
                    <EventCard
                      key={i}
                      event={event}
                      expanded={expanded === i}
                      onToggle={() => setExpanded(expanded === i ? null : i)}
                    />
                  ))}
                </div>
              ) : (
                <div className="flex flex-col items-center justify-center py-16 text-center">
                  <Newspaper size={32} className="text-gray-700 mb-3" />
                  <div className="text-gray-500 text-sm">No events found for {intel.symbol}</div>
                  <div className="text-gray-600 text-xs mt-1">
                    Configure API keys (Alpha Vantage, NewsAPI) for live event data
                  </div>
                </div>
              )}

              {intel.disclaimer && (
                <div className="flex items-start gap-2 bg-yellow-900/10 border border-yellow-800/20 rounded-xl p-3 text-xs text-yellow-700">
                  <AlertTriangle size={12} className="flex-shrink-0 mt-0.5" />
                  {intel.disclaimer}
                </div>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  );
}
