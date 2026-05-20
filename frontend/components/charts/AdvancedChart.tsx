"use client";

/**
 * AdvancedChart — candlestick chart with overlaid technical indicators,
 * volume sub-chart, pattern annotations, and an AI explanation panel.
 */

import { useState, useMemo } from "react";
import {
  ComposedChart, Bar, Line, XAxis, YAxis, CartesianGrid,
  Tooltip, ResponsiveContainer, ReferenceLine, Legend,
} from "recharts";
import type { OHLCVBar, SupportResistance, PatternMatch } from "@/lib/api";
import { fmtPrice, fmtVolume, cn } from "@/lib/utils";
import { TrendingUp, TrendingDown, Minus, ChevronDown, ChevronUp, Info } from "lucide-react";

// ── Indicator computation ─────────────────────────────────────────────────────

function computeSMA(closes: number[], period: number): (number | null)[] {
  return closes.map((_, i) =>
    i < period - 1 ? null : closes.slice(i - period + 1, i + 1).reduce((a, b) => a + b, 0) / period
  );
}

function computeEMA(closes: number[], period: number): (number | null)[] {
  const k = 2 / (period + 1);
  const result: (number | null)[] = new Array(closes.length).fill(null);
  let ema = closes.slice(0, period).reduce((a, b) => a + b, 0) / period;
  result[period - 1] = ema;
  for (let i = period; i < closes.length; i++) {
    ema = closes[i] * k + ema * (1 - k);
    result[i] = ema;
  }
  return result;
}

function computeRSI(closes: number[], period = 14): (number | null)[] {
  const result: (number | null)[] = new Array(closes.length).fill(null);
  if (closes.length < period + 1) return result;
  let gains = 0, losses = 0;
  for (let i = 1; i <= period; i++) {
    const d = closes[i] - closes[i - 1];
    if (d > 0) gains += d; else losses -= d;
  }
  let avgGain = gains / period;
  let avgLoss = losses / period;
  result[period] = avgLoss === 0 ? 100 : 100 - 100 / (1 + avgGain / avgLoss);
  for (let i = period + 1; i < closes.length; i++) {
    const d = closes[i] - closes[i - 1];
    avgGain = (avgGain * (period - 1) + Math.max(d, 0)) / period;
    avgLoss = (avgLoss * (period - 1) + Math.max(-d, 0)) / period;
    result[i] = avgLoss === 0 ? 100 : 100 - 100 / (1 + avgGain / avgLoss);
  }
  return result;
}

function computeMACD(closes: number[]): { macd: (number | null)[]; signal: (number | null)[]; hist: (number | null)[] } {
  const ema12 = computeEMA(closes, 12);
  const ema26 = computeEMA(closes, 26);
  const macd = closes.map((_, i) =>
    ema12[i] != null && ema26[i] != null ? (ema12[i] as number) - (ema26[i] as number) : null
  );
  const macdValues = macd.filter((v): v is number => v != null);
  const signalRaw = computeEMA(macdValues, 9);
  const signal: (number | null)[] = new Array(closes.length).fill(null);
  let si = 0;
  for (let i = 0; i < closes.length; i++) {
    if (macd[i] != null) { signal[i] = signalRaw[si] ?? null; si++; }
  }
  const hist = closes.map((_, i) =>
    macd[i] != null && signal[i] != null ? (macd[i] as number) - (signal[i] as number) : null
  );
  return { macd, signal, hist };
}

function computeBollinger(closes: number[], period = 20, stdDev = 2): { upper: (number | null)[]; mid: (number | null)[]; lower: (number | null)[] } {
  const mid = computeSMA(closes, period);
  const upper: (number | null)[] = new Array(closes.length).fill(null);
  const lower: (number | null)[] = new Array(closes.length).fill(null);
  for (let i = period - 1; i < closes.length; i++) {
    const slice = closes.slice(i - period + 1, i + 1);
    const mean = mid[i] as number;
    const variance = slice.reduce((s, v) => s + (v - mean) ** 2, 0) / period;
    const sd = Math.sqrt(variance) * stdDev;
    upper[i] = mean + sd;
    lower[i] = mean - sd;
  }
  return { upper, mid, lower };
}

// ── Candlestick shape ─────────────────────────────────────────────────────────

