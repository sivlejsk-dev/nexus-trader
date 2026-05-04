"use client";

import { useState } from "react";
import { Search, RefreshCw, AlertTriangle, Zap, TrendingUp } from "lucide-react";
import { api, type StrategyScore } from "@/lib/api";
import { StrategyRadarChart, GreeksSensitivityChart } from "@/components/charts/OptionsChart";
import { cn, fmtPrice, directionColor } from "@/lib/utils";

export default function ScannerPage() {
  const [symbol, setSymbol] = useState("AAPL");
  const [dte, setDte] = useState(30);
  const [strategies, setStrategies] = useState<StrategyScore[]>([]);
  const [meta, setMeta] = useState<any>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Greeks calculator state
  const [gSymbol, setGSymbol] = useState("AAPL");
  const [gStrike, setGStrike] = useState(200);
  const [gDte, setGDte] = useState(30);
  const [gIv, setGIv] = useState(0.3);
  const [gType, setGType] = useState<"call" | "put">("call");
  const [greeks, setGreeks] = useState<any>(null);
  const [gPrice, setGPrice] = useState(200);
  const [gLoading, setGLoading] = useState(false);

  const loadStrategies = async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await api.strategies(symbol, dte);
      setStrategies(res.strategies);
      setMeta(res);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  };

  const calcGreeks = async () => {
    setGLoading(true);
    try {
      const quote = await api.quote(gSymbol);
      const price = quote.price || gPrice;
      setGPrice(price);
      const res = await api.greeks({
        underlying_price: price,
        strike: gStrike,
        days_to_expiry: gDte,
        implied_volatility: gIv,
        option_type: gType,
      });
      setGreeks(res);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setGLoading(false);
    }
  };

  const scoreColor = (s: number) =>
    s >= 60 ? "text-green-400" : s >= 35 ? "text-yellow-400" : "text-gray-500";

  return (
    <div className="flex flex-col h-full bg-[#0a0e1a] overflow-auto">
      <div className="flex items-center gap-3 px-5 py-3 border-b border-[#1f2937] bg-[#111827]">
        <Zap size={16} className="text-blue-400" />
        <span className="text-sm font-semibold text-white">Options Scanner</span>
      </div>

      <div className="p-5 space-y-5">
        {/* Strategy scorer */}
        <div className="bg-[#111827] border border-[#1f2937] rounded-xl p-5">
          <div className="text-sm font-semibold text-white mb-4">Strategy Suitability Scorer</div>
          <div className="flex items-end gap-3 mb-4">
            <div>
              <label className="text-xs text-gray-500 mb-1 block">Symbol</label>
              <input
                value={symbol}
                onChange={(e) => setSymbol(e.target.value.toUpperCase())}
                className="bg-[#1f2937] border border-[#374151] rounded-lg px-3 py-2 text-sm text-white w-24 focus:outline-none focus:border-blue-500"
              />
            </div>
            <div>
              <label className="text-xs text-gray-500 mb-1 block">DTE</label>
              <input
                type="number"
                value={dte}
                onChange={(e) => setDte(Number(e.target.value))}
                min={1} max={365}
                className="bg-[#1f2937] border border-[#374151] rounded-lg px-3 py-2 text-sm text-white w-20 focus:outline-none focus:border-blue-500"
              />
            </div>
            <button
              onClick={loadStrategies}
              disabled={loading}
              className="bg-blue-600 hover:bg-blue-500 disabled:opacity-50 text-white text-sm px-4 py-2 rounded-lg flex items-center gap-2 transition-colors"
            >
              {loading ? <RefreshCw size={13} className="animate-spin" /> : <Search size={13} />}
              Score Strategies
            </button>
          </div>

          {error && (
            <div className="flex items-center gap-2 text-red-400 text-xs mb-3">
              <AlertTriangle size={12} /> {error}
            </div>
          )}

          {strategies.length > 0 && (
            <div className="grid grid-cols-2 gap-5">
              <div className="space-y-2">
                {strategies.map((s, i) => (
                  <div key={i} className="border border-[#1f2937] rounded-lg p-3">
                    <div className="flex items-center justify-between mb-1">
                      <span className="text-sm font-medium text-white">{s.name}</span>
                      <div className="flex items-center gap-2">
                        <span className={cn("text-xs capitalize", directionColor(s.direction.split("/")[0]))}>
                          {s.direction}
                        </span>
                        <span className={cn("text-sm font-bold font-mono", scoreColor(s.score))}>
                          {s.score.toFixed(0)}
                        </span>
                      </div>
                    </div>
                    {/* Score bar */}
                    <div className="w-full bg-[#1f2937] rounded-full h-1 mb-2">
                      <div
                        className={cn("h-1 rounded-full", s.score >= 60 ? "bg-green-500" : s.score >= 35 ? "bg-yellow-500" : "bg-gray-600")}
                        style={{ width: `${Math.min(s.score, 100)}%` }}
                      />
                    </div>
                    <div className="text-xs text-gray-500 space-y-0.5">
                      {s.rationale.map((r, j) => <div key={j}>· {r}</div>)}
                    </div>
                    <div className="mt-2 grid grid-cols-2 gap-1 text-[10px]">
                      <span className="text-gray-600">Max profit: <span className="text-gray-400">{s.max_profit}</span></span>
                      <span className="text-gray-600">Max loss: <span className="text-gray-400">{s.max_loss}</span></span>
                    </div>
                  </div>
                ))}
              </div>
              <StrategyRadarChart strategies={strategies} />
            </div>
          )}

          {meta?.disclaimer && (
            <p className="text-[10px] text-gray-600 mt-3 border-t border-[#1f2937] pt-3">{meta.disclaimer}</p>
          )}
        </div>

        {/* Greeks calculator */}
        <div className="bg-[#111827] border border-[#1f2937] rounded-xl p-5">
          <div className="text-sm font-semibold text-white mb-4">Black-Scholes Greeks Calculator</div>
          <div className="flex flex-wrap items-end gap-3 mb-4">
            {[
              { label: "Symbol", value: gSymbol, onChange: (v: string) => setGSymbol(v.toUpperCase()), type: "text", width: "w-20" },
              { label: "Strike ($)", value: gStrike, onChange: (v: string) => setGStrike(Number(v)), type: "number", width: "w-24" },
              { label: "DTE", value: gDte, onChange: (v: string) => setGDte(Number(v)), type: "number", width: "w-16" },
              { label: "IV (e.g. 0.30)", value: gIv, onChange: (v: string) => setGIv(Number(v)), type: "number", width: "w-24" },
            ].map(({ label, value, onChange, type, width }) => (
              <div key={label}>
                <label className="text-xs text-gray-500 mb-1 block">{label}</label>
                <input
                  type={type}
                  value={value}
                  onChange={(e) => onChange(e.target.value)}
                  step={type === "number" ? "any" : undefined}
                  className={cn("bg-[#1f2937] border border-[#374151] rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-blue-500", width)}
                />
              </div>
            ))}
            <div>
              <label className="text-xs text-gray-500 mb-1 block">Type</label>
              <select
                value={gType}
                onChange={(e) => setGType(e.target.value as "call" | "put")}
                className="bg-[#1f2937] border border-[#374151] rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-blue-500"
              >
                <option value="call">Call</option>
                <option value="put">Put</option>
              </select>
            </div>
            <button
              onClick={calcGreeks}
              disabled={gLoading}
              className="bg-blue-600 hover:bg-blue-500 disabled:opacity-50 text-white text-sm px-4 py-2 rounded-lg flex items-center gap-2 transition-colors"
            >
              {gLoading ? <RefreshCw size={13} className="animate-spin" /> : <TrendingUp size={13} />}
              Calculate
            </button>
          </div>

          {greeks && (
            <div className="grid grid-cols-2 gap-5">
              <div>
                <div className="grid grid-cols-3 gap-3 mb-3">
                  {[
                    { label: "Price", value: fmtPrice(greeks.greeks.price), color: "text-blue-400" },
                    { label: "Delta", value: greeks.greeks.delta?.toFixed(4), color: greeks.greeks.delta > 0 ? "text-green-400" : "text-red-400" },
                    { label: "Gamma", value: greeks.greeks.gamma?.toFixed(6), color: "text-yellow-400" },
                    { label: "Theta", value: greeks.greeks.theta?.toFixed(4), color: "text-red-400" },
                    { label: "Vega", value: greeks.greeks.vega?.toFixed(4), color: "text-purple-400" },
                    { label: "Rho", value: greeks.greeks.rho?.toFixed(4), color: "text-gray-400" },
                  ].map(({ label, value, color }) => (
                    <div key={label} className="bg-[#1f2937] rounded-lg p-3 text-center">
                      <div className="text-[10px] text-gray-500 uppercase tracking-wide">{label}</div>
                      <div className={cn("text-sm font-mono font-bold mt-1", color)}>{value}</div>
                    </div>
                  ))}
                </div>
                <p className="text-[10px] text-gray-600">{greeks.disclaimer}</p>
              </div>
              <GreeksSensitivityChart
                underlyingPrice={gPrice}
                strike={gStrike}
                dte={gDte}
                iv={gIv}
                optionType={gType}
              />
            </div>
          )}
        </div>

        {/* Disclaimer */}
        <div className="flex items-start gap-2 bg-yellow-900/10 border border-yellow-800/30 rounded-xl p-4 text-xs text-yellow-700">
          <AlertTriangle size={14} className="flex-shrink-0 mt-0.5" />
          Options trading involves substantial risk of loss and is not suitable for all investors.
          Strategy scores are algorithmic and do not constitute financial advice.
        </div>
      </div>
    </div>
  );
}
