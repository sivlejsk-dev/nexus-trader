"use client";

import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, Cell, LineChart, Line, Legend,
  RadarChart, Radar, PolarGrid, PolarAngleAxis,
  ComposedChart, ReferenceLine,
} from "recharts";
import type { StrategyScore } from "@/lib/api";
import { fmtPrice } from "@/lib/utils";

// ── Put/Call OI bar chart ─────────────────────────────────────────────────────

interface PCRProps {
  calls: Array<{ strike: number; open_interest?: number }>;
  puts: Array<{ strike: number; open_interest?: number }>;
  underlyingPrice: number;
}

export function PutCallOIChart({ calls, puts, underlyingPrice }: PCRProps) {
  // Build strike-aligned data
  const strikeMap: Record<number, { strike: number; call_oi: number; put_oi: number }> = {};
  calls.forEach((c) => {
    const s = c.strike;
    if (!strikeMap[s]) strikeMap[s] = { strike: s, call_oi: 0, put_oi: 0 };
    strikeMap[s].call_oi += c.open_interest || 0;
  });
  puts.forEach((p) => {
    const s = p.strike;
    if (!strikeMap[s]) strikeMap[s] = { strike: s, call_oi: 0, put_oi: 0 };
    strikeMap[s].put_oi += p.open_interest || 0;
  });

  const data = Object.values(strikeMap)
    .sort((a, b) => a.strike - b.strike)
    .filter((d) => d.call_oi > 0 || d.put_oi > 0)
    .slice(0, 20); // nearest 20 strikes

  return (
    <div>
      <div className="text-xs text-gray-400 mb-2">Open Interest by Strike</div>
      <ResponsiveContainer width="100%" height={220}>
        <BarChart data={data} margin={{ top: 4, right: 8, left: 0, bottom: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#1f2937" vertical={false} />
          <XAxis dataKey="strike" tick={{ fill: "#6b7280", fontSize: 9 }}
            tickLine={false} axisLine={false} tickFormatter={(v) => `$${v}`} />
          <YAxis tick={{ fill: "#6b7280", fontSize: 9 }} tickLine={false} axisLine={false} width={40} />
          <Tooltip
            contentStyle={{ background: "#1f2937", border: "1px solid #374151", borderRadius: 8 }}
            labelStyle={{ color: "#9ca3af" }}
            formatter={(v: number, name: string) => [v.toLocaleString(), name === "call_oi" ? "Call OI" : "Put OI"]}
          />
          <Bar dataKey="call_oi" fill="#10b981" opacity={0.8} name="Call OI" />
          <Bar dataKey="put_oi" fill="#ef4444" opacity={0.8} name="Put OI" />
          {underlyingPrice > 0 && (
            <Bar dataKey="call_oi" fill="transparent" stroke="none" />
          )}
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

// ── Strategy score radar ──────────────────────────────────────────────────────

interface StrategyRadarProps {
  strategies: StrategyScore[];
}

export function StrategyRadarChart({ strategies }: StrategyRadarProps) {
  const top6 = strategies.slice(0, 6);
  const data = top6.map((s) => ({ subject: s.name.replace(" ", "\n"), score: s.score }));

  return (
    <div>
      <div className="text-xs text-gray-400 mb-2">Strategy Suitability Scores</div>
      <ResponsiveContainer width="100%" height={220}>
        <RadarChart data={data}>
          <PolarGrid stroke="#1f2937" />
          <PolarAngleAxis dataKey="subject" tick={{ fill: "#6b7280", fontSize: 9 }} />
          <Radar name="Score" dataKey="score" stroke="#3b82f6" fill="#3b82f6" fillOpacity={0.25} />
        </RadarChart>
      </ResponsiveContainer>
    </div>
  );
}

// ── Greeks sensitivity chart ──────────────────────────────────────────────────

interface GreeksSensProps {
  underlyingPrice: number;
  strike: number;
  dte: number;
  iv: number;
  optionType: "call" | "put";
}

export function GreeksSensitivityChart({ underlyingPrice, strike, dte, iv, optionType }: GreeksSensProps) {
  // Compute delta across a range of underlying prices (client-side BS approximation)
  function normCDF(x: number) {
    return 0.5 * (1 + erf(x / Math.sqrt(2)));
  }
  function erf(x: number) {
    const t = 1 / (1 + 0.3275911 * Math.abs(x));
    const y = 1 - (((((1.061405429 * t - 1.453152027) * t) + 1.421413741) * t - 0.284496736) * t + 0.254829592) * t * Math.exp(-x * x);
    return x >= 0 ? y : -y;
  }

  const T = dte / 365;
  const r = 0.05;
  const range = underlyingPrice * 0.2;
  const steps = 30;
  const data = [];

  for (let i = 0; i <= steps; i++) {
    const S = underlyingPrice - range + (2 * range * i) / steps;
    if (S <= 0 || T <= 0 || iv <= 0) continue;
    const d1 = (Math.log(S / strike) + (r + 0.5 * iv * iv) * T) / (iv * Math.sqrt(T));
    const d2 = d1 - iv * Math.sqrt(T);
    const delta = optionType === "call" ? normCDF(d1) : normCDF(d1) - 1;
    const price = optionType === "call"
      ? S * normCDF(d1) - strike * Math.exp(-r * T) * normCDF(d2)
      : strike * Math.exp(-r * T) * normCDF(-d2) - S * normCDF(-d1);
    data.push({ price: parseFloat(S.toFixed(2)), delta: parseFloat(delta.toFixed(3)), value: parseFloat(Math.max(price, 0).toFixed(3)) });
  }

  return (
    <div>
      <div className="text-xs text-gray-400 mb-2">Option Value & Delta vs Underlying Price</div>
      <ResponsiveContainer width="100%" height={200}>
        <LineChart data={data} margin={{ top: 4, right: 8, left: 0, bottom: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#1f2937" vertical={false} />
          <XAxis dataKey="price" tick={{ fill: "#6b7280", fontSize: 9 }} tickLine={false} axisLine={false}
            tickFormatter={(v) => `$${v}`} interval={5} />
          <YAxis yAxisId="left" tick={{ fill: "#6b7280", fontSize: 9 }} tickLine={false} axisLine={false} width={40} />
          <YAxis yAxisId="right" orientation="right" tick={{ fill: "#6b7280", fontSize: 9 }} tickLine={false} axisLine={false} width={36} domain={[-1, 1]} />
          <Tooltip
            contentStyle={{ background: "#1f2937", border: "1px solid #374151", borderRadius: 8 }}
            labelStyle={{ color: "#9ca3af" }}
            labelFormatter={(v) => `Underlying: $${v}`}
          />
          <Legend wrapperStyle={{ fontSize: 10, color: "#9ca3af" }} />
          <Line yAxisId="left" type="monotone" dataKey="value" stroke="#3b82f6" dot={false} name="Option Value" strokeWidth={2} />
          <Line yAxisId="right" type="monotone" dataKey="delta" stroke="#f59e0b" dot={false} name="Delta" strokeWidth={1.5} strokeDasharray="4 2" />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}

// ── Backtest equity curve ─────────────────────────────────────────────────────

interface BacktestChartProps {
  trades: Array<{ entry_date: string; pnl_pct: number; win: boolean }>;
}

interface TradeBar {
  date: string;
  pnl_pct: number;
  cumulative: number;
  win: boolean;
}

export function BacktestEquityCurve({ trades }: BacktestChartProps) {
  let cumulative = 0;
  const data: TradeBar[] = trades.map((t) => {
    cumulative += t.pnl_pct;
    return {
      date: t.entry_date.slice(0, 7),
      pnl_pct: parseFloat(t.pnl_pct.toFixed(2)),
      cumulative: parseFloat(cumulative.toFixed(2)),
      win: t.win,
    };
  });

  return (
    <div>
      <div className="text-xs text-gray-400 mb-2">Cumulative P&L % (per trade)</div>
      <ResponsiveContainer width="100%" height={200}>
        <ComposedChart data={data} margin={{ top: 4, right: 8, left: 0, bottom: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#1f2937" vertical={false} />
          <XAxis dataKey="date" tick={{ fill: "#6b7280", fontSize: 9 }} tickLine={false} axisLine={false} />
          <YAxis
            tick={{ fill: "#6b7280", fontSize: 9 }}
            tickLine={false}
            axisLine={false}
            width={40}
            tickFormatter={(v: number) => `${v}%`}
          />
          <Tooltip
            contentStyle={{ background: "#1f2937", border: "1px solid #374151", borderRadius: 8 }}
            formatter={(v: number, name: string) => [
              `${v.toFixed(2)}%`,
              name === "pnl_pct" ? "Trade P&L" : "Cumulative",
            ]}
          />
          <ReferenceLine y={0} stroke="#374151" />
          <Bar dataKey="pnl_pct" name="Trade P&L">
            {data.map((d: TradeBar, i: number) => (
              <Cell key={i} fill={d.win ? "#10b981" : "#ef4444"} opacity={0.7} />
            ))}
          </Bar>
          <Line
            type="monotone"
            dataKey="cumulative"
            stroke="#3b82f6"
            dot={false}
            strokeWidth={2}
            name="Cumulative"
          />
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  );
}
