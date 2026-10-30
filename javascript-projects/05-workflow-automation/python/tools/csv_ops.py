"""CSV text operations: deterministic filtering, labelling and formatting for workflows.

Works on CSV *text* (for example the content of a file read by a previous step), so the
results can be handed straight to the next step. Use it for the parts of a job that must
be exactly right (which rows match, how many, which label a rating gets) and keep the AI
for the parts that need language.
"""

import csv
import io
import re
from typing import Any, Dict, List, Optional, Tuple
from .base_tool import BaseTool

OPERATORS = ["<", "<=", ">", ">=", "==", "!=", "contains"]

_RANGE = re.compile(
    r"^\s*(-?\d+(?:\.\d+)?)(?:\s*-\s*(-?\d+(?:\.\d+)?))?\s*:\s*(.+?)\s*$"
)


def parse_csv(content: str) -> Tuple[List[str], List[Dict[str, str]], int]:
    """Header names, one dict per row, and how many rows had to be repaired.

    A row with more cells than the header almost always has unquoted commas in its last
    (free-text) column, so the extra cells are joined back onto it instead of being lost.
    Raises ValueError for empty or headerless text.
    """
    text = (content or "").lstrip("\ufeff")
    if not text.strip():
        raise ValueError("CSV content is empty")
    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames:
        raise ValueError("CSV content has no header row")
    header = [name.strip() for name in reader.fieldnames]

    rows, repaired = [], 0
    for raw in reader:
        row = {name.strip(): (value or "") for name, value in raw.items() if name is not None}
        overflow = raw.get(None)
        if overflow:
            row[header[-1]] = ",".join([row[header[-1]]] + overflow)
            repaired += 1
        rows.append(row)
    return header, rows, repaired


def to_csv(header: List[str], rows: List[Dict[str, str]]) -> str:
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=header, lineterminator="\n", extrasaction="ignore")
    writer.writeheader()
    writer.writerows(rows)
    return buffer.getvalue()


def _number(text: str) -> Optional[float]:
    try:
        return float(str(text).strip())
    except ValueError:
        return None


def _matches(cell: str, operator: str, value: str) -> bool:
    left, right = _number(cell), _number(value)
    if operator == "contains":
        return value.lower() in cell.lower()
    if left is not None and right is not None:
        pair = (left, right)
    elif operator in ("==", "!="):
        pair = (cell.strip().lower(), value.strip().lower())
    else:
        return False  # an ordering comparison needs numbers on both sides
    return {
        "<": pair[0] < pair[1], "<=": pair[0] <= pair[1],
        ">": pair[0] > pair[1], ">=": pair[0] >= pair[1],
        "==": pair[0] == pair[1], "!=": pair[0] != pair[1],
    }[operator]


def parse_ranges(text: str) -> List[Tuple[float, float, str]]:
    """'4-5:Positive, 3:Neutral, 1-2:Negative' -> [(4, 5, 'Positive'), (3, 3, 'Neutral'), ...]"""
    ranges = []
    for part in (text or "").split(","):
        if not part.strip():
            continue
        match = _RANGE.match(part)
        if not match:
            raise ValueError(f"Cannot read range '{part.strip()}'. Use the form 1-2:Label or 3:Label")
        low = float(match.group(1))
        high = float(match.group(2)) if match.group(2) is not None else low
        if low > high:
            raise ValueError(f"Range '{part.strip()}' starts above where it ends")
        ranges.append((low, high, match.group(3)))
    if not ranges:
        raise ValueError("ranges is required for the label operation, e.g. 4-5:Positive,3:Neutral,1-2:Negative")
    return ranges


def _cell(text: str) -> str:
    return " ".join(str(text).split()).replace("|", "\\|")


