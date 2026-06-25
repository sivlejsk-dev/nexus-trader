from app.services.decision_engine import nexus_decision_engine
from app.services.market_data import compute_market_participation


def _bar(open_, high, low, close, volume=1_000_000):
    return {
        "date": "2026-01-01",
        "open": open_,
        "high": high,
        "low": low,
        "close": close,
        "volume": volume,
    }


def _prediction(direction="call", confidence=0.72):
    return {
        "prediction": {
            "direction": direction,
            "confidence": confidence,
            "entry_price": 100,
            "target_price": 108 if direction == "call" else 92,
            "stop_loss": 96 if direction == "call" else 104,
            "rationale": ["Momentum and trend confirm the thesis."],
            "risks": [],
        }
    }


def test_decision_engine_returns_buy_for_confirmed_call_setup():
    participation = compute_market_participation(
        "AAPL",
        [_bar(100, 106, 99, 105) for _ in range(20)],
    )
    decision = nexus_decision_engine.build_decision({
        "symbol": "AAPL",
        "quote": {"price": 100},
        "adaptive_prediction": _prediction("call", 0.72),
        "participation": participation,
        "patterns": {"summary": {"bias": "bullish"}},
        "reasoning": {"confidence": 0.7},
    })

    assert decision["action"] == "buy"
    assert decision["direction"] == "call"
    assert decision["confidence"] >= 0.67
    assert decision["target"] == 108
    assert "Next" not in decision["reason"]


def test_decision_engine_waits_on_neutral_prediction():
    decision = nexus_decision_engine.build_decision({
        "symbol": "AAPL",
        "quote": {"price": 100},
        "adaptive_prediction": _prediction("neutral", 0.42),
        "patterns": {"summary": {"bias": "neutral"}},
    })

    assert decision["action"] == "wait"
    assert decision["direction"] == "neutral"
    assert "clean entry" in decision["reason"]


def test_decision_engine_avoids_when_major_signals_conflict():
    participation = compute_market_participation(
        "AAPL",
        [_bar(105, 106, 99, 100) for _ in range(20)],
    )
    decision = nexus_decision_engine.build_decision({
        "symbol": "AAPL",
        "quote": {"price": 100},
        "adaptive_prediction": _prediction("call", 0.74),
        "participation": participation,
        "patterns": {"summary": {"bias": "bearish"}},
        "event_intelligence": {"composite": {"bias": "bearish", "confidence": 0.7}},
    })

    assert decision["action"] == "avoid"
    assert decision["contradictions"] >= 2
    assert "conflict" in decision["risk"].lower() or decision["warnings"]


def test_decision_engine_preserves_global_symbol():
    decision = nexus_decision_engine.build_decision({
        "symbol": "7203.T",
        "quote": {"price": 3000},
        "adaptive_prediction": _prediction("call", 0.68),
        "patterns": {"summary": {"bias": "bullish"}},
    })

    assert decision["symbol"] == "7203.T"
    assert decision["action"] == "buy"
