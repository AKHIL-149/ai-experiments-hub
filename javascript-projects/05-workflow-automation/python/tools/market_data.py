"""Stock quotes for workflows.

Two sources:
  yahoo      real, delayed prices from Yahoo Finance's public chart endpoint. It needs no key but
             is unofficial and undocumented: it can change, rate-limit or disappear. For
             personal, informational use only.
  simulated  deterministic made-up prices (stable within a day, different tomorrow) for demos,
             tests and working offline. Always labelled "simulated" in the output.

Nothing here places orders or moves money: it only reads prices.
"""

import csv
import hashlib
import io
import json
import os
import random
import re
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple
from .base_tool import BaseTool

SOURCES = ["yahoo", "simulated"]
MAX_SYMBOLS = 25
SYMBOL = re.compile(r"^[A-Z0-9^][A-Z0-9.\-=^]{0,11}$")
QUOTE_COLUMNS = ["symbol", "price", "prev_close", "change", "change_pct", "currency", "as_of", "source"]
CHART_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?range=5d&interval=1d"


class QuoteError(Exception):
    """One symbol could not be priced."""


def parse_symbols(text: str) -> List[str]:
    """'aapl, msft ,AAPL' -> ['AAPL', 'MSFT']: split on commas or spaces, upper-cased, de-duplicated, validated."""
    seen: List[str] = []
    for part in re.split(r"[,\s]+", (text or "").strip()):
        if not part:
            continue
        symbol = part.upper()
        if not SYMBOL.match(symbol):
            raise ValueError(f"'{part}' is not a valid ticker symbol (letters, numbers, . - = ^; up to 12 characters)")
        if symbol not in seen:
            seen.append(symbol)
    if not seen:
        raise ValueError("symbols is required, e.g. AAPL,MSFT,NVDA")
    if len(seen) > MAX_SYMBOLS:
        raise ValueError(f"At most {MAX_SYMBOLS} symbols per request ({len(seen)} given)")
    return seen


# ---------------------------------------------------------------------------- simulated

def _unit(*parts: str) -> random.Random:
    digest = hashlib.sha256("|".join(parts).encode()).digest()
    return random.Random(int.from_bytes(digest[:8], "big"))


def simulated_base_price(symbol: str) -> float:
    """A stable made-up price level for a symbol, between about 20 and 600."""
    return round(20 + _unit("base", symbol).random() * 580, 2)


def simulated_quote(symbol: str, today: Optional[date] = None) -> Dict[str, Any]:
    today = today or date.today()

    def price_on(day: date) -> float:
        move = (_unit("day", symbol, day.isoformat()).random() - 0.5) * 0.08  # -4% .. +4%
        return round(simulated_base_price(symbol) * (1 + move), 2)

    return _quote_row(symbol, price_on(today), price_on(today - timedelta(days=1)), "USD", today.isoformat(), "simulated")


# ---------------------------------------------------------------------------- yahoo

def fetch_json(url: str) -> Dict[str, Any]:
    """HTTP GET returning parsed JSON. Separate so tests can replace it."""
    request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (personal portfolio tracker)"})
    timeout = float(os.getenv("MARKET_DATA_TIMEOUT", "10"))
    last_error: Optional[Exception] = None
    for _ in range(2):
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return json.loads(response.read())
        except urllib.error.HTTPError as e:
            if e.code == 404:
                raise QuoteError("symbol not found")
            last_error = e
            if e.code != 429 and e.code < 500:
                break
        except (urllib.error.URLError, TimeoutError, ValueError) as e:
            last_error = e
    raise QuoteError(f"market data request failed ({last_error})")


def yahoo_quote(symbol: str) -> Dict[str, Any]:
    data = fetch_json(CHART_URL.format(symbol=urllib.parse.quote(symbol, safe="")))
    chart = data.get("chart") or {}
    if chart.get("error"):
        raise QuoteError((chart["error"].get("description") or "symbol not found"))
    results = chart.get("result") or []
    if not results:
        raise QuoteError("no data returned")
    result = results[0]
    closes = [c for c in (result.get("indicators", {}).get("quote") or [{}])[0].get("close", []) if c is not None]
    stamps = result.get("timestamp") or []
    meta = result.get("meta") or {}

    price = meta.get("regularMarketPrice")
    if price is None and closes:
        price = closes[-1]
    if price is None:
        raise QuoteError("no price available")
    # previous session's close: the bar before the latest one
    prev = closes[-2] if len(closes) >= 2 else meta.get("chartPreviousClose") or meta.get("previousClose")
    if prev is None:
        prev = price
    as_of_ts = meta.get("regularMarketTime") or (stamps[-1] if stamps else None)
    as_of = datetime.fromtimestamp(as_of_ts, tz=timezone.utc).strftime("%Y-%m-%d") if as_of_ts else date.today().isoformat()
    return _quote_row(symbol, float(price), float(prev), meta.get("currency") or "USD", as_of, "yahoo")


