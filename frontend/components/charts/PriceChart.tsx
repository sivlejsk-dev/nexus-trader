"use client";

import {
  ComposedChart, Bar, Line, XAxis, YAxis, CartesianGrid,
  Tooltip, ResponsiveContainer, ReferenceLine, Legend,
} from "recharts";
import type { OHLCVBar, SupportResistance } from "@/lib/api";
import { fmtPrice, fmtVolume } from "@/lib/utils";

interface Props {
  bars: OHLCVBar[];
  sr?: SupportResistance;
  sma50?: number;
  sma200?: number;
  height?: number;
}

// Custom candlestick bar shape
function CandleBar(props: any) {
  const { x, y, width, payload } = props;
  if (!payload) return null;
  const { open, close, high, low } = payload;
  const isUp = close >= open;
  const color = isUp ? "#10b981" : "#ef4444";
  const bodyTop = Math.min(open, close);
  const bodyBot = Math.max(open, close);
  const yScale = props.yAxis?.scale;
  if (!yScale) return null;

  const yTop = yScale(bodyTop);
  const yBot = yScale(bodyBot);
  const yHigh = yScale(high);
  const yLow = yScale(low);
  const bodyH = Math.max(yBot - yTop, 1);
  const cx = x + width / 2;

  return (
    <g>
      {/* Wick */}
      <line x1={cx} y1={yHigh} x2={cx} y2={yTop} stroke={color} strokeWidth={1} />
      <line x1={cx} y1={yBot} x2={cx} y2={yLow} stroke={color} strokeWidth={1} />
      {/* Body */}
      <rect x={x + 1} y={yTop} width={Math.max(width - 2, 1)} height={bodyH} fill={color} opacity={0.85} />
    </g>
  );
}

const CustomTooltip = ({ active, payload, label }: any) => {
  if (!active || !payload?.length) return null;
  const d = payload[0]?.payload;
  if (!d) return null;
  const isUp = d.close >= d.open;
  return (
    <div className="bg-[#1f2937] border border-[#374151] rounded-lg p-3 text-xs space-y-1 shadow-xl">
      <div className="text-gray-400 font-medium">{label}</div>
      <div className="grid grid-cols-2 gap-x-4 gap-y-0.5">
        <span className="text-gray-500">Open</span>  <span>{fmtPrice(d.open)}</span>
        <span className="text-gray-500">High</span>  <span className="text-green-400">{fmtPrice(d.high)}</span>
        <span className="text-gray-500">Low</span>   <span className="text-red-400">{fmtPrice(d.low)}</span>
        <span className="text-gray-500">Close</span> <span className={isUp ? "text-green-400" : "text-red-400"}>{fmtPrice(d.close)}</span>
        <span className="text-gray-500">Volume</span><span>{fmtVolume(d.volume)}</span>
      </div>
    </div>
  );
};

export function PriceChart({ bars, sr, sma50, sma200, height = 420 }: Props) {
  // Downsample to last 252 bars for performance
  const data = bars.slice(-252).map((b) => ({
    ...b,
    date: b.date.slice(5), // MM-DD
  }));

  const prices = data.map((b) => b.close);
  const minP = Math.min(...prices) * 0.98;
  const maxP = Math.max(...prices) * 1.02;

  // Tick every ~30 bars
  const tickInterval = Math.max(1, Math.floor(data.length / 8));

  return (
    <div style={{ height }}>
      <ResponsiveContainer width="100%" height="75%">
        <ComposedChart data={data} margin={{ top: 8, right: 16, left: 0, bottom: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#1f2937" vertical={false} />
          <XAxis
            dataKey="date"
            tick={{ fill: "#6b7280", fontSize: 10 }}
            tickLine={false}
            axisLine={false}
            interval={tickInterval}
          />
          <YAxis
            domain={[minP, maxP]}
            tick={{ fill: "#6b7280", fontSize: 10 }}
            tickLine={false}
            axisLine={false}
            tickFormatter={(v) => `$${v.toFixed(0)}`}
            width={52}
          />
          <Tooltip content={<CustomTooltip />} />

          {/* Support levels */}
          {sr?.support.map((lvl) => (
            <ReferenceLine key={`s${lvl}`} y={lvl} stroke="#10b981" strokeDasharray="4 4" strokeOpacity={0.5}
              label={{ value: `S ${fmtPrice(lvl)}`, fill: "#10b981", fontSize: 9, position: "insideTopRight" }} />
          ))}
          {/* Resistance levels */}
          {sr?.resistance.map((lvl) => (
            <ReferenceLine key={`r${lvl}`} y={lvl} stroke="#ef4444" strokeDasharray="4 4" strokeOpacity={0.5}
              label={{ value: `R ${fmtPrice(lvl)}`, fill: "#ef4444", fontSize: 9, position: "insideTopRight" }} />
          ))}

          {/* SMA lines */}
          {sma50 && (
            <ReferenceLine y={sma50} stroke="#f59e0b" strokeWidth={1.5}
              label={{ value: `SMA50 ${fmtPrice(sma50)}`, fill: "#f59e0b", fontSize: 9, position: "insideTopLeft" }} />
          )}
          {sma200 && (
            <ReferenceLine y={sma200} stroke="#8b5cf6" strokeWidth={1.5}
              label={{ value: `SMA200 ${fmtPrice(sma200)}`, fill: "#8b5cf6", fontSize: 9, position: "insideBottomLeft" }} />
          )}

          {/* Candlestick bars rendered as custom Bar */}
          <Bar dataKey="close" shape={<CandleBar />} isAnimationActive={false} />
        </ComposedChart>
      </ResponsiveContainer>

      {/* Volume sub-chart */}
      <ResponsiveContainer width="100%" height="25%">
        <ComposedChart data={data} margin={{ top: 0, right: 16, left: 0, bottom: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#1f2937" vertical={false} />
          <XAxis dataKey="date" hide />
          <YAxis tick={{ fill: "#6b7280", fontSize: 9 }} tickLine={false} axisLine={false}
            tickFormatter={fmtVolume} width={52} />
          <Bar dataKey="volume" isAnimationActive={false}
            fill="#3b82f6" opacity={0.5}
            // Color by direction
            label={false}
          />
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  );
}
