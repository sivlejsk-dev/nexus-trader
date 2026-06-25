"""Guided tutorial mode for Nexus."""
from __future__ import annotations

import re
from typing import Any, Dict, List

from app.nexus_core.memory_store import MemoryStore


TUTORIAL_STEPS: List[Dict[str, Any]] = [
    {
        "id": "voice",
        "title": "Ask Nexus by voice",
        "page": "/chat",
        "goal": "Use the microphone or chat box to ask one clear market question.",
        "example": "Analyze Toyota Japan",
        "why": "Voice is the fastest way to get a simple decision without hunting through pages.",
    },
    {
        "id": "console",
        "title": "Read the Nexus Decision",
        "page": "/console",
        "goal": "Open a symbol and start with the top decision card.",
        "example": "Open the console for AAPL and compare action, confidence, target, stop, and risk.",
        "why": "The decision card compresses technicals, participation, events, and learning into one answer.",
    },
    {
        "id": "what_if",
        "title": "Run a what-if",
        "page": "/chat",
        "goal": "Ask what happens if price reaches a target or stop.",
        "example": "What if AAPL calls go to 240 with a stop at 225?",
        "why": "What-if mode turns an idea into risk, reward, breakeven, and next-step logic.",
    },
    {
        "id": "simulate",
        "title": "Check history",
        "page": "/simulate",
        "goal": "Run a historical simulation before trusting a setup.",
        "example": "Simulate NVDA over the last 5 years",
        "why": "Simulation shows when Nexus-style signals worked and when they failed.",
    },
    {
        "id": "events",
        "title": "Check market events",
        "page": "/events",
        "goal": "Review news and external events that could change the trade.",
        "example": "What news could affect TSLA puts?",
        "why": "External events can invalidate clean technical setups or create volatility.",
    },
    {
        "id": "watchlist",
        "title": "Build a focused watchlist",
        "page": "/watchlist",
        "goal": "Track only the symbols you actually want Nexus to follow.",
        "example": "Add ASML.AS to my watchlist",
        "why": "A tighter watchlist makes Nexus context more useful and less noisy.",
    },
]


class TutorialModeService:
    """Manage step-by-step tutorial state in session memory."""

    def is_tutorial_request(self, message: str) -> bool:
        text = message.lower()
        return bool(re.search(r"\b(tutorial|teach me|walk me through|how do i use|guide me|show me how|next step)\b", text))

    async def build_response(self, message: str, memory: MemoryStore, app_context: Dict[str, Any] | None = None) -> Dict[str, Any]:
        current = int(await memory.get_preference("tutorial_step", 0) or 0)
        text = message.lower()
        if any(word in text for word in ("restart", "start over", "begin")):
            current = 0
        elif any(word in text for word in ("next", "continue", "done", "finished")):
            current = min(current + 1, len(TUTORIAL_STEPS) - 1)

        await memory.set_preference("tutorial_step", current)
        step = TUTORIAL_STEPS[current]
        complete_pct = round((current + 1) / len(TUTORIAL_STEPS) * 100)
        active_symbol = (app_context or {}).get("active_symbol")
        symbol_hint = f" Since you are focused on {active_symbol}, use that symbol for this step." if active_symbol else ""

        response = (
            f"Tutorial step {current + 1} of {len(TUTORIAL_STEPS)}: **{step['title']}**.\n\n"
            f"{step['goal']}{symbol_hint}\n\n"
            f"Try: `{step['example']}`\n\n"
            f"Why it matters: {step['why']}\n\n"
            "Say `next` when you finish, or ask Nexus to explain any part of this step."
        )
        voice = (
            f"Tutorial step {current + 1}: {step['title']}. "
            f"{step['goal']} Try saying: {step['example']}. "
            "Say next when you finish."
        )
        return {
            "active": True,
            "step_index": current,
            "total_steps": len(TUTORIAL_STEPS),
            "complete_pct": complete_pct,
            "step": step,
            "response": response,
            "voice_reasoning": voice,
            "app_command": {"type": "navigate", "path": step["page"], "label": step["title"]},
        }


tutorial_mode_service = TutorialModeService()
