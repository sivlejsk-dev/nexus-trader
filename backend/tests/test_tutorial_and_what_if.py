import pytest

from app.nexus_core.conversation import classify_intent, extract_symbols
from app.nexus_core.memory_store import get_memory_store
from app.services.tutorial_mode import tutorial_mode_service
from app.services.what_if import what_if_service


def test_tutorial_intent_has_priority_over_general_education():
    assert classify_intent("teach me how to use Nexus") == "tutorial"
    assert classify_intent("start tutorial mode") == "tutorial"


def test_what_if_intent_detects_scenario_language():
    assert classify_intent("what if AAPL goes to 240 with a stop at 225") == "what_if"
    assert what_if_service.is_what_if_request("risk reward if it hits 240")
    assert extract_symbols("what if AAPL goes to 240 with a stop at 225") == ["AAPL"]
    assert extract_symbols("start tutorial mode") == []


def test_what_if_simulates_basic_call_risk_reward():
    scenario = what_if_service.parse_request(
        "what if AAPL goes to 240 with a stop at 225 on 100 shares",
        quote={"price": 230},
        decision={"direction": "put"},
    )
    result = what_if_service.simulate("AAPL", scenario)

    assert result["available"] is True
    assert result["direction"] == "call"
    assert result["target_price"] == 240
    assert result["stop_price"] == 225
    assert result["reward_pct"] > 0
    assert result["risk_pct"] > 0
    assert result["risk_reward"] is not None


def test_what_if_simulates_put_direction():
    result = what_if_service.simulate(
        "AAPL",
        {
            "direction": "put",
            "current_price": 230,
            "target_price": 215,
            "stop_price": 238,
            "position_size": 100,
        },
    )

    assert result["direction"] == "put"
    assert result["reward_pct"] > 0
    assert result["risk_pct"] > 0
    assert "put" in result["summary"]


@pytest.mark.asyncio
async def test_tutorial_mode_advances_session_step():
    memory = get_memory_store("test_tutorial_mode_advances_session_step")
    await memory.clear_turns()
    await memory.set_preference("tutorial_step", 0)

    first = await tutorial_mode_service.build_response("start tutorial", memory, {})
    second = await tutorial_mode_service.build_response("next", memory, {})

    assert first["step_index"] == 0
    assert second["step_index"] == 1
    assert second["app_command"]["type"] == "navigate"
