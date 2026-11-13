"""Small text helpers shared by extraction and storage"""
import re
import unicodedata

_QUOTES = {"‘": "'", "’": "'", "“": '"', "”": '"', "–": "-", "—": "-", " ": " "}
_LEGAL_SUFFIXES = {"corp", "corporation", "inc", "incorporated", "ltd", "limited", "llc", "co", "company", "gmbh", "plc", "ag", "sa"}
_WORD = re.compile(r"[^\W_]+", re.UNICODE)


def fold(text: str) -> str:
    """Lowercase, straight quotes/dashes, single spaces"""
    text = unicodedata.normalize("NFKC", text)
    for a, b in _QUOTES.items():
        text = text.replace(a, b)
    return re.sub(r"\s+", " ", text).strip().casefold()


def strip_accents(text: str) -> str:
    """'Zürich' -> 'Zurich'"""
    return "".join(c for c in unicodedata.normalize("NFKD", text) if not unicodedata.combining(c))


def words(text: str) -> list[str]:
    return _WORD.findall(strip_accents(fold(text)).replace("'s ", " ").replace("'s", ""))


def words_and_commas(text: str) -> list[str]:
    """Like words(), but commas are kept as ',' tokens (they mark inserted clauses)"""
    return re.findall(r"[^\W_]+|,", fold(text).replace("'s ", " ").replace("'s", ""), flags=re.UNICODE)


def core_words(name: str) -> list[str]:
    """Words of a name without 'the' and legal suffixes (Acme Corp -> acme)"""
    ws = [w for w in words(name) if w != "the"]
    stripped = [w for w in ws if w not in _LEGAL_SUFFIXES]
    return stripped or ws


def strip_article(name: str) -> str:
    """'the Bombe' -> 'Bombe', 'a Fellow of the Royal Society' -> 'Fellow of the Royal Society' (never to nothing)"""
    parts = name.split(" ", 1)
    if len(parts) == 2 and parts[0].casefold() in ("the", "a", "an") and parts[1].strip():
        return parts[1].strip()
    return name


def entity_key(name: str) -> str:
    """Key for exact matching of the same entity written slightly differently (case, spacing, punctuation)"""
    return " ".join(words(name))


def name_in_text(name: str, text: str) -> bool:
    """Every significant word of the name appears as a word in the text"""
    needed = core_words(name)
    if not needed:
        return False
    have = set(words(text))
    return all(w in have for w in needed)


# words that do not identify an entity on their own ("University" matches every university)
GENERIC_WORDS = {"university", "institute", "college", "school", "company", "group", "laboratory", "laboratories", "lab", "society",
                 "academy", "centre", "center", "bank", "city", "of", "the", "and", "for", "in"}


def name_in_passage(name: str, quote: str, passage: str) -> bool:
    """The name is in the quote, or its first or last word is (the quote says 'Turing' or 'Widget-X' where the model
    wrote 'Alan Turing' or 'Widget-X Sensor') and every word of the name occurs somewhere in the passage."""
    if name_in_text(name, quote):
        return True
    needed = core_words(name)
    if len(needed) < 2:
        return False
    in_quote, in_passage = set(words(quote)), set(words(passage))
    anchors = [w for w in (needed[0], needed[-1]) if w not in GENERIC_WORDS]
    return any(w in in_quote for w in anchors) and all(w in in_passage for w in needed)


def locate(quote: str, text: str) -> tuple[int, int] | None:
    """Find `quote` inside `text` ignoring case, quote style and whitespace; return the span in the original text"""
    quote = quote.strip().strip("…").strip()
    while quote.endswith("..."):
        quote = quote[:-3].rstrip()
    if quote.startswith("..."):
        quote = quote[3:].lstrip()
    if not quote:
        return None
    # fold text char by char so we can map folded positions back to the original
    folded, origin = [], []
    prev_space = True
    for i, ch in enumerate(text):
        c = unicodedata.normalize("NFKC", ch)
        c = _QUOTES.get(ch, c)
        for cc in c.casefold():
            if cc.isspace():
                if prev_space:
                    continue
                cc, prev_space = " ", True
            else:
                prev_space = False
            folded.append(cc)
            origin.append(i)
    needle = fold(quote)
    hay = "".join(folded)
    pos = hay.find(needle)
    if pos < 0:
        return None
    start = origin[pos]
    end = origin[pos + len(needle) - 1] + 1
    return start, end


_MONTHS = {m: i for i, m in enumerate(
    ["january", "february", "march", "april", "may", "june", "july", "august", "september", "october", "november", "december"], 1)}
_MONTHS.update({k[:3]: v for k, v in list(_MONTHS.items())})
_MONTHS["sept"] = 9


def normalize_date(value: str) -> str:
    """'2020', '2020-03', '2020-03-15', 'March 2020', 'March 15, 2020' -> YYYY[-MM[-DD]]; '' when it is not a date"""
    v = (value or "").strip().strip(".").casefold()
    if not v:
        return ""
    m = re.fullmatch(r"(\d{4})(?:-(\d{1,2})(?:-(\d{1,2}))?)?", v)
    if m:
        y, mo, d = m.group(1), m.group(2), m.group(3)
        return _compose(y, mo, d)
    m = re.fullmatch(r"([a-z]+)\.?\s+(?:(\d{1,2})(?:st|nd|rd|th)?,?\s+)?(\d{4})", v)
    if m and m.group(1) in _MONTHS:
        return _compose(m.group(3), str(_MONTHS[m.group(1)]), m.group(2))
    m = re.fullmatch(r"(\d{1,2})(?:st|nd|rd|th)?\s+([a-z]+)\.?,?\s+(\d{4})", v)
    if m and m.group(2) in _MONTHS:
        return _compose(m.group(3), str(_MONTHS[m.group(2)]), m.group(1))
    return ""


def _compose(y: str, mo: str | None, d: str | None) -> str:
    year = int(y)
    if not 1000 <= year <= 2999:
        return ""
    if mo is None:
        return f"{year:04d}"
    month = int(mo)
    if not 1 <= month <= 12:
        return ""
    if d is None:
        return f"{year:04d}-{month:02d}"
    day = int(d)
    if not 1 <= day <= 31:
        return ""
    return f"{year:04d}-{month:02d}-{day:02d}"