function CandleBar(props: any) {
  const { x, width, payload } = props;
  if (!payload) return null;
  const { open, close, high, low } = payload;
  const isUp = close >= open;
  const color = isUp ? "#10b981" : "#ef4444";
  const yScale = props.yAxis?.scale;
  if (!yScale) return null;
  const yTop = yScale(Math.min(open, close));
  const yBot = yScale(Math.max(open, close));
  const yHigh = yScale(high);
  const yLow = yScale(low);
  const bodyH = Math.max(yBot - yTop, 1);
  const cx = x + width / 2;
  return (
    <g>
      <line x1={cx} y1={yHigh} x2={cx} y2={yTop} stroke={color} strokeWidth={1} />
      <line x1={cx} y1={yBot} x2={cx} y2={yLow} stroke={color} strokeWidth={1} />
      <rect x={x + 1} y={yTop} width={Math.max(width - 2, 1)} height={bodyH} fill={color} opacity={0.85} />
    </g>
  );
}

// ── Tooltip ───────────────────────────────────────────────────────────────────

const CandleTooltip = ({ active, payload, label }: any) => {
  if (!active || !payload?.length) return null;
  const d = payload[0]?.payload;
  if (!d) return null;
  const isUp = d.close >= d.open;
  return (
    <div className="bg-[#1a2235] border border-[#374151] rounded-xl p-3 text-xs shadow-2xl min-w-[180px]">
      <div className="text-gray-400 font-semibold mb-2">{label}</div>
      <div className="grid grid-cols-2 gap-x-4 gap-y-1">
        <span className="text-gray-500">Open</span>  <span className="font-mono">{fmtPrice(d.open)}</span>
        <span className="text-gray-500">High</span>  <span className="font-mono text-green-400">{fmtPrice(d.high)}</span>
        <span className="text-gray-500">Low</span>   <span className="font-mono text-red-400">{fmtPrice(d.low)}</span>
        <span className="text-gray-500">Close</span> <span className={cn("font-mono font-semibold", isUp ? "text-green-400" : "text-red-400")}>{fmtPrice(d.close)}</span>
        <span className="text-gray-500">Volume</span><span className="font-mono">{fmtVolume(d.volume)}</span>
        {d.sma20 != null && <><span className="text-gray-500">SMA20</span><span className="font-mono text-yellow-400">{fmtPrice(d.sma20)}</span></>}
        {d.sma50 != null && <><span className="text-gray-500">SMA50</span><span className="font-mono text-orange-400">{fmtPrice(d.sma50)}</span></>}
        {d.ema9 != null && <><span className="text-gray-500">EMA9</span><span className="font-mono text-cyan-400">{fmtPrice(d.ema9)}</span></>}
        {d.bbUpper != null && <><span className="text-gray-500">BB Upper</span><span className="font-mono text-purple-400">{fmtPrice(d.bbUpper)}</span></>}
        {d.bbLower != null && <><span className="text-gray-500">BB Lower</span><span className="font-mono text-purple-400">{fmtPrice(d.bbLower)}</span></>}
      </div>
    </div>
  );
};

// ── Indicator toggle button ───────────────────────────────────────────────────

function IndicatorBtn({ label, active, color, onClick }: { label: string; active: boolean; color: string; onClick: () => void }) {
  return (
    <button
      onClick={onClick}
      className={cn(
        "text-[10px] px-2 py-1 rounded-md border transition-all font-medium",
        active
          ? `border-transparent text-white`
          : "border-[#374151] text-gray-500 hover:text-gray-300 hover:border-[#4b5563]"
      )}
      style={active ? { backgroundColor: color + "33", borderColor: color, color } : {}}
    >
      {label}
    </button>
  );
}

// ── Pattern explanation panel ─────────────────────────────────────────────────

