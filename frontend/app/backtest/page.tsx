"use client";

import { useState } from "react";
import { Play, RefreshCw, AlertTriangle, TrendingUp, TrendingDown } from "lucide-react";
import { api, type BacktestResult } from "@/lib/api";
import { BacktestEquityCurve } from "@/components/charts/OptionsChart";
import { cn, fmtPrice } from "@/lib/utils";

export default function BacktestPage() {
  const [form, setForm] = useState({
    symbol: "AAPL",
    option_type: "call",
    strike_offset_pct: 0.05,
    days_to_expiry: 30,
    iv_assumption: 0.30,
    years: 5,
  });
  const [result, setResult] = useState<BacktestResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const run = async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await api.backtest(form);
      setResult(res);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  };

  const set = (k: string, v: any) => setForm((f) => ({ ...f, [k]: v }));

  return (
    <div className="flex flex-col h-full bg-[#0a0e1a] overflow-auto">
      <div className="flex items-center gap-3 px-5 py-3 border-b border-[#1f2937] bg-[#111827]">
        <TrendingUp size={16} className="text-blue-400" />
        <span className="text-sm font-semibold text-white">Strategy Backtester</span>
      </div>

      <div className="p-5 space-y-5">
        {/* Config */}
        <div className="bg-[#111827] border border-[#1f2937] rounded-xl p-5">
          <div className="text-sm font-semibold text-white mb-4">Backtest Configuration</div>
          <div className="grid grid-cols-3 gap-4 mb-4">
            {[
              { label: "Symbol", key: "symbol", type: "text" },
              { label: "Option Type", key: "option_type", type: "select", options: ["call", "put"] },
              { label: "Strike Offset %", key: "strike_offset_pct", type: "number", step: 0.01, min: 0, max: 0.5 },
              { label: "Days to Expiry", key: "days_to_expiry", type: "number", step: 1, min: 1, max: 365 },
              { label: "IV Assumption", key: "iv_assumption", type: "number", step: 0.01, min: 0.05, max: 2 },
              { label: "Years of History", key: "years", type: "number", step: 1, min: 1, max: 50 },
            ].map(({ label, key, type, options, step, min, max }: any) => (
              <div key={key}>
                <label className="text-xs text-gray-500 mb-1 block">{label}</label>
                {type === "select" ? (
                  <select
                    value={(form as any)[key]}
                    onChange={(e) => set(key, e.target.value)}
                    className="w-full bg-[#1f2937] border border-[#374151] rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-blue-500"
                  >
                    {options.map((o: string) => <option key={o} value={o}>{o}</option>)}
                  </select>
                ) : (
                  <input
                    type={type}
                    value={(form as any)[key]}
                    onChange={(e) => set(key, type === "text" ? e.target.value.toUpperCase() : Number(e.target.value))}
                    step={step} min={min} max={max}
                    className="w-full bg-[#1f2937] border border-[#374151] rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-blue-500"
                  />
                )}
              </div>
            ))}
          </div>
          <button
            onClick={run}
            disabled={loading}
            className="bg-blue-600 hover:bg-blue-500 disabled:opacity-50 text-white text-sm px-5 py-2.5 rounded-lg flex items-center gap-2 transition-colors"
          >
            {loading ? <RefreshCw size={13} className="animate-spin" /> : <Play size={13} />}
            Run Backtest
          </button>
        </div>

        {error && (
          <div className="flex items-center gap-2 bg-red-900/20 border border-red-800/40 rounded-lg px-4 py-3 text-sm text-red-400">
            <AlertTriangle size={14} /> {error}
          </div>
        )}

        {result && (
          <>
            {/* Summary stats */}
            <div className="bg-[#111827] border border-[#1f2937] rounded-xl p-5">
              <div className="text-sm font-semibold text-white mb-1">{result.strategy}</div>
              <div className="text-xs text-gray-500 mb-4">{result.total_trades} trades over {form.years} years</div>
              <div className="grid grid-cols-4 gap-3 mb-5">
                {[
                  { label: "Win Rate", value: `${result.win_rate}%`, color: result.win_rate >= 50 ? "text-green-400" : "text-red-400" },
                  { label: "Avg Win", value: `+${result.avg_win_pct}%`, color: "text-green-400" },
                  { label: "Avg Loss", value: `${result.avg_loss_pct}%`, color: "text-red-400" },
                  { label: "Expectancy", value: `${result.expectancy_pct}%`, color: result.expectancy_pct >= 0 ? "text-green-400" : "text-red-400" },
                  { label: "Total Trades", value: result.total_trades, color: "text-gray-200" },
                  { label: "Wins", value: result.wins, color: "text-green-400" },
                  { label: "Losses", value: result.losses, color: "text-red-400" },
                  { label: "Total P&L/contract", value: `$${result.total_pnl_per_contract}`, color: result.total_pnl_per_contract >= 0 ? "text-green-400" : "text-red-400" },
                ].map(({ label, value, color }) => (
                  <div key={label} className="bg-[#1f2937] rounded-lg p-3 text-center">
                    <div className="text-[10px] text-gray-500 uppercase tracking-wide">{label}</div>
                    <div className={cn("text-lg font-bold font-mono mt-1", color)}>{value}</div>
                  </div>
                ))}
              </div>
              <BacktestEquityCurve trades={result.trades} />
            </div>

            {/* Trade log */}
            <div className="bg-[#111827] border border-[#1f2937] rounded-xl p-5">
              <div className="text-sm font-semibold text-white mb-3">Recent Trades (last 20)</div>
              <div className="overflow-x-auto">
                <table className="w-full text-xs">
                  <thead>
                    <tr className="text-gray-500 border-b border-[#1f2937]">
                      {["Entry", "Exit", "Strike", "Entry $", "Exit $", "Underlying In", "Underlying Out", "P&L %", "Result"].map((h) => (
                        <th key={h} className="text-left py-2 pr-4 font-medium">{h}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {result.trades.map((t, i) => (
                      <tr key={i} className="border-b border-[#1f2937]/50 hover:bg-[#1f2937]/30">
                        <td className="py-1.5 pr-4 text-gray-400">{t.entry_date}</td>
                        <td className="py-1.5 pr-4 text-gray-400">{t.exit_date}</td>
                        <td className="py-1.5 pr-4 font-mono">{fmtPrice(t.strike)}</td>
                        <td className="py-1.5 pr-4 font-mono">{t.entry_price.toFixed(3)}</td>
                        <td className="py-1.5 pr-4 font-mono">{t.exit_price.toFixed(3)}</td>
                        <td className="py-1.5 pr-4 font-mono">{fmtPrice(t.underlying_entry)}</td>
                        <td className="py-1.5 pr-4 font-mono">{fmtPrice(t.underlying_exit)}</td>
                        <td className={cn("py-1.5 pr-4 font-mono font-semibold", t.win ? "text-green-400" : "text-red-400")}>
                          {t.pnl_pct > 0 ? "+" : ""}{t.pnl_pct.toFixed(1)}%
                        </td>
                        <td className="py-1.5">
                          {t.win
                            ? <span className="text-green-400 flex items-center gap-1"><TrendingUp size={10} /> Win</span>
                            : <span className="text-red-400 flex items-center gap-1"><TrendingDown size={10} /> Loss</span>}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>

            <div className="flex items-start gap-2 bg-yellow-900/10 border border-yellow-800/30 rounded-xl p-4 text-xs text-yellow-700">
              <AlertTriangle size={14} className="flex-shrink-0 mt-0.5" />
              {result.disclaimer}
            </div>
          </>
        )}
      </div>
    </div>
  );
}
