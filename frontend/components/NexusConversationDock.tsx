"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { Bot, Loader2, Mic, MicOff, User } from "lucide-react";
import { api } from "@/lib/api";
import { cn, getSessionId } from "@/lib/utils";

type SpeechRecognitionEventLike = Event & {
  results: SpeechRecognitionResultList;
  resultIndex: number;
};

type SpeechRecognitionErrorEventLike = Event & {
  error?: string;
};

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
}

function stripMarkdown(text: string) {
  return text
    .replace(/```[\s\S]*?```/g, "")
    .replace(/[#>*_`[\]()]/g, "")
    .replace(/\s+/g, " ")
    .trim();
}

export function NexusConversationDock() {
  const [sessionId] = useState(() => getSessionId());
  const [messages, setMessages] = useState<DockMessage[]>([
    {
      role: "assistant",
      content: "I’m here. Speak or type a market question and I’ll keep the thread moving.",
    },
  ]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [listening, setListening] = useState(false);
  const [voiceEnabled, setVoiceEnabled] = useState(false);
  const [voiceAvailable, setVoiceAvailable] = useState(true);
  const [voiceStatus, setVoiceStatus] = useState("Press Start to talk");
  const recognitionRef = useRef<BrowserSpeechRecognition | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);

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

    setMessages((prev) => [...prev, { role: "user", content: msg }]);
    setInput("");
    setLoading(true);

    try {
      const res = await api.chat(msg, sessionId);
      setMessages((prev) => [...prev, { role: "assistant", content: res.response }]);
      speak(res.response);
    } catch (error: any) {
      const content = `I couldn’t reach the Nexus backend: ${error.message}`;
      setMessages((prev) => [...prev, { role: "assistant", content }]);
      speak(content);
    } finally {
      setLoading(false);
    }
  }, [loading, sessionId, speak]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }, [messages, loading]);

  useEffect(() => {
    const Recognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!Recognition) {
      setVoiceAvailable(false);
      setVoiceStatus("Voice unavailable");
      return;
    }

    const recognition = new Recognition();
    recognition.continuous = true;
    recognition.interimResults = true;
    recognition.lang = "en-US";
    recognitionRef.current = recognition;

    recognition.onstart = () => {
      setListening(true);
      setVoiceStatus("Listening");
    };
    recognition.onend = () => {
      setListening(false);
      setVoiceStatus((current) => current === "Stopping" ? "Press Start to talk" : "Voice standby");
    };
    recognition.onerror = (event: SpeechRecognitionErrorEventLike) => {
      setListening(false);
      setVoiceEnabled(false);
      setVoiceStatus(event.error === "not-allowed" ? "Mic permission needed" : "Voice standby");
    };
    recognition.onresult = (event: SpeechRecognitionEventLike) => {
      let finalText = "";
      let interimText = "";
      for (let i = event.resultIndex; i < event.results.length; i += 1) {
        const result = event.results[i];
        if (result.isFinal) finalText += result[0].transcript;
        else interimText += result[0].transcript;
      }
      if (interimText) setInput(interimText.trim());
      if (finalText.trim()) {
        send(finalText);
      }
    };

    return () => {
      recognition.onend = null;
      recognition.stop();
    };
  }, [send]);

  useEffect(() => {
    if (!voiceEnabled) return;
    const recognition = recognitionRef.current;
    if (!recognition) return;
    try {
      recognition.start();
    } catch {}
  }, [voiceEnabled]);

  const toggleVoice = () => {
    if (!voiceAvailable) {
      setVoiceStatus("Voice unavailable");
      return;
    }
    const recognition = recognitionRef.current;
    if (!recognition) return;

    if (voiceEnabled || listening) {
      setVoiceEnabled(false);
      setVoiceStatus("Stopping");
      recognition.stop();
      return;
    }

    setVoiceEnabled(true);
    setVoiceStatus("Starting");
  };

  const handleKey = (event: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      send(input);
    }
  };

  return (
    <section className="fixed bottom-4 right-4 z-40 w-[min(420px,calc(100vw-2rem))] rounded-lg border border-[#1f2937] bg-[#0d1117]/95 shadow-2xl backdrop-blur">
      <div className="flex items-center gap-2 border-b border-[#1f2937] px-3 py-2">
        <div className="flex h-7 w-7 items-center justify-center rounded-md bg-blue-600">
          <Bot size={14} className="text-white" />
        </div>
        <div className="min-w-0 flex-1">
          <div className="text-xs font-semibold text-white">Nexus live conversation</div>
          <div className="flex items-center gap-1.5 text-[10px] text-gray-500">
            <Mic size={10} className={cn(listening ? "text-green-400" : "text-gray-600")} />
            {voiceStatus}
          </div>
        </div>
        <button
          onClick={toggleVoice}
          disabled={!voiceAvailable}
          className={cn(
            "flex h-8 items-center gap-1.5 rounded-md px-2.5 text-xs font-medium transition-colors",
            listening || voiceEnabled
              ? "bg-red-600/20 text-red-300 hover:bg-red-600/30"
              : "bg-blue-600 text-white hover:bg-blue-500",
            !voiceAvailable && "cursor-not-allowed bg-gray-800 text-gray-600"
          )}
        >
          {listening || voiceEnabled ? <MicOff size={12} /> : <Mic size={12} />}
          {listening || voiceEnabled ? "Stop" : "Start"}
        </button>
        {loading && <Loader2 size={14} className="animate-spin text-blue-400" />}
      </div>

      <div className="max-h-56 overflow-y-auto px-3 py-2 space-y-2">
        {messages.slice(-5).map((message, index) => (
          <div key={index} className={cn("flex gap-2 text-xs", message.role === "user" ? "justify-end" : "justify-start")}>
            {message.role === "assistant" && <Bot size={13} className="mt-0.5 flex-shrink-0 text-blue-400" />}
            <div className={cn(
              "max-w-[86%] rounded-lg px-2.5 py-2 leading-relaxed",
              message.role === "user"
                ? "bg-blue-600 text-white"
                : "border border-[#1f2937] bg-[#111827] text-gray-300"
            )}>
              {message.content}
            </div>
            {message.role === "user" && <User size={13} className="mt-0.5 flex-shrink-0 text-gray-400" />}
          </div>
        ))}
        <div ref={bottomRef} />
      </div>

      <div className="border-t border-[#1f2937] px-3 py-2">
        <textarea
          value={input}
          onChange={(event) => setInput(event.target.value)}
          onKeyDown={handleKey}
          placeholder="Talk or type naturally..."
          rows={1}
          className="max-h-24 w-full resize-none rounded-md border border-[#253044] bg-[#111827] px-3 py-2 text-sm text-gray-100 outline-none placeholder:text-gray-600 focus:border-blue-500"
        />
      </div>
    </section>
  );
}