function PatternExplanations({ patterns }: { patterns: PatternMatch[] }) {
  const [expanded, setExpanded] = useState<number | null>(null);
  if (!patterns.length) return null;

  return (
    <div className="mt-3 space-y-1.5">
      <div className="text-xs font-semibold text-gray-400 mb-2">Detected Patterns</div>
      {patterns.slice(0, 6).map((p, i) => (
        <div key={i} className="border border-[#1f2937] rounded-lg overflow-hidden">
          <button
            onClick={() => setExpanded(expanded === i ? null : i)}
            className="w-full flex items-center gap-2 px-3 py-2 hover:bg-[#1f2937]/50 transition-colors text-left"
          >
            <span className={cn(
              "w-2 h-2 rounded-full flex-shrink-0",
              p.direction === "bullish" ? "bg-green-400" : p.direction === "bearish" ? "bg-red-400" : "bg-yellow-400"
            )} />
            <span className="text-xs font-medium text-gray-200 flex-1">{p.name}</span>
            <span className={cn(
              "text-[10px] px-1.5 py-0.5 rounded font-medium",
              p.direction === "bullish" ? "bg-green-900/40 text-green-400" :
              p.direction === "bearish" ? "bg-red-900/40 text-red-400" : "bg-yellow-900/40 text-yellow-400"
            )}>
              {p.direction}
            </span>
            <span className="text-[10px] text-gray-500 font-mono">{Math.round(p.confidence * 100)}%</span>
            {expanded === i ? <ChevronUp size={12} className="text-gray-500" /> : <ChevronDown size={12} className="text-gray-500" />}
          </button>
          {expanded === i && (
            <div className="px-3 pb-3 space-y-2 bg-[#0d1117]/50">
              <p className="text-xs text-gray-400 leading-relaxed">{p.description}</p>
              {p.evidence.length > 0 && (
                <div>
                  <div className="text-[10px] text-gray-600 uppercase tracking-wide mb-1">Evidence</div>
                  <ul className="space-y-0.5">
                    {p.evidence.map((e, j) => (
                      <li key={j} className="text-[11px] text-gray-400 flex gap-1.5">
                        <span className="text-blue-500 mt-0.5">›</span>{e}
                      </li>
                    ))}
                  </ul>
                </div>
              )}
              <div className="flex gap-4 text-[10px]">
                {p.target_price && (
                  <span className="text-green-400">Target: {fmtPrice(p.target_price)}</span>
                )}
                {p.stop_loss && (
                  <span className="text-red-400">Stop: {fmtPrice(p.stop_loss)}</span>
                )}
              </div>
            </div>
          )}
        </div>
      ))}
    </div>
  );
}

// ── Main component ────────────────────────────────────────────────────────────

type Timeframe = "1M" | "3M" | "6M" | "1Y" | "2Y";

interface AdvancedChartProps {
  bars: OHLCVBar[];
  sr?: SupportResistance;
  patterns?: PatternMatch[];
  sma50?: number;
  sma200?: number;
  symbol?: string;
  patternExplanation?: string;
}

