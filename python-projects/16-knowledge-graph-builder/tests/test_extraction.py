from collections import Counter

import pytest

from src.services import extraction
from src.services.extraction import check_candidate, extract_chunk, fix_passive, normalize_predicate, word_order_ok
from src.services.llm import LLMBadOutput, LLMError
from tests.conftest import FakeLLM, rel

CHUNK = ("Acme Corp, founded in 2010 by Maria Lopez, acquired Beta Systems in March 2020. "
         "Dana Reyes served as CTO of Acme from 2019 to 2022. She later left. "
         "Revenue of Acme Inc. was 12M in 2021.")
S1 = "Acme Corp, founded in 2010 by Maria Lopez, acquired Beta Systems in March 2020."
S2 = "Dana Reyes served as CTO of Acme from 2019 to 2022."


def check(raw, chunk=CHUNK, context=True):
    rej, adj = Counter(), Counter()
    return check_candidate(raw, chunk, rej, context, adj), rej, adj


def good(**kw):
    base = rel("Acme Corp", "acquired", "Beta Systems", S1, "March 2020", "", "organization", "organization")
    base.update(kw)
    return base


def test_happy_path_normalises_everything():
    f, rej, _ = check(good(predicate="Acquired!"))
    assert (f.subject, f.predicate, f.object) == ("Acme Corp", "acquired", "Beta Systems")
    assert f.valid_from == "2020-03" and f.valid_to == "" and f.evidence == S1
    assert not rej


def test_evidence_must_be_in_the_text_and_is_replaced_by_the_original_wording():
    assert check(good(evidence="Acme Corp bought Beta Systems."))[1] == Counter(evidence_not_in_text=1)
    f, *_ = check(good(evidence=S1.lower().replace("  ", " ")))
    assert f.evidence == S1


def test_evidence_must_exist_and_be_short():
    assert check(good(evidence=""))[1]["no_evidence"] == 1
    long_chunk = S1 + " " + "Filler words go here. " * 40
    assert check(good(evidence=long_chunk.strip()), long_chunk)[1]["evidence_too_long"] == 1


def test_subject_and_object_must_appear_in_the_quote():
    f, rej, _ = check(good(subject="Zed Corp"))
    assert f is None and rej["subject_not_in_evidence"] == 1
    f, rej, _ = check(good(object="Gamma Ltd"))
    assert f is None and rej["object_not_in_evidence"] == 1


def test_legal_suffix_differences_are_fine():
    f, *_ = check(good(subject="Acme Inc."))
    assert f is not None


@pytest.mark.parametrize("name", ["He", "she", "It", "they", "The company", "the firm"])
def test_pronouns_and_generic_names_are_refused(name):
    f, rej, _ = check(rel(name, "left", "Acme Corp", "She later left. Revenue of Acme Inc. was 12M in 2021.", otype="organization"))
    assert f is None and rej["pronoun_or_generic_name"] == 1


@pytest.mark.parametrize("pred", ["is", "has", "related to", "associated with", "was"])
def test_vague_predicates_are_refused(pred):
    f, rej, _ = check(good(predicate=pred))
    assert f is None and rej["vague_predicate"] == 1


def test_long_predicates_are_refused():
    f, rej, _ = check(good(predicate="signed a very long supply contract with"))
    assert f is None and rej["predicate_too_long"] == 1


def test_malformed_items_are_counted_not_crashed_on():
    for raw in ("text", None, 5, {}, {"subject": "A"}, good(subject="", predicate="x")):
        f, rej, _ = check(raw)
        assert f is None and rej["malformed"] == 1


def test_subject_equal_to_object_is_refused():
    f, rej, _ = check(good(object="Acme Corp"))
    assert f is None and rej["subject_equals_object"] == 1


def test_value_must_appear_in_the_quote():
    q = "Revenue of Acme Inc. was 12M in 2021."
    f, rej, _ = check(rel("Acme Inc.", "reported revenue", "12M", q, "2021", otype="value", stype="organization"))
    assert f.object_type == "value" and f.object == "12M" and f.valid_from == "2021"
    f, rej, _ = check(rel("Acme Inc.", "reported revenue", "15M", q, "2021", otype="value", stype="organization"))
    assert f is None and rej["value_not_in_evidence"] == 1


def test_dates_not_in_the_quote_are_dropped_but_the_fact_is_kept():
    f, _, adj = check(good(start="2018"))
    assert f is not None and f.valid_from == "" and adj["date_dropped_not_in_evidence"] == 1
    f, _, adj = check(rel("Dana Reyes", "served as cto of", "Acme", S2, "2019", "2023", otype="organization"))
    assert (f.valid_from, f.valid_to) == ("2019", "") and adj["date_dropped_not_in_evidence"] == 1


