"use client";

import { useState, useRef, useEffect, useCallback } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import {
  Send, Trash2, Zap, User, Bot, Loader2, AlertTriangle,
  Plus, MessageSquare, Pencil, Check, X, Clock,
} from "lucide-react";
import { api, type ChatResponse, type ChatSession } from "@/lib/api";
import { getSessionId, cn } from "@/lib/utils";

interface Message {
  role: "user" | "assistant";
  content: string;
  intent?: string;
  symbols?: string[];
  timestamp: Date;
}

const STARTERS = [
  "Analyze AAPL technicals and give me a trade setup",
  "What options strategy suits TSLA right now?",
  "Explain the difference between a call debit spread and a naked call",
  "Is NVDA overbought? Check RSI and MACD",
  "What is IV crush and how do I avoid it?",
  "Show me a bullish options strategy for a low-IV environment",
];

function formatRelative(iso: string): string {
  const d = new Date(iso + "Z");
  const now = Date.now();
  const diff = now - d.getTime();
  if (diff < 60_000) return "just now";
  if (diff < 3_600_000) return `${Math.floor(diff / 60_000)}m ago`;
  if (diff < 86_400_000) return `${Math.floor(diff / 3_600_000)}h ago`;
  return `${Math.floor(diff / 86_400_000)}d ago`;
}

