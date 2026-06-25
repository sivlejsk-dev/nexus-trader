from app.nexus_core.reasoning import reasoning_engine
from app.services.adaptive_predictions import adaptive_prediction_service
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


def test_participation_detects_buying_pressure():
    bars = [_bar(100, 106, 99, 105) for _ in range(20)]

    result = compute_market_participation("AAPL", bars)

    assert result["available"] is True
    assert result["pressure_label"] in {"buying", "heavy_buying"}
    assert result["outcome_impact"]["direction"] == "bullish"
    assert result["buy_volume_pct"] > result["sell_volume_pct"]
    assert result["pressure_score"] > 0.12


def test_participation_detects_selling_pressure():
    bars = [_bar(105, 106, 99, 100) for _ in range(20)]

    result = compute_market_participation("AAPL", bars)

    assert result["available"] is True
    assert result["pressure_label"] in {"selling", "heavy_selling"}
    assert result["outcome_impact"]["direction"] == "bearish"
    assert result["sell_volume_pct"] > result["buy_volume_pct"]
    assert result["pressure_score"] < -0.12


def test_reasoning_uses_participation_as_directional_signal():
    participation = compute_market_participation(
        "AAPL",
        [_bar(100, 106, 99, 105) for _ in range(20)],
    )

    result = reasoning_engine.analyze_technicals({
        "price": 105,
        "participation": participation,
    })

    assert "bullish_participation" in result.supporting_data["signals"]
    assert any("buy-side participation" in step.description for step in result.steps)
    assert result.conclusion.startswith("Bullish bias")


def test_adaptive_prediction_scores_participation():
    participation = compute_market_participation(
        "AAPL",
        [_bar(100, 106, 99, 105) for _ in range(20)],
    )

    prediction = adaptive_prediction_service._score_current_setup(
        quote={"price": 105},
        technicals={},
        patterns={},
        participation=participation,
    )

    assert prediction["direction"] == "call"
    assert prediction["raw_scores"]["bullish"] > prediction["raw_scores"]["bearish"]
    assert any("buy-side participation" in item for item in prediction["rationale"])