def test_start_after_end_drops_both_dates():
    f, _, adj = check(rel("Dana Reyes", "served as cto of", "Acme", S2, "2022", "2019", otype="organization"))
    assert (f.valid_from, f.valid_to) == ("", "") and adj["date_dropped_start_after_end"] == 1


def test_unparseable_dates_become_empty():
    f, *_ = check(good(start="last spring"))
    assert f.valid_from == ""


@pytest.mark.parametrize("pred,expected", [
    ("was founded by", ("founded", True)), ("is owned by", ("owned", True)), ("has been bought by", ("bought", True)),
    ("founded", ("founded", False)), ("works at", ("works at", False)), ("by", ("by", False)),
    ("was acquired", ("acquired", False)),
])
def test_fix_passive(pred, expected):
    assert fix_passive(pred) == expected


def test_passive_predicate_swaps_subject_and_object():
    f, _, adj = check(rel("Beta Systems", "was acquired by", "Acme Corp", S1, "March 2020", otype="organization",
                          stype="organization"))
    assert (f.subject, f.predicate, f.object) == ("Acme Corp", "acquired", "Beta Systems") and adj["passive_swapped"] == 1


def test_passive_with_a_value_is_refused():
    f, rej, _ = check(rel("Acme Inc.", "was valued by", "12M", "Revenue of Acme Inc. was 12M in 2021.", otype="value"))
    assert f is None and rej["passive_with_value"] == 1


def test_quote_is_widened_to_the_previous_sentence_when_it_holds_the_name():
    chunk = "Marcus Veld joined Nordwind in 2019. He became CTO of Nordwind in 2020."
    raw = rel("Marcus Veld", "became cto of", "Nordwind", "He became CTO of Nordwind in 2020.", "2020", otype="organization")
    f, _, adj = check(raw, chunk)
    assert f is not None and f.evidence == chunk and adj["quote_widened_to_previous_sentence"] == 1
    f, rej, _ = check(raw, chunk, context=False)
    assert f is None and rej["subject_not_in_evidence"] == 1


def test_widening_goes_back_only_one_sentence():
    chunk = "Marcus Veld is here. Filler sentence number one. He became CTO of Nordwind in 2020."
    raw = rel("Marcus Veld", "became cto of", "Nordwind", "He became CTO of Nordwind in 2020.", otype="organization")
    f, rej, _ = check(raw, chunk)
    assert f is None and rej["subject_not_in_evidence"] == 1


def test_normalize_predicate():
    assert normalize_predicate("  Signed  A Contract, with! ") == "signed a contract with"
    assert normalize_predicate(None) == ""


# ---------- extract_chunk with a scripted model ----------

def test_extract_chunk_keeps_checked_facts_and_counts_the_rest():
    llm = FakeLLM(extract=lambda p: {"relations": [good(), good(subject="Zed Corp"), good()]})
    r = extract_chunk(llm, CHUNK, verify=False)
    assert len(r.facts) == 1 and r.candidates == 3
    assert r.rejected == Counter(subject_not_in_evidence=1, duplicate_in_chunk=1)


def test_verification_removes_unsupported_facts_and_marks_the_rest_verified():
    verdicts = iter(["supported", "unsupported"])
    raws = [good(), good(predicate="bought")]
    llm = FakeLLM(extract=lambda p: {"relations": raws}, verify=lambda p: next(verdicts))
    r = extract_chunk(llm, CHUNK, verify=True)
    assert [f.predicate for f in r.facts] == ["acquired"] and r.facts[0].verified
    assert r.rejected == Counter(verify_unsupported=1) and llm.count("verify") == 2


def test_verification_off_makes_no_extra_calls_and_marks_nothing_verified():
    llm = FakeLLM(extract=lambda p: {"relations": [good()]})
    r = extract_chunk(llm, CHUNK, verify=False)
    assert llm.count("verify") == 0 and not r.facts[0].verified


def test_unknown_verdict_counts_as_unsupported():
    llm = FakeLLM(extract=lambda p: {"relations": [good()]}, verify=lambda p: {"answer": "maybe"})
    assert extract_chunk(llm, CHUNK).rejected == Counter(verify_unsupported=1)


def test_verification_prompt_names_the_claim_and_the_quote():
    llm = FakeLLM(extract=lambda p: {"relations": [good()]})
    extract_chunk(llm, CHUNK)
    prompt = next(p for k, p in llm.calls if k == "verify")
    assert S1 in prompt and "Acme Corp" in prompt and "acquired" in prompt and "Beta Systems" in prompt


