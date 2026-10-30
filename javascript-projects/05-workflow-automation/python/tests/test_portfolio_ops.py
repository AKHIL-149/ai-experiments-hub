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


# ----------------------------------------------------------------------- alerts
# fixed_prices: AAPL 150 vs 145 (+3.45%, 10 shares = +$50), MSFT 190 vs 195 (-2.56%, 20 shares = -$100)

def alerts(tool, threshold, holdings=HOLDINGS, source="yahoo"):
    return tool.execute(operation="alerts", holdings=holdings, source=source, threshold=str(threshold))


def test_only_positions_that_moved_enough_are_alerted(tool, fixed_prices):
    out = alerts(tool, 3)
    assert out["success"] and out["count"] == 1 and out["symbols"] == "AAPL"
    assert out["summary"] == "1 of 2 positions moved at least 3%: AAPL +3.45%."
    lines = out["content"].splitlines()
    assert lines[0] == "symbol,direction,price,prev_close,day_change_pct,position_change,position_value"
    assert lines[1] == "AAPL,up,150.0,145.0,3.45,50.0,1500.0"


def test_alerts_catch_falls_as_well_as_rises_and_sort_by_size(tool, fixed_prices):
    out = alerts(tool, 2.5)
    assert out["count"] == 2 and out["symbols"] == "AAPL MSFT"           # 3.45% then 2.56%
    assert "AAPL +3.45%, MSFT -2.56%" in out["summary"]
    assert out["content"].splitlines()[2].startswith("MSFT,down,190.0,195.0,-2.56,-100.0,3800.0")
    assert "| AAPL | up |" in out["markdown"] and "| MSFT | down |" in out["markdown"] and "-$100.00" in out["markdown"]


def test_the_threshold_is_inclusive(tool, fixed_prices):
    assert alerts(tool, 3.45)["count"] == 1        # exactly equal counts
    assert alerts(tool, 3.46)["count"] == 0        # just above does not


def test_no_alert_says_so_and_names_the_largest_move(tool, fixed_prices):
    out = alerts(tool, 5)
    assert out["success"] and out["count"] == 0 and out["symbols"] == ""
    assert out["summary"] == "No alert: none of 2 positions moved at least 5% (largest move AAPL +3.45%)."
    assert out["content"].strip() == "symbol,direction,price,prev_close,day_change_pct,position_change,position_value"
    assert out["markdown"] == "(no positions moved that much)"


def test_alerts_report_the_whole_portfolio_move_and_the_check_time(tool, fixed_prices):
    out = alerts(tool, 3)
    assert out["portfolio_day_change_pct"] == -0.93 and out["as_of"] == "2026-10-30" and out["threshold"] == 3.0
    assert out["log_line"].split(",")[1:] == ["2026-10-30", "1", "AAPL", "3"]
    import re
    assert re.match(r"^\d{4}-\d\d-\d\d \d\d:\d\d,2026-10-30,1,AAPL,3$", out["log_line"])


def test_unpriced_symbols_are_left_out_and_reported(tool, fixed_prices):
    out = alerts(tool, 3, holdings=HOLDINGS + "ZZZZ9,5,10\n")
    assert out["success"] and out["count"] == 1 and "ZZZZ9" in out["notes"] and out["summary"].startswith("1 of 2 positions")


@pytest.mark.parametrize("threshold", ["abc", "0", "-1", "100.5", "", "nan", "inf", "3%"])
def test_threshold_must_be_a_number_above_0_and_up_to_100(tool, fixed_prices, threshold):
    out = alerts(tool, threshold)
    assert not out["success"] and "threshold must be a number above 0 and up to 100" in out["error"]


def test_a_missing_threshold_is_an_error_not_a_default(tool, fixed_prices):
    out = tool.execute(operation="alerts", holdings=HOLDINGS, source="yahoo")
    assert not out["success"] and "threshold" in out["error"]


def test_alerts_share_the_holdings_validation(tool, fixed_prices):
    assert "shares must be above 0" in alerts(tool, 3, holdings="symbol,shares,cost_basis\nAAPL,-1,1\n")["error"]
    assert "holdings is required" in tool.execute(operation="alerts", source="yahoo", threshold="3")["error"]
    assert "None of the holdings could be priced" in alerts(tool, 3, holdings="symbol,shares,cost_basis\nZZZZ9,1,1\n")["error"]


def test_alerts_are_ordered_by_size_of_move_not_by_the_order_in_the_file(tool, fixed_prices):
    reversed_file = "symbol,shares,cost_basis\nMSFT,20,200\nAAPL,10,100\n"      # smaller move listed first
    out = alerts(tool, 2.5, holdings=reversed_file)
    assert out["symbols"] == "AAPL MSFT" and out["summary"].index("AAPL") < out["summary"].index("MSFT")
