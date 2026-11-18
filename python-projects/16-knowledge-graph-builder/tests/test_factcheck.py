"""Checking a claim against the documents: the model only reads the claim, code decides the verdict"""
import pytest
from fastapi.testclient import TestClient

from src.core import config
from src.core.database import get_db
from src.services import factcheck as fc
from src.services.llm import LLMBadOutput, LLMError
from tests.conftest import FakeEmbedder, FakeLLM

S = config.Settings(_env_file=None)


class ClaimLLM(FakeLLM):
    """Reads claims from a table of {claim text: parsed statement}"""
    name = "fake:claims"

    def __init__(self, table, bad_first=False):
        super().__init__()
        self.table, self.bad_first, self.prompts = table, bad_first, []

    def generate_json(self, system, prompt, schema, max_tokens=None):
        assert system == fc.CLAIM_SYSTEM
        self.prompts.append(prompt)
        if self.bad_first and len(self.prompts) == 1:
            raise LLMBadOutput("x")
        r = self.table[prompt.removeprefix("Claim: ")]
        if isinstance(r, Exception):
            raise r
        return r


def parsed(s, r, o, start="", end=""):
    return {"subject": s, "relation": r, "object": o, "start": start, "end": end}


@pytest.fixture
def firm(story):
    w = story
    w.acme, w.quillon = w.ent("Acme Corp"), w.ent("Quillon Systems")
    w.kim, w.dana, w.maria = w.ent("Kim Soto", "person"), w.ent("Dana Reyes", "person"), w.ent("Maria Lopez", "person")
    w.dun, w.val = w.ent("Dunmere", "place"), w.ent("Valcross", "place")
    w.hq = w.fact(w.quillon, "headquartered in", w.dun, frm="2004", to="2012", title="h1")
    w.cto = w.fact(w.dana, "was CTO of", w.acme, frm="2019", to="2022", title="h2")
    w.open_cto = w.fact(w.kim, "became CTO of", w.acme, frm="2023", title="h3")
    w.fact(w.acme, "employs", value="340 people", title="h2")
    w.fact(w.maria, "works at", w.quillon, title="h4")
    w.db.commit()
    return w


def check(w, claim, table, **kw):
    return fc.check(w.db, claim, llm=ClaimLLM(table, **kw), embedder=FakeEmbedder(), settings=S)


# ---------------------------------------------------------------- reading the claim

def test_a_claim_is_read_into_a_statement_and_the_dates_must_be_in_the_claim(story):
    llm = ClaimLLM({"Veltra Dynamics acquired Soro Labs in 2018.": parsed("Veltra Dynamics", "acquired", "Soro Labs", "2018", "2020")})
    c = fc.parse_claim(llm, "Veltra Dynamics acquired Soro Labs in 2018.")
    assert (c.subject, c.relation, c.object, c.start, c.end) == ("Veltra Dynamics", "acquired", "Soro Labs", "2018", "")        # 2020 is not in the claim: dropped


def test_dates_written_out_are_understood(story):
    t = {"Acme hired Kim on 15 March 2021.": parsed("Acme", "hired", "Kim", "March 15, 2021", "")}
    assert fc.parse_claim(ClaimLLM(t), "Acme hired Kim on 15 March 2021.").start == "2021-03-15"
    t = {"Acme hired Kim in March 2021.": parsed("Acme", "hired", "Kim", "2021-03", "")}
    assert fc.parse_claim(ClaimLLM(t), "Acme hired Kim in March 2021.").start == "2021-03"


def test_a_bad_reading_is_retried_once_then_given_up(story):
    t = {"Veltra bought Soro.": parsed("Veltra", "bought", "Soro")}
    llm = ClaimLLM(t, bad_first=True)
    assert fc.parse_claim(llm, "Veltra bought Soro.").subject == "Veltra" and len(llm.prompts) == 2
    assert fc.parse_claim(ClaimLLM({"x y z": {"subject": "", "relation": "r", "object": "o", "start": "", "end": ""}}), "x y z") is None
    both_bad = ClaimLLM({"p q r": LLMBadOutput("x")})
    assert fc.parse_claim(both_bad, "p q r") is None and len(both_bad.prompts) == 2