def test_bad_json_is_retried_once_then_reported():
    answers = iter([LLMBadOutput("broken"), {"relations": [good()]}])
    llm = FakeLLM(extract=lambda p: next(answers))
    r = extract_chunk(llm, CHUNK, verify=False)
    assert len(r.facts) == 1 and r.error is None
    llm = FakeLLM(extract=lambda p: LLMBadOutput("broken"))
    r = extract_chunk(llm, CHUNK, verify=False)
    assert r.facts == [] and r.error == "broken" and llm.count("extract") == 2


def test_answer_without_a_relations_list_is_an_error_for_that_chunk():
    r = extract_chunk(FakeLLM(extract=lambda p: {"relations": "none"}), CHUNK, verify=False)
    assert r.error and r.facts == []


def test_connection_errors_are_not_swallowed():
    with pytest.raises(LLMError):
        extract_chunk(FakeLLM(extract=lambda p: LLMError("Cannot reach Ollama")), CHUNK)


def test_gleaning_adds_missed_facts_and_shows_the_model_what_was_found():
    second = rel("Dana Reyes", "served as cto of", "Acme", S2, "2019", "2022", otype="organization")
    answers = iter([{"relations": [good()]}, {"relations": [second]}, {"relations": []}])
    prompts = []

    def script(p):
        prompts.append(p)
        return next(answers)

    r = extract_chunk(FakeLLM(extract=script), CHUNK, verify=False, gleaning_passes=3)
    assert [f.subject for f in r.facts] == ["Acme Corp", "Dana Reyes"] and r.adjusted["found_by_gleaning"] == 1
    assert "Facts already found" in prompts[1] and "Acme Corp | acquired | Beta Systems" in prompts[1]
    assert len(prompts) == 3  # stopped after a pass found nothing new, despite 3 allowed


def test_failed_gleaning_call_keeps_what_was_found():
    answers = iter([{"relations": [good()]}, LLMBadOutput("x"), LLMBadOutput("x")])
    r = extract_chunk(FakeLLM(extract=lambda p: (_ for _ in ()).throw(a) if isinstance(a := next(answers), Exception) else a),
                      CHUNK, verify=False, gleaning_passes=1)
    assert len(r.facts) == 1 and r.rejected["gleaning_call_failed"] == 1


def test_gleaning_does_not_repeat_known_facts():
    llm = FakeLLM(extract=lambda p: {"relations": [good()]})
    r = extract_chunk(llm, CHUNK, verify=False, gleaning_passes=2)
    assert len(r.facts) == 1 and r.rejected["duplicate_in_chunk"] == 1


def test_fact_count_is_capped(monkeypatch):
    monkeypatch.setattr(extraction, "MAX_FACTS_PER_CHUNK", 2)
    raws = [good(object=o) for o in ("Beta Systems",)] + [
        rel("Acme Corp", f"verb{i}", "Beta Systems", S1, otype="organization", stype="organization") for i in range(5)]
    r = extract_chunk(FakeLLM(extract=lambda p: {"relations": raws}), CHUNK, verify=False)
    assert len(r.facts) == 2 and r.rejected["too_many_facts"] == 4


class FlakyVerifier(FakeLLM):
    """Extraction works; each verification call takes the next scripted answer (an exception is raised)"""

    def __init__(self, answers):
        super().__init__(extract=lambda p: {"relations": [good()]})
        self.answers = iter(answers)

    def generate_json(self, system, prompt, schema):
        if system != extraction.VERIFY_SYSTEM:
            return super().generate_json(system, prompt, schema)
        self.calls.append(("verify", prompt))
        answer = next(self.answers)
        if isinstance(answer, Exception):
            raise answer
        return {"answer": "yes" if answer == "supported" else "no"}


def test_verification_retries_once_on_bad_output_then_gives_up():
    llm = FlakyVerifier([LLMBadOutput("x"), "supported"])
    r = extract_chunk(llm, CHUNK)
    assert len(r.facts) == 1 and llm.count("verify") == 2

    llm = FlakyVerifier([LLMBadOutput("x"), LLMBadOutput("y"), "supported"])
    r = extract_chunk(llm, CHUNK)
    assert r.facts == [] and r.rejected["verify_unsupported"] == 1 and llm.count("verify") == 2


