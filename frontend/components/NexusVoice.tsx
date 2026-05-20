"use client";

/**
 * NexusVoice — unified voice + chat dock.
 *
 * Features:
 * - Floating button (bottom-right), draggable panel when open
 * - Push-to-talk OR continuous listening toggle
 * - TTS queue: Nexus speaks every response, can be muted
 * - Waveform visualizer while listening
 * - Inline simulation/prediction results when Nexus triggers them autonomously
 * - Voice mode flag sent to backend so responses are spoken-word friendly
 */

import {
  useCallback, useEffect, useRef, useState, useMemo,
} from "react";
import {
  Bot, Mic, MicOff, Volume2, VolumeX, X, Minimize2, Maximize2,
  GripHorizontal, MessageCircle, Send, Loader2, User,
  TrendingUp, TrendingDown, Minus, BarChart2, Zap, RefreshCw,
} from "lucide-react";
import { api, type ChatResponse } from "@/lib/api";
import { cn, getSessionId, fmtPrice, confidenceColor } from "@/lib/utils";

// ── Speech API types ──────────────────────────────────────────────────────────

interface SpeechRecognitionEvent extends Event {
  results: SpeechRecognitionResultList;
  resultIndex: number;
}
interface SpeechRecognitionErrorEvent extends Event { error?: string }
interface BrowserSpeechRecognition extends EventTarget {
  continuous: boolean; interimResults: boolean; lang: string;
  onstart: (() => void) | null; onend: (() => void) | null;
  onerror: ((e: SpeechRecognitionErrorEvent) => void) | null;
  onresult: ((e: SpeechRecognitionEvent) => void) | null;
  start(): void; stop(): void;
}
declare global {
  interface Window {
    SpeechRecognition?: new () => BrowserSpeechRecognition;
    webkitSpeechRecognition?: new () => BrowserSpeechRecognition;
  }
}

// ── TTS queue ─────────────────────────────────────────────────────────────────

