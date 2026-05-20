"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import {
  Bot, Loader2, Mic, MicOff, User, X, Minimize2, Maximize2,
  GripHorizontal, MessageCircle, ChevronDown,
} from "lucide-react";
import { api } from "@/lib/api";
import { cn, getSessionId } from "@/lib/utils";

type SpeechRecognitionEventLike = Event & {
  results: SpeechRecognitionResultList;
  resultIndex: number;
};
type SpeechRecognitionErrorEventLike = Event & { error?: string };
interface BrowserSpeechRecognition extends EventTarget {
  continuous: boolean;
  interimResults: boolean;
  lang: string;
  onstart: (() => void) | null;
  onend: (() => void) | null;
  onerror: ((event: SpeechRecognitionErrorEventLike) => void) | null;
  onresult: ((event: SpeechRecognitionEventLike) => void) | null;
  start: () => void;
  stop: () => void;
}
type SpeechRecognitionCtor = new () => BrowserSpeechRecognition;
declare global {
  interface Window {
    SpeechRecognition?: SpeechRecognitionCtor;
    webkitSpeechRecognition?: SpeechRecognitionCtor;
  }
}

interface DockMessage {
  role: "user" | "assistant";
  content: string;
  ts?: number;
}

function stripMarkdown(text: string) {
  return text
    .replace(/```[\s\S]*?```/g, "")
    .replace(/[#>*_`[\]()]/g, "")
    .replace(/\s+/g, " ")
    .trim();
}

const DEFAULT_POS = { x: 24, y: 24 }; // distance from bottom-right

export function NexusConversationDock() {
  const [sessionId] = useState(() => getSessionId());
  const [open, setOpen] = useState(false);
  const [minimized, setMinimized] = useState(false);
  const [messages, setMessages] = useState<DockMessage[]>([
    {
      role: "assistant",
      content: "I'm Nexus. Ask me about any stock, options strategy, or market event.",
      ts: Date.now(),
    },
  ]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [listening, setListening] = useState(false);
  const [voiceEnabled, setVoiceEnabled] = useState(false);
  const [voiceAvailable, setVoiceAvailable] = useState(true);
  const [voiceStatus, setVoiceStatus] = useState("Press mic to talk");
  const [unread, setUnread] = useState(0);

  // Drag state
  const [pos, setPos] = useState(DEFAULT_POS);
  const dragging = useRef(false);
  const dragStart = useRef({ mx: 0, my: 0, px: 0, py: 0 });
  const panelRef = useRef<HTMLDivElement>(null);

  const recognitionRef = useRef<BrowserSpeechRecognition | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);

  // Reset unread when opened
  useEffect(() => { if (open) setUnread(0); }, [open]);

  const speak = useCallback((text: string) => {
    if (typeof window === "undefined" || !window.speechSynthesis) return;
    window.speechSynthesis.cancel();
    const utterance = new SpeechSynthesisUtterance(stripMarkdown(text));
    utterance.rate = 0.98;
    utterance.pitch = 0.95;
    window.speechSynthesis.speak(utterance);
  }, []);

  const send = useCallback(async (text: string) => {
    const msg = text.trim();
    if (!msg || loading) return;
    setMessages((prev) => [...prev, { role: "user", content: msg, ts: Date.now() }]);
    setInput("");
    setLoading(true);
    try {
      const res = await api.chat(msg, sessionId);
      const reply = { role: "assistant" as const, content: res.response, ts: Date.now() };
      setMessages((prev) => [...prev, reply]);
      if (!open) setUnread((n) => n + 1);
      speak(res.response);
    } catch (error: any) {
      const content = `Backend unreachable: ${error.message}`;
      setMessages((prev) => [...prev, { role: "assistant", content, ts: Date.now() }]);
    } finally {
      setLoading(false);
    }
  }, [loading, sessionId, speak, open]);

  useEffect(() => {
    if (open) bottomRef.current?.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }, [messages, loading, open]);

  // Voice setup
  useEffect(() => {
    const Recognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!Recognition) { setVoiceAvailable(false); setVoiceStatus("Voice unavailable"); return; }
    const recognition = new Recognition();
    recognition.continuous = true;
    recognition.interimResults = true;
    recognition.lang = "en-US";
    recognitionRef.current = recognition;
    recognition.onstart = () => { setListening(true); setVoiceStatus("Listening…"); };
    recognition.onend = () => { setListening(false); setVoiceStatus("Press mic to talk"); };
    recognition.onerror = (e: SpeechRecognitionErrorEventLike) => {
      setListening(false); setVoiceEnabled(false);
      setVoiceStatus(e.error === "not-allowed" ? "Mic permission needed" : "Press mic to talk");
    };
    recognition.onresult = (e: SpeechRecognitionEventLike) => {
      let final = ""; let interim = "";
      for (let i = e.resultIndex; i < e.results.length; i++) {
        if (e.results[i].isFinal) final += e.results[i][0].transcript;
        else interim += e.results[i][0].transcript;
      }
      if (interim) setInput(interim.trim());
      if (final.trim()) send(final);
    };
    return () => { recognition.onend = null; recognition.stop(); };
  }, [send]);

  useEffect(() => {
    if (!voiceEnabled) return;
    try { recognitionRef.current?.start(); } catch {}
  }, [voiceEnabled]);

  const toggleVoice = () => {
    if (!voiceAvailable) return;
    if (voiceEnabled || listening) {
      setVoiceEnabled(false);
      recognitionRef.current?.stop();
    } else {
      setVoiceEnabled(true);
    }
  };

  // Drag handlers
  const onMouseDown = (e: React.MouseEvent) => {
    if ((e.target as HTMLElement).closest("button, textarea, input")) return;
    dragging.current = true;
    dragStart.current = { mx: e.clientX, my: e.clientY, px: pos.x, py: pos.y };
    e.preventDefault();
  };

  useEffect(() => {
    const onMove = (e: MouseEvent) => {
      if (!dragging.current) return;
      const dx = e.clientX - dragStart.current.mx;
      const dy = e.clientY - dragStart.current.my;
      const panel = panelRef.current;
      if (!panel) return;
      const pw = panel.offsetWidth;
      const ph = panel.offsetHeight;
      const maxX = window.innerWidth - pw - 8;
      const maxY = window.innerHeight - ph - 8;
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

  // Floating button (closed state)
  if (!open) {
    return (
      <button
        onClick={() => setOpen(true)}
        style={{ bottom: pos.y, right: pos.x }}
        className="fixed z-50 w-14 h-14 rounded-full bg-blue-600 hover:bg-blue-500 shadow-2xl flex items-center justify-center transition-all hover:scale-105 active:scale-95 group"
        title="Open Nexus AI"
      >
        <MessageCircle size={24} className="text-white" />
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

  return (
    <div
      ref={panelRef}
      style={{ bottom: pos.y, right: pos.x }}
      className="fixed z-50 w-[min(420px,calc(100vw-2rem))] rounded-xl border border-[#1f2937] bg-[#0d1117]/97 shadow-2xl backdrop-blur-sm select-none"
    >
      {/* Header — drag handle */}
      <div
        onMouseDown={onMouseDown}
        className="flex items-center gap-2 border-b border-[#1f2937] px-3 py-2.5 cursor-grab active:cursor-grabbing rounded-t-xl bg-[#111827]"
      >
        <GripHorizontal size={14} className="text-gray-600 flex-shrink-0" />
        <div className="flex h-7 w-7 items-center justify-center rounded-md bg-blue-600 flex-shrink-0">
          <Bot size={14} className="text-white" />
        </div>
        <div className="min-w-0 flex-1">
          <div className="text-xs font-semibold text-white">Nexus AI</div>
          <div className="flex items-center gap-1.5 text-[10px] text-gray-500">
            <span className={cn("w-1.5 h-1.5 rounded-full", listening ? "bg-green-400 animate-pulse" : "bg-gray-600")} />
            {voiceStatus}
          </div>
        </div>
        <button
          onClick={toggleVoice}
          disabled={!voiceAvailable}
          className={cn(
            "flex h-7 items-center gap-1 rounded-md px-2 text-xs font-medium transition-colors",
            listening || voiceEnabled
              ? "bg-red-600/20 text-red-300 hover:bg-red-600/30"
              : "bg-[#1f2937] text-gray-400 hover:text-white",
            !voiceAvailable && "opacity-40 cursor-not-allowed"
          )}
        >
          {listening || voiceEnabled ? <MicOff size={11} /> : <Mic size={11} />}
        </button>
        {loading && <Loader2 size={13} className="animate-spin text-blue-400 flex-shrink-0" />}
        <button
          onClick={() => setMinimized((m) => !m)}
          className="text-gray-500 hover:text-gray-300 transition-colors p-1"
          title={minimized ? "Expand" : "Minimize"}
        >
          {minimized ? <Maximize2 size={13} /> : <Minimize2 size={13} />}
        </button>
        <button
          onClick={() => setOpen(false)}
          className="text-gray-500 hover:text-red-400 transition-colors p-1"
          title="Close"
        >
          <X size={13} />
        </button>
      </div>

      {!minimized && (
        <>
          {/* Messages */}
          <div className="max-h-72 overflow-y-auto px-3 py-3 space-y-3">
            {messages.slice(-12).map((message, index) => (
              <div
                key={index}
                className={cn("flex gap-2 text-xs", message.role === "user" ? "justify-end" : "justify-start")}
              >
                {message.role === "assistant" && (
                  <div className="w-6 h-6 rounded-full bg-blue-600/20 border border-blue-600/30 flex items-center justify-center flex-shrink-0 mt-0.5">
                    <Bot size={11} className="text-blue-400" />
                  </div>
                )}
                <div className={cn(
                  "max-w-[85%] rounded-xl px-3 py-2 leading-relaxed",
                  message.role === "user"
                    ? "bg-blue-600 text-white rounded-br-sm"
                    : "border border-[#1f2937] bg-[#111827] text-gray-300 rounded-bl-sm"
                )}>
                  {message.content}
                </div>
                {message.role === "user" && (
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
                <div className="border border-[#1f2937] bg-[#111827] rounded-xl rounded-bl-sm px-3 py-2">
                  <div className="flex gap-1 items-center h-4">
                    <span className="w-1.5 h-1.5 bg-blue-400 rounded-full animate-bounce" style={{ animationDelay: "0ms" }} />
                    <span className="w-1.5 h-1.5 bg-blue-400 rounded-full animate-bounce" style={{ animationDelay: "150ms" }} />
                    <span className="w-1.5 h-1.5 bg-blue-400 rounded-full animate-bounce" style={{ animationDelay: "300ms" }} />
                  </div>
                </div>
              </div>
            )}
            <div ref={bottomRef} />
          </div>

          {/* Input */}
          <div className="border-t border-[#1f2937] px-3 py-2.5">
            <textarea
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={handleKey}
              placeholder="Ask about any stock, event, or strategy…"
              rows={2}
              className="w-full resize-none rounded-lg border border-[#253044] bg-[#111827] px-3 py-2 text-sm text-gray-100 outline-none placeholder:text-gray-600 focus:border-blue-500 transition-colors"
            />
            <div className="flex justify-between items-center mt-1.5">
              <span className="text-[10px] text-gray-600">Enter to send · Shift+Enter for newline</span>
              <button
                onClick={() => send(input)}
                disabled={!input.trim() || loading}
                className="bg-blue-600 hover:bg-blue-500 disabled:opacity-40 text-white text-xs px-3 py-1.5 rounded-lg transition-colors font-medium"
              >
                Send
              </button>
            </div>
          </div>
        </>
      )}
    </div>
  );
}