@pytest.mark.parametrize("subject,obj,quote,expected", [
    ("Acme", "Beta", "Acme acquired Beta in 2020.", True),                                   # active
    ("Acme", "Beta", "Beta was acquired by Acme in 2020.", True),                           # passive, claim written correctly
    ("Beta", "Acme", "Beta was acquired by Acme in 2020.", False),                          # passive read as active: reversed
    ("Beta", "Acme", "Acme acquired Beta in 2020.", False),                                  # active read backwards
    ("Acme", "Beta", "Acme, which is based in Oslo, was bought by Beta.", False),
    ("Acme", "Oslo", "Acme, which is based in Oslo, was bought by Beta.", True),             # 'by' comes after Oslo
    ("Widget-X Sensor", "Widget-W", "The Widget-X replaced the Widget-W in 2021.", True),   # names share a first word
    ("Widget-W", "Widget-X Sensor", "The Widget-X replaced the Widget-W in 2021.", False),
    ("Acme", "Beta", "Acme was founded in 2010 by Maria. Beta is a rival.", True),           # different sentences: cannot judge
    ("Acme", "Gamma", "Acme exists.", True),                                                 # name missing: cannot judge
    ("Acme Corp", "Beta Systems", "Acme Corp, founded in 2010 by Maria Lopez, acquired Beta Systems.", True),  # 'by' inside a clause
    ("Acme Corp", "Maria Lopez", "Acme Corp was founded in 2010 by Maria Lopez.", False),
    ("Maria Lopez", "Acme Corp", "Acme Corp, founded in 2010 by Maria Lopez, acquired Beta Systems.", True),
    ("Acme", "Acme Corp", "Acme Corp was founded by Maria.", True),                           # both names start at the same word
    ("The University", "Queen Margit", "The University was founded by the Queen Margit.", False),  # 'by the <object>'
    ("Queen Margit", "The University", "The University was founded by the Queen Margit.", True),
])
def test_word_order_ok(subject, obj, quote, expected):
    assert word_order_ok(subject, obj, quote) is expected


def test_reversed_facts_are_dropped_without_any_model_call():
    raws = [rel("Maria Lopez", "founded", "Acme Corp", S1, otype="organization"),   # fine: passive 'by Maria Lopez'
            rel("Acme Corp", "founded", "Maria Lopez", S1, otype="person", stype="organization")]  # reversed
    llm = FakeLLM(extract=lambda p: {"relations": raws})
    r = extract_chunk(llm, CHUNK, verify=False)
    assert [(f.subject, f.object) for f in r.facts] == [("Maria Lopez", "Acme Corp")]
    assert r.rejected == Counter(reversed_word_order=1) and llm.count("verify") == 0


def test_value_facts_skip_the_word_order_check():
    q = "In 2021, revenue of Acme Inc. was 12M."
    llm = FakeLLM(extract=lambda p: {"relations": [rel("Acme Inc.", "reported revenue", "12M", q, "2021", otype="value", stype="organization")]})
    assert len(extract_chunk(llm, q, verify=False).facts) == 1


def test_widened_quote_stays_short():
    long_first = "Marcus Veld " + "worked on many different and varied projects over the years " * 8 + "at the firm."
    chunk = long_first + " He became CTO of Nordwind in 2020."
    assert len(long_first) > 400
    raw = rel("Marcus Veld", "became cto of", "Nordwind", "He became CTO of Nordwind in 2020.", otype="organization")
    f, rej, _ = check(raw, chunk)
    assert f is None and rej["subject_not_in_evidence"] == 1


def test_widened_quote_accepts_a_surname_when_the_full_name_is_in_the_passage():
    chunk = "Alan Turing was born in 1912. During the war, Turing worked at Bletchley Park. He designed the Bombe."
    raw = rel("Alan Turing", "designed", "Bombe", "He designed the Bombe.", otype="product")
    f, _, adj = check(raw, chunk)
    assert f is not None and f.evidence == "During the war, Turing worked at Bletchley Park. He designed the Bombe."
    assert adj["quote_widened_to_previous_sentence"] == 1


def test_same_statement_found_with_and_without_dates_keeps_the_dated_one():
    undated = rel("Acme Corp", "acquired", "Beta Systems", S1, otype="organization", stype="organization")
    dated = rel("Acme Corp", "acquired", "Beta Systems", S1, "March 2020", otype="organization", stype="organization")
    for raws, expected_adjusted in (([undated, dated], 1), ([dated, undated], 0)):
        r = extract_chunk(FakeLLM(extract=lambda p: {"relations": raws}), CHUNK, verify=False)
        assert len(r.facts) == 1 and r.facts[0].valid_from == "2020-03"
        assert r.adjusted["undated_merged_into_dated"] == expected_adjusted
    other_period = rel("Acme Corp", "acquired", "Beta Systems", S1, "2010", otype="organization", stype="organization")
    r = extract_chunk(FakeLLM(extract=lambda p: {"relations": [dated, other_period]}), CHUNK, verify=False)
    assert [f.valid_from for f in r.facts] == ["2020-03", "2010"]  # different periods are different facts
