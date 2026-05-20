"use client";

import { useState, useRef, useEffect, useCallback } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import {
  Send, Trash2, Zap, User, Bot, Loader2, AlertTriangle,
  Plus, MessageSquare, Pencil, Check, X, Clock,
  TrendingUp, TrendingDown, Minus, BarChart2, ExternalLink,
  BrainCircuit, Globe, Mic, MicOff, Volume2, VolumeX,
} from "lucide-react";
import { api, type ChatResponse, type ChatSession, type FullAnalysis, type SimulationResult } from "@/lib/api";
import { getSessionId, cn, fmtPrice, fmtPct, changeColor, confidenceColor, directionColor } from "@/lib/utils";

interface Message {
  role: "user" | "assistant";
  content: string;
  intent?: string;
  symbols?: string[];
  timestamp: Date;
  simulation?: SimulationResult;
  triggeredActions?: string[];
}

// ── Inline simulation result card ─────────────────────────────────────────────

function InlineSimulation({ sim }: { sim: SimulationResult }) {
  const wr = sim.win_rate;
  const dr = sim.date_range || {};
  return (
    <div className="mt-2 bg-[#0d1117] border border-[#1f2937] rounded-xl p-3 text-xs space-y-2">
      <div className="flex items-center gap-2">
        <BarChart2 size={12} className="text-blue-400" />
        <span className="font-semibold text-gray-200">{sim.symbol} — Historical Simulation</span>
        <span className="text-gray-600 ml-auto">{dr.start?.slice(0,4)} – {dr.end?.slice(0,4)}</span>
      </div>
      <div className="grid grid-cols-3 gap-2 text-center">
        {[
          { label: "Win Rate",    value: wr != null ? `${wr}%` : "—",   color: (wr ?? 0) >= 55 ? "text-green-400" : "text-red-400" },
          { label: "Predictions", value: sim.total_predictions,          color: "text-white" },
          { label: "Avg P&L",     value: sim.avg_pnl_pct != null ? `${sim.avg_pnl_pct > 0 ? "+" : ""}${sim.avg_pnl_pct}%` : "—",
            color: (sim.avg_pnl_pct ?? 0) >= 0 ? "text-green-400" : "text-red-400" },
        ].map(({ label, value, color }) => (
          <div key={label} className="bg-[#111827] rounded-lg p-2">
            <div className={cn("text-base font-bold font-mono", color)}>{value}</div>
            <div className="text-[10px] text-gray-600">{label}</div>
          </div>
        ))}
      </div>
      {sim.events && sim.events.length > 0 && (
        <div className="text-[10px] text-gray-500">
          {sim.events.length} world events in this period ·{" "}
          {sim.events.slice(0, 2).map(e => e.title).join(", ")}
          {sim.events.length > 2 ? ` +${sim.events.length - 2} more` : ""}
        </div>
      )}
      <a href={`/simulate`} className="block text-center text-[10px] text-blue-400 hover:text-blue-300 transition-colors pt-1">
        Open full simulation →
      </a>
    </div>
  );
}

function formatRelative(iso: string): string {
  const d = new Date(iso + "Z");
  const diff = Date.now() - d.getTime();
  if (diff < 60_000) return "just now";
  if (diff < 3_600_000) return `${Math.floor(diff / 60_000)}m ago`;
  if (diff < 86_400_000) return `${Math.floor(diff / 3_600_000)}h ago`;
  return `${Math.floor(diff / 86_400_000)}d ago`;
}

// ── Symbol analysis panel ─────────────────────────────────────────────────────

