"""Portfolio maths for workflows: sample portfolios, valuation and a value history.

All numbers are computed here, never by the AI. The tool only reads prices; it does not trade,
and it gives no advice. Holdings are CSV text with the columns symbol, shares, cost_basis
(cost_basis = the price paid per share).
"""

import csv
import io
import random
from datetime import date, datetime, timezone
from typing import Any, Dict, List, Tuple
from .base_tool import BaseTool
from .csv_ops import parse_csv
from .market_data import SOURCES, get_quotes, parse_symbols

# Large, well-known US companies: a universe for random sample portfolios (not a recommendation)
UNIVERSE = [
    "AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "META", "TSLA", "BRK-B", "JPM", "V",
    "JNJ", "WMT", "PG", "XOM", "UNH", "MA", "HD", "KO", "PEP", "COST",
    "DIS", "NFLX", "ADBE", "CRM", "INTC", "AMD", "CSCO", "ORCL", "NKE", "MCD",
    "BAC", "PFE", "T", "VZ", "ABBV", "MRK", "CVX", "LLY", "AVGO", "TXN",
]
SHARE_LOTS = [5, 10, 15, 20, 25, 40, 50, 75, 100, 150]
MAX_HOLDINGS = 25


def money(value: float) -> str:
    return f"-${abs(value):,.2f}" if value < 0 else f"${value:,.2f}"


def signed_money(value: float) -> str:
    return f"{'+' if value >= 0 else '-'}${abs(value):,.2f}"


def pct(value: float) -> str:
    return f"{value:+.2f}%"


def _markdown(header: List[str], rows: List[List[str]]) -> str:
    lines = ["| " + " | ".join(header) + " |", "| " + " | ".join("---" for _ in header) + " |"]
    return "\n".join(lines + ["| " + " | ".join(r) + " |" for r in rows])


def _to_csv(fields: List[str], rows: List[Dict[str, Any]]) -> str:
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=fields, lineterminator="\n", extrasaction="ignore")
    writer.writeheader()
    writer.writerows(rows)
    return buffer.getvalue()


def _number(text: Any, what: str, row: int) -> float:
    try:
        return float(str(text).strip().replace("$", ""))
    except ValueError:
        raise ValueError(f"Holding {row}: {what} '{text}' is not a number")


def read_holdings(text: str) -> List[Dict[str, Any]]:
    """Validated holdings, with repeated symbols merged (shares added, cost averaged)."""
    header, rows, _ = parse_csv(text)
    lookup = {h.strip().lower(): h for h in header}
    missing = [c for c in ("symbol", "shares", "cost_basis") if c not in lookup]
    if missing:
        raise ValueError(f"Holdings need the columns symbol, shares, cost_basis (missing: {', '.join(missing)}; found: {', '.join(header)})")
    if not rows:
        raise ValueError("The portfolio has no holdings")

    merged: Dict[str, Dict[str, float]] = {}
    for i, row in enumerate(rows, start=1):
        symbols = parse_symbols(row[lookup["symbol"]])
        if len(symbols) != 1:
            raise ValueError(f"Holding {i}: the symbol cell must hold exactly one ticker, not '{row[lookup['symbol']]}'")
        symbol = symbols[0]
        shares = _number(row[lookup["shares"]], "shares", i)
        cost = _number(row[lookup["cost_basis"]], "cost_basis", i)
        if shares <= 0:
            raise ValueError(f"Holding {i} ({symbol}): shares must be above 0")
        if cost < 0:
            raise ValueError(f"Holding {i} ({symbol}): cost_basis cannot be negative")
        if symbol in merged:
            held = merged[symbol]
            total = held["shares"] + shares
            held["cost_basis"] = (held["cost_basis"] * held["shares"] + cost * shares) / total
            held["shares"] = total
        else:
            merged[symbol] = {"shares": shares, "cost_basis": cost}
    return [{"symbol": s, **v} for s, v in merged.items()]


def _format_shares(shares: float) -> str:
    return f"{shares:g}"


