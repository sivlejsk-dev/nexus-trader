"use client";

import { useState } from "react";
import { BookOpen, ChevronDown, ChevronUp } from "lucide-react";
import { cn } from "@/lib/utils";

const TOPICS = [
  {
    title: "Options Basics",
    items: [
      { q: "What is a call option?", a: "A call option gives the buyer the right, but not the obligation, to purchase 100 shares of the underlying stock at the strike price before the expiration date. Buyers profit when the stock rises above the strike + premium paid." },
      { q: "What is a put option?", a: "A put option gives the buyer the right to sell 100 shares at the strike price before expiration. Buyers profit when the stock falls below the strike - premium paid." },
      { q: "What is IV (Implied Volatility)?", a: "IV is the market's forecast of a stock's likely movement, expressed as an annualized percentage. High IV means expensive options (market expects big moves). Low IV means cheap options. IV crush occurs when IV drops sharply after a catalyst (e.g., earnings)." },
      { q: "What is IV Rank?", a: "IV Rank compares current IV to its 52-week range: (Current IV - 52w Low) / (52w High - 52w Low) × 100. A rank of 80 means IV is near its yearly high — options are expensive. Below 20 means options are cheap." },
    ],
  },
  {
    title: "The Greeks",
    items: [
      { q: "Delta", a: "Delta measures how much an option's price changes per $1 move in the underlying. Call deltas range 0 to 1; put deltas range -1 to 0. A delta of 0.50 means the option moves $0.50 for every $1 the stock moves. Delta also approximates the probability of expiring ITM." },
      { q: "Gamma", a: "Gamma measures the rate of change of delta per $1 move in the underlying. High gamma (near ATM, near expiry) means delta changes rapidly — positions can swing dramatically. Long options have positive gamma; short options have negative gamma." },
      { q: "Theta", a: "Theta is time decay — how much value an option loses per day, all else equal. Long options have negative theta (you lose value daily). Short options have positive theta (you collect decay). Theta accelerates in the final 30 days before expiry." },
      { q: "Vega", a: "Vega measures sensitivity to a 1% change in IV. Long options have positive vega (benefit from rising IV). Short options have negative vega (hurt by rising IV). Vega is highest for ATM options with more time to expiry." },
    ],
  },
  {
    title: "Common Strategies",
    items: [
      { q: "Long Call", a: "Buy a call when you're bullish. Max loss = premium paid. Max profit = unlimited. Best in low-IV environments with 30-60 DTE. Choose a strike near ATM for balanced risk/reward." },
      { q: "Long Put", a: "Buy a put when you're bearish or want portfolio protection. Max loss = premium paid. Best in low-IV environments. Useful as a hedge against long stock positions." },
      { q: "Covered Call", a: "Own 100 shares + sell 1 call. Generates income in sideways/slightly bullish markets. Caps upside at the strike price. Best in high-IV environments. Max profit = (strike - cost basis) + premium." },
      { q: "Iron Condor", a: "Sell an OTM call spread + sell an OTM put spread simultaneously. Profits when the stock stays within a range. Best in high-IV, low-movement environments. Max profit = net premium received. Max loss = wing width - premium." },
      { q: "Long Straddle", a: "Buy an ATM call + ATM put with the same strike and expiry. Profits from a large move in either direction. Best before catalysts (earnings, FDA decisions) when IV is low. Max loss = total premium paid." },
    ],
  },
  {
    title: "Risk Management",
    items: [
      { q: "Position sizing", a: "Never risk more than 1-5% of your portfolio on a single options trade. Options can go to zero — size accordingly. A common rule: risk no more than 2% of account value per trade." },
      { q: "Stop losses for options", a: "Consider closing a long option if it loses 50% of its value. For short options, close if the position reaches 2× the premium received. Never let short naked options run against you without a plan." },
      { q: "Earnings risk", a: "Options prices inflate before earnings (IV expansion) and collapse after (IV crush). Buying options before earnings is expensive. Selling premium before earnings can be profitable but carries gap risk." },
      { q: "Liquidity", a: "Always check the bid-ask spread before trading. A spread wider than 5% of the ask price indicates poor liquidity. Use limit orders, never market orders, for options. Stick to high-volume underlyings (SPY, AAPL, TSLA, etc.)." },
    ],
  },
  {
    title: "Technical Analysis",
    items: [
      { q: "RSI (Relative Strength Index)", a: "RSI measures momentum on a 0-100 scale. Above 70 = overbought (potential pullback). Below 30 = oversold (potential bounce). RSI divergence (price makes new high but RSI doesn't) is a powerful reversal signal." },
      { q: "MACD", a: "MACD (Moving Average Convergence Divergence) shows momentum and trend direction. When MACD crosses above the signal line = bullish. Below = bearish. The histogram shows the difference between MACD and signal." },
      { q: "Support & Resistance", a: "Support is a price level where buying pressure historically stops a decline. Resistance is where selling pressure stops a rally. Breakouts above resistance (with volume) are bullish. Breakdowns below support are bearish." },
      { q: "Bollinger Band Squeeze", a: "When Bollinger Bands narrow (low volatility), it often precedes a sharp breakout. The direction of the breakout determines whether to buy calls or puts. Combine with volume and trend for confirmation." },
    ],
  },
];

function AccordionItem({ q, a }: { q: string; a: string }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="border border-[#1f2937] rounded-lg overflow-hidden">
      <button
        onClick={() => setOpen(!open)}
        className="w-full flex items-center justify-between px-4 py-3 text-left text-sm font-medium text-gray-200 hover:bg-[#1f2937]/50 transition-colors"
      >
        {q}
        {open ? <ChevronUp size={14} className="text-gray-500 flex-shrink-0" /> : <ChevronDown size={14} className="text-gray-500 flex-shrink-0" />}
      </button>
      {open && (
        <div className="px-4 pb-4 text-sm text-gray-400 leading-relaxed border-t border-[#1f2937] pt-3">
          {a}
        </div>
      )}
    </div>
  );
}

export default function LearnPage() {
  return (
    <div className="flex flex-col h-full bg-[#0a0e1a] overflow-auto">
      <div className="flex items-center gap-3 px-5 py-3 border-b border-[#1f2937] bg-[#111827]">
        <BookOpen size={16} className="text-blue-400" />
        <span className="text-sm font-semibold text-white">Learn</span>
        <span className="text-xs text-gray-500 ml-1">Options & Technical Analysis Reference</span>
      </div>

      <div className="p-5 space-y-6 max-w-3xl">
        {TOPICS.map((topic) => (
          <div key={topic.title}>
            <h2 className="text-sm font-semibold text-blue-400 uppercase tracking-wide mb-3">{topic.title}</h2>
            <div className="space-y-2">
              {topic.items.map((item) => (
                <AccordionItem key={item.q} q={item.q} a={item.a} />
              ))}
            </div>
          </div>
        ))}

        <div className="bg-yellow-900/10 border border-yellow-800/30 rounded-xl p-4 text-xs text-yellow-700 leading-relaxed">
          <strong className="text-yellow-600">Important:</strong> This educational content is for informational purposes only.
          Options trading involves substantial risk of loss and is not suitable for all investors.
          The strategies described here may not be appropriate for your financial situation.
          Always consult a licensed financial advisor before trading.
        </div>
      </div>
    </div>
  );
}