function SymbolPanel({ symbol, onClose }: { symbol: string; onClose: () => void }) {
  const [data, setData] = useState<FullAnalysis | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setLoading(true);
    setError(null);
    setData(null);
    api.analysis(symbol)
      .then(setData)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, [symbol]);

  const adaptive = data?.adaptive_prediction;
  const quote = data?.quote;
  const patterns = data?.patterns;
  const eventIntel = (data as any)?.event_intelligence;

  return (
    <div className="w-72 flex-shrink-0 flex flex-col bg-[#0d1117] border-l border-[#1f2937] overflow-y-auto">
      {/* Header */}
      <div className="flex items-center gap-2 px-3 py-2.5 border-b border-[#1f2937] bg-[#111827]">
        <BarChart2 size={13} className="text-blue-400" />
        <span className="text-xs font-semibold text-white font-mono">{symbol}</span>
        <div className="flex-1" />
        <a href={`/console?symbol=${symbol}`} target="_blank"
          className="text-[10px] text-blue-400 hover:text-blue-300 flex items-center gap-0.5 transition-colors">
          <ExternalLink size={9} /> Console
        </a>
        <button onClick={onClose} className="text-gray-600 hover:text-gray-300 transition-colors ml-1">
          <X size={13} />
        </button>
      </div>

      {loading && (
        <div className="flex items-center justify-center h-32">
          <Loader2 size={18} className="animate-spin text-blue-400" />
        </div>
      )}

      {error && (
        <div className="m-3 text-xs text-red-400 bg-red-900/20 border border-red-800/30 rounded-lg p-2">
          {error}
        </div>
      )}

      {data && !loading && (
        <div className="p-3 space-y-3">
          {/* Quote */}
          {quote && (
            <div className="bg-[#111827] border border-[#1f2937] rounded-xl p-3">
              <div className="flex items-baseline gap-2 mb-1">
                <span className="text-xl font-bold font-mono text-white">{fmtPrice(quote.price)}</span>
                <span className={cn("text-sm font-mono font-semibold", changeColor(quote.change_pct))}>
                  {fmtPct(quote.change_pct)}
                </span>
              </div>
              <div className="grid grid-cols-2 gap-x-3 gap-y-0.5 text-[10px]">
                {[["Open", fmtPrice(quote.open)], ["High", fmtPrice(quote.high)], ["Low", fmtPrice(quote.low)], ["Prev", fmtPrice(quote.prev_close)]].map(([l, v]) => (
                  <div key={l} className="flex justify-between">
                    <span className="text-gray-600">{l}</span>
                    <span className="text-gray-300 font-mono">{v}</span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Nexus prediction */}
          {adaptive && (
            <div className={cn("border rounded-xl p-3",
              adaptive.prediction.direction === "call" ? "bg-green-900/10 border-green-800/30" :
              adaptive.prediction.direction === "put"  ? "bg-red-900/10 border-red-800/30" :
              "bg-[#111827] border-[#1f2937]")}>
              <div className="flex items-center gap-1.5 mb-2">
                <BrainCircuit size={12} className="text-cyan-400" />
                <span className="text-[10px] font-semibold text-gray-300">Nexus Prediction</span>
              </div>
              <div className="flex items-center gap-2 mb-2">
                <span className={cn("text-lg font-bold uppercase",
                  adaptive.prediction.direction === "call" ? "text-green-400" :
                  adaptive.prediction.direction === "put"  ? "text-red-400" : "text-gray-400")}>
                  {adaptive.prediction.direction}
                </span>
                <span className={cn("text-sm font-mono font-semibold", confidenceColor(adaptive.prediction.confidence))}>
                  {Math.round(adaptive.prediction.confidence * 100)}%
                </span>
              </div>
              <div className="grid grid-cols-2 gap-2 mb-2">
                <div className="bg-[#1f2937]/60 rounded-lg p-2 text-center">
                  <div className="text-[9px] text-gray-600">Target</div>
                  <div className="text-xs font-mono text-green-400">{fmtPrice(adaptive.prediction.target_price)}</div>
                </div>
                <div className="bg-[#1f2937]/60 rounded-lg p-2 text-center">
                  <div className="text-[9px] text-gray-600">Stop</div>
                  <div className="text-xs font-mono text-red-400">{fmtPrice(adaptive.prediction.stop_loss)}</div>
                </div>
              </div>
              <ul className="space-y-1">
                {adaptive.prediction.rationale.slice(0, 3).map((r, i) => (
                  <li key={i} className="text-[10px] text-gray-400 flex gap-1.5">
                    <span className="text-cyan-500 flex-shrink-0">›</span>{r}
                  </li>
                ))}
              </ul>
              {adaptive.review.win_rate != null && (
                <div className="mt-2 pt-2 border-t border-[#1f2937] flex items-center justify-between text-[10px]">
                  <span className="text-gray-600">Track record</span>
                  <span className={cn("font-mono font-semibold", adaptive.review.win_rate >= 50 ? "text-green-400" : "text-red-400")}>
                    {adaptive.review.win_rate}% ({adaptive.review.completed} reviewed)
                  </span>
                </div>
              )}
            </div>
          )}

          {/* Market bias */}
          {patterns?.summary && (
            <div className="bg-[#111827] border border-[#1f2937] rounded-xl p-3">
              <div className="text-[10px] text-gray-600 mb-1.5">Market Bias</div>
              <div className="flex items-center gap-2">
                {patterns.summary.bias === "bullish" ? <TrendingUp size={14} className="text-green-400" /> :
                 patterns.summary.bias === "bearish" ? <TrendingDown size={14} className="text-red-400" /> :
                 <Minus size={14} className="text-gray-400" />}
                <span className={cn("text-sm font-semibold capitalize", directionColor(patterns.summary.bias || "neutral"))}>
                  {patterns.summary.bias || "neutral"}
                </span>
                <span className="text-[10px] text-gray-600 ml-auto">
                  {patterns.summary.bullish_signals}↑ {patterns.summary.bearish_signals}↓
                </span>
              </div>
            </div>
          )}

          {/* Event intelligence */}
          {eventIntel?.composite && (
            <div className={cn("border rounded-xl p-3",
              eventIntel.composite.bias === "bullish" ? "bg-green-900/10 border-green-800/30" :
              eventIntel.composite.bias === "bearish" ? "bg-red-900/10 border-red-800/30" :
              "bg-yellow-900/10 border-yellow-800/30")}>
              <div className="flex items-center gap-1.5 mb-1">
                <Globe size={11} className="text-blue-400" />
                <span className="text-[10px] font-semibold text-gray-300">Event Intelligence</span>
              </div>
              <div className={cn("text-xs font-bold capitalize",
                eventIntel.composite.bias === "bullish" ? "text-green-400" :
                eventIntel.composite.bias === "bearish" ? "text-red-400" : "text-yellow-400")}>
                {eventIntel.composite.bias === "bullish" ? "Call bias" :
                 eventIntel.composite.bias === "bearish" ? "Put bias" : "Volatility"}
              </div>
              <div className="text-[10px] text-gray-500 mt-0.5">
                {Math.round((eventIntel.composite.confidence || 0) * 100)}% confidence
              </div>
            </div>
          )}

          {/* Quick links */}
          <div className="flex gap-2">
            <a href={`/simulate?symbol=${symbol}`}
              className="flex-1 text-center text-[10px] py-1.5 rounded-lg bg-[#1f2937] text-gray-400 hover:text-white hover:bg-[#374151] transition-colors border border-[#374151]">
              Simulate history
            </a>
            <a href={`/events?symbol=${symbol}`}
              className="flex-1 text-center text-[10px] py-1.5 rounded-lg bg-[#1f2937] text-gray-400 hover:text-white hover:bg-[#374151] transition-colors border border-[#374151]">
              Events
            </a>
          </div>
        </div>
      )}
    </div>
  );
}

// ── Main chat page ────────────────────────────────────────────────────────────

export default function ChatPage() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [sessionId, setSessionId] = useState<string>(() => getSessionId());
  const [activeSymbol, setActiveSymbol] = useState<string | null>(null);
  const [voiceMode, setVoiceMode] = useState(false);
  const [muted, setMuted] = useState(false);
  const [listening, setListening] = useState(false);
  const [interimText, setInterimText] = useState("");
  const recognitionRef = useRef<any>(null);
  const voiceAvailable = typeof window !== "undefined" &&
    !!(window.SpeechRecognition || (window as any).webkitSpeechRecognition);

  const [sessions, setSessions] = useState<ChatSession[]>([]);
  const [sessionsLoading, setSessionsLoading] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editTitle, setEditTitle] = useState("");
  const [memorySuggestions, setMemorySuggestions] = useState<string[]>([]);

  const bottomRef = useRef<HTMLDivElement>(null);

  const loadSessions = useCallback(async () => {
    setSessionsLoading(true);
    try { const res = await api.getSessions(); setSessions(res.sessions); } catch {}
    setSessionsLoading(false);
  }, []);

  const loadSessionHistory = useCallback(async (sid: string) => {
    try {
      const res = await api.getSession(sid);
      const turns = res.turns as Array<{ role: string; content: string; intent?: string; symbols?: string[]; timestamp: string }>;
      setMessages(turns.filter((t) => t.role === "user" || t.role === "assistant").map((t) => ({
        role: t.role as "user" | "assistant",
        content: t.content, intent: t.intent, symbols: t.symbols,
        timestamp: new Date(t.timestamp + "Z"),
      })));
      // Restore last active symbol from history
      const lastWithSymbol = [...turns].reverse().find((t) => t.symbols && t.symbols.length > 0);
      if (lastWithSymbol?.symbols?.[0]) setActiveSymbol(lastWithSymbol.symbols[0]);
    } catch {}
  }, []);

  useEffect(() => { loadSessions(); }, [loadSessions]);
  useEffect(() => { loadSessionHistory(sessionId); }, [sessionId, loadSessionHistory]);
  useEffect(() => { bottomRef.current?.scrollIntoView({ behavior: "smooth" }); }, [messages]);

  // Load memory-based suggestions on mount
  useEffect(() => {
    api.memorySummary().then((mem) => {
      const suggestions: string[] = [];
      if (mem.top_symbols[0]) suggestions.push(`Analyze ${mem.top_symbols[0].symbol} for me`);
      if (mem.top_symbols[1]) suggestions.push(`Should I buy ${mem.top_symbols[1].symbol} calls?`);
      if (mem.recent_scenarios[0]) suggestions.push(`Run that simulation again`);
      if (mem.recent_predictions[0]) {
        const p = mem.recent_predictions[0];
        suggestions.push(`How accurate was your ${p.symbol} ${p.direction} call?`);
      }
      if (suggestions.length > 0) setMemorySuggestions(suggestions);
    }).catch(() => {});
  }, []);

  // TTS helper
  const speak = useCallback((text: string) => {
    if (muted || typeof window === "undefined" || !window.speechSynthesis) return;
    window.speechSynthesis.cancel();
    const clean = text.replace(/```[\s\S]*?```/g, "").replace(/[#*_`>[\]()]/g, "").replace(/\s+/g, " ").trim().slice(0, 500);
    const utt = new SpeechSynthesisUtterance(clean);
    utt.rate = 1.0; utt.pitch = 0.95;
    window.speechSynthesis.speak(utt);
  }, [muted]);

  const send = useCallback(async (text: string) => {
    const msg = text.trim();
    if (!msg || loading) return;
    setMessages((prev) => [...prev, { role: "user", content: msg, timestamp: new Date() }]);
    setInput(""); setInterimText("");
    setLoading(true);
    try {
      const res: ChatResponse = await api.chat(msg, sessionId, voiceMode);
      setMessages((prev) => [...prev, {
        role: "assistant", content: res.response,
        intent: res.intent, symbols: res.symbols, timestamp: new Date(),
        simulation: res.simulation,
        triggeredActions: res.triggered_actions,
      }]);
      if (res.active_symbol) setActiveSymbol(res.active_symbol);
      else if (res.symbols && res.symbols.length > 0) setActiveSymbol(res.symbols[0]);
      if (voiceMode) speak(res.response);
      loadSessions();
    } catch (e: any) {
      setMessages((prev) => [...prev, {
        role: "assistant",
        content: `⚠️ Error: ${e.message}. Make sure the backend is running.`,
        timestamp: new Date(),
      }]);
    } finally {
      setLoading(false);
    }
  }, [loading, sessionId, loadSessions, voiceMode, speak]);

  // Voice recognition setup
  useEffect(() => {
    if (!voiceAvailable) return;
    const Ctor = (window.SpeechRecognition || (window as any).webkitSpeechRecognition) as any;
    const rec = new Ctor();
    rec.continuous = false; rec.interimResults = true; rec.lang = "en-US";
    rec.onstart = () => setListening(true);
    rec.onend = () => setListening(false);
    rec.onerror = () => setListening(false);
    rec.onresult = (e: any) => {
      let final = ""; let interim = "";
      for (let i = e.resultIndex; i < e.results.length; i++) {
        if (e.results[i].isFinal) final += e.results[i][0].transcript;
        else interim += e.results[i][0].transcript;
      }
      if (interim) setInterimText(interim.trim());
      if (final.trim()) { setInterimText(""); send(final.trim()); }
    };
    recognitionRef.current = rec;
    return () => { rec.onend = null; try { rec.stop(); } catch {} };
  }, [send, voiceAvailable]);

  const toggleListen = () => {
    const rec = recognitionRef.current;
    if (!rec) return;
    if (listening) { try { rec.stop(); } catch {} }
    else { window.speechSynthesis?.cancel(); try { rec.start(); } catch {} }
  };

  const newSession = () => {
    const id = `session_${Date.now()}_${Math.random().toString(36).slice(2)}`;
    localStorage.setItem("nexus_session_id", id);
    setSessionId(id); setMessages([]); setActiveSymbol(null); loadSessions();
  };

  const switchSession = (sid: string) => {
    localStorage.setItem("nexus_session_id", sid);
    setSessionId(sid);
  };

  const clearChat = async () => {
    try { await api.clearHistory(sessionId); } catch {}
    setMessages([]); setActiveSymbol(null);
  };

  const deleteSession = async (sid: string) => {
    try { await api.deleteSession(sid); } catch {}
    if (sid === sessionId) newSession(); else loadSessions();
  };

  const startRename = (s: ChatSession) => { setEditingId(s.id); setEditTitle(s.title); };
  const confirmRename = async (sid: string) => {
    if (editTitle.trim()) { try { await api.renameSession(sid, editTitle.trim()); } catch {} loadSessions(); }
    setEditingId(null);
  };

  const handleKey = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(input); }
  };

  return (
    <div className="flex h-full bg-[#0a0e1a] overflow-hidden">

      {/* Session sidebar */}
      <aside className="w-52 flex-shrink-0 flex flex-col bg-[#0d1117] border-r border-[#1f2937] hidden md:flex">
        <div className="flex items-center justify-between px-3 py-3 border-b border-[#1f2937]">
          <span className="text-xs font-semibold text-gray-400 uppercase tracking-wide">History</span>
          <button onClick={newSession} title="New conversation"
            className="w-6 h-6 rounded-md bg-blue-600 hover:bg-blue-500 flex items-center justify-center transition-colors">
            <Plus size={12} className="text-white" />
          </button>
        </div>
        <div className="flex-1 overflow-y-auto py-1">
          {sessionsLoading && (
            <div className="flex items-center gap-2 px-3 py-2 text-xs text-gray-600">
              <Loader2 size={11} className="animate-spin" /> Loading…
            </div>
          )}
          {sessions.map((s) => (
            <div key={s.id} onClick={() => switchSession(s.id)}
              className={cn("group relative flex flex-col px-3 py-2.5 cursor-pointer transition-colors",
                s.id === sessionId ? "bg-blue-600/15 border-r-2 border-blue-500" : "hover:bg-[#1f2937]/60")}>
              {editingId === s.id ? (
                <div className="flex items-center gap-1" onClick={(e) => e.stopPropagation()}>
                  <input autoFocus value={editTitle} onChange={(e) => setEditTitle(e.target.value)}
                    onKeyDown={(e) => { if (e.key === "Enter") confirmRename(s.id); if (e.key === "Escape") setEditingId(null); }}
                    className="flex-1 bg-[#1f2937] text-xs text-white px-1.5 py-0.5 rounded border border-blue-500 focus:outline-none min-w-0" />
                  <button onClick={() => confirmRename(s.id)} className="text-green-400"><Check size={11} /></button>
                  <button onClick={() => setEditingId(null)} className="text-gray-500"><X size={11} /></button>
                </div>
              ) : (
                <>
                  <div className="flex items-start gap-1.5">
                    <MessageSquare size={11} className={cn("mt-0.5 flex-shrink-0", s.id === sessionId ? "text-blue-400" : "text-gray-600")} />
                    <span className={cn("text-xs leading-snug line-clamp-2 flex-1 min-w-0", s.id === sessionId ? "text-gray-200" : "text-gray-400")}>
                      {s.title}
                    </span>
                  </div>
                  <div className="flex items-center gap-1.5 mt-1 ml-4">
                    <Clock size={9} className="text-gray-700" />
                    <span className="text-[10px] text-gray-600">{formatRelative(s.updated_at)}</span>
                  </div>
                  <div className="absolute right-2 top-2 hidden group-hover:flex items-center gap-1" onClick={(e) => e.stopPropagation()}>
                    <button onClick={() => startRename(s)} className="w-5 h-5 rounded flex items-center justify-center text-gray-600 hover:text-gray-300 hover:bg-[#374151]"><Pencil size={9} /></button>
                    <button onClick={() => deleteSession(s.id)} className="w-5 h-5 rounded flex items-center justify-center text-gray-600 hover:text-red-400 hover:bg-[#374151]"><Trash2 size={9} /></button>
                  </div>
                </>
              )}
            </div>
          ))}
          {!sessionsLoading && sessions.length === 0 && (
            <p className="px-3 py-4 text-xs text-gray-700 text-center">No conversations yet</p>
          )}
        </div>
      </aside>

      {/* Main chat */}
      <div className="flex-1 flex flex-col min-w-0">
        <div className="flex items-center gap-3 px-5 py-3 border-b border-[#1f2937] bg-[#111827]">
          <div className="w-7 h-7 rounded-lg bg-blue-600 flex items-center justify-center">
            <Zap size={14} className="text-white" />
          </div>
          <div className="min-w-0">
            <div className="text-sm font-semibold text-white">Nexus AI</div>
            <div className="text-[10px] text-gray-500 truncate">
              {sessions.find((s) => s.id === sessionId)?.title || "New conversation"}
            </div>
          </div>
          <div className="flex-1" />
          {activeSymbol && (
            <button onClick={() => setActiveSymbol(null)}
              className="flex items-center gap-1.5 text-[10px] bg-blue-600/20 border border-blue-600/30 text-blue-400 px-2 py-1 rounded-lg hover:bg-blue-600/30 transition-colors">
              <BarChart2 size={10} /> {activeSymbol} <X size={9} />
            </button>
          )}
          {/* Voice controls */}
          <button onClick={() => setVoiceMode((v) => !v)}
            className={cn("text-[10px] px-2 py-1 rounded-lg border transition-colors font-medium",
              voiceMode ? "bg-blue-600/20 border-blue-600/40 text-blue-400" : "border-[#374151] text-gray-600 hover:text-gray-300")}
            title="Voice mode: shorter spoken responses">
            Voice
          </button>
          <button onClick={() => setMuted((m) => !m)}
            className={cn("p-1.5 rounded-lg transition-colors", muted ? "text-gray-600" : "text-gray-400 hover:text-white")}
            title={muted ? "Unmute" : "Mute TTS"}>
            {muted ? <VolumeX size={13} /> : <Volume2 size={13} />}
          </button>
          {voiceAvailable && (
            <button onClick={toggleListen}
              className={cn("p-1.5 rounded-lg transition-colors",
                listening ? "text-red-400 bg-red-900/20" : "text-gray-500 hover:text-gray-300 hover:bg-[#1f2937]")}
              title={listening ? "Stop listening" : "Push to talk"}>
              {listening ? <MicOff size={13} /> : <Mic size={13} />}
            </button>
          )}
          {messages.length > 0 && (
            <button onClick={clearChat} className="flex items-center gap-1.5 text-xs text-gray-500 hover:text-red-400 transition-colors">
              <Trash2 size={12} /> Clear
            </button>
          )}
        </div>

        <div className="flex-1 overflow-auto px-5 py-4 space-y-4">
          {messages.length === 0 && (
            <div className="flex flex-col items-center justify-center h-full gap-6 text-center">
              <div className="w-16 h-16 rounded-2xl bg-blue-600/20 border border-blue-600/30 flex items-center justify-center">
                <Zap size={28} className="text-blue-400" />
              </div>
              <div>
                <h2 className="text-lg font-semibold text-white mb-2">Nexus AI Trading Assistant</h2>
                <p className="text-sm text-gray-500 max-w-md leading-relaxed">
                  Mention any ticker and Nexus will pull up live analysis, call/put predictions, and event intelligence automatically.
                  Say "simulate Apple from 1995 to 2000" and Nexus will run it and explain the results.
                </p>
              </div>
              <div className="flex flex-wrap gap-2 justify-center">
                {(memorySuggestions.length > 0 ? memorySuggestions : [
                  "Analyze AAPL for me",
                  "Simulate NVDA over the last 5 years",
                  "Should I buy TSLA calls?",
                  "How accurate have your predictions been?",
                ]).map((q) => (
                  <button key={q} onClick={() => send(q)}
                    className="text-xs bg-[#111827] border border-[#1f2937] text-gray-400 hover:text-white hover:border-blue-600/40 px-3 py-1.5 rounded-lg transition-colors">
                    {q}
                  </button>
                ))}
              </div>
              {memorySuggestions.length > 0 && (
                <p className="text-[10px] text-gray-700">Suggestions based on your history</p>
              )}
            </div>
          )}

          {messages.map((msg, i) => (
            <div key={i} className={cn("flex gap-3", msg.role === "user" ? "justify-end" : "justify-start")}>
              {msg.role === "assistant" && (
                <div className="w-7 h-7 rounded-lg bg-blue-600/20 border border-blue-600/30 flex items-center justify-center flex-shrink-0 mt-0.5">
                  <Bot size={13} className="text-blue-400" />
                </div>
              )}
              <div className={cn("max-w-[78%]")}>
                <div className={cn("rounded-2xl px-4 py-3 text-sm",
                  msg.role === "user"
                    ? "bg-blue-600 text-white rounded-tr-sm"
                    : "bg-[#111827] border border-[#1f2937] text-gray-200 rounded-tl-sm")}>
                  {msg.role === "assistant"
                    ? <div className="prose-nexus"><ReactMarkdown remarkPlugins={[remarkGfm]}>{msg.content}</ReactMarkdown></div>
                    : <p>{msg.content}</p>}
                  <div className="flex items-center gap-2 mt-2 flex-wrap">
                    <span className="text-[10px] opacity-40">
                      {msg.timestamp.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}
                    </span>
                    {msg.intent && msg.intent !== "general" && (
                      <span className="text-[10px] bg-blue-900/30 text-blue-400 px-1.5 py-0.5 rounded">{msg.intent.replace(/_/g, " ")}</span>
                    )}
                    {msg.triggeredActions && msg.triggeredActions.length > 0 && (
                      <span className="text-[10px] bg-cyan-900/30 text-cyan-400 px-1.5 py-0.5 rounded">
                        auto: {msg.triggeredActions[0].split(":")[0]}
                      </span>
                    )}
                    {msg.symbols?.map((s) => (
                      <button key={s} onClick={() => setActiveSymbol(s)}
                        className="text-[10px] bg-gray-800 hover:bg-blue-900/30 text-gray-400 hover:text-blue-400 px-1.5 py-0.5 rounded font-mono transition-colors">
                        {s}
                      </button>
                    ))}
                  </div>
                </div>
                {/* Inline simulation result */}
                {msg.simulation && <InlineSimulation sim={msg.simulation} />}
              </div>
              {msg.role === "user" && (
                <div className="w-7 h-7 rounded-lg bg-gray-700 flex items-center justify-center flex-shrink-0 mt-0.5">
                  <User size={13} className="text-gray-300" />
                </div>
              )}
            </div>
          ))}

          {/* Interim voice text */}
          {interimText && (
            <div className="flex justify-end">
              <div className="bg-blue-600/20 border border-blue-600/20 rounded-2xl rounded-tr-sm px-4 py-2 text-sm text-blue-300 italic max-w-[78%]">
                {interimText}…
              </div>
            </div>
          )}

          {loading && (
            <div className="flex gap-3">
              <div className="w-7 h-7 rounded-lg bg-blue-600/20 border border-blue-600/30 flex items-center justify-center flex-shrink-0">
                <Bot size={13} className="text-blue-400" />
              </div>
              <div className="bg-[#111827] border border-[#1f2937] rounded-2xl rounded-tl-sm px-4 py-3">
                <div className="flex gap-1 items-center">
                  <span className="w-1.5 h-1.5 bg-blue-400 rounded-full animate-bounce" style={{ animationDelay: "0ms" }} />
                  <span className="w-1.5 h-1.5 bg-blue-400 rounded-full animate-bounce" style={{ animationDelay: "150ms" }} />
                  <span className="w-1.5 h-1.5 bg-blue-400 rounded-full animate-bounce" style={{ animationDelay: "300ms" }} />
                </div>
              </div>
            </div>
          )}
          <div ref={bottomRef} />
        </div>

        <div className="px-5 py-1.5 flex items-center gap-1.5 text-[10px] text-gray-600 border-t border-[#1f2937]">
          <AlertTriangle size={10} /> Not financial advice. Options trading involves substantial risk of loss.
        </div>

        <div className="px-5 pb-4 pt-2">
          <div className="flex items-end gap-2 bg-[#111827] border border-[#1f2937] focus-within:border-blue-600/50 rounded-xl px-4 py-3 transition-colors">
            <textarea autoFocus value={input} onChange={(e) => setInput(e.target.value)} onKeyDown={handleKey}
              placeholder={listening ? "Listening… or type here" : "Ask about stocks, options, patterns, strategies… mention any ticker"}
              rows={1}
              className="flex-1 bg-transparent text-sm text-gray-200 placeholder-gray-600 resize-none focus:outline-none max-h-32"
              style={{ lineHeight: "1.5" }} />
            {voiceAvailable && (
              <button onClick={toggleListen}
                className={cn("w-8 h-8 rounded-lg flex items-center justify-center transition-colors flex-shrink-0",
                  listening ? "bg-red-600 hover:bg-red-500" : "bg-[#1f2937] hover:bg-[#374151] text-gray-400 hover:text-white")}
                title={listening ? "Stop" : "Push to talk"}>
                {listening ? <MicOff size={14} className="text-white" /> : <Mic size={14} />}
              </button>
            )}
            <button onClick={() => send(input)} disabled={!input.trim() || loading}
              className="w-8 h-8 rounded-lg bg-blue-600 hover:bg-blue-500 disabled:opacity-40 flex items-center justify-center transition-colors flex-shrink-0">
              <Send size={14} className="text-white" />
            </button>
          </div>
          <p className="text-[10px] text-gray-700 mt-1.5 text-center">Enter to send · Shift+Enter for new line · Mic for voice</p>
        </div>
      </div>

      {/* Symbol analysis panel */}
      {activeSymbol && <SymbolPanel symbol={activeSymbol} onClose={() => setActiveSymbol(null)} />}
    </div>
  );
}
