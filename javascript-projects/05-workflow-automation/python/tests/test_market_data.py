"""Run from the project root: python3 -m pytest python/tests -q"""
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest

from tools import market_data
from tools.market_data import MarketDataTool, QuoteError, parse_symbols, simulated_quote
from tool_registry import ToolRegistry


def chart(closes, price=None, currency="USD", error=None, ts=1793304001):
    if error:
        return {"chart": {"result": None, "error": {"description": error}}}
    return {"chart": {"result": [{
        "meta": {"regularMarketPrice": price if price is not None else closes[-1], "currency": currency, "regularMarketTime": ts},
        "timestamp": list(range(len(closes))),
        "indicators": {"quote": [{"close": closes}]},
    }], "error": None}}


@pytest.fixture
def fake_yahoo(monkeypatch):
    calls = []
    responses = {}

    def fetch(url):
        calls.append(url)
        symbol = url.split("/chart/")[1].split("?")[0]
        reply = responses.get(symbol)
        if isinstance(reply, Exception):
            raise reply
        return reply

    monkeypatch.setattr(market_data, "fetch_json", fetch)
    fetch.calls, fetch.responses = calls, responses
    return fetch


def test_registered():
    assert "market_data" in ToolRegistry().list_tools()


def test_parse_symbols_cleans_and_dedupes():
    assert parse_symbols(" aapl, msft ,AAPL,nvda  brk-b ") == ["AAPL", "MSFT", "NVDA", "BRK-B"]
    assert parse_symbols("^GSPC,BTC-USD,EURUSD=X") == ["^GSPC", "BTC-USD", "EURUSD=X"]


@pytest.mark.parametrize("bad", ["", "  ", ",,", "AAPL;rm", "AAPL|MSFT", "A/B", "AAPL?x=1", "$AAPL", "TOOLONGSYMBOLXX", "a b!"])
def test_parse_symbols_rejects_bad_input(bad):
    with pytest.raises(ValueError):
        parse_symbols(bad)


def test_parse_symbols_limits_the_count():
    assert len(parse_symbols(",".join(f"S{i}" for i in range(25)))) == 25
    with pytest.raises(ValueError, match="At most 25"):
        parse_symbols(",".join(f"S{i}" for i in range(26)))


def test_simulated_prices_are_stable_within_a_day_and_arithmetic_is_consistent():
    day = date(2026, 10, 30)
    a, b = simulated_quote("AAPL", day), simulated_quote("AAPL", day)
    assert a == b and a["source"] == "simulated" and a["as_of"] == "2026-10-30"
    assert a["change"] == round(a["price"] - a["prev_close"], 2)
    assert a["change_pct"] == pytest.approx(a["change"] / a["prev_close"] * 100, abs=0.01)
    assert 15 < a["price"] < 700
    assert simulated_quote("MSFT", day)["price"] != a["price"]


def test_simulated_yesterdays_close_is_the_previous_day_price():
    today = date(2026, 10, 30)
    assert simulated_quote("NVDA", today)["prev_close"] == simulated_quote("NVDA", today - timedelta(days=1))["price"]


def test_simulated_tool_run_returns_csv_and_summary():
    out = MarketDataTool().execute(symbols="aapl,msft,nvda", source="simulated")
    assert out["success"] and out["rows"] == 3 and out["source"] == "simulated"
    lines = out["content"].splitlines()
    assert lines[0] == "symbol,price,prev_close,change,change_pct,currency,as_of,source"
    assert [l.split(",")[0] for l in lines[1:]] == ["AAPL", "MSFT", "NVDA"]
    assert out["up"] + out["down"] <= 3 and out["notes"] == "All symbols priced." and out["failed"] == []
    assert "3 priced" in out["summary"]


def test_yahoo_uses_the_latest_price_and_the_previous_sessions_close(fake_yahoo):
    fake_yahoo.responses["AAPL"] = chart([100.0, 102.0, 101.0, 110.0], price=111.5)
    out = MarketDataTool().execute(symbols="AAPL", source="yahoo")
    row = out["content"].splitlines()[1].split(",")
    assert row[:5] == ["AAPL", "111.5", "101.0", "10.5", "10.4"] and row[7] == "yahoo"
    assert row[6] == "2026-10-29"  # as_of from the market timestamp, in UTC


def test_yahoo_skips_null_closes_and_falls_back_to_the_last_close(fake_yahoo):
    resp = chart([50.0, 52.0, None], price=None)
    resp["chart"]["result"][0]["meta"].pop("regularMarketPrice")
    fake_yahoo.responses["X"] = resp
    quote = market_data.yahoo_quote("X")
    assert quote["price"] == 52.0 and quote["prev_close"] == 50.0


def test_yahoo_single_bar_has_zero_change(fake_yahoo):
    fake_yahoo.responses["NEW"] = chart([20.0])
    assert market_data.yahoo_quote("NEW")["change"] == 0.0


def test_symbols_are_url_encoded(fake_yahoo):
    fake_yahoo.responses["^GSPC"] = chart([1.0, 2.0])
    MarketDataTool().execute(symbols="^GSPC", source="yahoo")
    assert "/chart/%5EGSPC?" in fake_yahoo.calls[0]


def test_one_failed_symbol_does_not_sink_the_rest(fake_yahoo):
    fake_yahoo.responses["AAPL"] = chart([1.0, 2.0])
    fake_yahoo.responses["ZZZZ"] = chart(None, error="No data found, symbol may be delisted")
    out = MarketDataTool().execute(symbols="AAPL,ZZZZ", source="yahoo")
    assert out["success"] and out["rows"] == 1
    assert out["failed"] == [{"symbol": "ZZZZ", "error": "No data found, symbol may be delisted"}]
    assert "Could not price: ZZZZ" in out["notes"]


def test_all_symbols_failing_is_an_error_naming_the_reasons(fake_yahoo):
    fake_yahoo.responses["A"] = QuoteError("symbol not found")
    out = MarketDataTool().execute(symbols="A", source="yahoo")
    assert not out["success"] and "A: symbol not found" in out["error"]


def test_bad_source_and_symbols_are_reported(fake_yahoo):
    assert "source must be one of" in MarketDataTool().execute(symbols="AAPL", source="bloomberg")["error"]
    assert "not a valid ticker" in MarketDataTool().execute(symbols="AAPL;DROP", source="simulated")["error"]


def test_network_failure_is_a_readable_error(monkeypatch):
    import urllib.error

    def boom(*a, **k):
        raise urllib.error.URLError("no route to host")

    monkeypatch.setattr(market_data.urllib.request, "urlopen", boom)
    out = MarketDataTool().execute(symbols="AAPL", source="yahoo")
    assert not out["success"] and "market data request failed" in out["error"]


def test_a_404_means_symbol_not_found_without_retrying(monkeypatch):
    import urllib.error
    attempts = []

    def not_found(*a, **k):
        attempts.append(1)
        raise urllib.error.HTTPError("u", 404, "nf", {}, None)

    monkeypatch.setattr(market_data.urllib.request, "urlopen", not_found)
    with pytest.raises(QuoteError, match="symbol not found"):
        market_data.fetch_json("https://example.invalid")
    assert len(attempts) == 1
