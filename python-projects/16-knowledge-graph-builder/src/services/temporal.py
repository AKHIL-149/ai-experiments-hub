"""Time in the graph: what a fact's dates say about a moment or a period, and which time a question asks about.

Dates are stored as the text states them: "2019", "2019-03" or "2019-03-15", so each one is a *range* of days
(2019 = 1 January to 31 December). A fact has a start and an end, either may be missing:
  * "from 2015 to 2018"  -> start 2015, end 2018
  * "since 2023"         -> start 2023, no end stated (it may or may not still hold: the text does not say)
  * "bought it in 2019"  -> start 2019, no end (an event, which the text also does not mark as an event)

For a question's period the status of a fact is one of
  during    the stated dates surely cover the whole period
  overlaps  they overlap it, or might (a year-only date, a fact that began or ended inside the period)
  open      it began before the period and no end is stated: it may still have held (we do not know)
  outside   it cannot have held in the period (it ended before, or began after)
  undated   the text gives no date, so nothing can be said

No language model is involved: a question's time is found with patterns, and every status is a comparison of dates.
"""
import re
from calendar import monthrange
from dataclasses import dataclass
from datetime import date

from src.services.text_utils import _MONTHS

NEG, POS = -10**9, 10**9      # "no lower / upper bound"

STATUSES = ("during", "overlaps", "open", "outside", "undated")


def parse_period(value: str | None) -> tuple[int, int] | None:
    """'2019' / '2019-03' / '2019-03-15' -> (first day, last day) as day numbers; None for '' or anything else"""
    m = re.fullmatch(r"(\d{4})(?:-(\d{2})(?:-(\d{2}))?)?", (value or "").strip())
    if not m:
        return None
    y, mo, d = int(m.group(1)), m.group(2), m.group(3)
    try:
        if mo is None:
            return date(y, 1, 1).toordinal(), date(y, 12, 31).toordinal()
        if d is None:
            return date(y, int(mo), 1).toordinal(), date(y, int(mo), monthrange(y, int(mo))[1]).toordinal()
        day = date(y, int(mo), int(d)).toordinal()
        return day, day
    except ValueError:
        return None


@dataclass(frozen=True)
class Window:
    """The period a question is about. lo / hi are day numbers; None = no limit on that side"""
    lo: int | None
    hi: int | None
    label: str
    kind: str = "in"          # in | before | after | between | now

    def to_dict(self) -> dict:
        f = lambda n: date.fromordinal(n).isoformat() if n is not None else None  # noqa: E731
        return {"label": self.label, "kind": self.kind, "from": f(self.lo), "to": f(self.hi)}


def window_of(value: str, kind: str = "in", label: str | None = None) -> Window | None:
    p = parse_period(value)
    return Window(p[0], p[1], label or value, kind) if p else None


def window_between(a: str, b: str) -> Window | None:
    pa, pb = parse_period(a), parse_period(b)
    if not pa or not pb:
        return None
    if pa[0] > pb[0]:
        a, b = b, a                      # "between 2018 and 2015" means the same as "between 2015 and 2018"
    return Window(min(pa[0], pb[0]), max(pa[1], pb[1]), f"{a} to {b}", "between")


def classify(valid_from: str | None, valid_to: str | None, window: Window) -> str:
    """What the fact's dates say about the window (see the module text)"""
    s, e = parse_period(valid_from), parse_period(valid_to)
    if not s and not e:
        return "undated"
    w_lo = window.lo if window.lo is not None else NEG
    w_hi = window.hi if window.hi is not None else POS
    fact_first = s[0] if s else NEG          # the earliest day it could have begun
    fact_last = e[1] if e else POS           # the latest day it could have ended
    if fact_first > w_hi or fact_last < w_lo:
        return "outside"
    if s and e and window.lo is not None and window.hi is not None and s[1] <= window.lo and e[0] >= window.hi:
        return "during"
    if s and not e and window.lo is not None and s[1] < window.lo:
        return "open"
    return "overlaps"


def describe(status: str, window: Window) -> str:
    """The status in words, for the model and for the person reading the answer"""
    return {
        "during": f"dated: holds throughout {window.label}",
        "overlaps": f"dated: overlaps {window.label}",
        "open": "dated: began earlier, no end date stated, so it may still have held",
        "undated": "no date stated",
        "outside": f"dated outside {window.label}",
    }[status]


# ---------------------------------------------------------------- the time a question asks about

_MONTH_NAMES = "|".join(sorted(_MONTHS, key=len, reverse=True))
_DAY = r"(?:\d{1,2}(?:st|nd|rd|th)?)"
# one date as a person writes it: 15 March 2021, March 15, 2021, March 2021, 2021-03-15, 2021-03, 2021
_DATE = (rf"(?:{_DAY}\s+(?:{_MONTH_NAMES})\.?,?\s+\d{{4}}|(?:{_MONTH_NAMES})\.?\s+{_DAY},?\s+\d{{4}}|(?:{_MONTH_NAMES})\.?,?\s+\d{{4}}"
         r"|\d{4}-\d{2}-\d{2}|\d{4}-\d{2}|\d{4})(?!\d)")
_DECADE = r"the\s+(\d{3})0s"


def _iso(text: str) -> str:
    """'15 March 2021' / 'March 2021' / '2021' -> '2021-03-15' / '2021-03' / '2021'"""
    from src.services.text_utils import normalize_date
    return normalize_date(text.replace(",", " ").strip())


@dataclass(frozen=True)
class TimeQuery:
    window: Window
    question: str       # the question without the time words ("Who was the CTO of Acme?"), for planning and searching
    text: str           # the words that were taken as the time ("in 2021")


