"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import {
  Bot, Mic, MicOff, Volume2, VolumeX, X, Minimize2, Maximize2,
  GripHorizontal, MessageCircle, Send, Loader2, User, BarChart2,
  CheckCircle, XCircle, History, Zap, BookOpen, AlertTriangle,
  ChevronDown, ChevronUp, BrainCircuit, Activity,
} from "lucide-react";
import {
  api,
  type ChatResponse,
  type SimulationResult,
  type AppCommand,
  type PendingConfirmation,
  type SessionInsight,
  type ToolCall,
} from "@/lib/api";
import { cn, getSessionId } from "@/lib/utils";

// ── Speech API types ──────────────────────────────────────────────────────────
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
  start(): void; stop(): void; abort(): void;
}
declare const webkitSpeechRecognition: new () => SR;
declare const SpeechRecognition: new () => SR;

// ── Message type ──────────────────────────────────────────────────────────────
interface Msg {
  id: string;
  role: "user" | "assistant" | "system";
  content: string;
  timestamp: Date;
  simulation?: SimulationResult;
  app_commands?: AppCommand[];
  pending_confirmations?: PendingConfirmation[];
  voice_reasoning?: string;
  new_insights?: SessionInsight[];
  tool_log?: ToolCall[];
  intent?: string;
}