class CsvOpsTool(BaseTool):
    """Filter, label and format CSV text."""

    @property
    def name(self) -> str:
        return "csv_operations"

    @property
    def description(self) -> str:
        return """Work on CSV text (with a header row) exactly, without an AI guessing.
        Operations:
        - filter: keep the rows where column <operator> value (numbers compare as numbers)
        - label: add a column whose value comes from numeric ranges of another column
        - to_markdown: turn the CSV into a markdown table
        - count: count the data rows"""

    def get_parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "operation": {
                    "type": "string",
                    "enum": ["filter", "label", "to_markdown", "count"],
                    "description": "What to do with the CSV"
                },
                "content": {
                    "type": "string",
                    "description": "The CSV text, including its header row (usually {{something.content}})"
                },
                "column": {
                    "type": "string",
                    "description": "Column to test (filter) or to read numbers from (label)"
                },
                "operator": {
                    "type": "string",
                    "enum": OPERATORS,
                    "description": "Comparison for filter"
                },
                "value": {
                    "type": "string",
                    "description": "Value to compare with (filter)"
                },
                "new_column": {
                    "type": "string",
                    "description": "Name of the column to add (label)"
                },
                "ranges": {
                    "type": "string",
                    "description": "Label rules for label, e.g. 4-5:Positive,3:Neutral,1-2:Negative"
                },
                "columns": {
                    "type": "string",
                    "description": "Comma-separated columns to show, in order (to_markdown; default all)"
                },
                "if_empty": {
                    "type": "string",
                    "description": "Text to return instead when no rows are left (filter, to_markdown)"
                }
            },
            "required": ["operation", "content"]
        }

    def execute(
        self, operation: str, content: str, column: str = None, operator: str = None,
        value: str = None, new_column: str = None, ranges: str = None,
        columns: str = None, if_empty: str = None
    ) -> Dict[str, Any]:
        try:
            header, rows, repaired = parse_csv(content)
            note = {"repaired_rows": repaired} if repaired else {}

            if operation == "count":
                return {"success": True, "operation": operation, "rows": len(rows), "content": str(len(rows)), **note}

            if operation == "filter":
                kept = self._filter(header, rows, column, operator, value)
                if not kept and if_empty:
                    text = if_empty
                else:
                    text = to_csv(header, kept)
                return {"success": True, "operation": operation, "content": text,
                        "rows": len(kept), "total": len(rows), **note}

            if operation == "label":
                labelled, unlabelled = self._label(header, rows, column, new_column, ranges)
                return {"success": True, "operation": operation,
                        "content": to_csv(header + [new_column], labelled),
                        "rows": len(labelled), "unlabelled": unlabelled, **note}

            if operation == "to_markdown":
                shown = self._columns(header, columns)
                if not rows and if_empty:
                    return {"success": True, "operation": operation, "content": if_empty, "rows": 0, **note}
                lines = ["| " + " | ".join(_cell(c) for c in shown) + " |",
                         "| " + " | ".join("---" for _ in shown) + " |"]
                lines += ["| " + " | ".join(_cell(r.get(c, "")) for c in shown) + " |" for r in rows]
                return {"success": True, "operation": operation, "content": "\n".join(lines),
                        "rows": len(rows), **note}

            raise ValueError(f"Unknown operation: {operation}")

        except Exception as e:
            return {"success": False, "error": str(e), "operation": operation}

    @staticmethod
    def _require_column(header: List[str], column: Optional[str]) -> str:
        if not column:
            raise ValueError("column is required")
        wanted = column.strip()
        for name in header:
            if name == wanted:
                return name
        for name in header:
            if name.lower() == wanted.lower():
                return name
        raise ValueError(f"No column named '{column}'. The columns are: {', '.join(header)}")

    def _filter(self, header, rows, column, operator, value) -> List[Dict[str, str]]:
        name = self._require_column(header, column)
        if operator not in OPERATORS:
            raise ValueError(f"operator must be one of: {', '.join(OPERATORS)}")
        if value is None or value == "":
            raise ValueError("value is required for the filter operation")
        return [r for r in rows if _matches(r.get(name, ""), operator, value)]

    def _label(self, header, rows, column, new_column, ranges):
        name = self._require_column(header, column)
        if not new_column or not new_column.strip():
            raise ValueError("new_column is required for the label operation")
        new_column = new_column.strip()
        if new_column in header:
            raise ValueError(f"The CSV already has a column named '{new_column}'")
        rules = parse_ranges(ranges)

        out, unlabelled = [], 0
        for row in rows:
            number = _number(row.get(name, ""))
            label = next((lab for lo, hi, lab in rules if number is not None and lo <= number <= hi), "")
            if not label:
                unlabelled += 1
            out.append({**row, new_column: label})
        return out, unlabelled

    @staticmethod
    def _columns(header: List[str], columns: Optional[str]) -> List[str]:
        if not columns or not columns.strip():
            return header
        wanted = [c.strip() for c in columns.split(",") if c.strip()]
        lookup = {h.lower(): h for h in header}
        missing = [c for c in wanted if c.lower() not in lookup]
        if missing:
            raise ValueError(f"No column named '{missing[0]}'. The columns are: {', '.join(header)}")
        return [lookup[c.lower()] for c in wanted]