export default function ChatPage() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [sessionId, setSessionId] = useState<string>(() => getSessionId());

  // Session sidebar
  const [sessions, setSessions] = useState<ChatSession[]>([]);
  const [sessionsLoading, setSessionsLoading] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editTitle, setEditTitle] = useState("");

  const bottomRef = useRef<HTMLDivElement>(null);

  // Load session list
  const loadSessions = useCallback(async () => {
    setSessionsLoading(true);
    try {
      const res = await api.getSessions();
      setSessions(res.sessions);
    } catch {}
    setSessionsLoading(false);
  }, []);

  // Load a specific session's history into the chat view
  const loadSessionHistory = useCallback(async (sid: string) => {
    try {
      const res = await api.getSession(sid);
      const turns = res.turns as Array<{ role: string; content: string; intent?: string; symbols?: string[]; timestamp: string }>;
      setMessages(
        turns
          .filter((t) => t.role === "user" || t.role === "assistant")
          .map((t) => ({
            role: t.role as "user" | "assistant",
            content: t.content,
            intent: t.intent,
            symbols: t.symbols,
            timestamp: new Date(t.timestamp + "Z"),
          }))
      );
    } catch {}
  }, []);

  useEffect(() => {
    loadSessions();
  }, [loadSessions]);

  // When session changes, load its history
  useEffect(() => {
    loadSessionHistory(sessionId);
  }, [sessionId, loadSessionHistory]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const send = useCallback(async (text: string) => {
    const msg = text.trim();
    if (!msg || loading) return;

    setMessages((prev) => [...prev, { role: "user", content: msg, timestamp: new Date() }]);
    setInput("");
    setLoading(true);

    try {
      const res: ChatResponse = await api.chat(msg, sessionId);
      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          content: res.response,
          intent: res.intent,
          symbols: res.symbols,
          timestamp: new Date(),
        },
      ]);
      // Refresh session list so title + timestamp update
      loadSessions();
    } catch (e: any) {
      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          content: `⚠️ Error: ${e.message}. Make sure the backend is running.`,
          timestamp: new Date(),
        },
      ]);
    } finally {
      setLoading(false);
    }
  }, [loading, sessionId, loadSessions]);

  const newSession = () => {
    const id = `session_${Date.now()}_${Math.random().toString(36).slice(2)}`;
    localStorage.setItem("nexus_session_id", id);
    setSessionId(id);
    setMessages([]);
    loadSessions();
  };

  const switchSession = (sid: string) => {
    localStorage.setItem("nexus_session_id", sid);
    setSessionId(sid);
  };

  const clearChat = async () => {
    try { await api.clearHistory(sessionId); } catch {}
    setMessages([]);
  };

  const deleteSession = async (sid: string) => {
    try { await api.deleteSession(sid); } catch {}
    if (sid === sessionId) newSession();
    else loadSessions();
  };

  const startRename = (s: ChatSession) => {
    setEditingId(s.id);
    setEditTitle(s.title);
  };

  const confirmRename = async (sid: string) => {
    if (editTitle.trim()) {
      try { await api.renameSession(sid, editTitle.trim()); } catch {}
      loadSessions();
    }
    setEditingId(null);
  };

  const handleKey = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(input); }
  };

  return (
    <div className="flex h-full bg-[#0a0e1a]">

      {/* ── Session sidebar ── */}
      <aside className="w-56 flex-shrink-0 flex flex-col bg-[#0d1117] border-r border-[#1f2937]">
        <div className="flex items-center justify-between px-3 py-3 border-b border-[#1f2937]">
          <span className="text-xs font-semibold text-gray-400 uppercase tracking-wide">History</span>
          <button
            onClick={newSession}
            title="New conversation"
            className="w-6 h-6 rounded-md bg-blue-600 hover:bg-blue-500 flex items-center justify-center transition-colors"
          >
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
            <div
              key={s.id}
              onClick={() => switchSession(s.id)}
              className={cn(
                "group relative flex flex-col px-3 py-2.5 cursor-pointer transition-colors",
                s.id === sessionId
                  ? "bg-blue-600/15 border-r-2 border-blue-500"
                  : "hover:bg-[#1f2937]/60"
              )}
            >
              {editingId === s.id ? (
                <div className="flex items-center gap-1" onClick={(e) => e.stopPropagation()}>
                  <input
                    autoFocus
                    value={editTitle}
                    onChange={(e) => setEditTitle(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === "Enter") confirmRename(s.id);
                      if (e.key === "Escape") setEditingId(null);
                    }}
                    className="flex-1 bg-[#1f2937] text-xs text-white px-1.5 py-0.5 rounded border border-blue-500 focus:outline-none min-w-0"
                  />
                  <button onClick={() => confirmRename(s.id)} className="text-green-400 hover:text-green-300">
                    <Check size={11} />
                  </button>
                  <button onClick={() => setEditingId(null)} className="text-gray-500 hover:text-gray-300">
                    <X size={11} />
                  </button>
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
                    <span className="text-[10px] text-gray-700">· {s.turn_count} msgs</span>
                  </div>
                  {/* Action buttons — visible on hover */}
                  <div className="absolute right-2 top-2 hidden group-hover:flex items-center gap-1" onClick={(e) => e.stopPropagation()}>
                    <button
                      onClick={() => startRename(s)}
                      className="w-5 h-5 rounded flex items-center justify-center text-gray-600 hover:text-gray-300 hover:bg-[#374151] transition-colors"
                    >
                      <Pencil size={9} />
                    </button>
                    <button
                      onClick={() => deleteSession(s.id)}
                      className="w-5 h-5 rounded flex items-center justify-center text-gray-600 hover:text-red-400 hover:bg-[#374151] transition-colors"
                    >
                      <Trash2 size={9} />
                    </button>
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

      {/* ── Main chat area ── */}
      <div className="flex-1 flex flex-col min-w-0">
        {/* Header */}
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
          {messages.length > 0 && (
            <button
              onClick={clearChat}
              className="flex items-center gap-1.5 text-xs text-gray-500 hover:text-red-400 transition-colors"
            >
              <Trash2 size={12} /> Clear
            </button>
          )}
        </div>

        {/* Messages */}
        <div className="flex-1 overflow-auto px-5 py-4 space-y-4">
          {messages.length === 0 && (
            <div className="flex flex-col items-center justify-center h-full gap-6 text-center">
              <div className="w-16 h-16 rounded-2xl bg-blue-600/20 border border-blue-600/30 flex items-center justify-center">
                <Zap size={28} className="text-blue-400" />
              </div>
              <div>
                <h2 className="text-lg font-semibold text-white mb-1">Nexus AI Trading Assistant</h2>
                <p className="text-sm text-gray-500 max-w-md">
                  Ask about stocks, options strategies, technical analysis, Greeks, IV, patterns, or anything market-related.
                  Every conversation is saved automatically.
                </p>
              </div>
              <div className="grid grid-cols-2 gap-2 max-w-xl w-full">
                {STARTERS.map((s) => (
                  <button
                    key={s}
                    onClick={() => send(s)}
                    className="text-left text-xs text-gray-400 bg-[#111827] border border-[#1f2937] hover:border-blue-600/40 hover:text-gray-200 rounded-lg px-3 py-2.5 transition-all"
                  >
                    {s}
                  </button>
                ))}
              </div>
            </div>
          )}

          {messages.map((msg, i) => (
            <div key={i} className={cn("flex gap-3", msg.role === "user" ? "justify-end" : "justify-start")}>
              {msg.role === "assistant" && (
                <div className="w-7 h-7 rounded-lg bg-blue-600/20 border border-blue-600/30 flex items-center justify-center flex-shrink-0 mt-0.5">
                  <Bot size={13} className="text-blue-400" />
                </div>
              )}
              <div className={cn(
                "max-w-[78%] rounded-2xl px-4 py-3 text-sm",
                msg.role === "user"
                  ? "bg-blue-600 text-white rounded-tr-sm"
                  : "bg-[#111827] border border-[#1f2937] text-gray-200 rounded-tl-sm"
              )}>
                {msg.role === "assistant" ? (
                  <div className="prose-nexus">
                    <ReactMarkdown remarkPlugins={[remarkGfm]}>{msg.content}</ReactMarkdown>
                  </div>
                ) : (
                  <p>{msg.content}</p>
                )}
                <div className="flex items-center gap-2 mt-2 flex-wrap">
                  <span className="text-[10px] opacity-40">
                    {msg.timestamp.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}
                  </span>
                  {msg.intent && msg.intent !== "general" && (
                    <span className="text-[10px] bg-blue-900/30 text-blue-400 px-1.5 py-0.5 rounded">
                      {msg.intent.replace(/_/g, " ")}
                    </span>
                  )}
                  {msg.symbols?.map((s) => (
                    <span key={s} className="text-[10px] bg-gray-800 text-gray-400 px-1.5 py-0.5 rounded font-mono">
                      {s}
                    </span>
                  ))}
                </div>
              </div>
              {msg.role === "user" && (
                <div className="w-7 h-7 rounded-lg bg-gray-700 flex items-center justify-center flex-shrink-0 mt-0.5">
                  <User size={13} className="text-gray-300" />
                </div>
              )}
            </div>
          ))}

          {loading && (
            <div className="flex gap-3">
              <div className="w-7 h-7 rounded-lg bg-blue-600/20 border border-blue-600/30 flex items-center justify-center flex-shrink-0">
                <Bot size={13} className="text-blue-400" />
              </div>
              <div className="bg-[#111827] border border-[#1f2937] rounded-2xl rounded-tl-sm px-4 py-3">
                <Loader2 size={14} className="animate-spin text-blue-400" />
              </div>
            </div>
          )}
          <div ref={bottomRef} />
        </div>

        {/* Disclaimer */}
        <div className="px-5 py-1.5 flex items-center gap-1.5 text-[10px] text-gray-600 border-t border-[#1f2937]">
          <AlertTriangle size={10} />
          Not financial advice. Options trading involves substantial risk of loss.
        </div>

        {/* Input */}
        <div className="px-5 pb-4 pt-2">
          <div className="flex items-end gap-2 bg-[#111827] border border-[#1f2937] focus-within:border-blue-600/50 rounded-xl px-4 py-3 transition-colors">
            <textarea
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={handleKey}
              placeholder="Ask about stocks, options, patterns, strategies…"
              rows={1}
              className="flex-1 bg-transparent text-sm text-gray-200 placeholder-gray-600 resize-none focus:outline-none max-h-32"
              style={{ lineHeight: "1.5" }}
            />
            <button
              onClick={() => send(input)}
              disabled={!input.trim() || loading}
              className="w-8 h-8 rounded-lg bg-blue-600 hover:bg-blue-500 disabled:opacity-40 disabled:cursor-not-allowed flex items-center justify-center transition-colors flex-shrink-0"
            >
              <Send size={14} className="text-white" />
            </button>
          </div>
          <p className="text-[10px] text-gray-700 mt-1.5 text-center">Enter to send · Shift+Enter for new line · All conversations saved automatically</p>
        </div>
      </div>
    </div>
  );
}
