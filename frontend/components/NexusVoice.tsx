"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import {
  Bot, Mic, MicOff, Volume2, VolumeX, X, Minimize2, Maximize2,
  GripHorizontal, MessageCircle, Send, Loader2, User, BarChart2,
} from "lucide-react";
import { api, type ChatResponse, type SimulationResult } from "@/lib/api";
import { cn, getSessionId } from "@/lib/utils";

// ── Speech types ──────────────────────────────────────────────────────────────
interface SREvent extends Event {
  results: SpeechRecognitionResultList;
  resultIndex: number;
}
interface SRErrorEvent extends Event { error?: string }
interface SR extends EventTarget {
  continuous: boolean; interimResults: boolean; lang: string;
  onstart: (() => void) | null; onend: (() => void) | null;
  onerror: ((e: SRErrorEvent) => void) | null;
  onresult: ((e: SREvent) => void) | null;
  start(): void; stop(): void;
}
declare global {
  interface Window {
    SpeechRecognition?: new () => SR;
    webkitSpeechRecognition?: new () => SR;
  }
}

// ── TTS ───────────────────────────────────────────────────────────────────────
function ttsSpeak(text: string, muted: boolean) {
  if (muted || typeof window === "undefined" || !window.speechSynthesis) return;
  window.speechSynthesis.cancel();
  const clean = text
    .replace(/```[\s\S]*?```/g, "")
    .replace(/#{1,6} /g, "")
    .replace(/[*_`>[\]()]/g, "")
    .replace(/⚠️[^\n]*/g, "")
    .replace(/\s+/g, " ")
    .trim()
    .slice(0, 500);
  if (!clean) return;
  const u = new SpeechSynthesisUtterance(clean);
  u.rate = 1.0; u.pitch = 0.95; u.volume = 1.0;
  window.speechSynthesis.speak(u);
}

// ── Inline simulation card ────────────────────────────────────────────────────
function SimCard({ sim }: { sim: SimulationResult }) {
  const wr = sim.win_rate;
  const dr = sim.date_range || {};
  return (
    <div className="mt-2 bg-[#0a0e1a] border border-[#1f2937] rounded-xl p-3 space-y-2">
      <div className="flex items-center gap-2">
        <BarChart2 size={11} className="text-blue-400" />
        <span className="text-xs font-semibold text-gray-200">{sim.symbol}</span>
        <span className="text-[10px] text-gray-600 ml-auto">{dr.start?.slice(0,4)}–{dr.end?.slice(0,4)}</span>
      </div>
      <div className="grid grid-cols-3 gap-2 text-center">
        {[
          { l: "Win Rate", v: wr != null ? `${wr}%` : "—",   c: (wr ?? 0) >= 55 ? "text-green-400" : "text-red-400" },
          { l: "Trades",   v: String(sim.total_predictions),  c: "text-white" },
          { l: "Avg P&L",  v: sim.avg_pnl_pct != null ? `${sim.avg_pnl_pct > 0 ? "+" : ""}${sim.avg_pnl_pct}%` : "—",
            c: (sim.avg_pnl_pct ?? 0) >= 0 ? "text-green-400" : "text-red-400" },
        ].map(({ l, v, c }) => (
          <div key={l} className="bg-[#111827] rounded-lg p-2">
            <div className={cn("text-sm font-bold font-mono", c)}>{v}</div>
            <div className="text-[10px] text-gray-600">{l}</div>
          </div>
        ))}
      </div>
      {sim.events && sim.events.length > 0 && (
        <p className="text-[10px] text-gray-600">
          {sim.events.length} world events · {sim.events.slice(0,2).map(e => e.title).join(", ")}
          {sim.events.length > 2 ? ` +${sim.events.length - 2} more` : ""}
        </p>
      )}
      <a href="/analysis" className="block text-center text-[10px] text-blue-400 hover:text-blue-300 transition-colors">
        Open full analysis →
      </a>
    </div>
  );
}

// ── Message type ──────────────────────────────────────────────────────────────
interface Msg {
  role: "user" | "assistant";
  content: string;
  ts: number;
  simulation?: SimulationResult;
  symbols?: string[];
  isError?: boolean;
}

// ── Main component ────────────────────────────────────────────────────────────
export function NexusVoice() {
  const [sessionId] = useState(() => getSessionId());
  const [open, setOpen]             = useState(false);
  const [minimized, setMinimized]   = useState(false);
  const [muted, setMuted]           = useState(false);
  const [voiceMode, setVoiceMode]   = useState(false);
  const [listening, setListening]   = useState(false);
  const [continuous, setContinuous] = useState(false);
  const [input, setInput]           = useState("");
  const [interim, setInterim]       = useState("");
  const [loading, setLoading]       = useState(false);
  const [unread, setUnread]         = useState(0);
  const [activeSymbol, setActiveSymbol] = useState<string | null>(null);
  const [messages, setMessages] = useState<Msg[]>([{
    role: "assistant",
    content: "I'm Nexus. Ask me about any stock, say 'simulate Apple from 2000 to 2010', or ask me to predict a move.",
    ts: Date.now(),
  }]);

  // Drag: offset from default anchor in pixels
  const [drag, setDrag]   = useState({ x: 0, y: 0 });
  const dragging          = useRef(false);
  const dragOrigin        = useRef({ mx: 0, my: 0, ox: 0, oy: 0 });
  const continuousRef     = useRef(false);
  const bottomRef         = useRef<HTMLDivElement>(null);
  const recRef            = useRef<SR | null>(null);

  const voiceAvailable = typeof window !== "undefined" &&
    !!(window.SpeechRecognition || window.webkitSpeechRecognition);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }, [messages, loading]);

  useEffect(() => { if (open) setUnread(0); }, [open]);

  // ── Send ──────────────────────────────────────────────────────────────────
  const send = useCallback(async (text: string) => {
    const msg = text.trim();
    if (!msg || loading) return;
    setInput(""); setInterim("");
    setMessages(prev => [...prev, { role: "user", content: msg, ts: Date.now() }]);
    setLoading(true);
    try {
      const res: ChatResponse = await api.chat(msg, sessionId, voiceMode);
      const reply: Msg = {
        role: "assistant",
        content: res.response,
        ts: Date.now(),
        symbols: res.symbols,
        simulation: res.simulation ?? undefined,
      };
      setMessages(prev => [...prev, reply]);
      if (!open) setUnread(n => n + 1);
      if (res.active_symbol) setActiveSymbol(res.active_symbol);
      else if (res.symbols?.[0]) setActiveSymbol(res.symbols[0]);
      ttsSpeak(res.response, muted);
    } catch (e: any) {
      setMessages(prev => [...prev, {
        role: "assistant",
        content: `Error: ${e.message || "backend unreachable"}`,
        ts: Date.now(),
        isError: true,
      }]);
    } finally {
      setLoading(false);
    }
  }, [loading, sessionId, voiceMode, muted, open]);

  // ── Speech recognition ────────────────────────────────────────────────────
  useEffect(() => {
    if (!voiceAvailable) return;
    const Ctor = (window.SpeechRecognition || window.webkitSpeechRecognition)!;
    const rec = new Ctor();
    rec.continuous = true;
    rec.interimResults = true;
    rec.lang = "en-US";
    rec.onstart = () => setListening(true);
    rec.onend = () => {
      setListening(false);
      if (continuousRef.current) {
        setTimeout(() => { try { rec.start(); } catch {} }, 250);
      }
    };
    rec.onerror = (e: SRErrorEvent) => {
      setListening(false);
      if (e.error === "not-allowed") {
        setMessages(prev => [...prev, {
          role: "assistant",
          content: "Microphone permission denied. Please allow mic access in your browser settings, then reload.",
          ts: Date.now(), isError: true,
        }]);
        continuousRef.current = false;
        setContinuous(false);
      }
    };
    rec.onresult = (e: SREvent) => {
      let final = ""; let inter = "";
      for (let i = e.resultIndex; i < e.results.length; i++) {
        if (e.results[i].isFinal) final += e.results[i][0].transcript;
        else inter += e.results[i][0].transcript;
      }
      if (inter) setInterim(inter.trim());
      if (final.trim()) { setInterim(""); send(final.trim()); }
    };
    recRef.current = rec;
    return () => { rec.onend = null; try { rec.stop(); } catch {} };
  }, [send, voiceAvailable]);

  const startListening = () => {
    window.speechSynthesis?.cancel();
    try { recRef.current?.start(); } catch {}
  };
  const stopListening = () => {
    continuousRef.current = false;
    setContinuous(false);
    try { recRef.current?.stop(); } catch {}
  };
  const toggleContinuous = () => {
    if (continuous) {
      continuousRef.current = false;
      setContinuous(false);
      try { recRef.current?.stop(); } catch {}
    } else {
      window.speechSynthesis?.cancel();
      continuousRef.current = true;
      setContinuous(true);
      try { recRef.current?.start(); } catch {}
    }
  };

  // ── Drag ──────────────────────────────────────────────────────────────────
  const onHeaderMouseDown = (e: React.MouseEvent) => {
    if ((e.target as HTMLElement).closest("button")) return;
    dragging.current = true;
    dragOrigin.current = { mx: e.clientX, my: e.clientY, ox: drag.x, oy: drag.y };
    e.preventDefault();
  };

  useEffect(() => {
    const onMove = (e: MouseEvent) => {
      if (!dragging.current) return;
      setDrag({
        x: dragOrigin.current.ox + (e.clientX - dragOrigin.current.mx),
        y: dragOrigin.current.oy + (e.clientY - dragOrigin.current.my),
      });
    };
    const onUp = () => { dragging.current = false; };
    window.addEventListener("mousemove", onMove);
    window.addEventListener("mouseup", onUp);
    return () => {
      window.removeEventListener("mousemove", onMove);
      window.removeEventListener("mouseup", onUp);
    };
  }, []);

  const handleKey = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(input); }
  };

  // Panel position: anchored bottom-right, offset by drag
  const panelStyle: React.CSSProperties = {
    position: "fixed",
    bottom: 24 - drag.y,
    right:  24 - drag.x,
    zIndex: 50,
    width: "min(440px, calc(100vw - 1rem))",
  };

  // ── Floating button ───────────────────────────────────────────────────────
  if (!open) {
    return (
      <button
        onClick={() => setOpen(true)}
        style={{ position: "fixed", bottom: 24 - drag.y, right: 24 - drag.x, zIndex: 50 }}
        className={cn(
          "w-14 h-14 rounded-full shadow-2xl flex items-center justify-center transition-all hover:scale-105 active:scale-95 group",
          listening || continuous ? "bg-red-600 ring-4 ring-red-500/30" : "bg-blue-600 hover:bg-blue-500"
        )}
      >
        {listening || continuous
          ? <Mic size={22} className="text-white animate-pulse" />
          : <MessageCircle size={22} className="text-white" />}
        {unread > 0 && (
          <span className="absolute -top-1 -right-1 w-5 h-5 bg-red-500 rounded-full text-[10px] text-white flex items-center justify-center font-bold">
            {unread}
          </span>
        )}
        <span className="absolute right-full mr-3 px-2.5 py-1 bg-[#1f2937] border border-[#374151] rounded-lg text-xs text-white whitespace-nowrap opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none shadow-lg">
          Ask Nexus
        </span>
      </button>
    );
  }

  // ── Open panel ────────────────────────────────────────────────────────────
  return (
    <div style={panelStyle} className="rounded-2xl border border-[#1f2937] bg-[#0d1117] shadow-2xl">

      {/* Header */}
      <div
        onMouseDown={onHeaderMouseDown}
        className="flex items-center gap-2 px-3 py-2.5 border-b border-[#1f2937] bg-[#111827] rounded-t-2xl cursor-grab active:cursor-grabbing select-none"
      >
        <GripHorizontal size={13} className="text-gray-600 flex-shrink-0 pointer-events-none" />
        <div className={cn("w-7 h-7 rounded-lg flex items-center justify-center flex-shrink-0",
          listening || continuous ? "bg-red-600" : "bg-blue-600")}>
          <Bot size={13} className="text-white" />
        </div>
        <div className="flex-1 min-w-0 pointer-events-none">
          <div className="text-xs font-semibold text-white">Nexus AI</div>
          <div className="flex items-center gap-1.5 text-[10px] text-gray-500">
            <span className={cn("w-1.5 h-1.5 rounded-full",
              listening || continuous ? "bg-red-400 animate-pulse" : "bg-gray-600")} />
            {continuous ? "Always listening" : listening ? "Listening…" : activeSymbol ? `Tracking ${activeSymbol}` : "Ready"}
          </div>
        </div>

        <button onClick={() => setVoiceMode(v => !v)}
          className={cn("text-[10px] px-2 py-1 rounded-md border transition-colors font-medium",
            voiceMode ? "bg-blue-600/20 border-blue-600/40 text-blue-400" : "border-[#374151] text-gray-600 hover:text-gray-300")}
          title="Voice mode: shorter spoken responses">
          Voice
        </button>

        <button onClick={() => { setMuted(m => !m); if (!muted) window.speechSynthesis?.cancel(); }}
          className={cn("p-1 rounded transition-colors", muted ? "text-gray-600" : "text-gray-400 hover:text-white")}
          title={muted ? "Unmute" : "Mute"}>
          {muted ? <VolumeX size={13} /> : <Volume2 size={13} />}
        </button>

        {voiceAvailable && (
          <button onClick={toggleContinuous}
            className={cn("p-1 rounded transition-colors",
              continuous ? "text-red-400" : "text-gray-500 hover:text-gray-300")}
            title={continuous ? "Stop always-on" : "Always-on listening"}>
            {continuous ? <Mic size={13} /> : <MicOff size={13} />}
          </button>
        )}

        {loading && <Loader2 size={13} className="animate-spin text-blue-400 flex-shrink-0" />}

        <button onClick={() => setMinimized(m => !m)}
          className="p-1 text-gray-500 hover:text-gray-300 transition-colors">
          {minimized ? <Maximize2 size={13} /> : <Minimize2 size={13} />}
        </button>
        <button onClick={() => { setOpen(false); window.speechSynthesis?.cancel(); stopListening(); }}
          className="p-1 text-gray-500 hover:text-red-400 transition-colors">
          <X size={13} />
        </button>
      </div>

      {!minimized && (
        <>
          {/* Messages */}
          <div className="max-h-80 overflow-y-auto px-3 py-3 space-y-3">
            {messages.slice(-16).map((msg, i) => (
              <div key={i} className={cn("flex gap-2 text-xs", msg.role === "user" ? "justify-end" : "justify-start")}>
                {msg.role === "assistant" && (
                  <div className="w-6 h-6 rounded-full bg-blue-600/20 border border-blue-600/30 flex items-center justify-center flex-shrink-0 mt-0.5">
                    <Bot size={11} className="text-blue-400" />
                  </div>
                )}
                <div className="max-w-[88%]">
                  <div className={cn("rounded-xl px-3 py-2 leading-relaxed",
                    msg.role === "user"
                      ? "bg-blue-600 text-white rounded-br-sm"
                      : msg.isError
                        ? "bg-red-900/20 border border-red-800/30 text-red-300 rounded-bl-sm"
                        : "bg-[#111827] border border-[#1f2937] text-gray-300 rounded-bl-sm")}>
                    {msg.content}
                  </div>
                  {msg.symbols && msg.symbols.length > 0 && (
                    <div className="flex gap-1 mt-1 flex-wrap">
                      {msg.symbols.map(s => (
                        <button key={s} onClick={() => setActiveSymbol(s)}
                          className="text-[10px] bg-[#1f2937] text-blue-400 px-1.5 py-0.5 rounded font-mono hover:bg-blue-900/30 transition-colors">
                          {s}
                        </button>
                      ))}
                    </div>
                  )}
                  {msg.simulation && <SimCard sim={msg.simulation} />}
                </div>
                {msg.role === "user" && (
                  <div className="w-6 h-6 rounded-full bg-[#1f2937] flex items-center justify-center flex-shrink-0 mt-0.5">
                    <User size={11} className="text-gray-400" />
                  </div>
                )}
              </div>
            ))}

            {loading && (
              <div className="flex gap-2 justify-start">
                <div className="w-6 h-6 rounded-full bg-blue-600/20 border border-blue-600/30 flex items-center justify-center flex-shrink-0">
                  <Bot size={11} className="text-blue-400" />
                </div>
                <div className="bg-[#111827] border border-[#1f2937] rounded-xl rounded-bl-sm px-3 py-2">
                  <div className="flex gap-1 items-center h-4">
                    {[0,150,300].map(d => (
                      <span key={d} className="w-1.5 h-1.5 bg-blue-400 rounded-full animate-bounce"
                        style={{ animationDelay: `${d}ms` }} />
                    ))}
                  </div>
                </div>
              </div>
            )}

            {interim && (
              <div className="flex justify-end">
                <div className="bg-blue-600/20 border border-blue-600/20 rounded-xl px-3 py-1.5 text-xs text-blue-300 italic max-w-[85%]">
                  {interim}…
                </div>
              </div>
            )}
            <div ref={bottomRef} />
          </div>

          {/* Input */}
          <div className="border-t border-[#1f2937] px-3 py-2.5 space-y-2">
            <div className="flex gap-2">
              <textarea
                value={input}
                onChange={e => setInput(e.target.value)}
                onKeyDown={handleKey}
                placeholder={continuous ? "Listening… or type here" : "Ask about any stock, scenario, or prediction…"}
                rows={2}
                className="flex-1 resize-none rounded-xl border border-[#253044] bg-[#111827] px-3 py-2 text-sm text-gray-100 outline-none placeholder:text-gray-600 focus:border-blue-500 transition-colors"
              />
              <div className="flex flex-col gap-1.5">
                <button onClick={() => send(input)} disabled={!input.trim() || loading}
                  className="w-9 h-9 bg-blue-600 hover:bg-blue-500 disabled:opacity-40 text-white rounded-xl flex items-center justify-center transition-colors">
                  <Send size={14} />
                </button>
                {voiceAvailable && (
                  <button
                    onMouseDown={startListening}
                    onMouseUp={stopListening}
                    onTouchStart={startListening}
                    onTouchEnd={stopListening}
                    className={cn("w-9 h-9 rounded-xl flex items-center justify-center transition-colors",
                      listening ? "bg-red-600 text-white" : "bg-[#1f2937] hover:bg-[#374151] text-gray-400 hover:text-white")}
                    title="Hold to talk">
                    {listening ? <MicOff size={14} /> : <Mic size={14} />}
                  </button>
                )}
              </div>
            </div>
            <div className="flex items-center justify-between text-[10px] text-gray-700">
              <span>Enter to send · Hold mic to talk</span>
              {activeSymbol && <span className="text-blue-500 font-mono">tracking {activeSymbol}</span>}
            </div>
          </div>
        </>
      )}
    </div>
  );
}