// ── TTS helper ────────────────────────────────────────────────────────────────
function ttsSpeak(text: string, muted: boolean) {
  if (muted || typeof window === "undefined" || !window.speechSynthesis) return;
  window.speechSynthesis.cancel();
  const clean = text
    .replace(/\[\[NEXUS_CMD:[^\]]*\]\]/g, "")
    .replace(/[*_`#>]/g, "")
    .replace(/\s+/g, " ")
    .trim()
    .slice(0, 500);
  if (!clean) return;
  const utt = new SpeechSynthesisUtterance(clean);
  utt.rate = 1.05; utt.pitch = 1.0; utt.volume = 1.0;
  window.speechSynthesis.speak(utt);
}

// ── SimCard ───────────────────────────────────────────────────────────────────
function SimCard({ sim }: { sim: SimulationResult }) {
  const wr = sim.win_rate ?? 0;
  return (
    <div className="mt-2 bg-[#0d1117] border border-[#1f2937] rounded-lg p-3 text-xs space-y-1.5">
      <div className="flex items-center gap-2">
        <BarChart2 size={11} className="text-blue-400" />
        <span className="font-semibold text-gray-300">{sim.symbol} Simulation</span>
        <span className={cn("ml-auto font-mono font-bold", wr >= 55 ? "text-green-400" : "text-red-400")}>{wr}%</span>
      </div>
      <div className="flex gap-3 text-gray-500">
        <span>{sim.total_predictions} trades</span>
        <span>{sim.date_range.start?.slice(0,4)}–{sim.date_range.end?.slice(0,4)}</span>
        {sim.avg_pnl_pct != null && (
          <span className={sim.avg_pnl_pct >= 0 ? "text-green-400" : "text-red-400"}>
            avg {sim.avg_pnl_pct >= 0 ? "+" : ""}{sim.avg_pnl_pct}%
          </span>
        )}
      </div>
      <a href="/analysis" className="text-blue-400 hover:text-blue-300 text-[10px]">
        Open full analysis →
      </a>
    </div>
  );
}

// ── ConfirmationCard ──────────────────────────────────────────────────────────
function ConfirmationCard({
  cmd, onConfirm, onReject,
}: {
  cmd: PendingConfirmation;
  onConfirm: (id: string) => void;
  onReject: (id: string) => void;
}) {
  const label = {
    trade_buy: "Buy order",
    trade_sell: "Sell order",
    trade_options: "Options trade",
    clear_watchlist: "Clear watchlist",
    delete_session: "Delete session",
  }[cmd.type] ?? cmd.type;

  return (
    <div className="mt-2 bg-yellow-900/20 border border-yellow-800/40 rounded-lg p-3 text-xs space-y-2">
      <div className="flex items-center gap-2 text-yellow-400">
        <AlertTriangle size={11} />
        <span className="font-semibold">Confirmation required: {label}</span>
      </div>
      {cmd.symbol && <div className="text-gray-400">Symbol: <span className="font-mono text-white">{cmd.symbol}</span></div>}
      <div className="flex gap-2">
        <button onClick={() => onConfirm(cmd.id)}
          className="flex items-center gap-1 bg-green-700 hover:bg-green-600 text-white px-3 py-1 rounded text-[10px] font-semibold transition-colors">
          <CheckCircle size={10} /> Confirm
        </button>
        <button onClick={() => onReject(cmd.id)}
          className="flex items-center gap-1 bg-red-900/40 hover:bg-red-800/60 text-red-400 px-3 py-1 rounded text-[10px] font-semibold transition-colors">
          <XCircle size={10} /> Cancel
        </button>
      </div>
    </div>
  );
}

// ── InsightBadge ──────────────────────────────────────────────────────────────
function InsightBadge({ insights }: { insights: SessionInsight[] }) {
  if (!insights.length) return null;
  return (
    <div className="mt-1.5 flex flex-wrap gap-1">
      {insights.slice(0, 3).map((ins, i) => (
        <span key={i} className="text-[9px] px-1.5 py-0.5 rounded bg-cyan-900/20 border border-cyan-800/30 text-cyan-400">
          {ins.insight_type}: {ins.content.slice(0, 40)}
        </span>
      ))}
    </div>
  );
}

// ── ToolCallLog ───────────────────────────────────────────────────────────────

const TOOL_ICONS: Record<string, string> = {
  web_search:       "🔍",
  fetch_page:       "📄",
  get_stock_price:  "📈",
  run_simulation:   "⚙️",
  optimize_weights: "🧬",
  research_symbol:  "🔬",
  research_strategy:"📚",
  research_event:   "🌐",
  get_model_stats:  "📊",
  remember_finding: "💾",
};

function ToolCallLog({ calls }: { calls: ToolCall[] }) {
  const [expanded, setExpanded] = useState<number | null>(null);
  if (!calls.length) return null;

  return (
    <div className="mt-2 space-y-1">
      <div className="text-[9px] text-gray-600 uppercase tracking-wide px-1 flex items-center gap-1">
        <Zap size={8} className="text-yellow-500" />
        {calls.length} tool{calls.length > 1 ? "s" : ""} used
      </div>
      {calls.map((call, i) => {
        const icon = TOOL_ICONS[call.name] ?? "🔧";
        const isSearch = call.name === "web_search";
        const isFetch  = call.name === "fetch_page";
        const results  = isSearch ? (call.result as any)?.results : null;
        const sources  = results?.slice(0, 3) as Array<{title: string; url: string; snippet: string}> | null;

        return (
          <div key={i} className="bg-[#0d1117] border border-[#1f2937] rounded-lg overflow-hidden">
            <button onClick={() => setExpanded(expanded === i ? null : i)}
              className="w-full flex items-center gap-2 px-2.5 py-1.5 text-left hover:bg-[#1f2937]/40 transition-colors">
              <span className="text-[11px]">{icon}</span>
              <span className="text-[10px] text-gray-400 flex-1 truncate">{call.label}</span>
              <span className="text-[9px] text-gray-700 flex-shrink-0">{call.elapsed}s</span>
              {expanded === i
                ? <ChevronUp size={9} className="text-gray-600 flex-shrink-0" />
                : <ChevronDown size={9} className="text-gray-600 flex-shrink-0" />}
            </button>

            {expanded === i && (
              <div className="px-2.5 pb-2.5 space-y-1.5 border-t border-[#1f2937]">
                {/* Args */}
                <div className="text-[9px] text-gray-600 pt-1.5">
                  {Object.entries(call.args).map(([k, v]) => (
                    <span key={k} className="mr-2">
                      <span className="text-gray-700">{k}:</span>{" "}
                      <span className="text-gray-500">{String(v).slice(0, 60)}</span>
                    </span>
                  ))}
                </div>

                {/* Search results */}
                {sources && sources.length > 0 && (
                  <div className="space-y-1">
                    <div className="text-[9px] text-gray-600 uppercase tracking-wide">Sources</div>
                    {sources.map((s, j) => (
                      <div key={j} className="text-[10px] space-y-0.5">
                        <a href={s.url} target="_blank" rel="noopener noreferrer"
                          className="text-blue-400 hover:text-blue-300 truncate block leading-tight">
                          {s.title || s.url}
                        </a>
                        <p className="text-gray-600 leading-relaxed line-clamp-2">{s.snippet}</p>
                      </div>
                    ))}
                  </div>
                )}

                {/* Fetch result */}
                {isFetch && (call.result as any)?.content && (
                  <div className="text-[10px] text-gray-500 leading-relaxed line-clamp-4">
                    {String((call.result as any).content).slice(0, 300)}…
                  </div>
                )}

                {/* Generic result for other tools */}
                {!isSearch && !isFetch && (
                  <div className="text-[10px] text-gray-600 font-mono leading-relaxed">
                    {JSON.stringify(call.result, null, 2).slice(0, 400)}
                  </div>
                )}
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}

// ── SessionLog drawer ─────────────────────────────────────────────────────────
function SessionLog({ messages, onClose }: { messages: Msg[]; onClose: () => void }) {
  return (
    <div className="absolute inset-0 bg-[#0d1117] rounded-2xl flex flex-col z-10">
      <div className="flex items-center gap-2 px-4 py-3 border-b border-[#1f2937]">
        <History size={13} className="text-blue-400" />
        <span className="text-xs font-semibold text-gray-300">Session Log</span>
        <span className="text-[10px] text-gray-600 bg-[#1f2937] px-2 py-0.5 rounded-full ml-auto">{messages.length} turns</span>
        <button onClick={onClose} className="text-gray-500 hover:text-white ml-2"><X size={13} /></button>
      </div>
      <div className="flex-1 overflow-y-auto p-3 space-y-2">
        {messages.map(m => (
          <div key={m.id} className={cn("text-xs rounded-lg px-3 py-2",
            m.role === "user" ? "bg-blue-900/20 text-blue-200" : "bg-[#1f2937] text-gray-300")}>
            <div className="flex items-center gap-2 mb-1">
              <span className="text-[10px] text-gray-600 uppercase">{m.role}</span>
              <span className="text-[10px] text-gray-700">{m.timestamp.toLocaleTimeString()}</span>
              {m.intent && <span className="text-[10px] text-gray-700 ml-auto">{m.intent}</span>}
            </div>
            <p className="leading-relaxed line-clamp-3">{m.content}</p>
          </div>
        ))}
      </div>
    </div>
  );
}

// ── Main component ────────────────────────────────────────────────────────────
export function NexusVoice() {
  const router = useRouter();
  const sessionId = getSessionId();

  // UI state
  const [open, setOpen]           = useState(false);
  const [minimized, setMinimized] = useState(false);
  const [muted, setMuted]         = useState(false);
  const [voiceMode, setVoiceMode] = useState(false);
  const [showLog, setShowLog]     = useState(false);
  const [unread, setUnread]       = useState(0);

  // Drag state
  const [drag, setDrag]   = useState({ x: 0, y: 0 });
  const dragRef           = useRef({ dragging: false, startX: 0, startY: 0, ox: 0, oy: 0 });

  // Chat state
  const [messages, setMessages]   = useState<Msg[]>([{
    id: "init",
    role: "assistant",
    content: "I'm Nexus. Ask me about any stock, say 'simulate Apple 5 years', or ask me to predict a move. I'll speak my reasoning aloud in voice mode.",
    timestamp: new Date(),
  }]);
  const [input, setInput]         = useState("");
  const [loading, setLoading]     = useState(false);
  const [activeSymbol, setActiveSymbol] = useState<string | null>(null);

  // Voice state
  const [listening, setListening]   = useState(false);
  const [continuous, setContinuous] = useState(false);
  const [interim, setInterim]       = useState("");
  const srRef         = useRef<SR | null>(null);
  const continuousRef = useRef(false);

  const bottomRef = useRef<HTMLDivElement>(null);

  // ── Scroll to bottom ──
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  // ── Unread badge ──
  useEffect(() => {
    if (!open) return;
    setUnread(0);
  }, [open]);

  // ── Drag handlers ──
  const onDragStart = useCallback((e: React.MouseEvent) => {
    e.preventDefault();
    dragRef.current = { dragging: true, startX: e.clientX, startY: e.clientY, ox: drag.x, oy: drag.y };
    const onMove = (ev: MouseEvent) => {
      if (!dragRef.current.dragging) return;
      setDrag({
        x: dragRef.current.ox + (ev.clientX - dragRef.current.startX),
        y: dragRef.current.oy + (ev.clientY - dragRef.current.startY),
      });
    };
    const onUp = () => {
      dragRef.current.dragging = false;
      window.removeEventListener("mousemove", onMove);
      window.removeEventListener("mouseup", onUp);
    };
    window.addEventListener("mousemove", onMove);
    window.addEventListener("mouseup", onUp);
  }, [drag]);

  // ── App-control dispatcher ──
  const dispatchCommand = useCallback((cmd: AppCommand) => {
    switch (cmd.type) {
      case "navigate":
        if (cmd.path) router.push(cmd.path);
        break;
      case "analyze":
        if (cmd.symbol) router.push(`/analysis?symbol=${cmd.symbol}`);
        break;
      case "simulate":
        if (cmd.symbol) router.push(`/analysis?symbol=${cmd.symbol}&years=${cmd.years ?? 5}`);
        break;
      case "watchlist_add":
        if (cmd.symbol) {
          api.addToWatchlist(sessionId, cmd.symbol).catch(() => {});
        }
        break;
      case "show_analysis":
        router.push("/analysis");
        break;
      case "show_events":
        router.push("/events");
        break;
    }
  }, [router, sessionId]);

  const handleConfirm = useCallback(async (cmdId: string) => {
    await api.confirmCommand(cmdId, true);
    // Find the command in messages and execute it
    for (const msg of messages) {
      const cmd = msg.pending_confirmations?.find(c => c.id === cmdId);
      if (cmd) { dispatchCommand(cmd); break; }
    }
    setMessages(prev => prev.map(m => ({
      ...m,
      pending_confirmations: m.pending_confirmations?.filter(c => c.id !== cmdId),
    })));
  }, [messages, dispatchCommand]);

  const handleReject = useCallback(async (cmdId: string) => {
    await api.confirmCommand(cmdId, false);
    setMessages(prev => prev.map(m => ({
      ...m,
      pending_confirmations: m.pending_confirmations?.filter(c => c.id !== cmdId),
    })));
  }, []);

  // ── Send message ──
  const send = useCallback(async (text: string) => {
    const msg = text.trim();
    if (!msg || loading) return;
    setInput("");
    setInterim("");

    const userMsg: Msg = { id: Date.now().toString(), role: "user", content: msg, timestamp: new Date() };
    setMessages(prev => [...prev, userMsg]);
    setLoading(true);

    try {
      const res: ChatResponse = await api.chat(msg, sessionId, voiceMode);

      if (res.active_symbol) setActiveSymbol(res.active_symbol);

      // Auto-dispatch safe app commands
      if (res.app_commands?.length) {
        for (const cmd of res.app_commands) {
          dispatchCommand(cmd);
        }
      }

      const assistantMsg: Msg = {
        id: (Date.now() + 1).toString(),
        role: "assistant",
        content: res.response,
        timestamp: new Date(),
        simulation: res.simulation as SimulationResult | undefined,
        app_commands: res.app_commands,
        pending_confirmations: res.pending_confirmations,
        voice_reasoning: res.voice_reasoning,
        new_insights: res.new_insights,
        tool_log: res.tool_log,
        intent: res.intent,
      };
      setMessages(prev => [...prev, assistantMsg]);

      if (!open) setUnread(n => n + 1);

      // Speak: prefer voice_reasoning (prediction rationale), else response
      const toSpeak = voiceMode && res.voice_reasoning ? res.voice_reasoning : res.response;
      ttsSpeak(toSpeak, muted);

    } catch (err: any) {
      setMessages(prev => [...prev, {
        id: (Date.now() + 1).toString(),
        role: "assistant",
        content: `Error: ${err.message || "Request failed"}`,
        timestamp: new Date(),
      }]);
    } finally {
      setLoading(false);
    }
  }, [loading, sessionId, voiceMode, muted, open, dispatchCommand]);

  // ── Speech recognition ──
  const startListening = useCallback(() => {
    const SR = typeof SpeechRecognition !== "undefined" ? SpeechRecognition
      : typeof webkitSpeechRecognition !== "undefined" ? webkitSpeechRecognition : null;
    if (!SR) {
      setMessages(prev => [...prev, {
        id: Date.now().toString(), role: "system",
        content: "Speech recognition is not supported in this browser.",
        timestamp: new Date(),
      }]);
      return;
    }
    if (srRef.current) { try { srRef.current.abort(); } catch {} }
    const sr = new SR();
    sr.continuous = continuousRef.current;
    sr.interimResults = true;
    sr.lang = "en-US";
    srRef.current = sr;

    sr.onstart = () => setListening(true);
    sr.onend = () => {
      setListening(false);
      setInterim("");
      if (continuousRef.current) {
        setTimeout(() => { if (continuousRef.current) startListening(); }, 300);
      }
    };
    sr.onerror = (e) => {
      if (e.error !== "no-speech" && e.error !== "aborted") {
        setMessages(prev => [...prev, {
          id: Date.now().toString(), role: "system",
          content: `Mic error: ${e.error}`,
          timestamp: new Date(),
        }]);
      }
      setListening(false);
    };
    sr.onresult = (e) => {
      let final = "", inter = "";
      for (let i = e.resultIndex; i < e.results.length; i++) {
        const t = e.results[i][0].transcript;
        if (e.results[i].isFinal) final += t;
        else inter += t;
      }
      setInterim(inter);
      if (final.trim()) {
        setInput(prev => (prev + " " + final).trim());
        if (continuousRef.current) {
          setTimeout(() => send(final.trim()), 100);
        }
      }
    };
    try { sr.start(); } catch {}
  }, [send]);

  const stopListening = useCallback(() => {
    continuousRef.current = false;
    setContinuous(false);
    try { srRef.current?.stop(); } catch {}
    setListening(false);
  }, []);

  const toggleContinuous = useCallback(() => {
    const next = !continuous;
    setContinuous(next);
    continuousRef.current = next;
    if (next) startListening();
    else stopListening();
  }, [continuous, startListening, stopListening]);

  // Cleanup on unmount
  useEffect(() => () => { try { srRef.current?.abort(); } catch {} }, []);

  // ── Mute toggle ──
  const toggleMute = useCallback(() => {
    setMuted(m => {
      if (!m) window.speechSynthesis?.cancel();
      return !m;
    });
  }, []);

  // ── Render ──
  const panelStyle: React.CSSProperties = {
    position: "fixed",
    bottom: `${24 - drag.y}px`,
    right: `${24 - drag.x}px`,
    zIndex: 9999,
  };

  return (
    <div style={panelStyle}>
      {/* ── Collapsed FAB ── */}
      {!open && (
        <button onClick={() => setOpen(true)}
          className="relative w-12 h-12 rounded-full bg-blue-600 hover:bg-blue-500 shadow-2xl flex items-center justify-center transition-all hover:scale-105">
          <Bot size={22} className="text-white" />
          {unread > 0 && (
            <span className="absolute -top-1 -right-1 w-5 h-5 bg-red-500 rounded-full text-[10px] text-white flex items-center justify-center font-bold">
              {unread > 9 ? "9+" : unread}
            </span>
          )}
        </button>
      )}

      {/* ── Open panel ── */}
      {open && (
        <div className={cn(
          "flex flex-col bg-[#111827] border border-[#1f2937] rounded-2xl shadow-2xl overflow-hidden transition-all",
          minimized ? "w-72 h-12" : "w-80 sm:w-96 h-[560px]"
        )}>
          {/* Header */}
          <div onMouseDown={onDragStart}
            className="flex items-center gap-2 px-3 py-2.5 border-b border-[#1f2937] bg-[#0d1117] cursor-grab active:cursor-grabbing flex-shrink-0 select-none">
            <GripHorizontal size={13} className="text-gray-600" />
            <div className="w-6 h-6 rounded-full bg-blue-600 flex items-center justify-center flex-shrink-0">
              <Bot size={13} className="text-white" />
            </div>
            <span className="text-xs font-semibold text-white">Nexus</span>
            {activeSymbol && (
              <span className="text-[10px] text-blue-400 font-mono bg-blue-900/20 px-1.5 py-0.5 rounded">
                {activeSymbol}
              </span>
            )}
            {listening && (
              <span className="text-[10px] text-red-400 animate-pulse ml-1">● REC</span>
            )}
            <div className="flex-1" />
            {/* Session log */}
            <button onClick={() => setShowLog(s => !s)} title="Session log"
              className={cn("p-1 rounded transition-colors", showLog ? "text-blue-400" : "text-gray-500 hover:text-gray-300")}>
              <History size={13} />
            </button>
            {/* Voice mode */}
            <button onClick={() => setVoiceMode(v => !v)} title="Voice mode"
              className={cn("p-1 rounded transition-colors", voiceMode ? "text-cyan-400" : "text-gray-500 hover:text-gray-300")}>
              <Zap size={13} />
            </button>
            {/* Mute */}
            <button onClick={toggleMute} title={muted ? "Unmute" : "Mute"}
              className="p-1 rounded text-gray-500 hover:text-gray-300 transition-colors">
              {muted ? <VolumeX size={13} /> : <Volume2 size={13} />}
            </button>
            {/* Minimize */}
            <button onClick={() => setMinimized(m => !m)}
              className="p-1 rounded text-gray-500 hover:text-gray-300 transition-colors">
              {minimized ? <Maximize2 size={13} /> : <Minimize2 size={13} />}
            </button>
            {/* Close */}
            <button onClick={() => setOpen(false)}
              className="p-1 rounded text-gray-500 hover:text-red-400 transition-colors">
              <X size={13} />
            </button>
          </div>

          {!minimized && (
            <>
              {/* Body */}
              <div className="relative flex-1 overflow-hidden">
                {/* Session log overlay */}
                {showLog && <SessionLog messages={messages} onClose={() => setShowLog(false)} />}

                {/* Messages */}
                <div className="h-full overflow-y-auto p-3 space-y-3">
                  {messages.map(msg => (
                    <div key={msg.id} className={cn("flex gap-2", msg.role === "user" ? "justify-end" : "justify-start")}>
                      {msg.role !== "user" && (
                        <div className={cn("w-6 h-6 rounded-full flex items-center justify-center flex-shrink-0 mt-0.5",
                          msg.role === "system" ? "bg-yellow-900/40" : "bg-blue-600")}>
                          {msg.role === "system" ? <AlertTriangle size={11} className="text-yellow-400" /> : <Bot size={11} className="text-white" />}
                        </div>
                      )}
                      <div className={cn("max-w-[85%] space-y-1")}>
                        <div className={cn("rounded-2xl px-3 py-2 text-xs leading-relaxed",
                          msg.role === "user"
                            ? "bg-blue-600 text-white rounded-br-sm"
                            : msg.role === "system"
                            ? "bg-yellow-900/20 border border-yellow-800/30 text-yellow-300"
                            : "bg-[#1f2937] text-gray-200 rounded-bl-sm")}>
                          {/* Strip embedded commands from display */}
                          {msg.content.replace(/\[\[NEXUS_CMD:[^\]]*\]\]/g, "").trim()}
                        </div>

                        {/* Voice reasoning badge */}
                        {msg.voice_reasoning && (
                          <div className="flex items-center gap-1 text-[10px] text-cyan-400 px-1">
                            <Volume2 size={9} />
                            <span>Reasoning spoken aloud</span>
                          </div>
                        )}

                        {/* App commands executed */}
                        {msg.app_commands && msg.app_commands.length > 0 && (
                          <div className="flex flex-wrap gap-1 px-1">
                            {msg.app_commands.map((cmd, i) => (
                              <span key={i} className="text-[9px] px-1.5 py-0.5 rounded bg-blue-900/20 border border-blue-800/30 text-blue-400">
                                ⚡ {cmd.type}{cmd.symbol ? ` ${cmd.symbol}` : ""}{cmd.path ? ` → ${cmd.path}` : ""}
                              </span>
                            ))}
                          </div>
                        )}

                        {/* Tool calls (research panel) */}
                        {msg.tool_log && msg.tool_log.length > 0 && (
                          <ToolCallLog calls={msg.tool_log} />
                        )}

                        {/* Pending confirmations */}
                        {msg.pending_confirmations?.map(cmd => (
                          <ConfirmationCard key={cmd.id} cmd={cmd}
                            onConfirm={handleConfirm} onReject={handleReject} />
                        ))}

                        {/* Simulation card */}
                        {msg.simulation && <SimCard sim={msg.simulation} />}

                        {/* New insights */}
                        {msg.new_insights && msg.new_insights.length > 0 && (
                          <InsightBadge insights={msg.new_insights} />
                        )}

                        <div className="text-[9px] text-gray-700 px-1">
                          {msg.timestamp.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}
                        </div>
                      </div>
                      {msg.role === "user" && (
                        <div className="w-6 h-6 rounded-full bg-gray-700 flex items-center justify-center flex-shrink-0 mt-0.5">
                          <User size={11} className="text-gray-300" />
                        </div>
                      )}
                    </div>
                  ))}

                  {loading && (
                    <div className="flex gap-2 justify-start">
                      <div className="w-6 h-6 rounded-full bg-blue-600 flex items-center justify-center flex-shrink-0">
                        <Bot size={11} className="text-white" />
                      </div>
                      <div className="bg-[#1f2937] rounded-2xl rounded-bl-sm px-3 py-2">
                        <Loader2 size={13} className="animate-spin text-blue-400" />
                      </div>
                    </div>
                  )}

                  {interim && (
                    <div className="text-[10px] text-gray-600 italic px-2">{interim}…</div>
                  )}
                  <div ref={bottomRef} />
                </div>
              </div>

              {/* Input bar */}
              <div className="flex-shrink-0 border-t border-[#1f2937] bg-[#0d1117] p-2 space-y-1.5">
                <div className="flex items-center gap-2">
                  <input
                    value={input}
                    onChange={e => setInput(e.target.value)}
                    onKeyDown={e => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(input); } }}
                    placeholder={listening ? "Listening…" : "Ask Nexus anything…"}
                    className="flex-1 bg-[#1f2937] border border-[#374151] rounded-lg px-3 py-1.5 text-xs text-white placeholder-gray-600 focus:outline-none focus:border-blue-500"
                  />
                  <button onClick={() => send(input)} disabled={loading || !input.trim()}
                    className="w-7 h-7 bg-blue-600 hover:bg-blue-500 disabled:opacity-40 rounded-lg flex items-center justify-center transition-colors flex-shrink-0">
                    {loading ? <Loader2 size={12} className="animate-spin text-white" /> : <Send size={12} className="text-white" />}
                  </button>
                  {/* Continuous voice toggle */}
                  <button onClick={toggleContinuous}
                    title={continuous ? "Stop always-on mic" : "Always-on mic"}
                    className={cn("w-7 h-7 rounded-lg flex items-center justify-center transition-colors flex-shrink-0",
                      continuous ? "bg-red-600 hover:bg-red-500" : "bg-[#1f2937] hover:bg-[#374151]")}>
                    {continuous ? <MicOff size={12} className="text-white" /> : <Mic size={12} className="text-gray-400" />}
                  </button>
                  {/* Push-to-talk */}
                  <button
                    onMouseDown={() => { continuousRef.current = false; startListening(); }}
                    onMouseUp={stopListening}
                    onTouchStart={() => { continuousRef.current = false; startListening(); }}
                    onTouchEnd={stopListening}
                    title="Hold to talk"
                    className={cn("w-7 h-7 rounded-lg flex items-center justify-center transition-colors flex-shrink-0",
                      listening && !continuous ? "bg-red-600 animate-pulse" : "bg-[#1f2937] hover:bg-[#374151]")}>
                    <Mic size={12} className={listening && !continuous ? "text-white" : "text-gray-500"} />
                  </button>
                </div>
                <div className="flex items-center justify-between text-[9px] text-gray-700 px-1">
                  <span className="truncate">
                    {continuous ? "🔴 Always-on mic" : "Hold 🎤 to talk"}
                    {" · "}
                    <span className="text-gray-600">Try: "research NVDA" · "search RSI strategy" · "optimize AAPL"</span>
                  </span>
                  <div className="flex items-center gap-2 flex-shrink-0 ml-1">
                    {voiceMode && <span className="text-cyan-600">⚡</span>}
                    {activeSymbol && <span className="text-blue-600 font-mono">{activeSymbol}</span>}
                  </div>
                </div>
              </div>
            </>
          )}
        </div>
      )}
    </div>
  );
}