_PATTERNS = [
    # (regex, builder(match, today) -> Window | None)
    (re.compile(rf"\bbetween\s+({_DATE})\s+and\s+({_DATE})", re.I), lambda m, t: window_between(_iso(m.group(1)), _iso(m.group(2)))),
    (re.compile(rf"\bfrom\s+({_DATE})\s+(?:to|until|till|through)\s+({_DATE})", re.I), lambda m, t: window_between(_iso(m.group(1)), _iso(m.group(2)))),
    (re.compile(rf"\b(?:in|during|throughout)\s+{_DECADE}", re.I),
     lambda m, t: Window(date(int(m.group(1)) * 10, 1, 1).toordinal(), date(int(m.group(1)) * 10 + 9, 12, 31).toordinal(), f"the {m.group(1)}0s", "in")),
    (re.compile(rf"\b(?:before|prior\s+to)\s+({_DATE})", re.I),
     lambda m, t: _bounded(_iso(m.group(1)), "before")),
    (re.compile(rf"\b(?:until|till|up\s+to)\s+({_DATE})", re.I),
     lambda m, t: _bounded(_iso(m.group(1)), "before", inclusive=True)),
    (re.compile(rf"\b(?:after|following)\s+({_DATE})", re.I),
     lambda m, t: _bounded(_iso(m.group(1)), "after", after_end=True)),
    (re.compile(rf"\bsince\s+({_DATE})", re.I), lambda m, t: _bounded(_iso(m.group(1)), "after")),
    (re.compile(rf"\b(?:in|on|during|as\s+of|throughout|around)\s+({_DATE})", re.I), lambda m, t: window_of(_iso(m.group(1)))),
    (re.compile(r"\b(?:currently|presently|at\s+present|these\s+days|right\s+now|as\s+of\s+now|as\s+of\s+today|today|now|current|present)\b", re.I),
     lambda m, t: Window(t.toordinal(), t.toordinal(), f"now ({t.isoformat()})", "now")),
]


def _bounded(value: str, kind: str, *, inclusive: bool = False, after_end: bool = False) -> Window | None:
    p = parse_period(value)
    if not p:
        return None
    if kind == "before":
        hi = p[1] if inclusive else p[0] - 1
        return Window(None, hi, f"{'until' if inclusive else 'before'} {value}", "before")
    lo = p[1] + 1 if after_end else p[0]
    return Window(lo, None, f"{'after' if after_end else 'since'} {value}", "after")


def parse_time(question: str, today: date | None = None) -> TimeQuery | None:
    """The time a question asks about ("in 2021", "between 2015 and 2018", "before March 2020", "currently"), or None.
    Only the first time expression is used. A bare year with no preposition ("Expo 2020") is not a time."""
    today = today or date.today()
    best = None
    for pattern, build in _PATTERNS:
        for m in pattern.finditer(question):
            w = build(m, today)
            if w is None:
                continue
            if best is None or m.start() < best[0].start():
                best = (m, w)
            break
    if best is None:
        return None
    m, w = best
    core = (question[:m.start()] + question[m.end():])
    core = re.sub(r"\s+([?.,!])", r"\1", core)
    core = re.sub(r"\s{2,}", " ", core).strip().rstrip(",").strip()
    core = re.sub(r"\s+([?.,!])", r"\1", core).lstrip(" ,;:").strip()
    return TimeQuery(w, core or question, m.group(0))


def window_from_params(at: str | None = None, start: str | None = None, end: str | None = None, today: date | None = None) -> Window | None:
    """The period an API call asks about: `at` (a year, month, day, or "now"), or `start` and/or `end` (a range, open on a missing side).
    None when none is given; ValueError with a message for the person when a date is not one."""
    today = today or date.today()
    at, start, end = (v.strip() if v else "" for v in (at, start, end))
    if at and (start or end):
        raise ValueError("Give either 'at' or 'from' and 'to', not both")
    if at:
        if at.casefold() == "now":
            return Window(today.toordinal(), today.toordinal(), f"now ({today.isoformat()})", "now")
        w = window_of(at)
        if w is None:
            raise ValueError(f"'{at}' is not a date: use YYYY, YYYY-MM or YYYY-MM-DD")
        return w
    if start or end:
        a, b = parse_period(start) if start else None, parse_period(end) if end else None
        if (start and not a) or (end and not b):
            raise ValueError(f"'{start if start and not a else end}' is not a date: use YYYY, YYYY-MM or YYYY-MM-DD")
        if a and b:
            return window_between(start, end)
        return Window(a[0], None, f"since {start}", "after") if a else Window(None, b[1], f"until {end}", "before")
    return None


# ---------------------------------------------------------------- two facts and their periods

def _not_after(x: str, y: str) -> bool:
    """x is not later than y, compared as precisely as both are written ('2019' vs '2019-03' compares the years)"""
    n = min(len(x), len(y))
    return x[:n] <= y[:n]


def overlap_status(a_from: str | None, a_to: str | None, b_from: str | None, b_to: str | None) -> str:
    """Can two facts have held at the same time?
      none      one surely ended before (or when) the other began: a handover, not an overlap ("2012-2019" and "2019-2022")
      certain   both begin on stated dates, at least one ends on a stated date, and the periods share time
      possible  they might overlap: a missing start, or neither one states an end ("since 2020" and "since 2023")
      unknown   neither has any date
    """
    a_from, a_to, b_from, b_to = (v or "" for v in (a_from, a_to, b_from, b_to))
    if not (a_from or a_to or b_from or b_to):
        return "unknown"
    if a_to and b_from and _not_after(a_to, b_from):
        return "none"
    if b_to and a_from and _not_after(b_to, a_from):
        return "none"
    if a_from and b_from and (a_to or b_to):
        return "certain"
    return "possible"
