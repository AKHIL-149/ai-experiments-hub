import pytest

from src.services.text_utils import (core_words, entity_key, locate, name_in_passage, name_in_text, normalize_date,
                                     strip_article)

TEXT = "Acme Corp, founded in 2010 by Maria Lopez,  acquired\nBeta Systems in “March 2020”."


def test_locate_ignores_case_whitespace_and_quote_style_and_returns_original_text():
    span = locate("maria lopez, acquired beta systems", TEXT)
    assert TEXT[span[0]:span[1]] == "Maria Lopez,  acquired\nBeta Systems"
    span = locate('in "March 2020".', TEXT)
    assert TEXT[span[0]:span[1]] == "in “March 2020”."


def test_locate_refuses_text_that_is_not_there():
    assert locate("Acme Corp founded", TEXT) is None  # the comma is missing
    assert locate("Acme bought Beta", TEXT) is None
    assert locate("   ", TEXT) is None


def test_locate_trims_ellipsis_the_model_adds():
    span = locate("... acquired Beta Systems …", TEXT)
    assert TEXT[span[0]:span[1]].startswith("acquired")


@pytest.mark.parametrize("name,text,expected", [
    ("Acme Corp", "Dana served as CTO of Acme from 2019", True),      # legal suffix ignored
    ("Acme Inc.", "Dana served as CTO of Acme from 2019", True),
    ("Beta Systems", "Beta's offices", False),                          # 'systems' missing
    ("Maria Lopez", "Maria said so", False),                            # partial name is not enough
    ("The Treaty of Aldermoor", "the treaty of Aldermoor was signed", True),
    ("Widget-X", "The Widget-X replaced it", True),
    ("", "anything", False),
])
def test_name_in_text(name, text, expected):
    assert name_in_text(name, text) is expected


def test_name_in_passage_allows_completed_names_but_not_invented_ones():
    quote = "The Widget-X replaced the Widget-W in 2021."
    passage = "The Widget-X sensor is made in Munich. " + quote
    assert name_in_passage("Widget-X Sensor", quote, passage)           # 'sensor' is elsewhere in the passage
    assert not name_in_passage("Widget-X Sensor", quote, quote)          # ...but not if it is nowhere
    assert not name_in_passage("Gizmo Sensor", quote, passage)           # an anchor word must be in the quote
    assert not name_in_passage("Maria", "Someone else", "Maria is elsewhere")
    assert name_in_passage("Alan Turing", "Turing joined the laboratory.", "Alan Turing was born in 1912. Turing joined the laboratory.")  # surname
    assert not name_in_passage("Alan Turing", "Turing joined the laboratory.", "Turing joined the laboratory.")  # 'alan' nowhere
    assert not name_in_passage("University of Oslo", "The University grew.", "University of Oslo. The University grew.")  # generic anchor


@pytest.mark.parametrize("raw,expected", [
    ("2020", "2020"), ("2020-3", "2020-03"), ("2020-03-15", "2020-03-15"), ("March 2020", "2020-03"),
    ("Mar 3, 2020", "2020-03-03"), ("3rd March 2020", "2020-03-03"), ("sept 2019", "2019-09"),
    ("13/2020", ""), ("abc", ""), ("0999", ""), ("2020-13", ""), ("2020-02-40", ""), ("", ""), (None, ""),
    ("3000", ""),
])
def test_normalize_date(raw, expected):
    assert normalize_date(raw) == expected


def test_entity_key_and_core_words():
    assert entity_key("Acme, Inc.") == entity_key("  ACME   inc") == "acme inc"
    assert core_words("The Acme Corp") == ["acme"]
    assert core_words("Corp") == ["corp"]  # never strip a name down to nothing


@pytest.mark.parametrize("raw,expected", [
    ("the Bombe", "Bombe"), ("The Treaty of Aldermoor", "Treaty of Aldermoor"), ("a Fellow of the Royal Society", "Fellow of the Royal Society"),
    ("An Post", "Post"), ("The", "The"), ("Theodore", "Theodore"), ("the  ", "the  "), ("Acme", "Acme"),
])
def test_strip_article(raw, expected):
    assert strip_article(raw) == expected
