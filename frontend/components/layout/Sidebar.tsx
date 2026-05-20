"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  BarChart2, MessageSquare, TrendingUp, Activity,
  BookOpen, Star, ChevronRight, Zap,
  PanelLeftClose, PanelLeftOpen, Globe, BrainCircuit,
  FlaskConical, Menu, X, History,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { useState, useEffect } from "react";

const NAV = [
  { href: "/console",     label: "Console",     icon: BarChart2,    desc: "Visual analysis" },
  { href: "/chat",        label: "Nexus AI",    icon: MessageSquare,desc: "AI assistant" },
  { href: "/simulate",    label: "Simulate",    icon: History,      desc: "History replay" },
  { href: "/scanner",     label: "Scanner",     icon: Activity,     desc: "Options flow" },
  { href: "/backtest",    label: "Backtest",    icon: TrendingUp,   desc: "Strategy testing" },
  { href: "/events",      label: "Events",      icon: Globe,        desc: "Market events" },
  { href: "/predictions", label: "Predictions", icon: BrainCircuit, desc: "AI accuracy" },
  { href: "/watchlist",   label: "Watchlist",   icon: Star,         desc: "Track symbols" },
  { href: "/learn",       label: "Learn",       icon: BookOpen,     desc: "Education" },
  { href: "/test",        label: "API Tests",   icon: FlaskConical, desc: "Live endpoint tests" },
];

const STORAGE_KEY = "nexus_sidebar_collapsed";

export function Sidebar() {
  const path = usePathname();
  const [collapsed, setCollapsed] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);

  useEffect(() => {
    const stored = localStorage.getItem(STORAGE_KEY);
    if (stored !== null) setCollapsed(stored === "true");
  }, []);

  // Close mobile drawer on route change
  useEffect(() => { setMobileOpen(false); }, [path]);

  const toggle = () => {
    setCollapsed((c) => {
      localStorage.setItem(STORAGE_KEY, String(!c));
      return !c;
    });
  };

  const NavItems = ({ onClick }: { onClick?: () => void }) => (
    <>
      {NAV.map(({ href, label, icon: Icon, desc }) => {
        const active = path === href || path.startsWith(href + "/");
        return (
          <Link key={href} href={href} onClick={onClick}
            title={collapsed ? label : undefined}
            className={cn(
              "flex items-center rounded-lg text-sm transition-all group relative",
              collapsed ? "justify-center px-0 py-2.5" : "gap-3 px-3 py-2.5",
              active
                ? "bg-blue-600/20 text-blue-400 border border-blue-600/30"
                : "text-gray-400 hover:bg-[#1f2937] hover:text-gray-200"
            )}>
            <Icon size={16} className={cn("flex-shrink-0",
              active ? "text-blue-400" : "text-gray-500 group-hover:text-gray-300")} />
            {!collapsed && (
              <>
                <div className="flex-1 min-w-0">
                  <div className="font-medium">{label}</div>
                  <div className="text-[10px] text-gray-600 group-hover:text-gray-500">{desc}</div>
                </div>
                {active && <ChevronRight size={12} className="text-blue-400" />}
              </>
            )}
            {collapsed && (
              <div className="absolute left-full ml-3 px-2.5 py-1.5 bg-[#1f2937] border border-[#374151] rounded-lg text-xs text-white whitespace-nowrap opacity-0 group-hover:opacity-100 pointer-events-none transition-opacity z-50 shadow-xl">
                <div className="font-medium">{label}</div>
                <div className="text-[10px] text-gray-400">{desc}</div>
              </div>
            )}
          </Link>
        );
      })}
    </>
  );

  return (
    <>
      {/* ── Mobile hamburger button ── */}
      <button
        onClick={() => setMobileOpen(true)}
        className="md:hidden fixed top-3 left-3 z-50 w-9 h-9 bg-[#111827] border border-[#1f2937] rounded-lg flex items-center justify-center text-gray-400 hover:text-white shadow-lg"
        aria-label="Open menu"
      >
        <Menu size={16} />
      </button>

      {/* ── Mobile overlay drawer ── */}
      {mobileOpen && (
        <div className="md:hidden fixed inset-0 z-50 flex">
          {/* Backdrop */}
          <div className="absolute inset-0 bg-black/60 backdrop-blur-sm" onClick={() => setMobileOpen(false)} />
          {/* Drawer */}
          <aside className="relative w-64 flex flex-col bg-[#111827] border-r border-[#1f2937] h-full shadow-2xl">
            <div className="flex items-center gap-2 px-4 h-14 border-b border-[#1f2937]">
              <div className="w-8 h-8 rounded-lg bg-blue-600 flex items-center justify-center">
                <Zap size={16} className="text-white" />
              </div>
              <div className="flex-1">
                <div className="text-sm font-bold text-white tracking-wide">NEXUS</div>
                <div className="text-[10px] text-gray-500 uppercase tracking-widest">Trader</div>
              </div>
              <button onClick={() => setMobileOpen(false)} className="text-gray-500 hover:text-white transition-colors">
                <X size={16} />
              </button>
            </div>
            <nav className="flex-1 py-3 space-y-0.5 px-2 overflow-y-auto">
              <NavItems onClick={() => setMobileOpen(false)} />
            </nav>
            <div className="px-3 py-3 border-t border-[#1f2937]">
              <p className="text-[9px] text-gray-600 leading-relaxed">
                Not financial advice. Options trading involves substantial risk of loss.
              </p>
            </div>
          </aside>
        </div>
      )}

      {/* ── Desktop sidebar ── */}
      <aside className={cn(
        "hidden md:flex flex-shrink-0 flex-col bg-[#111827] border-r border-[#1f2937] transition-all duration-200 relative",
        collapsed ? "w-14" : "w-56"
      )}>
        {/* Logo */}
        <div className={cn("flex items-center border-b border-[#1f2937] h-14",
          collapsed ? "justify-center" : "px-4 gap-2")}>
          {!collapsed && (
            <div className="flex items-center gap-2 flex-1 min-w-0">
              <div className="w-8 h-8 rounded-lg bg-blue-600 flex items-center justify-center flex-shrink-0">
                <Zap size={16} className="text-white" />
              </div>
              <div className="min-w-0">
                <div className="text-sm font-bold text-white tracking-wide">NEXUS</div>
                <div className="text-[10px] text-gray-500 uppercase tracking-widest">Trader</div>
              </div>
            </div>
          )}
          {collapsed && (
            <div className="w-8 h-8 rounded-lg bg-blue-600 flex items-center justify-center">
              <Zap size={16} className="text-white" />
            </div>
          )}
        </div>

        {/* Collapse toggle tab */}
        <button onClick={toggle}
          className="absolute -right-3 top-4 z-50 w-6 h-6 bg-[#1f2937] border border-[#374151] rounded-full flex items-center justify-center text-gray-400 hover:text-white hover:bg-[#374151] transition-colors shadow-lg"
          title={collapsed ? "Expand sidebar" : "Collapse sidebar"}>
          {collapsed ? <PanelLeftOpen size={11} /> : <PanelLeftClose size={11} />}
        </button>

        {/* Nav */}
        <nav className="flex-1 py-3 space-y-0.5 px-2 overflow-y-auto">
          <NavItems />
        </nav>

        {!collapsed && (
          <div className="px-3 py-3 border-t border-[#1f2937]">
            <p className="text-[9px] text-gray-600 leading-relaxed">
              Not financial advice. Options trading involves substantial risk of loss.
              Always consult a licensed advisor.
            </p>
          </div>
        )}
      </aside>
    </>
  );
}
