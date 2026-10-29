import pytest

from responder import clean_response, decode_email_bytes


@pytest.mark.parametrize("raw,expected", [
    ("Here is a potential email response:\n\nDear A,\n\nHi.\n\nBest,\nB", "Dear A,\n\nHi.\n\nBest,\nB"),
    ("Here's a follow-up email based on the original context:\n\nHi X,\nYo", "Hi X,\nYo"),
    ("Sure! Here is the email:\n\nHi", "Hi"),
    ("```\nHi Bob,\nThanks\n```", "Hi Bob,\nThanks"),
    ("Hi Bob,\n\nThanks.\n\nBest,\nAl\n\nNote: you may want to personalize this.", "Hi Bob,\n\nThanks.\n\nBest,\nAl"),
    ("Hi Bob,\n\nThanks.\n\nFeel free to adjust the tone.", "Hi Bob,\n\nThanks."),
    ("\n\n  Hi Bob  \n\n", "Hi Bob"),
    ("", ""),
])
def test_clean_response(raw, expected):
    assert clean_response(raw) == expected


def test_clean_keeps_legit_note_in_body():
    text = "Hi Bob,\n\nNote that the meeting moved to 3pm.\n\nBest,\nAl"
    assert clean_response(text) == text


def test_only_preamble_becomes_empty():
    assert clean_response("Here is the email:") == ""


def test_decode_utf8_and_bom():
    assert decode_email_bytes("café".encode("utf-8")) == "café"
    assert decode_email_bytes(b"\xef\xbb\xbfHi") == "Hi"


def test_decode_cp1252_outlook_export():
    text = "I don’t think “Tuesday” works – José"  # curly quotes/dash are 0x92/0x93/0x96 in cp1252
    assert decode_email_bytes(text.encode("cp1252")) == text


def test_decode_rejects_binary():
    with pytest.raises(ValueError):
        decode_email_bytes(bytes(range(256)))