def generate_holdings(count: Any, seed: Any, source: str) -> Dict[str, Any]:
    try:
        n = int(str(count).strip())
    except ValueError:
        raise ValueError("count must be a whole number")
    if not 1 <= n <= MAX_HOLDINGS:
        raise ValueError(f"count must be between 1 and {MAX_HOLDINGS}")
    try:
        seed_number = int(str(seed).strip())
    except ValueError:
        raise ValueError("seed must be a whole number (the same seed gives the same portfolio)")

    rng = random.Random(seed_number)
    chosen = rng.sample(UNIVERSE, n)
    quotes, failed = get_quotes(chosen, source)
    if not quotes:
        raise ValueError("Could not price any of the chosen symbols, so no cost basis can be set")
    price = {q["symbol"]: q["price"] for q in quotes}

    holdings = []
    for symbol in chosen:
        if symbol not in price:
            continue
        shares = rng.choice(SHARE_LOTS)
        cost = round(price[symbol] * rng.uniform(0.7, 1.3), 2)  # bought somewhat above or below today's price
        holdings.append({"symbol": symbol, "shares": shares, "cost_basis": f"{cost:.2f}"})

    md = _markdown(["Symbol", "Shares", "Cost basis"],
                   [[h["symbol"], _format_shares(h["shares"]), money(float(h["cost_basis"]))] for h in holdings])
    skipped = f" ({len(failed)} skipped: no price)" if failed else ""
    return {
        "success": True, "operation": "generate",
        "content": _to_csv(["symbol", "shares", "cost_basis"], holdings), "markdown": md,
        "rows": len(holdings), "seed": seed_number, "source": source,
        "summary": f"Generated {len(holdings)} made-up holdings{skipped} with seed {seed_number} (cost basis set around {source} prices). "
                   "These are sample positions, not real investments.",
    }


def compute_positions(holdings_text: str, source: str):
    """Priced positions (value, gain/loss, day change per holding), the quotes used, and the symbols that failed."""
    holdings = read_holdings(holdings_text)
    quotes, failed = get_quotes([h["symbol"] for h in holdings], source)
    quote = {q["symbol"]: q for q in quotes}

    rows: List[Dict[str, Any]] = []
    for h in holdings:
        q = quote.get(h["symbol"])
        if not q:
            continue
        value = h["shares"] * q["price"]
        cost = h["shares"] * h["cost_basis"]
        day = h["shares"] * q["change"]
        rows.append({
            "symbol": h["symbol"], "shares": h["shares"], "cost_basis": round(h["cost_basis"], 2), "price": q["price"],
            "prev_close": q["prev_close"],
            "market_value": round(value, 2), "cost_value": round(cost, 2),
            "gain_loss": round(value - cost, 2), "gain_loss_pct": round((value - cost) / cost * 100, 2) if cost else 0.0,
            "day_change": round(day, 2), "day_change_pct": q["change_pct"],
        })
    if not rows:
        detail = "; ".join(f"{f['symbol']}: {f['error']}" for f in failed)
        raise ValueError(f"None of the holdings could be priced ({detail})")
    return rows, quotes, failed


def value_holdings(holdings_text: str, source: str) -> Dict[str, Any]:
    rows, quotes, failed = compute_positions(holdings_text, source)

    total_value = sum(r["market_value"] for r in rows)
    total_cost = sum(r["cost_value"] for r in rows)
    day_change = sum(r["day_change"] for r in rows)
    prev_value = total_value - day_change
    for r in rows:
        r["weight_pct"] = round(r["market_value"] / total_value * 100, 2) if total_value else 0.0

    biggest = max(rows, key=lambda r: r["market_value"])
    mover = max(rows, key=lambda r: abs(r["day_change_pct"]))
    best = max(rows, key=lambda r: r["gain_loss_pct"])
    worst = min(rows, key=lambda r: r["gain_loss_pct"])
    total_gain = total_value - total_cost
    total_gain_pct = total_gain / total_cost * 100 if total_cost else 0.0
    day_pct = day_change / prev_value * 100 if prev_value else 0.0
    as_of = max(q["as_of"] for q in quotes)

    fields = ["symbol", "shares", "cost_basis", "price", "market_value", "cost_value", "gain_loss",
              "gain_loss_pct", "day_change", "day_change_pct", "weight_pct"]
    markdown = _markdown(
        ["Symbol", "Shares", "Price", "Value", "Gain/Loss", "Gain %", "Day", "Day %", "Weight"],
        [[r["symbol"], _format_shares(r["shares"]), money(r["price"]), money(r["market_value"]),
          signed_money(r["gain_loss"]), pct(r["gain_loss_pct"]), signed_money(r["day_change"]),
          pct(r["day_change_pct"]), f"{r['weight_pct']:.1f}%"] for r in sorted(rows, key=lambda r: -r["market_value"])]
    )
    totals_text = "\n".join([
        f"- **Total value:** {money(total_value)} ({len(rows)} positions)",
        f"- **Total cost:** {money(total_cost)}",
        f"- **Total gain/loss:** {signed_money(total_gain)} ({pct(total_gain_pct)})",
        f"- **Largest position:** {biggest['symbol']} ({biggest['weight_pct']:.1f}% of the portfolio)",
        f"- **Today:** {signed_money(day_change)} ({pct(day_pct)})",
        f"- **Largest move today:** {mover['symbol']} {pct(mover['day_change_pct'])}",
        f"- **Best / worst vs cost:** {best['symbol']} {pct(best['gain_loss_pct'])} / {worst['symbol']} {pct(worst['gain_loss_pct'])}",
    ])
    unpriced = [f["symbol"] for f in failed]
    return {
        "success": True, "operation": "value", "source": source, "as_of": as_of,
        "content": _to_csv(fields, rows), "markdown": markdown, "totals_text": totals_text,
        "positions": len(rows), "rows": len(rows),
        "total_value": round(total_value, 2), "total_cost": round(total_cost, 2),
        "total_gain": round(total_gain, 2), "total_gain_pct": round(total_gain_pct, 2),
        "day_change": round(day_change, 2), "day_change_pct": round(day_pct, 2),
        "largest_position_symbol": biggest["symbol"], "largest_position_weight_pct": biggest["weight_pct"],
        "largest_move_symbol": mover["symbol"], "largest_move_pct": mover["day_change_pct"],
        "largest_move_abs_pct": abs(mover["day_change_pct"]),
        "unpriced": unpriced,
        "notes": "All positions priced." if not unpriced else "Not priced (left out of the totals): " + ", ".join(unpriced),
        "summary": f"{len(rows)} positions worth {money(total_value)}; {signed_money(day_change)} ({pct(day_pct)}) today; "
                   f"{signed_money(total_gain)} ({pct(total_gain_pct)}) versus cost.",
        "history_row": f"{as_of},{total_value:.2f},{total_cost:.2f},{day_change:.2f},{len(rows)}",
    }