def test_an_unreadable_claim_is_unclear(story):
    r = check(story, "Hmm, maybe.", {"Hmm, maybe.": {"subject": "", "relation": "", "object": "", "start": "", "end": ""}})
    assert r["verdict"] == "unclear" and r["parsed"] is None and "could not be read" in r["summary"] and r["evidence"] == []


def test_the_model_is_unreachable(story):
    with pytest.raises(LLMError):
        check(story, "Veltra acquired Soro.", {"Veltra acquired Soro.": LLMError("down")})


def test_an_unknown_subject_is_unclear_not_false(story):
    r = check(story, "Zorn Inc acquired Soro Labs.", {"Zorn Inc acquired Soro Labs.": parsed("Zorn Inc", "acquired", "Soro Labs")})
    assert r["verdict"] == "unclear" and "“Zorn Inc” is not in the documents" in r["summary"]


# ---------------------------------------------------------------- the verdicts

def test_supported_with_the_quote_that_says_it(firm):
    r = check(firm, "Veltra Dynamics acquired Soro Labs in 2018.", {"Veltra Dynamics acquired Soro Labs in 2018.": parsed("Veltra Dynamics", "acquired", "Soro Labs", "2018")})
    assert r["verdict"] == "supported" and r["summary"].startswith("The documents say this: Veltra Dynamics acquired Soro Labs (2018..)")
    e = r["evidence"][0]
    assert e["role"] == "supports" and e["quote"] == "Veltra Dynamics acquired Soro Labs." and e["document_title"] == "d01" and e["valid_from"] == "2018"
    assert r["parsed"] == {"subject": "Veltra Dynamics", "relation": "acquired", "object": "Soro Labs", "start": "2018", "end": None}


def test_a_synonym_of_the_relation_still_supports(firm):
    r = check(firm, "Veltra Dynamics bought Soro Labs.", {"Veltra Dynamics bought Soro Labs.": parsed("Veltra Dynamics", "bought", "Soro Labs")})
    assert r["verdict"] == "supported"


def test_supported_but_the_dates_differ(firm):
    r = check(firm, "Veltra Dynamics acquired Soro Labs in 2015.", {"Veltra Dynamics acquired Soro Labs in 2015.": parsed("Veltra Dynamics", "acquired", "Soro Labs", "2015")})
    assert r["verdict"] == "supported_other_dates" and "other dates" in r["summary"] and r["evidence"][0]["role"] == "supports"


@pytest.mark.parametrize("claim_from,claim_to,fits", [
    ("2020", "", True),            # in the middle of 2019-2022
    ("2019", "", True), ("2022", "", True),
    ("2018", "", False), ("2023", "", False),
    ("2018", "2020", True), ("2021", "2025", True), ("2023", "2025", False), ("2010", "2018", False),
])
def test_which_claim_dates_fit_a_dated_fact(claim_from, claim_to, fits):
    assert fc.dates_fit_fact(claim_from, claim_to, "2019", "2022") is fits


def test_which_claim_dates_fit_open_and_undated_facts():
    assert fc.dates_fit_fact("2025", "", "2023", "") is True           # began 2023, no end stated: assumed to hold
    assert fc.dates_fit_fact("2020", "", "2023", "") is False          # before it began
    assert fc.dates_fit_fact("2020", "", "", "") is True and fc.dates_fit_fact("", "", "2023", "2024") is True
    assert fc.dates_fit_fact("2020", "", "", "2022") is True and fc.dates_fit_fact("2023", "", "", "2022") is False
    assert fc.dates_fit_fact("2019-06", "", "2019", "") is True


def test_the_relation_the_other_way_round_is_a_contradiction(firm):
    r = check(firm, "Soro Labs acquired Veltra Dynamics.", {"Soro Labs acquired Veltra Dynamics.": parsed("Soro Labs", "acquired", "Veltra Dynamics")})
    assert r["verdict"] == "contradicted" and "other way round" in r["summary"] and r["evidence"][0]["role"] == "contradicts"
    assert r["evidence"][0]["text"].startswith("Veltra Dynamics acquired Soro Labs")


