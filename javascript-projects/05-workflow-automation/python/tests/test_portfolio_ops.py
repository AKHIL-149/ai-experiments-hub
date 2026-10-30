"""Run from the project root: python3 -m pytest python/tests -q"""
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest

from tools import portfolio_ops
from tools.market_data import simulated_base_price
from tools.portfolio_ops import PortfolioOpsTool, UNIVERSE, SHARE_LOTS, read_history
from tool_registry import ToolRegistry


def q(symbol, price, prev, as_of="2026-10-30"):
    change = round(price - prev, 2)
    return {"symbol": symbol, "price": price, "prev_close": prev, "change": change,
            "change_pct": round(change / prev * 100, 2), "currency": "USD", "as_of": as_of, "source": "yahoo"}


@pytest.fixture
def tool():
    return PortfolioOpsTool()


@pytest.fixture
def fixed_prices(monkeypatch):
    prices = {"AAPL": q("AAPL", 150.0, 145.0), "MSFT": q("MSFT", 190.0, 195.0)}

    def fake(symbols, source):
        got = [prices[s] for s in symbols if s in prices]
        return got, [{"symbol": s, "error": "symbol not found"} for s in symbols if s not in prices]

    monkeypatch.setattr(portfolio_ops, "get_quotes", fake)
    return prices


HOLDINGS = "symbol,shares,cost_basis\nAAPL,10,100\nMSFT,20,200\n"


def test_registered():
    assert "portfolio_operations" in ToolRegistry().list_tools()


def test_value_matches_hand_calculation(tool, fixed_prices):
    out = tool.execute(operation="value", holdings=HOLDINGS, source="yahoo")
    assert out["success"]
    # AAPL: 10 x 150 = 1500 vs cost 1000 (+500), day +50.  MSFT: 20 x 190 = 3800 vs cost 4000 (-200), day -100
    assert out["total_value"] == 5300.00 and out["total_cost"] == 5000.00
    assert out["total_gain"] == 300.00 and out["total_gain_pct"] == 6.00
    assert out["day_change"] == -50.00 and out["day_change_pct"] == -0.93  # -50 / (5300 + 50)
    assert out["positions"] == 2 and out["as_of"] == "2026-10-30"
    assert out["largest_move_symbol"] == "AAPL" and out["largest_move_pct"] == 3.45 and out["largest_move_abs_pct"] == 3.45
    assert out["largest_position_symbol"] == "MSFT" and out["largest_position_weight_pct"] == 71.7   # 3800 of 5300
    rows = {r.split(",")[0]: r.split(",") for r in out["content"].splitlines()[1:]}
    assert rows["AAPL"][4:8] == ["1500.0", "1000.0", "500.0", "50.0"]
    assert rows["MSFT"][4:8] == ["3800.0", "4000.0", "-200.0", "-5.0"]
    assert rows["AAPL"][10] == "28.3" and rows["MSFT"][10] == "71.7"          # weights add to 100
    assert out["history_row"] == "2026-10-30,5300.00,5000.00,-50.00,2"


def test_value_text_is_formatted_for_reading(tool, fixed_prices):
    out = tool.execute(operation="value", holdings=HOLDINGS, source="yahoo")
    assert "**Total value:** $5,300.00 (2 positions)" in out["totals_text"]
    assert "**Largest position:** MSFT (71.7% of the portfolio)" in out["totals_text"]
    assert "**Today:** -$50.00 (-0.93%)" in out["totals_text"]          # the sign goes before the $, never "$-50.00"
    assert "$-" not in out["totals_text"] + out["markdown"]
    assert "**Total gain/loss:** +$300.00 (+6.00%)" in out["totals_text"]
    first_row = out["markdown"].splitlines()[2]
    assert first_row.startswith("| MSFT |")  # biggest position first
    assert "-$200.00" in out["markdown"] and "+$500.00" in out["markdown"] and "71.7%" in out["markdown"]
    assert "positions worth $5,300.00" in out["summary"]