# ---------------------------------------------------------------------------- shared

def _quote_row(symbol, price, prev, currency, as_of, source) -> Dict[str, Any]:
    change = price - prev
    return {
        "symbol": symbol, "price": round(price, 2), "prev_close": round(prev, 2),
        "change": round(change, 2), "change_pct": round(change / prev * 100, 2) if prev else 0.0,
        "currency": currency, "as_of": as_of, "source": source,
    }


def get_quotes(symbols: List[str], source: str) -> Tuple[List[Dict[str, Any]], List[Dict[str, str]]]:
    """Quotes (in the order asked) and the symbols that failed, with the reason."""
    if source not in SOURCES:
        raise ValueError(f"source must be one of: {', '.join(SOURCES)}")
    fetch = yahoo_quote if source == "yahoo" else simulated_quote

    def one(symbol: str):
        try:
            return fetch(symbol), None
        except QuoteError as e:
            return None, {"symbol": symbol, "error": str(e)}

    with ThreadPoolExecutor(max_workers=5) as pool:
        outcomes = list(pool.map(one, symbols))
    return [q for q, _ in outcomes if q], [f for _, f in outcomes if f]


def quotes_to_csv(quotes: List[Dict[str, Any]]) -> str:
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=QUOTE_COLUMNS, lineterminator="\n")
    writer.writeheader()
    writer.writerows(quotes)
    return buffer.getvalue()


def market_summary(quotes: List[Dict[str, Any]]) -> str:
    up = sum(1 for q in quotes if q["change"] > 0)
    down = sum(1 for q in quotes if q["change"] < 0)
    flat = len(quotes) - up - down
    best = max(quotes, key=lambda q: q["change_pct"])
    worst = min(quotes, key=lambda q: q["change_pct"])
    return (f"{len(quotes)} priced: {up} up, {down} down, {flat} unchanged. "
            f"Largest rise {best['symbol']} {best['change_pct']:+.2f}%; largest fall {worst['symbol']} {worst['change_pct']:+.2f}%.")


class MarketDataTool(BaseTool):
    """Read stock quotes (real delayed prices or simulated ones)."""

    @property
    def name(self) -> str:
        return "market_data"

    @property
    def description(self) -> str:
        return """Get stock quotes for a list of ticker symbols: price, previous close and the day's change.
        Sources: yahoo (real, delayed, unofficial) or simulated (made-up, works offline).
        Read-only: it never places orders."""

    def get_parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "symbols": {"type": "string", "description": "Comma-separated tickers, e.g. AAPL,MSFT,NVDA (max 25)"},
                "source": {"type": "string", "enum": SOURCES, "description": "yahoo = real delayed prices; simulated = made-up prices"}
            },
            "required": ["symbols"]
        }

    def execute(self, symbols: str, source: str = "yahoo") -> Dict[str, Any]:
        try:
            wanted = parse_symbols(symbols)
            quotes, failed = get_quotes(wanted, source)
            if not quotes:
                detail = "; ".join(f"{f['symbol']}: {f['error']}" for f in failed)
                raise ValueError(f"No prices could be fetched ({detail})")
            return {
                "success": True, "operation": "quote", "source": source,
                "content": quotes_to_csv(quotes), "rows": len(quotes),
                "summary": market_summary(quotes),
                "up": sum(1 for q in quotes if q["change"] > 0),
                "down": sum(1 for q in quotes if q["change"] < 0),
                "failed": failed,
                "notes": ("All symbols priced." if not failed else
                          "Could not price: " + "; ".join(f"{f['symbol']} ({f['error']})" for f in failed)),
            }
        except Exception as e:
            return {"success": False, "error": str(e), "operation": "quote"}
