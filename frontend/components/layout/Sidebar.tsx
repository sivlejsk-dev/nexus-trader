"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  BarChart2, MessageSquare, TrendingUp, Activity,
  BookOpen, Star, ChevronRight, Zap,
} from "lucide-react";
import { cn } from "@/lib/utils";

const NAV = [
  { href: "/console",   label: "Console",    icon: BarChart2,     desc: "Visual analysis" },
  { href: "/chat",      label: "Nexus AI",   icon: MessageSquare, desc: "AI assistant" },
  { href: "/scanner",   label: "Scanner",    icon: Activity,      desc: "Options flow" },
  { href: "/backtest",  label: "Backtest",   icon: TrendingUp,    desc: "Strategy testing" },
  { href: "/watchlist", label: "Watchlist",  icon: Star,          desc: "Track symbols" },
  { href: "/learn",     label: "Learn",      icon: BookOpen,      desc: "Education" },
];

export function Sidebar() {
  const path = usePathname();

  return (
    <aside className="w-56 flex-shrink-0 flex flex-col bg-[#111827] border-r border-[#1f2937]">
      {/* Logo */}
      <div className="flex items-center gap-2 px-4 py-5 border-b border-[#1f2937]">
        <div className="w-8 h-8 rounded-lg bg-blue-600 flex items-center justify-center">
          <Zap size={16} className="text-white" />
        </div>
        <div>
          <div className="text-sm font-bold text-white tracking-wide">NEXUS</div>
          <div className="text-[10px] text-gray-500 uppercase tracking-widest">Trader</div>
        </div>
      </div>

      {/* Nav */}
      <nav className="flex-1 py-3 space-y-0.5 px-2">
        {NAV.map(({ href, label, icon: Icon, desc }) => {
          const active = path === href || path.startsWith(href + "/");
          return (
            <Link
              key={href}
              href={href}
              className={cn(
                "flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm transition-all group",
                active
                  ? "bg-blue-600/20 text-blue-400 border border-blue-600/30"
                  : "text-gray-400 hover:bg-[#1f2937] hover:text-gray-200"
              )}
            >
              <Icon size={16} className={active ? "text-blue-400" : "text-gray-500 group-hover:text-gray-300"} />
              <div className="flex-1 min-w-0">
                <div className="font-medium">{label}</div>
                <div className="text-[10px] text-gray-600 group-hover:text-gray-500">{desc}</div>
              </div>
              {active && <ChevronRight size={12} className="text-blue-400" />}
            </Link>
          );
        })}
      </nav>

      {/* Disclaimer footer */}
      <div className="px-3 py-3 border-t border-[#1f2937]">
        <p className="text-[9px] text-gray-600 leading-relaxed">
          Not financial advice. Options trading involves substantial risk of loss.
          Always consult a licensed advisor.
        </p>
      </div>
    </aside>
  );
}