def test_value_merges_repeated_symbols_with_a_weighted_cost(tool, fixed_prices):
    out = tool.execute(operation="value", holdings="symbol,shares,cost_basis\nAAPL,10,100\nAAPL,30,140\n", source="yahoo")
    assert out["positions"] == 1
    # 40 shares, average cost (10*100 + 30*140) / 40 = 130 -> cost 5200, value 6000
    assert out["total_cost"] == 5200.00 and out["total_value"] == 6000.00


def test_value_leaves_out_unpriced_symbols_and_says_so(tool, fixed_prices):
    out = tool.execute(operation="value", holdings=HOLDINGS + "ZZZZ,5,10\n", source="yahoo")
    assert out["success"] and out["positions"] == 2 and out["unpriced"] == ["ZZZZ"]
    assert out["total_value"] == 5300.00 and "ZZZZ" in out["notes"]


def test_value_fails_when_nothing_can_be_priced(tool, fixed_prices):
    out = tool.execute(operation="value", holdings="symbol,shares,cost_basis\nZZZZ,5,10\n", source="yahoo")
    assert not out["success"] and "ZZZZ: symbol not found" in out["error"]


@pytest.mark.parametrize("csv_text, message", [
    ("symbol,shares\nAAPL,10\n", "missing: cost_basis"),
    ("symbol,shares,cost_basis\nAAPL,ten,100\n", "shares 'ten' is not a number"),
    ("symbol,shares,cost_basis\nAAPL,0,100\n", "shares must be above 0"),
    ("symbol,shares,cost_basis\nAAPL,-5,100\n", "shares must be above 0"),
    ("symbol,shares,cost_basis\nAAPL,5,-1\n", "cost_basis cannot be negative"),
    ("symbol,shares,cost_basis\nA;B,5,1\n", "not a valid ticker"),
    ("symbol,shares,cost_basis\nAAPL MSFT,5,1\n", "exactly one ticker"),
    ("symbol,shares,cost_basis\nAAPL,MSFT,5,1\n", "is not a number"),
    ("symbol,shares,cost_basis\n", "no holdings"),
    ("   \n", "empty"),
])
def test_value_rejects_bad_holdings(tool, fixed_prices, csv_text, message):
    out = tool.execute(operation="value", holdings=csv_text, source="yahoo")
    assert not out["success"] and message in out["error"]


def test_value_accepts_dollar_signs_and_any_column_case(tool, fixed_prices):
    out = tool.execute(operation="value", holdings="Symbol,Shares,Cost_Basis\nAAPL,10,$100.00\n", source="yahoo")
    assert out["success"] and out["total_cost"] == 1000.00


def test_value_needs_holdings_and_a_known_source(tool, fixed_prices):
    assert "holdings is required" in tool.execute(operation="value", source="yahoo")["error"]
    assert "source must be one of" in tool.execute(operation="value", holdings=HOLDINGS, source="bloomberg")["error"]


def test_generate_is_deterministic_for_a_seed_and_differs_between_seeds(tool):
    a = tool.execute(operation="generate", count="6", seed="42", source="simulated")
    b = tool.execute(operation="generate", count="6", seed="42", source="simulated")
    c = tool.execute(operation="generate", count="6", seed="43", source="simulated")
    assert a["success"] and a["content"] == b["content"] and a["content"] != c["content"]
    assert a["rows"] == 6 and a["seed"] == 42
    assert "made-up" in a["summary"] and "not real investments" in a["summary"]


def test_generate_makes_valid_distinct_holdings_priced_near_the_market(tool):
    out = tool.execute(operation="generate", count="12", seed="7", source="simulated")
    lines = out["content"].splitlines()
    assert lines[0] == "symbol,shares,cost_basis"
    symbols = [l.split(",")[0] for l in lines[1:]]
    assert len(set(symbols)) == 12 and set(symbols) <= set(UNIVERSE)
    from tools.market_data import simulated_quote
    for line in lines[1:]:
        symbol, shares, cost = line.split(",")
        assert int(shares) in SHARE_LOTS
        price = simulated_quote(symbol)["price"]
        assert 0.69 * price <= float(cost) <= 1.31 * price


