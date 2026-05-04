"use client";

import { useState, useEffect, useCallback } from "react";
import { Plus, Trash2, RefreshCw, Star, AlertTriangle, TrendingUp, TrendingDown } from "lucide-react";
import { api, type Quote } from "@/lib/api";
import { getSessionId, cn, fmtPrice, fmtPct, fmtVolume, changeColor } from "@/lib/utils";

const DEFAULT_SYMBOLS = ["AAPL", "TSLA", "NVDA", "SPY", "QQQ"];

export default function WatchlistPage() {
  const [sessionId] = useState(() => getSessionId());
  const [quotes, setQuotes] = useState<Quote[]>([]);
  const [symbols, setSymbols] = useState<string[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [refreshing, setRefreshing] = useState(false);

  const loadWatchlist = useCallback(async () => {
    setLoading(true);
    try {
      const res = await api.getWatchlist(sessionId);
      if (res.symbols.length === 0) {
        // Seed defaults on first load
        for (const s of DEFAULT_SYMBOLS) {
          await api.addToWatchlist(sessionId, s);
        }
        const res2 = await api.getWatchlist(sessionId);
        setSymbols(res2.symbols);
        setQuotes(res2.quotes);
      } else {
        setSymbols(res.symbols);
        setQuotes(res.quotes);
      }
    } catch {}
    setLoading(false);
  }, [sessionId]);

  useEffect(() => { loadWatchlist(); }, [loadWatchlist]);

  const refresh = async () => {
    setRefreshing(true);
    try {
      const res = await api.getWatchlist(sessionId);
      setQuotes(res.quotes);
    } catch {}
    setRefreshing(false);
  };

  const add = async () => {
    const sym = input.trim().toUpperCase();
    if (!sym || symbols.includes(sym)) return;
    await api.addToWatchlist(sessionId, sym);
    setInput("");
    await refresh();
  };

  const remove = async (sym: string) => {
    await api.removeFromWatchlist(sessionId, sym);
    setSymbols((s) => s.filter((x) => x !== sym));
    setQuotes((q) => q.filter((x) => x.symbol !== sym));
  };

  return (
    <div className="flex flex-col h-full bg-[#0a0e1a] overflow-auto">
      <div className="flex items-center gap-3 px-5 py-3 border-b border-[#1f2937] bg-[#111827]">
        <Star size={16} className="text-blue-400" />
        <span className="text-sm font-semibold text-white">Watchlist</span>
        <div className="flex-1" />
        <button
          onClick={refresh}
          disabled={refreshing}
          className="flex items-center gap-1.5 text-xs text-gray-500 hover:text-gray-300 transition-colors"
        >
          <RefreshCw size={12} className={refreshing ? "animate-spin" : ""} /> Refresh
        </button>
      </div>

      <div className="p-5 space-y-4">
        {/* Add symbol */}
        <div className="flex gap-2">
          <input
            value={input}
            onChange={(e) => setInput(e.target.value.toUpperCase())}
            onKeyDown={(e) => e.key === "Enter" && add()}
            placeholder="Add symbol…"
            className="bg-[#111827] border border-[#1f2937] rounded-lg px-3 py-2 text-sm text-white placeholder-gray-600 w-36 focus:outline-none focus:border-blue-500"
          />
          <button
            onClick={add}
            className="bg-blue-600 hover:bg-blue-500 text-white text-sm px-3 py-2 rounded-lg flex items-center gap-1.5 transition-colors"
          >
            <Plus size={13} /> Add
          </button>
        </div>

        {loading ? (
          <div className="flex items-center gap-2 text-gray-500 text-sm">
            <RefreshCw size={14} className="animate-spin" /> Loading…
          </div>
        ) : (
          <div className="bg-[#111827] border border-[#1f2937] rounded-xl overflow-hidden">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-[#1f2937] text-xs text-gray-500">
                  <th className="text-left px-4 py-3 font-medium">Symbol</th>
                  <th className="text-right px-4 py-3 font-medium">Price</th>
                  <th className="text-right px-4 py-3 font-medium">Change</th>
                  <th className="text-right px-4 py-3 font-medium">Volume</th>
                  <th className="text-right px-4 py-3 font-medium">High</th>
                  <th className="text-right px-4 py-3 font-medium">Low</th>
                  <th className="px-4 py-3" />
                </tr>
              </thead>
              <tbody>
                {quotes.map((q) => (
                  <tr key={q.symbol} className="border-b border-[#1f2937]/50 hover:bg-[#1f2937]/30 transition-colors">
                    <td className="px-4 py-3">
                      <div className="flex items-center gap-2">
                        <div className={cn(
                          "w-1.5 h-1.5 rounded-full live-dot",
                          (q.change_pct ?? 0) >= 0 ? "bg-green-400" : "bg-red-400"
                        )} />
                        <span className="font-bold font-mono text-white">{q.symbol}</span>
                      </div>
                    </td>
                    <td className="px-4 py-3 text-right font-mono text-white">{fmtPrice(q.price)}</td>
                    <td className={cn("px-4 py-3 text-right font-mono font-semibold", changeColor(q.change_pct))}>
                      <div className="flex items-center justify-end gap-1">
                        {(q.change_pct ?? 0) >= 0 ? <TrendingUp size={11} /> : <TrendingDown size={11} />}
                        {fmtPct(q.change_pct)}
                      </div>
                    </td>
                    <td className="px-4 py-3 text-right font-mono text-gray-400">{fmtVolume(q.volume)}</td>
                    <td className="px-4 py-3 text-right font-mono text-green-400">{fmtPrice(q.high)}</td>
                    <td className="px-4 py-3 text-right font-mono text-red-400">{fmtPrice(q.low)}</td>
                    <td className="px-4 py-3 text-right">
                      <button
                        onClick={() => remove(q.symbol)}
                        className="text-gray-600 hover:text-red-400 transition-colors"
                      >
                        <Trash2 size={13} />
                      </button>
                    </td>
                  </tr>
                ))}
                {quotes.length === 0 && (
                  <tr>
                    <td colSpan={7} className="px-4 py-8 text-center text-gray-600 text-sm">
                      No symbols in watchlist. Add one above.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        )}

        <div className="flex items-start gap-2 bg-yellow-900/10 border border-yellow-800/30 rounded-xl p-4 text-xs text-yellow-700">
          <AlertTriangle size={14} className="flex-shrink-0 mt-0.5" />
          Prices shown are delayed or simulated depending on your configured data provider.
          Not financial advice.
        </div>
      </div>
    </div>
  );
}