def test_a_symmetric_relation_the_other_way_round_is_not(firm):
    firm.fact(firm.veltra, "partnered with", firm.acme, title="x")
    firm.db.commit()
    r = check(firm, "Acme Corp partnered with Veltra Dynamics.", {"Acme Corp partnered with Veltra Dynamics.": parsed("Acme Corp", "partnered with", "Veltra Dynamics")})
    assert r["verdict"] == "not_found"          # the documents state it only one way; that does not contradict


def test_a_different_object_for_a_one_at_a_time_relation_contradicts(firm):
    r = check(firm, "Quillon Systems is headquartered in Valcross.", {"Quillon Systems is headquartered in Valcross.": parsed("Quillon Systems", "is headquartered in", "Valcross")})
    assert r["verdict"] == "contradicted" and "something else" in r["summary"] and r["evidence"][0]["role"] == "contradicts"


def test_a_place_the_documents_do_not_know_still_clashes_with_the_one_they_name(firm):
    r = check(firm, "Quillon Systems is headquartered in Zorbia.", {"Quillon Systems is headquartered in Zorbia.": parsed("Quillon Systems", "is headquartered in", "Zorbia")})
    assert r["verdict"] == "contradicted" and "Dunmere" in r["summary"]
    other_time = check(firm, "Quillon Systems is headquartered in Zorbia since 2015.", {"Quillon Systems is headquartered in Zorbia since 2015.": parsed("Quillon Systems", "is headquartered in", "Zorbia", "2015")})
    assert other_time["verdict"] == "not_found"
    nothing = check(firm, "Acme Corp is headquartered in Zorbia.", {"Acme Corp is headquartered in Zorbia.": parsed("Acme Corp", "is headquartered in", "Zorbia")})
    assert nothing["verdict"] == "not_found"


def test_but_not_when_the_claim_is_about_another_time(firm):
    r = check(firm, "Quillon Systems is headquartered in Valcross since 2015.", {"Quillon Systems is headquartered in Valcross since 2015.": parsed("Quillon Systems", "is headquartered in", "Valcross", "2015")})
    assert r["verdict"] == "not_found"          # Dunmere was 2004-2012: no clash with 2015


def test_a_different_holder_for_a_one_at_a_time_role_contradicts(firm):
    r = check(firm, "Maria Lopez was the CTO of Acme Corp in 2021.", {"Maria Lopez was the CTO of Acme Corp in 2021.": parsed("Maria Lopez", "was CTO of", "Acme Corp", "2021")})
    assert r["verdict"] == "contradicted" and "someone else" in r["summary"] and r["evidence"][0]["text"].startswith("Dana Reyes was CTO of Acme Corp")


def test_the_right_holder_for_the_right_time_is_supported_and_the_wrong_time_is_not(firm):
    ok = check(firm, "Dana Reyes was CTO of Acme Corp in 2021.", {"Dana Reyes was CTO of Acme Corp in 2021.": parsed("Dana Reyes", "was CTO of", "Acme Corp", "2021")})
    assert ok["verdict"] == "supported"
    late = check(firm, "Dana Reyes was CTO of Acme Corp in 2024.", {"Dana Reyes was CTO of Acme Corp in 2024.": parsed("Dana Reyes", "was CTO of", "Acme Corp", "2024")})
    assert late["verdict"] == "supported_other_dates"


def test_nothing_in_the_documents_is_not_found_never_false(firm):
    r = check(firm, "Veltra Dynamics acquired Tamsen Labs.", {"Veltra Dynamics acquired Tamsen Labs.": parsed("Veltra Dynamics", "acquired", "Tamsen Labs")})
    assert r["verdict"] == "not_found" and r["summary"] == "The documents do not say this." and r["evidence"] == []