def test_a_generated_portfolio_can_be_valued_straight_away(tool):
    sample = tool.execute(operation="generate", count="5", seed="1", source="simulated")
    valued = tool.execute(operation="value", holdings=sample["content"], source="simulated")
    assert valued["success"] and valued["positions"] == 5 and valued["total_value"] > 0


@pytest.mark.parametrize("count, seed, message", [
    ("0", "1", "between 1 and 25"), ("26", "1", "between 1 and 25"), ("many", "1", "count must be a whole number"),
    ("5", "abc", "seed must be a whole number"), ("5", "", "seed must be a whole number"), ("2.5", "1", "count must be a whole number"),
])
def test_generate_rejects_bad_arguments(tool, count, seed, message):
    out = tool.execute(operation="generate", count=count, seed=seed, source="simulated")
    assert not out["success"] and message in out["error"]


def test_generate_keeps_going_when_a_symbol_has_no_price(tool, monkeypatch):
    real = portfolio_ops.get_quotes
    monkeypatch.setattr(portfolio_ops, "get_quotes",
                        lambda symbols, source: ([x for x in real(symbols, source)[0] if x["symbol"] != symbols[0]],
                                                 [{"symbol": symbols[0], "error": "gone"}]))
    out = tool.execute(operation="generate", count="4", seed="3", source="simulated")
    assert out["success"] and out["rows"] == 3 and "1 skipped" in out["summary"]


HISTORY = ("date,total_value,total_cost,day_change,positions\n"
           "2026-10-27,10000.00,9000.00,0.00,3\n"
           "2026-10-28,10250.00,9000.00,250.00,3\n"
           "2026-10-29,10100.00,9000.00,-150.00,3\n")


def test_trend_summarises_the_period_exactly(tool):
    out = tool.execute(operation="trend", history=HISTORY)
    assert out["success"] and out["days"] == 3 and out["rows"] == 3
    assert out["first_date"] == "2026-10-27" and out["last_date"] == "2026-10-29"
    assert out["change"] == 100.00 and out["change_pct"] == 1.00
    assert "$10,000.00 to $10,100.00" in out["summary"] and "+$100.00, +1.00%" in out["summary"]
    assert "Best day 2026-10-28 +$250.00" in out["summary"] and "worst day 2026-10-29 -$150.00" in out["summary"]
    assert out["markdown"].splitlines()[2] == "| 2026-10-27 | $10,000.00 | +$0.00 |"


def test_trend_with_one_day_says_so(tool):
    out = tool.execute(operation="trend", history="2026-10-30,5300.00,5000.00,-50.00,2\n")
    assert out["success"] and out["days"] == 1 and "Only one day tracked" in out["summary"] and out["change"] == 0


def test_trend_keeps_the_last_entry_per_day_and_orders_by_date(tool):
    text = "2026-10-29,200,0,0,1\n2026-10-28,100,0,0,1\n2026-10-29,300,0,5,1\n"
    entries = read_history(text)
    assert [(e[0], e[1]) for e in entries] == [(date(2026, 10, 28), 100.0), (date(2026, 10, 29), 300.0)]


def test_trend_ignores_damaged_lines_but_needs_at_least_one_good_one(tool):
    out = tool.execute(operation="trend", history="garbage\n2026-10-28,100,90,1,2\nnot-a-date,1,2,3,4\n2026-10-29,x,y,z,w\n")
    assert out["success"] and out["days"] == 1
    assert "no readable rows" in tool.execute(operation="trend", history="nothing useful")["error"]
    assert "no readable rows" in tool.execute(operation="trend")["error"]


def test_unknown_operation(tool):
    assert "Unknown operation" in tool.execute(operation="trade")["error"]