function stripForSpeech(text: string): string {
  return text
    .replace(/```[\s\S]*?```/g, "")
    .replace(/#{1,6}\s/g, "")
    .replace(/[*_`>[\]()]/g, "")
    .replace(/⚠️.*$/gm, "")
    .replace(/\s+/g, " ")
    .trim()
    .slice(0, 600); // cap at ~45 seconds of speech
}

class TTSQueue {
  private queue: string[] = [];
  private speaking = false;
  muted = false;

  enqueue(text: string) {
    if (this.muted) return;
    this.queue.push(stripForSpeech(text));
    if (!this.speaking) this._next();
  }

  private _next() {
    if (!this.queue.length) { this.speaking = false; return; }
    this.speaking = true;
    const text = this.queue.shift()!;
    const utt = new SpeechSynthesisUtterance(text);
    utt.rate = 1.0; utt.pitch = 0.95; utt.volume = 1.0;
    utt.onend = () => this._next();
    utt.onerror = () => this._next();
    window.speechSynthesis.speak(utt);
  }

  cancel() {
    this.queue = [];
    this.speaking = false;
    window.speechSynthesis.cancel();
  }
}

const ttsQueue = new TTSQueue();

// ── Waveform visualizer ───────────────────────────────────────────────────────

function Waveform({ active }: { active: boolean }) {
  const bars = 12;
  return (
    <div className="flex items-center gap-0.5 h-5">
      {Array.from({ length: bars }).map((_, i) => (
        <div
          key={i}
          className={cn(
            "w-0.5 rounded-full transition-all",
            active ? "bg-blue-400" : "bg-gray-600"
          )}
          style={{
            height: active
              ? `${20 + Math.sin(Date.now() / 200 + i) * 10}%`
              : "20%",
            animation: active ? `wave ${0.5 + (i % 4) * 0.1}s ease-in-out infinite alternate` : "none",
            animationDelay: `${i * 40}ms`,
          }}
        />
      ))}
    </div>
  );
}

// ── Inline simulation mini-result ─────────────────────────────────────────────

function SimulationMini({ sim }: { sim: any }) {
  if (!sim) return null;
  const wr = sim.win_rate;
  const dr = sim.date_range || {};
  return (
    <div className="mt-2 bg-[#0d1117] border border-[#1f2937] rounded-xl p-3 text-xs space-y-1.5">
      <div className="flex items-center gap-2">
        <BarChart2 size={11} className="text-blue-400" />
        <span className="font-semibold text-gray-300">{sim.symbol} simulation</span>
        <span className="text-gray-600">{dr.start?.slice(0,4)}–{dr.end?.slice(0,4)}</span>
      </div>
      <div className="grid grid-cols-3 gap-2 text-center">
        <div>
          <div className={cn("text-base font-bold font-mono", (wr ?? 0) >= 55 ? "text-green-400" : "text-red-400")}>
            {wr != null ? `${wr}%` : "—"}
          </div>
          <div className="text-[10px] text-gray-600">Win rate</div>
        </div>
        <div>
          <div className="text-base font-bold font-mono text-white">{sim.total_predictions}</div>
          <div className="text-[10px] text-gray-600">Predictions</div>
        </div>
        <div>
          <div className={cn("text-base font-bold font-mono", (sim.avg_pnl_pct ?? 0) >= 0 ? "text-green-400" : "text-red-400")}>
            {sim.avg_pnl_pct != null ? `${sim.avg_pnl_pct > 0 ? "+" : ""}${sim.avg_pnl_pct}%` : "—"}
          </div>
          <div className="text-[10px] text-gray-600">Avg P&L</div>
        </div>
      </div>
      <a href="/simulate" className="block text-center text-[10px] text-blue-400 hover:text-blue-300 transition-colors">
        View full simulation →
      </a>
    </div>
  );
}

// ── Prediction mini-result ────────────────────────────────────────────────────

function PredictionMini({ pred }: { pred: any }) {
  if (!pred?.prediction) return null;
  const p = pred.prediction;
  const dir = p.direction;
  return (
    <div className={cn(
      "mt-2 border rounded-xl p-3 text-xs space-y-1",
      dir === "call" ? "bg-green-900/10 border-green-800/30" :
      dir === "put"  ? "bg-red-900/10 border-red-800/30" :
      "bg-[#0d1117] border-[#1f2937]"
    )}>
      <div className="flex items-center gap-2">
        <Zap size={11} className="text-cyan-400" />
        <span className="font-semibold text-gray-300">Nexus Prediction</span>
        <span className={cn("ml-auto font-bold uppercase text-sm",
          dir === "call" ? "text-green-400" : dir === "put" ? "text-red-400" : "text-gray-400")}>
          {dir}
        </span>
        <span className={cn("font-mono text-xs", confidenceColor(p.confidence))}>
          {Math.round(p.confidence * 100)}%
        </span>
      </div>
      <div className="flex gap-3 text-[10px]">
        <span className="text-green-400">Target {fmtPrice(p.target_price)}</span>
        <span className="text-red-400">Stop {fmtPrice(p.stop_loss)}</span>
      </div>
    </div>
  );
}

// ── Message bubble ────────────────────────────────────────────────────────────

interface Msg {
  role: "user" | "assistant";
  content: string;
  ts: number;
  simulation?: any;
  prediction?: any;
  intent?: string;
  symbols?: string[];
}

function MsgBubble({ msg, onSymbolClick }: { msg: Msg; onSymbolClick: (s: string) => void }) {
  const isUser = msg.role === "user";
  return (
    <div className={cn("flex gap-2 text-xs", isUser ? "justify-end" : "justify-start")}>
      {!isUser && (
        <div className="w-6 h-6 rounded-full bg-blue-600/20 border border-blue-600/30 flex items-center justify-center flex-shrink-0 mt-0.5">
          <Bot size={11} className="text-blue-400" />
        </div>
      )}
      <div className="max-w-[88%]">
        <div className={cn(
          "rounded-xl px-3 py-2 leading-relaxed",
          isUser
            ? "bg-blue-600 text-white rounded-br-sm"
            : "bg-[#111827] border border-[#1f2937] text-gray-300 rounded-bl-sm"
        )}>
          {msg.content}
        </div>
        {msg.symbols && msg.symbols.length > 0 && (
          <div className="flex gap-1 mt-1 flex-wrap">
            {msg.symbols.map((s) => (
              <button key={s} onClick={() => onSymbolClick(s)}
                className="text-[10px] bg-[#1f2937] text-blue-400 px-1.5 py-0.5 rounded font-mono hover:bg-blue-900/30 transition-colors">
                {s}
              </button>
            ))}
          </div>
        )}
        {msg.simulation && <SimulationMini sim={msg.simulation} />}
        {msg.prediction && <PredictionMini pred={msg.prediction} />}
      </div>
      {isUser && (
        <div className="w-6 h-6 rounded-full bg-[#1f2937] flex items-center justify-center flex-shrink-0 mt-0.5">
          <User size={11} className="text-gray-400" />
        </div>
      )}
    </div>
  );
}

// ── Main component ────────────────────────────────────────────────────────────

const DEFAULT_POS = { x: 24, y: 24 };

export function NexusVoice() {
  const [sessionId] = useState(() => getSessionId());
  const [open, setOpen] = useState(false);
  const [minimized, setMinimized] = useState(false);
  const [messages, setMessages] = useState<Msg[]>([{
    role: "assistant",
    content: "I'm Nexus. Ask me about any stock, say 'simulate Apple from 1995 to 2000', or ask me to predict a move.",
    ts: Date.now(),
  }]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [listening, setListening] = useState(false);
  const [continuous, setContinuous] = useState(false);
  const [muted, setMuted] = useState(false);
  const [voiceMode, setVoiceMode] = useState(false);
  const [unread, setUnread] = useState(0);
  const [interimText, setInterimText] = useState("");
  const [activeSymbol, setActiveSymbol] = useState<string | null>(null);

  // Drag
  const [pos, setPos] = useState(DEFAULT_POS);
  const dragging = useRef(false);
  const dragStart = useRef({ mx: 0, my: 0, px: 0, py: 0 });
  const panelRef = useRef<HTMLDivElement>(null);
  const bottomRef = useRef<HTMLDivElement>(null);
  const recognitionRef = useRef<BrowserSpeechRecognition | null>(null);
  const voiceAvailable = typeof window !== "undefined" &&
    !!(window.SpeechRecognition || window.webkitSpeechRecognition);

  useEffect(() => { if (open) setUnread(0); }, [open]);
  useEffect(() => {
    ttsQueue.muted = muted;
    if (muted) ttsQueue.cancel();
  }, [muted]);
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }, [messages, loading]);

  // ── Send message ──────────────────────────────────────────────────────────

  const send = useCallback(async (text: string) => {
    const msg = text.trim();
    if (!msg || loading) return;
    setInput(""); setInterimText("");
    setMessages((prev) => [...prev, { role: "user", content: msg, ts: Date.now() }]);
    setLoading(true);
    try {
      const res: ChatResponse = await api.chat(msg, sessionId, voiceMode);
      const reply: Msg = {
        role: "assistant",
        content: res.response,
        ts: Date.now(),
        intent: res.intent,
        symbols: res.symbols,
        simulation: res.simulation,
        prediction: (res.market_context as any)?.adaptive_prediction,
      };
      setMessages((prev) => [...prev, reply]);
      if (!open) setUnread((n) => n + 1);
      if (res.active_symbol) setActiveSymbol(res.active_symbol);
      else if (res.symbols?.[0]) setActiveSymbol(res.symbols[0]);
      ttsQueue.enqueue(res.response);
    } catch (e: any) {
      const errMsg = `Backend error: ${e.message}`;
      setMessages((prev) => [...prev, { role: "assistant", content: errMsg, ts: Date.now() }]);
    } finally {
      setLoading(false);
    }
  }, [loading, sessionId, voiceMode, open]);

  // ── Speech recognition ────────────────────────────────────────────────────

  useEffect(() => {
    if (!voiceAvailable) return;
    const Ctor = window.SpeechRecognition || window.webkitSpeechRecognition!;
    const rec = new Ctor();
    rec.continuous = true;
    rec.interimResults = true;
    rec.lang = "en-US";
    rec.onstart = () => setListening(true);
    rec.onend = () => {
      setListening(false);
      if (continuous) { try { rec.start(); } catch {} }
    };
    rec.onerror = () => { setListening(false); setContinuous(false); };
    rec.onresult = (e: SpeechRecognitionEvent) => {
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
  }, [send, continuous, voiceAvailable]);

  const toggleListen = () => {
    const rec = recognitionRef.current;
    if (!rec) return;
    if (listening) {
      setContinuous(false);
      try { rec.stop(); } catch {}
    } else {
      ttsQueue.cancel();
      try { rec.start(); } catch {}
    }
  };

  const toggleContinuous = () => {
    const rec = recognitionRef.current;
    if (!rec) return;
    if (continuous) {
      setContinuous(false);
      try { rec.stop(); } catch {}
    } else {
      setContinuous(true);
      ttsQueue.cancel();
      try { rec.start(); } catch {}
    }
  };

  // ── Drag ──────────────────────────────────────────────────────────────────

  const onMouseDown = (e: React.MouseEvent) => {
    if ((e.target as HTMLElement).closest("button,textarea,input,a")) return;
    dragging.current = true;
    dragStart.current = { mx: e.clientX, my: e.clientY, px: pos.x, py: pos.y };
    e.preventDefault();
  };

  useEffect(() => {
    const onMove = (e: MouseEvent) => {
      if (!dragging.current) return;
      const panel = panelRef.current;
      if (!panel) return;
      const dx = e.clientX - dragStart.current.mx;
      const dy = e.clientY - dragStart.current.my;
      const maxX = window.innerWidth - panel.offsetWidth - 8;
      const maxY = window.innerHeight - panel.offsetHeight - 8;
      setPos({
        x: Math.max(8, Math.min(maxX, dragStart.current.px - dx)),
        y: Math.max(8, Math.min(maxY, dragStart.current.py - dy)),
      });
    };
    const onUp = () => { dragging.current = false; };
    window.addEventListener("mousemove", onMove);
    window.addEventListener("mouseup", onUp);
    return () => { window.removeEventListener("mousemove", onMove); window.removeEventListener("mouseup", onUp); };
  }, []);

  const handleKey = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(input); }
  };

  // ── Floating button ───────────────────────────────────────────────────────

  if (!open) {
    return (
      <button
        onClick={() => setOpen(true)}
        style={{ bottom: pos.y, right: pos.x }}
        className={cn(
          "fixed z-50 w-14 h-14 rounded-full shadow-2xl flex items-center justify-center transition-all hover:scale-105 active:scale-95 group",
          listening || continuous
            ? "bg-red-600 hover:bg-red-500 ring-4 ring-red-500/30"
            : "bg-blue-600 hover:bg-blue-500"
        )}
        title="Open Nexus AI"
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
          {listening ? "Listening…" : "Ask Nexus"}
        </span>
      </button>
    );
  }

  // ── Open panel ────────────────────────────────────────────────────────────

  return (
    <div
      ref={panelRef}
      style={{ bottom: pos.y, right: pos.x }}
      className="fixed z-50 w-[min(440px,calc(100vw-1rem))] rounded-2xl border border-[#1f2937] bg-[#0d1117]/97 shadow-2xl backdrop-blur-sm select-none"
    >
      {/* Header */}
      <div
        onMouseDown={onMouseDown}
        className="flex items-center gap-2 border-b border-[#1f2937] px-3 py-2.5 cursor-grab active:cursor-grabbing rounded-t-2xl bg-[#111827]"
      >
        <GripHorizontal size={13} className="text-gray-600 flex-shrink-0" />
        <div className={cn(
          "w-7 h-7 rounded-lg flex items-center justify-center flex-shrink-0",
          listening || continuous ? "bg-red-600" : "bg-blue-600"
        )}>
          <Bot size={13} className="text-white" />
        </div>
        <div className="flex-1 min-w-0">
          <div className="text-xs font-semibold text-white">Nexus AI</div>
          <div className="flex items-center gap-1.5 text-[10px] text-gray-500">
            <span className={cn("w-1.5 h-1.5 rounded-full flex-shrink-0",
              listening || continuous ? "bg-red-400 animate-pulse" : "bg-gray-600")} />
            {continuous ? "Always listening" : listening ? "Listening…" : activeSymbol ? `Tracking ${activeSymbol}` : "Ready"}
          </div>
        </div>

        {/* Waveform */}
        {(listening || continuous) && <Waveform active={listening} />}

        {/* Voice mode toggle */}
        <button onClick={() => setVoiceMode((v) => !v)}
          className={cn("text-[10px] px-2 py-1 rounded-md border transition-colors font-medium",
            voiceMode ? "bg-blue-600/20 border-blue-600/40 text-blue-400" : "border-[#374151] text-gray-600 hover:text-gray-300")}
          title="Voice mode: shorter spoken responses">
          Voice
        </button>

        {/* Mute TTS */}
        <button onClick={() => setMuted((m) => !m)}
          className={cn("p-1 rounded transition-colors", muted ? "text-gray-600" : "text-gray-400 hover:text-white")}
          title={muted ? "Unmute Nexus" : "Mute Nexus"}>
          {muted ? <VolumeX size={13} /> : <Volume2 size={13} />}
        </button>

        {/* Continuous listen */}
        {voiceAvailable && (
          <button onClick={toggleContinuous}
            className={cn("p-1 rounded transition-colors",
              continuous ? "text-red-400 hover:text-red-300" : "text-gray-500 hover:text-gray-300")}
            title={continuous ? "Stop always-on listening" : "Enable always-on listening"}>
            {continuous ? <Mic size={13} /> : <MicOff size={13} />}
          </button>
        )}

        {loading && <Loader2 size={13} className="animate-spin text-blue-400 flex-shrink-0" />}
        <button onClick={() => setMinimized((m) => !m)} className="text-gray-500 hover:text-gray-300 p-1 transition-colors">
          {minimized ? <Maximize2 size={13} /> : <Minimize2 size={13} />}
        </button>
        <button onClick={() => { setOpen(false); ttsQueue.cancel(); }} className="text-gray-500 hover:text-red-400 p-1 transition-colors">
          <X size={13} />
        </button>
      </div>

      {!minimized && (
        <>
          {/* Messages */}
          <div className="max-h-80 overflow-y-auto px-3 py-3 space-y-3">
            {messages.slice(-14).map((msg, i) => (
              <MsgBubble key={i} msg={msg} onSymbolClick={(s) => setActiveSymbol(s)} />
            ))}
            {loading && (
              <div className="flex gap-2 justify-start">
                <div className="w-6 h-6 rounded-full bg-blue-600/20 border border-blue-600/30 flex items-center justify-center flex-shrink-0">
                  <Bot size={11} className="text-blue-400" />
                </div>
                <div className="bg-[#111827] border border-[#1f2937] rounded-xl rounded-bl-sm px-3 py-2">
                  <div className="flex gap-1 items-center h-4">
                    {[0, 150, 300].map((d) => (
                      <span key={d} className="w-1.5 h-1.5 bg-blue-400 rounded-full animate-bounce" style={{ animationDelay: `${d}ms` }} />
                    ))}
                  </div>
                </div>
              </div>
            )}
            {interimText && (
              <div className="flex justify-end">
                <div className="bg-blue-600/30 border border-blue-600/20 rounded-xl px-3 py-1.5 text-xs text-blue-300 italic max-w-[85%]">
                  {interimText}…
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
                onChange={(e) => setInput(e.target.value)}
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
                  <button onClick={toggleListen}
                    className={cn("w-9 h-9 rounded-xl flex items-center justify-center transition-colors",
                      listening ? "bg-red-600 hover:bg-red-500 text-white" : "bg-[#1f2937] hover:bg-[#374151] text-gray-400 hover:text-white")}>
                    {listening ? <MicOff size={14} /> : <Mic size={14} />}
                  </button>
                )}
              </div>
            </div>
            <div className="flex items-center justify-between text-[10px] text-gray-700">
              <span>Enter to send · Shift+Enter newline</span>
              {activeSymbol && (
                <span className="text-blue-500 font-mono">tracking {activeSymbol}</span>
              )}
            </div>
          </div>
        </>
      )}
    </div>
  );
}