def test_a_different_relation_between_the_same_two_things_is_shown_as_related(firm):
    r = check(firm, "Veltra Dynamics acquired Pennant Robotics.", {"Veltra Dynamics acquired Pennant Robotics.": parsed("Veltra Dynamics", "acquired", "Pennant Robotics")})
    assert r["verdict"] == "not_found" and "connect the two in another way" in r["summary"]
    assert [e["role"] for e in r["evidence"]] == ["related"] and "invested in" in r["evidence"][0]["text"]


def test_a_value_is_supported_or_contradicted(firm):
    ok = check(firm, "Acme Corp employs 340 people.", {"Acme Corp employs 340 people.": parsed("Acme Corp", "employs", "340 people")})
    assert ok["verdict"] == "supported" and ok["parsed"]["object"] == "340 people"
    same_number = check(firm, "Acme Corp employs 340.", {"Acme Corp employs 340.": parsed("Acme Corp", "employs", "340")})
    assert same_number["verdict"] == "supported"
    bad = check(firm, "Acme Corp employs 400 people.", {"Acme Corp employs 400 people.": parsed("Acme Corp", "employs", "400 people")})
    assert bad["verdict"] == "contradicted" and "different value" in bad["summary"] and bad["evidence"][0]["text"] == "Acme Corp employs 340 people"
    none = check(firm, "Acme Corp sells 400 people.", {"Acme Corp sells 400 people.": parsed("Acme Corp", "sells", "400 people")})
    assert none["verdict"] == "not_found"


def test_a_value_with_other_dates_is_supported_with_other_dates(firm):
    firm.fact(firm.acme, "has revenue of", value="9 million", frm="2020", to="2021", title="r")
    firm.db.commit()
    r = check(firm, "Acme Corp has revenue of 9 million in 2025.", {"Acme Corp has revenue of 9 million in 2025.": parsed("Acme Corp", "has revenue of", "9 million", "2025")})
    assert r["verdict"] == "supported_other_dates"


def test_a_fact_a_person_left_out_is_not_evidence(firm):
    from src.models.conflict import Conflict
    from src.services import conflicts as cf
    ravi_cto = firm.fact(firm.ravi, "was CTO of", firm.acme, frm="2020", to="2021", title="z")
    firm.db.commit()
    claim = {"Ravi Anand was CTO of Acme Corp in 2021.": parsed("Ravi Anand", "was CTO of", "Acme Corp", "2021")}
    assert check(firm, "Ravi Anand was CTO of Acme Corp in 2021.", claim)["verdict"] == "supported"
    cf.run_detection(firm.db, owner_id=None)
    c = firm.db.query(Conflict).filter((Conflict.fact_a_id == ravi_cto.id) | (Conflict.fact_b_id == ravi_cto.id)).first()
    cf.resolve(firm.db, c.id, "keep_a" if c.fact_b_id == ravi_cto.id else "keep_b")           # trust Dana, give up Ravi's
    firm.db.commit()
    r = check(firm, "Ravi Anand was CTO of Acme Corp in 2021.", claim)
    assert r["verdict"] == "contradicted" and r["evidence"][0]["text"].startswith("Dana Reyes was CTO of Acme Corp")


# ---------------------------------------------------------------- the API

@pytest.fixture
def client(factory, firm, monkeypatch):
    import server

    def override():
        s = factory()
        try:
            yield s
        finally:
            s.close()

    server.app.dependency_overrides[get_db] = override
    monkeypatch.setattr("src.api.conflicts.get_settings", lambda: config.Settings(_env_file=None))
    monkeypatch.setattr("src.api.conflicts.get_embedder", lambda settings=None: FakeEmbedder())
    monkeypatch.setattr("src.api.conflicts.get_llm", lambda settings=None: ClaimLLM({"Veltra Dynamics acquired Soro Labs in 2018.": parsed("Veltra Dynamics", "acquired", "Soro Labs", "2018")}))
    c = TestClient(server.app)
    yield c
    server.app.dependency_overrides.clear()


def test_the_check_endpoint(client):
    r = client.post("/api/check", json={"claim": "Veltra Dynamics acquired Soro Labs in 2018."})
    assert r.status_code == 200 and r.json()["verdict"] == "supported" and r.json()["evidence"][0]["quote"]