def parse_threshold(value: Any) -> float:
    try:
        threshold = float(str(value).strip())
    except (TypeError, ValueError):
        threshold = float("nan")
    if not 0 < threshold <= 100:  # also rejects nan and inf
        raise ValueError("threshold must be a number above 0 and up to 100 (a percent, e.g. 3)")
    return threshold


def check_moves(holdings_text: str, source: str, threshold_value: Any) -> Dict[str, Any]:
    """Which positions moved at least `threshold` percent today, in either direction."""
    threshold = parse_threshold(threshold_value)
    rows, quotes, failed = compute_positions(holdings_text, source)

    hits = sorted((r for r in rows if abs(r["day_change_pct"]) >= threshold), key=lambda r: -abs(r["day_change_pct"]))
    fields = ["symbol", "direction", "price", "prev_close", "day_change_pct", "position_change", "position_value"]
    alert_rows = [{
        "symbol": r["symbol"], "direction": "up" if r["day_change"] > 0 else "down" if r["day_change"] < 0 else "flat",
        "price": r["price"], "prev_close": r["prev_close"], "day_change_pct": r["day_change_pct"],
        "position_change": r["day_change"], "position_value": r["market_value"],
    } for r in hits]

    total_value = sum(r["market_value"] for r in rows)
    day_change = sum(r["day_change"] for r in rows)
    prev_value = total_value - day_change
    biggest = max(rows, key=lambda r: abs(r["day_change_pct"]))
    label = f"{threshold:g}"
    if hits:
        moves = ", ".join(f"{r['symbol']} {pct(r['day_change_pct'])}" for r in hits)
        summary = f"{len(hits)} of {len(rows)} positions moved at least {label}%: {moves}."
        markdown = _markdown(
            ["Symbol", "Direction", "Price", "Prev close", "Move", "Position change", "Position value"],
            [[a["symbol"], a["direction"], money(a["price"]), money(a["prev_close"]), pct(a["day_change_pct"]),
              signed_money(a["position_change"]), money(a["position_value"])] for a in alert_rows])
    else:
        summary = (f"No alert: none of {len(rows)} positions moved at least {label}% "
                   f"(largest move {biggest['symbol']} {pct(biggest['day_change_pct'])}).")
        markdown = "(no positions moved that much)"

    symbols = " ".join(r["symbol"] for r in hits)
    as_of = max(q["as_of"] for q in quotes)
    checked_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")
    unpriced = [f["symbol"] for f in failed]
    return {
        "success": True, "operation": "alerts", "source": source, "as_of": as_of, "threshold": threshold,
        "count": len(hits), "symbols": symbols, "rows": len(hits), "positions": len(rows),
        "content": _to_csv(fields, alert_rows), "markdown": markdown, "summary": summary,
        "portfolio_day_change_pct": round(day_change / prev_value * 100, 2) if prev_value else 0.0,
        "unpriced": unpriced,
        "notes": "All positions priced." if not unpriced else "Not priced (left out of the check): " + ", ".join(unpriced),
        "log_line": f"{checked_at},{as_of},{len(hits)},{symbols},{label}",
    }