export function AdvancedChart({
  bars,
  sr,
  patterns = [],
  sma50,
  sma200,
  symbol,
  patternExplanation,
}: AdvancedChartProps) {
  const [timeframe, setTimeframe] = useState<Timeframe>("1Y");
  const [showSMA20, setShowSMA20] = useState(true);
  const [showSMA50, setShowSMA50] = useState(true);
  const [showEMA9, setShowEMA9] = useState(false);
  const [showBB, setShowBB] = useState(false);
  const [showVolume, setShowVolume] = useState(true);
  const [showRSI, setShowRSI] = useState(true);
  const [showMACD, setShowMACD] = useState(false);
  const [showPatterns, setShowPatterns] = useState(true);

  const tfBars: Record<Timeframe, number> = { "1M": 22, "3M": 66, "6M": 126, "1Y": 252, "2Y": 504 };

  const data = useMemo(() => {
    const slice = bars.slice(-tfBars[timeframe]);
    const closes = slice.map((b) => b.close);
    const sma20arr = computeSMA(closes, 20);
    const sma50arr = computeSMA(closes, 50);
    const ema9arr = computeEMA(closes, 9);
    const bb = computeBollinger(closes, 20, 2);
    const rsiArr = computeRSI(closes, 14);
    const { macd, signal: macdSig, hist } = computeMACD(closes);

    return slice.map((b, i) => ({
      ...b,
      date: b.date.slice(5),
      sma20: sma20arr[i] != null ? +sma20arr[i]!.toFixed(2) : null,
      sma50: sma50arr[i] != null ? +sma50arr[i]!.toFixed(2) : null,
      ema9: ema9arr[i] != null ? +ema9arr[i]!.toFixed(2) : null,
      bbUpper: bb.upper[i] != null ? +bb.upper[i]!.toFixed(2) : null,
      bbMid: bb.mid[i] != null ? +bb.mid[i]!.toFixed(2) : null,
      bbLower: bb.lower[i] != null ? +bb.lower[i]!.toFixed(2) : null,
      rsi: rsiArr[i] != null ? +rsiArr[i]!.toFixed(1) : null,
      macd: macd[i] != null ? +macd[i]!.toFixed(3) : null,
      macdSig: macdSig[i] != null ? +macdSig[i]!.toFixed(3) : null,
      macdHist: hist[i] != null ? +hist[i]!.toFixed(3) : null,
    }));
  }, [bars, timeframe]);

  const prices = data.map((b) => b.close);
  const minP = Math.min(...prices) * 0.985;
  const maxP = Math.max(...prices) * 1.015;
  const tickInterval = Math.max(1, Math.floor(data.length / 8));

  const subChartCount = [showVolume, showRSI, showMACD].filter(Boolean).length;
  const mainH = subChartCount === 0 ? 380 : subChartCount === 1 ? 300 : subChartCount === 2 ? 240 : 200;
  const subH = 90;

  return (
    <div className="space-y-0">
      {/* Toolbar */}
      <div className="flex items-center gap-2 flex-wrap mb-3">
        {/* Timeframe */}
        <div className="flex gap-1 bg-[#1f2937] rounded-lg p-0.5">
          {(["1M", "3M", "6M", "1Y", "2Y"] as Timeframe[]).map((tf) => (
            <button
              key={tf}
              onClick={() => setTimeframe(tf)}
              className={cn(
                "text-[10px] px-2.5 py-1 rounded-md font-medium transition-colors",
                timeframe === tf ? "bg-blue-600 text-white" : "text-gray-500 hover:text-gray-300"
              )}
            >
              {tf}
            </button>
          ))}
        </div>

        <div className="w-px h-4 bg-[#374151]" />

        {/* Overlays */}
        <IndicatorBtn label="SMA20" active={showSMA20} color="#eab308" onClick={() => setShowSMA20((v) => !v)} />
        <IndicatorBtn label="SMA50" active={showSMA50} color="#f97316" onClick={() => setShowSMA50((v) => !v)} />
        <IndicatorBtn label="EMA9" active={showEMA9} color="#06b6d4" onClick={() => setShowEMA9((v) => !v)} />
        <IndicatorBtn label="BB" active={showBB} color="#a855f7" onClick={() => setShowBB((v) => !v)} />

        <div className="w-px h-4 bg-[#374151]" />

        {/* Sub-charts */}
        <IndicatorBtn label="Volume" active={showVolume} color="#3b82f6" onClick={() => setShowVolume((v) => !v)} />
        <IndicatorBtn label="RSI" active={showRSI} color="#10b981" onClick={() => setShowRSI((v) => !v)} />
        <IndicatorBtn label="MACD" active={showMACD} color="#f59e0b" onClick={() => setShowMACD((v) => !v)} />

        <div className="w-px h-4 bg-[#374151]" />
        <IndicatorBtn label="Patterns" active={showPatterns} color="#60a5fa" onClick={() => setShowPatterns((v) => !v)} />
      </div>

      {/* Main candlestick chart */}
      <ResponsiveContainer width="100%" height={mainH}>
        <ComposedChart data={data} margin={{ top: 4, right: 16, left: 0, bottom: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#1a2235" vertical={false} />
          <XAxis dataKey="date" tick={{ fill: "#4b5563", fontSize: 9 }} tickLine={false} axisLine={false} interval={tickInterval} />
          <YAxis domain={[minP, maxP]} tick={{ fill: "#4b5563", fontSize: 9 }} tickLine={false} axisLine={false}
            tickFormatter={(v) => `$${v.toFixed(0)}`} width={52} />
          <Tooltip content={<CandleTooltip />} />

          {/* S/R levels */}
          {sr?.support.map((lvl) => (
            <ReferenceLine key={`s${lvl}`} y={lvl} stroke="#10b981" strokeDasharray="4 3" strokeOpacity={0.45}
              label={{ value: `S ${fmtPrice(lvl)}`, fill: "#10b981", fontSize: 8, position: "insideTopRight" }} />
          ))}
          {sr?.resistance.map((lvl) => (
            <ReferenceLine key={`r${lvl}`} y={lvl} stroke="#ef4444" strokeDasharray="4 3" strokeOpacity={0.45}
              label={{ value: `R ${fmtPrice(lvl)}`, fill: "#ef4444", fontSize: 8, position: "insideTopRight" }} />
          ))}

          {/* Bollinger bands */}
          {showBB && <Line type="monotone" dataKey="bbUpper" stroke="#a855f7" strokeWidth={1} dot={false} strokeDasharray="3 2" connectNulls />}
          {showBB && <Line type="monotone" dataKey="bbMid" stroke="#a855f7" strokeWidth={0.5} dot={false} strokeOpacity={0.5} connectNulls />}
          {showBB && <Line type="monotone" dataKey="bbLower" stroke="#a855f7" strokeWidth={1} dot={false} strokeDasharray="3 2" connectNulls />}

          {/* Moving averages */}
          {showEMA9 && <Line type="monotone" dataKey="ema9" stroke="#06b6d4" strokeWidth={1.5} dot={false} connectNulls />}
          {showSMA20 && <Line type="monotone" dataKey="sma20" stroke="#eab308" strokeWidth={1.5} dot={false} connectNulls />}
          {showSMA50 && <Line type="monotone" dataKey="sma50" stroke="#f97316" strokeWidth={1.5} dot={false} connectNulls />}

          {/* Candlesticks */}
          <Bar dataKey="close" shape={<CandleBar />} isAnimationActive={false} />
        </ComposedChart>
      </ResponsiveContainer>

      {/* Volume sub-chart */}
      {showVolume && (
        <ResponsiveContainer width="100%" height={subH}>
          <ComposedChart data={data} margin={{ top: 2, right: 16, left: 0, bottom: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#1a2235" vertical={false} />
            <XAxis dataKey="date" hide />
            <YAxis tick={{ fill: "#4b5563", fontSize: 8 }} tickLine={false} axisLine={false} tickFormatter={fmtVolume} width={52} />
            <Tooltip
              contentStyle={{ background: "#1a2235", border: "1px solid #374151", borderRadius: 8, fontSize: 11 }}
              formatter={(v: number) => [fmtVolume(v), "Volume"]}
            />
            <Bar dataKey="volume" isAnimationActive={false} fill="#3b82f6" opacity={0.5} />
          </ComposedChart>
        </ResponsiveContainer>
      )}

      {/* RSI sub-chart */}
      {showRSI && (
        <ResponsiveContainer width="100%" height={subH}>
          <ComposedChart data={data} margin={{ top: 2, right: 16, left: 0, bottom: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#1a2235" vertical={false} />
            <XAxis dataKey="date" hide />
            <YAxis domain={[0, 100]} tick={{ fill: "#4b5563", fontSize: 8 }} tickLine={false} axisLine={false} width={52}
              ticks={[30, 50, 70]} />
            <Tooltip
              contentStyle={{ background: "#1a2235", border: "1px solid #374151", borderRadius: 8, fontSize: 11 }}
              formatter={(v: number) => [v?.toFixed(1), "RSI"]}
            />
            <ReferenceLine y={70} stroke="#ef4444" strokeDasharray="3 2" strokeOpacity={0.5}
              label={{ value: "OB 70", fill: "#ef4444", fontSize: 8, position: "insideTopRight" }} />
            <ReferenceLine y={30} stroke="#10b981" strokeDasharray="3 2" strokeOpacity={0.5}
              label={{ value: "OS 30", fill: "#10b981", fontSize: 8, position: "insideBottomRight" }} />
            <ReferenceLine y={50} stroke="#374151" strokeDasharray="2 2" strokeOpacity={0.4} />
            <Line type="monotone" dataKey="rsi" stroke="#10b981" strokeWidth={1.5} dot={false} connectNulls />
          </ComposedChart>
        </ResponsiveContainer>
      )}

      {/* MACD sub-chart */}
      {showMACD && (
        <ResponsiveContainer width="100%" height={subH}>
          <ComposedChart data={data} margin={{ top: 2, right: 16, left: 0, bottom: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#1a2235" vertical={false} />
            <XAxis dataKey="date" hide />
            <YAxis tick={{ fill: "#4b5563", fontSize: 8 }} tickLine={false} axisLine={false} width={52} />
            <Tooltip
              contentStyle={{ background: "#1a2235", border: "1px solid #374151", borderRadius: 8, fontSize: 11 }}
              formatter={(v: number, name: string) => [v?.toFixed(3), name === "macd" ? "MACD" : name === "macdSig" ? "Signal" : "Histogram"]}
            />
            <ReferenceLine y={0} stroke="#374151" />
            <Bar dataKey="macdHist" isAnimationActive={false} fill="#f59e0b" opacity={0.6} />
            <Line type="monotone" dataKey="macd" stroke="#3b82f6" strokeWidth={1.5} dot={false} connectNulls />
            <Line type="monotone" dataKey="macdSig" stroke="#ef4444" strokeWidth={1} dot={false} strokeDasharray="3 2" connectNulls />
          </ComposedChart>
        </ResponsiveContainer>
      )}

      {/* Pattern explanations */}
      {showPatterns && patterns.length > 0 && (
        <PatternExplanations patterns={patterns} />
      )}

      {/* AI pattern explanation */}
      {patternExplanation && (
        <div className="mt-3 flex gap-2 bg-blue-900/10 border border-blue-800/30 rounded-xl p-3">
          <Info size={14} className="text-blue-400 flex-shrink-0 mt-0.5" />
          <p className="text-xs text-gray-400 leading-relaxed">{patternExplanation}</p>
        </div>
      )}
    </div>
  );
}