def test_the_check_endpoint_validates_and_reports_a_down_model(client, monkeypatch):
    assert client.post("/api/check", json={"claim": "hi"}).status_code == 422
    assert client.post("/api/check", json={}).status_code == 422
    assert client.post("/api/check", json={"claim": "x" * 501}).status_code == 422

    def broken(settings=None):
        raise LLMError("Ollama is not running")
    monkeypatch.setattr("src.api.conflicts.get_llm", broken)
    r = client.post("/api/check", json={"claim": "Veltra Dynamics acquired Soro Labs in 2018."})
    assert r.status_code == 503 and "Ollama" in r.json()["detail"]


# ---------------------------------------------------------------- passive claims (found by the held-out run)

def test_a_passive_claim_is_turned_round_like_the_extraction_does(story):
    t = {"Soro Labs was acquired by Veltra Dynamics.": parsed("Soro Labs", "was acquired by", "Veltra Dynamics")}
    c = fc.parse_claim(ClaimLLM(t), "Soro Labs was acquired by Veltra Dynamics.")
    assert (c.subject, c.relation, c.object) == ("Veltra Dynamics", "acquired", "Soro Labs")


@pytest.mark.parametrize("relation", ["is led by", "were led by", "has been led by"])
def test_each_passive_form_is_turned_round(story, relation):
    t = {"x led by y": parsed("Wick", relation, "Greta")}
    c = fc.parse_claim(ClaimLLM(t), "x led by y")
    assert (c.subject, c.relation, c.object) == ("Greta", "led", "Wick")


def test_a_relation_that_merely_ends_in_by_alone_is_left_alone(story):
    t = {"Acme passed by Beta": parsed("Acme", "by", "Beta")}
    assert fc.parse_claim(ClaimLLM(t), "Acme passed by Beta").relation == "by"


def test_a_passive_claim_is_supported_by_the_active_fact(firm):
    r = check(firm, "Soro Labs was acquired by Veltra Dynamics.", {"Soro Labs was acquired by Veltra Dynamics.": parsed("Soro Labs", "was acquired by", "Veltra Dynamics")})
    assert r["verdict"] == "supported" and r["parsed"]["subject"] == "Veltra Dynamics"


def test_a_passive_claim_naming_another_holder_is_contradicted(firm):
    r = check(firm, "Acme Corp was led by Maria Lopez in 2021.", {"Acme Corp was led by Maria Lopez in 2021.": parsed("Acme Corp", "was led by", "Maria Lopez", "2021")})
    assert r["parsed"]["subject"] == "Maria Lopez" and r["parsed"]["relation"] == "led"


def test_a_holder_the_documents_do_not_know_clashes_with_the_ones_they_name(firm):
    r = check(firm, "Greta Lund was CTO of Acme Corp in 2021.", {"Greta Lund was CTO of Acme Corp in 2021.": parsed("Greta Lund", "was CTO of", "Acme Corp", "2021")})
    assert r["verdict"] == "contradicted" and "someone else" in r["summary"] and r["evidence"][0]["role"] == "contradicts"
    assert r["evidence"][0]["text"].startswith("Dana Reyes was CTO of Acme Corp") and r["evidence"][0]["quote"]
    assert any("not in the documents, but Acme Corp has other holders" in w for w in r["reasoning"])


def test_but_not_for_a_time_when_nobody_held_it_or_for_a_relation_with_several(firm):
    old = check(firm, "Greta Lund was CTO of Acme Corp in 2005.", {"Greta Lund was CTO of Acme Corp in 2005.": parsed("Greta Lund", "was CTO of", "Acme Corp", "2005")})
    assert old["verdict"] == "unclear"
    many = check(firm, "Greta Lund invested in Acme Corp.", {"Greta Lund invested in Acme Corp.": parsed("Greta Lund", "invested in", "Acme Corp")})
    assert many["verdict"] == "unclear"
    nothing = check(firm, "Greta Lund was CTO of Zorn Ltd.", {"Greta Lund was CTO of Zorn Ltd.": parsed("Greta Lund", "was CTO of", "Zorn Ltd")})
    assert nothing["verdict"] == "unclear"
