"""Run from the project root: python3 -m pytest python/tests -q"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest

from tools.csv_ops import CsvOpsTool, parse_ranges
from tool_registry import ToolRegistry

CSV = (
    'id,customer,rating,comment\n'
    '1,Dana,5,"Great, really"\n'
    '2,Sam,2,Logged out\n'
    '3,"Quote ""Q"" Man",1,"He said ""it broke"""\n'
    '4,Tom,3,CSV | export\n'
)


@pytest.fixture
def tool():
    return CsvOpsTool()


def run(tool, **kwargs):
    kwargs.setdefault("content", CSV)
    return tool.execute(**kwargs)


def test_registered_and_discoverable():
    assert "csv_operations" in ToolRegistry().list_tools()


def test_filter_numbers_compare_as_numbers_not_text(tool):
    out = run(tool, operation="filter", column="rating", operator="<=", value="2")
    assert out["success"] and out["rows"] == 2 and out["total"] == 4
    assert "Sam" in out["content"] and "Dana" not in out["content"]
    # as text "10" < "2"; as numbers 10 > 2
    big = run(tool, operation="filter", content="n\n10\n2\n", column="n", operator=">", value="5")
    assert big["rows"] == 1 and "10" in big["content"]


def test_filter_keeps_quoted_commas_and_quotes_intact(tool):
    out = run(tool, operation="filter", column="rating", operator="<=", value="1")
    assert out["rows"] == 1
    assert '"Quote ""Q"" Man"' in out["content"]
    again = run(tool, operation="count", content=out["content"])
    assert again["rows"] == 1


def test_filter_text_operators_are_case_insensitive(tool):
    assert run(tool, operation="filter", column="customer", operator="==", value="SAM")["rows"] == 1
    assert run(tool, operation="filter", column="comment", operator="contains", value="LOGGED")["rows"] == 1
    assert run(tool, operation="filter", column="customer", operator="!=", value="sam")["rows"] == 3


def test_ordering_on_non_numbers_matches_nothing_instead_of_guessing(tool):
    out = run(tool, operation="filter", column="customer", operator="<", value="Z")
    assert out["success"] and out["rows"] == 0


def test_filter_with_no_match_returns_the_if_empty_text(tool):
    out = run(tool, operation="filter", column="rating", operator=">", value="9", if_empty="(none)")
    assert out["rows"] == 0 and out["content"] == "(none)"
    plain = run(tool, operation="filter", column="rating", operator=">", value="9")
    assert plain["content"].strip() == "id,customer,rating,comment"


def test_column_lookup_ignores_case_and_reports_valid_names(tool):
    assert run(tool, operation="filter", column="RATING", operator="==", value="5")["rows"] == 1
    bad = run(tool, operation="filter", column="stars", operator="==", value="5")
    assert not bad["success"] and "id, customer, rating, comment" in bad["error"]


def test_filter_requires_valid_operator_and_value(tool):
    assert "operator" in run(tool, operation="filter", column="rating", operator="~", value="1")["error"]
    assert "value" in run(tool, operation="filter", column="rating", operator="==")["error"]


def test_label_adds_a_column_from_ranges(tool):
    out = run(tool, operation="label", column="rating", new_column="sentiment",
              ranges="4-5:Positive, 3:Neutral, 1-2:Negative")
    assert out["success"] and out["unlabelled"] == 0
    lines = out["content"].splitlines()
    assert lines[0] == "id,customer,rating,comment,sentiment"
    assert lines[1].endswith(",Positive") and lines[2].endswith(",Negative") and lines[4].endswith(",Neutral")


def test_label_counts_rows_no_range_covers(tool):
    out = run(tool, operation="label", content="r\n7\nabc\n\n", column="r", new_column="l", ranges="1-5:Low")
    assert out["unlabelled"] == 2  # 7 and abc fall outside the range; blank lines are skipped by csv


def test_label_rejects_bad_input(tool):
    assert "already has" in run(tool, operation="label", column="rating", new_column="id", ranges="1:x")["error"]
    assert "Cannot read range" in run(tool, operation="label", column="rating", new_column="s", ranges="high")["error"]
    assert "ranges is required" in run(tool, operation="label", column="rating", new_column="s", ranges="")["error"]
    assert "new_column" in run(tool, operation="label", column="rating", ranges="1:x")["error"]
    with pytest.raises(ValueError):
        parse_ranges("5-1:Backwards")


def test_to_markdown_escapes_pipes_and_picks_columns(tool):
    out = run(tool, operation="to_markdown", columns="id, Comment")
    lines = out["content"].splitlines()
    assert lines[0] == "| id | comment |"  # "Comment" resolves to the CSV's own spelling
    assert lines[1] == "| --- | --- |"
    assert r"CSV \| export" in out["content"]
    assert out["rows"] == 4


def test_to_markdown_all_columns_by_default_and_if_empty(tool):
    assert run(tool, operation="to_markdown")["content"].splitlines()[0] == "| id | customer | rating | comment |"
    empty = run(tool, operation="to_markdown", content="a,b\n", if_empty="no data")
    assert empty["content"] == "no data"
    assert "No column named 'zzz'" in run(tool, operation="to_markdown", columns="id,zzz")["error"]


def test_count(tool):
    assert run(tool, operation="count")["rows"] == 4
    assert run(tool, operation="count", content="a,b\n")["rows"] == 0


def test_empty_and_odd_input(tool):
    assert "empty" in run(tool, operation="count", content="  \n ")["error"]
    # a BOM (added by some spreadsheet exports) must not become part of the first column name
    bom = run(tool, operation="filter", content="\ufeffid,x\n1,2\n", column="id", operator="==", value="1")
    assert bom["success"] and bom["rows"] == 1
    ragged = run(tool, operation="to_markdown", content="a,b\n1\n1,2,3\n")  # short and long rows
    assert ragged["success"] and ragged["rows"] == 2
    assert "Unknown operation" in run(tool, operation="explode")["error"]
    assert not run(tool, operation="count", content=None)["success"]


def test_unquoted_commas_in_the_last_column_are_kept_not_dropped(tool):
    csv_text = "id,customer,comment\n1,Sam,The app, honestly, logs me out, a lot\n2,Lee,Fine\n"
    out = tool.execute(operation="filter", content=csv_text, column="id", operator="==", value="1")
    assert out["success"] and out["rows"] == 1
    assert "honestly" in out["content"] and "a lot" in out["content"]
    assert out["repaired_rows"] == 1
    table = tool.execute(operation="to_markdown", content=csv_text)
    assert "The app, honestly, logs me out, a lot" in table["content"]
    assert table["repaired_rows"] == 1


def test_clean_csv_reports_no_repairs(tool):
    out = run(tool, operation="to_markdown")
    assert "repaired_rows" not in out


def test_short_rows_are_padded_and_not_counted_as_repaired(tool):
    out = tool.execute(operation="to_markdown", content="a,b,c\n1,2\n")
    assert out["success"] and "repaired_rows" not in out