def read_history(text: str) -> List[Tuple[date, float, float, float, int]]:
    """History lines 'date,total_value,total_cost,day_change,positions'; header and blank lines skipped,
    one entry per date (the last one wins), oldest first."""
    by_day: Dict[date, Tuple[date, float, float, float, int]] = {}
    for line in (text or "").splitlines():
        cells = [c.strip() for c in line.split(",")]
        if len(cells) < 5:
            continue
        try:
            day = date.fromisoformat(cells[0])
            by_day[day] = (day, float(cells[1]), float(cells[2]), float(cells[3]), int(float(cells[4])))
        except ValueError:
            continue  # the header, or a damaged line
    return [by_day[d] for d in sorted(by_day)]


def summarize_history(text: str) -> Dict[str, Any]:
    entries = read_history(text)
    if not entries:
        raise ValueError("The history has no readable rows (expected: date,total_value,total_cost,day_change,positions)")
    first, last = entries[0], entries[-1]
    shown = entries[-10:]
    markdown = _markdown(["Date", "Value", "Day change"],
                         [[e[0].isoformat(), money(e[1]), signed_money(e[3])] for e in shown])
    if len(entries) == 1:
        summary = (f"Only one day tracked so far ({first[0].isoformat()}, {money(first[1])}). "
                   "Run the tracker on other days to build a trend.")
        change = change_pct = 0.0
    else:
        change = last[1] - first[1]
        change_pct = change / first[1] * 100 if first[1] else 0.0
        best = max(entries[1:], key=lambda e: e[3])
        worst = min(entries[1:], key=lambda e: e[3])
        summary = (f"{len(entries)} days tracked ({first[0].isoformat()} to {last[0].isoformat()}): value moved from "
                   f"{money(first[1])} to {money(last[1])} ({signed_money(change)}, {pct(change_pct)}). "
                   f"Best day {best[0].isoformat()} {signed_money(best[3])}; worst day {worst[0].isoformat()} {signed_money(worst[3])}.")
    return {
        "success": True, "operation": "trend", "rows": len(entries), "days": len(entries),
        "first_date": first[0].isoformat(), "last_date": last[0].isoformat(),
        "change": round(change, 2), "change_pct": round(change_pct, 2),
        "markdown": markdown, "content": markdown, "summary": summary,
    }


class PortfolioOpsTool(BaseTool):
    """Sample portfolios, valuation and history for a stock portfolio."""

    @property
    def name(self) -> str:
        return "portfolio_operations"

    @property
    def description(self) -> str:
        return """Portfolio maths on holdings CSV (columns symbol, shares, cost_basis). Read-only: no trading, no advice.
        Operations:
        - generate: make a random SAMPLE portfolio (count, seed, source)
        - value: price the holdings and compute value, gain/loss, day change and weights (holdings, source)
        - alerts: list the positions that moved at least `threshold` percent today, up or down (holdings, source, threshold)
        - trend: summarise a history of daily totals (history)"""

    def get_parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "operation": {"type": "string", "enum": ["generate", "value", "alerts", "trend"], "description": "What to do"},
                "count": {"type": "string", "description": f"generate: how many holdings (1-{MAX_HOLDINGS})"},
                "seed": {"type": "string", "description": "generate: any whole number; the same seed gives the same portfolio"},
                "holdings": {"type": "string", "description": "value: holdings CSV text (usually {{portfolio.content}})"},
                "history": {"type": "string", "description": "trend: history lines date,total_value,total_cost,day_change,positions"},
                "threshold": {"type": "string", "description": "alerts: flag positions whose move today is at least this many percent (above 0, up to 100)"},
                "source": {"type": "string", "enum": SOURCES, "description": "Prices: yahoo (real, delayed) or simulated (made-up)"}
            },
            "required": ["operation"]
        }

    def execute(self, operation: str, count: str = None, seed: str = None, holdings: str = None,
                history: str = None, source: str = "yahoo", threshold: str = None) -> Dict[str, Any]:
        try:
            if operation in ("generate", "value", "alerts") and source not in SOURCES:
                raise ValueError(f"source must be one of: {', '.join(SOURCES)}")
            if operation == "generate":
                return generate_holdings(count, seed, source)
            if operation == "value":
                if not holdings:
                    raise ValueError("holdings is required for the value operation")
                return value_holdings(holdings, source)
            if operation == "alerts":
                if not holdings:
                    raise ValueError("holdings is required for the alerts operation")
                return check_moves(holdings, source, threshold)
            if operation == "trend":
                return summarize_history(history)
            raise ValueError(f"Unknown operation: {operation}")
        except Exception as e:
            return {"success": False, "error": str(e), "operation": operation}
