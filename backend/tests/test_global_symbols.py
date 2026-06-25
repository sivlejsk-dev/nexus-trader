from app.nexus_core.conversation import extract_symbols
from app.services.symbol_resolver import extract_global_symbols, resolve_symbol


def test_resolves_common_global_company_aliases():
    assert resolve_symbol("Toyota", context="analyze Toyota Japan")["symbol"] == "7203.T"
    assert resolve_symbol("Samsung", context="check Samsung Korea")["symbol"] == "005930.KS"
    assert resolve_symbol("ASML", context="ASML Amsterdam")["symbol"] == "ASML.AS"


def test_preserves_explicit_yahoo_global_tickers():
    assert resolve_symbol("7203.T")["symbol"] == "7203.T"
    assert resolve_symbol("VOD.L")["symbol"] == "VOD.L"
    assert resolve_symbol("SHOP.TO")["symbol"] == "SHOP.TO"


def test_extracts_global_symbols_from_natural_language():
    assert extract_global_symbols("analyze Toyota Japan")[0] == "7203.T"
    assert extract_symbols("simulate Samsung Korea five years")[0] == "005930.KS"
