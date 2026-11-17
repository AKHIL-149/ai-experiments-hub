"""Time: what dates say about a period, and which period a question asks about"""
from datetime import date

import pytest

from src.services import ask as ask_mod
from src.services import graph_query as gq
from src.services import temporal as tm
from src.services.temporal import classify, parse_period, parse_time, window_between, window_of
from tests.conftest import FakeEmbedder, ScriptedLLM

TODAY = date(2026, 11, 16)


# ---------------------------------------------------------------- dates as ranges

@pytest.mark.parametrize("value,first,last", [
    ("2021", date(2021, 1, 1), date(2021, 12, 31)),
    ("2021-02", date(2021, 2, 1), date(2021, 2, 28)),
    ("2020-02", date(2020, 2, 1), date(2020, 2, 29)),          # leap year
    ("2021-03-15", date(2021, 3, 15), date(2021, 3, 15)),
])
def test_a_date_is_the_range_of_days_it_could_mean(value, first, last):
    assert parse_period(value) == (first.toordinal(), last.toordinal())


@pytest.mark.parametrize("value", ["", None, "soon", "21", "2021-13", "2021-02-30", "2021-1", "March 2021", "2021/03"])
def test_anything_that_is_not_a_stored_date_is_no_range(value):
    assert parse_period(value) is None


# ---------------------------------------------------------------- classify

W2021 = window_of("2021")


@pytest.mark.parametrize("frm,to,expected", [
    ("2020", "2022", "during"),          # the stated dates cover the whole year
    ("2016", "2019", "outside"),         # ended before
    ("2022", "", "outside"),             # began after
    ("2022", "2024", "outside"),
    ("2016", "", "open"),                # began earlier, nothing says it ended
    ("2021", "", "overlaps"),            # began inside the year
    ("2021", "2021", "overlaps"),        # a year-only start and end might not cover every day
    ("2019", "2021", "overlaps"),        # ended inside the year
    ("", "2022", "overlaps"),            # "until 2022": no start known, so it may cover the year
    ("", "2020", "outside"),             # ended before
    ("", "", "undated"),
    (None, None, "undated"),
])
def test_status_of_a_fact_for_a_year(frm, to, expected):
    assert classify(frm, to, W2021) == expected


def test_month_precision_decides_what_a_year_cannot():
    w = window_of("2021-06")
    assert classify("2021-03", "2021-09", w) == "during"
    assert classify("2021-07", "", w) == "outside"
    assert classify("2021-06-30", "", w) == "overlaps"
    assert classify("2021", "", w) == "overlaps"           # which month in 2021 is not stated
    assert classify("2021-05", "", w) == "open"
    assert classify("2021-01", "2021-05", w) == "outside"


def test_a_range_window_counts_any_overlap_and_a_covering_fact_as_during():
    w = window_between("2015", "2018")
    assert classify("2014", "2019", w) == "during"
    assert classify("2016", "2017", w) == "overlaps"
    assert classify("2017", "2020", w) == "overlaps"
    assert classify("2010", "2014", w) == "outside"
    assert classify("2019", "", w) == "outside"
    assert classify("2010", "", w) == "open"


def test_before_and_after_windows_are_open_ended():
    before = parse_time("before 2020", TODAY).window
    assert classify("2015", "2017", before) == "overlaps" and classify("2020", "", before) == "outside"
    assert classify("2019", "", before) == "overlaps" and classify("2021", "2022", before) == "outside"
    after = parse_time("after 2019", TODAY).window
    assert classify("2020", "", after) == "overlaps" and classify("2015", "2018", after) == "outside"
    assert classify("2015", "", after) == "open"
    assert classify("2019", "", after) == "open"            # began inside 2019, which is before "after 2019"... and no end stated
    assert classify("", "", after) == "undated"


def test_now_leaves_out_what_ended_and_keeps_what_is_open():
    now = parse_time("who is the current CEO", TODAY).window
    assert classify("2015", "2018", now) == "outside"
    assert classify("2020", "", now) == "open"
    assert classify("2026-01", "", now) == "open"
    assert classify("2026", "", now) == "overlaps"          # "2026" might be after today
    assert classify("2027", "", now) == "outside"


def test_every_status_has_words_for_people():
    for s in tm.STATUSES:
        assert tm.describe(s, W2021)
    assert "2021" in tm.describe("during", W2021) and "no end date" in tm.describe("open", W2021)


# ---------------------------------------------------------------- the time in a question

def lab(q):
    t = parse_time(q, TODAY)
    return None if t is None else (t.window.label, t.window.kind, t.question)


@pytest.mark.parametrize("question,expected", [
    ("Who was the CTO of Acme in 2021?", ("2021", "in", "Who was the CTO of Acme?")),
    ("Who was CTO of Acme during 2021?", ("2021", "in", "Who was CTO of Acme?")),
    ("Who was the CTO of Acme as of 2021?", ("2021", "in", "Who was the CTO of Acme?")),
    ("Who led Acme in March 2021?", ("2021-03", "in", "Who led Acme?")),
    ("Who led Acme in March, 2021?", ("2021-03", "in", "Who led Acme?")),
    ("Who led Acme on 15 March 2021?", ("2021-03-15", "in", "Who led Acme?")),
    ("Who led Acme on March 15th, 2021?", ("2021-03-15", "in", "Who led Acme?")),
    ("Who led Acme in 2021-03?", ("2021-03", "in", "Who led Acme?")),
    ("Who was CEO between 2015 and 2018?", ("2015 to 2018", "between", "Who was CEO?")),
    ("Who was CEO from March 2016 to June 2018?", ("2016-03 to 2018-06", "between", "Who was CEO?")),
    ("Who was CEO before 2020?", ("before 2020", "before", "Who was CEO?")),
    ("Who was CEO prior to 2020?", ("before 2020", "before", "Who was CEO?")),
    ("Who was CEO until 2020?", ("until 2020", "before", "Who was CEO?")),
    ("Which companies did Acme buy after 2019?", ("after 2019", "after", "Which companies did Acme buy?")),
    ("Which companies did Acme buy since 2019?", ("since 2019", "after", "Which companies did Acme buy?")),
    ("What did Acme do in the 1990s?", ("the 1990s", "in", "What did Acme do?")),
    ("Who is the current CTO of Acme?", ("now (2026-11-16)", "now", "Who is the CTO of Acme?")),
    ("Who is the CTO of Acme now?", ("now (2026-11-16)", "now", "Who is the CTO of Acme?")),
    ("Who is currently the CTO of Acme?", ("now (2026-11-16)", "now", "Who is the CTO of Acme?")),
    ("Who was the CTO of Acme in 2021, according to the news?", ("2021", "in", "Who was the CTO of Acme, according to the news?")),
])
def test_the_time_a_question_names(question, expected):
    assert lab(question) == expected


@pytest.mark.parametrize("question", [
    "Who founded Acme?",
    "When did Acme acquire Beta?",              # asks for a date, names none
    "Who attended Expo 2020?",                   # a year without a time word is part of a name
    "What happened at the 2020 summit?",
    "Who has 2021 employees?",
    "Who was CEO in the nineties?",             # not supported: no guess
    "Who was CEO in 99999?",
    "Who was CEO in 20211?",
    "Who led Acme in 2021-13?",
    "Which president founded Acme?",            # 'present' inside a word
    "Who knows Acme?",                          # 'now' inside a word
])
def test_a_question_without_a_time_has_none(question):
    assert parse_time(question, TODAY) is None


def test_only_the_first_time_is_used():
    assert lab("Who was CEO in 2015 and CTO in 2018?")[:2] == ("2015", "in")


def test_the_window_can_be_shown_to_people_and_apis():
    w = parse_time("Who was CEO in March 2021?", TODAY).window
    assert w.to_dict() == {"label": "2021-03", "kind": "in", "from": "2021-03-01", "to": "2021-03-31"}
    assert parse_time("before 2020", TODAY).window.to_dict()["from"] is None


def test_a_bad_date_in_a_phrase_is_not_a_time():
    assert parse_time("Who was CEO between 2015 and 2021-13?", TODAY) is None
    assert window_of("2021-13") is None and window_between("2015", "x") is None


# ---------------------------------------------------------------- the edges of each comparison (to the day)

def test_a_range_may_be_written_backwards():
    assert window_between("2018", "2015") == window_between("2015", "2018")
    assert parse_time("Who was CEO between 2018 and 2015?", TODAY).window == window_between("2015", "2018")


def test_touching_on_a_single_day_counts_as_overlap():
    day = window_of("2021-06-15")
    assert classify("2020-01-01", "2021-06-15", day) == "during"        # it ended on that very day: it covered the day
    assert classify("2021-06-15", "2022-01-01", day) == "during"        # it began on that very day
    assert classify("2021-06-15", "", day) == "overlaps"                # began that day, no end: might have started later in the day... of the same day, so not "open"
    assert classify("2020-01-01", "2021-06-14", day) == "outside"
    assert classify("2021-06-16", "2022-01-01", day) == "outside"
    assert classify("2021-06-14", "", day) == "open"                    # began the day before, nothing says it ended


def test_a_fact_covers_a_period_only_from_its_first_to_its_last_day():
    june = window_of("2021-06-01")
    assert classify("2021-06-01", "2021-12-31", june) == "during"
    assert classify("2021-05-01", "2021-12-31", window_of("2021-06")) == "during"
    assert classify("2021-06-02", "2021-12-31", june) == "outside"      # began the day after
    assert classify("2021-05-31", "2021-06-01", june) == "during"
    assert classify("2021-05-31", "2021-05-31", june) == "outside"
    day = window_of("2021-06-30")
    assert classify("2021-01-01", "2021-06-30", day) == "during"
    assert classify("2021-01-01", "2021-06-29", day) == "outside"


def test_a_year_only_start_or_end_is_not_sharp_enough_to_cover_a_month():
    assert classify("2020", "2022", window_of("2020-06")) == "overlaps"          # which month in 2020 it began is not stated
    assert classify("2019", "2021", window_of("2021-12")) == "overlaps"           # nor when in 2021 it ended
    assert classify("2019", "2022", window_of("2021-12")) == "during"


def test_until_and_since_mean_the_whole_year_named():
    until = parse_time("Who led it until 2020?", TODAY).window
    assert until.to_dict()["to"] == "2020-12-31" and classify("2020-06", "", until) == "overlaps"
    before = parse_time("Who led it before 2020?", TODAY).window
    assert before.to_dict()["to"] == "2019-12-31" and classify("2020-06", "", before) == "outside"
    since = parse_time("Who led it since 2019?", TODAY).window
    assert since.to_dict()["from"] == "2019-01-01" and classify("2019-06", "", since) == "overlaps"
    after = parse_time("Who led it after 2019?", TODAY).window
    assert after.to_dict()["from"] == "2020-01-01" and classify("2019-06", "", after) == "open"


@pytest.mark.parametrize("word,kind", [("till", "before"), ("up to", "before"), ("until", "before"), ("prior to", "before"),
                                        ("following", "after"), ("after", "after"), ("since", "after"), ("during", "in"), ("throughout", "in")])
def test_each_way_of_saying_a_time_is_understood(word, kind):
    t = parse_time(f"Who led Acme {word} 2020?", TODAY)
    assert t is not None and t.window.kind == kind and t.question == "Who led Acme?"


def test_a_decade_is_ten_whole_years():
    w = parse_time("What did Acme do in the 1990s?", TODAY).window
    assert w.to_dict() == {"label": "the 1990s", "kind": "in", "from": "1990-01-01", "to": "1999-12-31"}


def test_the_earliest_time_in_the_question_is_the_one_used_whatever_its_kind():
    assert lab("Who was CEO before 2010 and in 2015?")[:2] == ("before 2010", "before")
    assert lab("Who was CEO in 2015 and before 2010?")[:2] == ("2015", "in")


def test_the_question_loses_its_time_words_and_keeps_the_rest_tidy():
    assert parse_time("Who led Acme in 2021 ?", TODAY).question == "Who led Acme?"
    assert parse_time("In 2021, who led Acme?", TODAY).question == "who led Acme?"
    assert parse_time("Who led   Acme   in 2021?", TODAY).question == "Who led Acme?"


# ---------------------------------------------------------------- the index leaves out what the dates exclude

@pytest.fixture
def firm(world):
    """Acme's CTOs over time, plus a fact with no date"""
    w, db = world, world.db
    w.acme = w.ent("Acme Corp")
    w.maria, w.dana, w.kim, w.omar = (w.ent(n, "person") for n in ("Maria Lopez", "Dana Reyes", "Kim Soto", "Omar Haddad"))
    w.f_maria = w.fact(w.maria, "was CTO of", w.acme, frm="2012", to="2019", title="hist")
    w.f_dana = w.fact(w.dana, "was CTO of", w.acme, frm="2019", to="2022", title="hist")
    w.f_kim = w.fact(w.kim, "became CTO of", w.acme, frm="2023", title="news")
    w.f_omar = w.fact(w.omar, "advises", w.acme, title="news")
    w.f_hq = w.fact(w.acme, "has headquarters in", value="Oslo", title="news")
    db.commit()
    return w


def ids(index):
    return {f.id for f in index.facts.values()}


def test_a_period_removes_facts_that_cannot_have_held_and_marks_the_rest(firm):
    idx = gq.GraphIndex(firm.db, window=window_of("2021"))
    assert ids(idx) == {firm.f_dana.id, firm.f_omar.id, firm.f_hq.id}
    assert idx.facts[firm.f_dana.id].time == "during"
    assert idx.facts[firm.f_omar.id].time == "undated"
    assert sorted(idx.excluded) == sorted(["Maria Lopez was CTO of Acme Corp (2012..2019)", "Kim Soto became CTO of Acme Corp (2023..)"])


def test_without_a_period_nothing_is_left_out_or_marked(firm):
    idx = gq.GraphIndex(firm.db)
    assert len(idx.facts) == 5 and idx.excluded == [] and {f.time for f in idx.facts.values()} == {""}


def test_an_entity_with_only_excluded_facts_can_still_be_named(firm):
    idx = gq.GraphIndex(firm.db, window=window_of("2021"))
    assert [s.name for s in idx.link("What did Maria Lopez do?")] == ["Maria Lopez"]
    assert idx.out.get(firm.maria.id, []) == []


def test_excluded_facts_do_not_make_paths(firm):
    assert [f.id for f in gq.GraphIndex(firm.db).paths(firm.maria.id, firm.acme.id)[0]] == [firm.f_maria.id]
    assert gq.GraphIndex(firm.db, window=window_of("2021")).paths(firm.maria.id, firm.acme.id) == []


# ---------------------------------------------------------------- asking with a time

def run(firm, question, llm, mode="graph", **kw):
    return ask_mod.ask(firm.db, question, mode=mode, llm=llm, embedder=FakeEmbedder(), settings=ask_mod.Settings(_env_file=None), today=TODAY, **kw)


def plan_cto():
    return lambda q: {"start": ["Acme Corp"], "steps": [{"relation": "CTO of", "direction": "in"}]}


def test_the_question_is_planned_without_its_time_and_the_model_sees_what_each_fact_says(firm):
    llm = ScriptedLLM(plan=plan_cto(), answer=lambda p: {"found": True, "answer": "Dana Reyes", "cited": ["F1"]})
    r = run(firm, "Who was the CTO of Acme Corp in 2021?", llm)
    assert llm.prompts["plan"] == ["Q: Who was the CTO of Acme Corp?"]
    prompt = llm.prompts["answer"][0]
    assert "[F1] Dana Reyes was CTO of Acme Corp (2019..2022)   [dated: holds throughout 2021]" in prompt
    assert "Maria Lopez" not in prompt and "Kim Soto" not in prompt           # dated outside 2021
    assert prompt.startswith("Question: Who was the CTO of Acme Corp in 2021?")   # the person's own words stay
    assert r["found"] and r["answer"] == "Dana Reyes" and r["citations"][0]["time"] == "during"


def test_the_model_is_told_what_the_tags_mean_only_when_a_time_was_asked(firm):
    seen = []
    llm = ScriptedLLM(plan=plan_cto(), answer=lambda p: {"found": False, "answer": "not found", "cited": []})
    orig = llm.generate_json

    def spy(system, prompt, schema, max_tokens=None):
        seen.append(system)
        return orig(system, prompt, schema, max_tokens)

    llm.generate_json = spy
    run(firm, "Who was the CTO of Acme Corp in 2021?", llm)
    run(firm, "Who was the CTO of Acme Corp?", llm)
    timed = [s for s in seen if "The question is about a time: 2021" in s]
    assert len(timed) == 1 and "may still have held" in timed[0] or "never as certain" in timed[0]
    assert seen[-1] == ask_mod.ANSWER_SYSTEM


def test_the_report_says_which_time_was_found_and_what_was_left_out(firm):
    llm = ScriptedLLM(plan=plan_cto(), answer=lambda p: {"found": True, "answer": "Dana Reyes", "cited": ["F1"]})
    t = run(firm, "Who was the CTO of Acme Corp in 2021?", llm)["reasoning"]["time"]
    assert t["asked"] == "in 2021" and t["label"] == "2021" and t["from"] == "2021-01-01" and t["to"] == "2021-12-31"
    assert t["question_used"] == "Who was the CTO of Acme Corp?" and t["left_out"] == 2
    assert t["facts_by_status"] == {"during": 1, "undated": 2}      # what is left after the facts dated outside were removed


def test_no_time_in_the_question_means_no_time_in_the_report_and_nothing_left_out(firm):
    llm = ScriptedLLM(plan=plan_cto(), answer=lambda p: {"found": True, "answer": "x", "cited": ["F1", "F2", "F3"]})
    r = run(firm, "Who was the CTO of Acme Corp?", llm)
    assert "time" not in r["reasoning"] and len(r["citations"]) == 3 and "time" not in r["citations"][0]
    assert "[dated" not in llm.prompts["answer"][0]


def test_when_every_fact_is_dated_outside_the_time_the_answer_says_why(firm):
    llm = ScriptedLLM(plan=lambda q: {"start": ["Maria Lopez"], "steps": [{"relation": "was CTO of", "direction": "out"}]})
    r = run(firm, "Which company was Maria Lopez CTO of in 2021?", llm)
    assert r["found"] is False and r["citations"] == [] and llm.prompts["answer"] == []        # the model is not asked
    assert "outside 2021" in r["note"] and "Maria Lopez was CTO of Acme Corp (2012..2019)" in r["note"]


def test_a_chain_walks_only_facts_that_fit_the_time(firm):
    for year, who in (("2013", "Maria Lopez"), ("2020", "Dana Reyes"), ("2025", "Kim Soto")):
        llm = ScriptedLLM(plan=plan_cto(), answer=lambda p: {"found": True, "answer": "x", "cited": ["F1"]})
        r = run(firm, f"Who was the CTO of Acme Corp in {year}?", llm)
        assert r["reasoning"]["answer_entities"] == [who], year


def test_an_open_ended_fact_is_offered_with_its_caveat(firm):
    llm = ScriptedLLM(plan=plan_cto(), answer=lambda p: {"found": True, "answer": "Kim Soto", "cited": ["F1"]})
    r = run(firm, "Who was the CTO of Acme Corp in 2025?", llm)
    assert "[dated: began earlier, no end date stated, so it may still have held]" in llm.prompts["answer"][0]
    assert r["citations"][0]["time"] == "open"


def test_a_between_question_keeps_everyone_whose_dates_overlap(firm):
    llm = ScriptedLLM(plan=plan_cto(), answer=lambda p: {"found": True, "answer": "x", "cited": ["F1", "F2"]})
    r = run(firm, "Who was the CTO of Acme Corp between 2018 and 2020?", llm)
    assert sorted(r["reasoning"]["answer_entities"]) == ["Dana Reyes", "Maria Lopez"]


def test_a_year_at_the_start_of_an_entity_name_is_not_a_time(firm):
    games = firm.ent("2020 Summer Games", "event")
    firm.fact(firm.maria, "won a medal at", games, frm="2021", title="news")
    firm.db.commit()
    llm = ScriptedLLM(plan=lambda q: {"start": ["2020 Summer Games"], "steps": []}, answer=lambda p: {"found": True, "answer": "Maria Lopez", "cited": ["F1"]})
    r = run(firm, "Who won a medal at the 2020 Summer Games?", llm)
    assert "time" not in r["reasoning"]
    llm = ScriptedLLM(plan=lambda q: {"start": ["2020 Summer Games"], "steps": []}, answer=lambda p: {"found": True, "answer": "Maria Lopez", "cited": ["F1"]})
    r = run(firm, "Who medalled in 2020 Summer Games?", llm)
    assert "time" not in r["reasoning"] and "Maria Lopez" in llm.prompts["answer"][0]
    llm = ScriptedLLM(plan=plan_cto(), answer=lambda p: {"found": True, "answer": "Dana Reyes", "cited": ["F1"]})
    assert run(firm, "Who was the CTO of Acme Corp in 2021?", llm)["reasoning"]["time"]["label"] == "2021"       # a real time still works


def test_an_entity_that_merely_contains_the_year_does_not_cancel_a_real_time(firm):
    expo = firm.ent("Expo 2021 Fair", "event")
    firm.fact(firm.acme, "exhibited at", expo, frm="2021", title="news")
    firm.db.commit()
    llm = ScriptedLLM(plan=plan_cto(), answer=lambda p: {"found": True, "answer": "Dana Reyes", "cited": ["F1"]})
    r = run(firm, "Who was the CTO of Acme Corp in 2021?", llm)
    assert r["reasoning"]["time"]["label"] == "2021" and "Maria Lopez" not in llm.prompts["answer"][0]


def test_now_means_the_day_the_question_is_asked(firm):
    llm = ScriptedLLM(plan=plan_cto(), answer=lambda p: {"found": True, "answer": "Kim Soto", "cited": ["F1"]})
    r = run(firm, "Who is the current CTO of Acme Corp?", llm)
    assert r["reasoning"]["time"]["label"] == "now (2026-11-16)" and r["reasoning"]["time"]["from"] == "2026-11-16"


def test_a_year_that_is_part_of_an_entity_name_is_not_a_time(firm):
    expo = firm.ent("Expo 2020", "event")
    firm.fact(firm.acme, "exhibited at", expo, frm="2021", title="news")
    firm.db.commit()
    llm = ScriptedLLM(plan=lambda q: {"start": ["Expo 2020"], "steps": []}, answer=lambda p: {"found": True, "answer": "Acme", "cited": ["F1"]})
    r = run(firm, "Who exhibited at Expo 2020?", llm)
    assert "time" not in r["reasoning"]
    llm2 = ScriptedLLM(plan=lambda q: {"start": ["Expo 2020"], "steps": []}, answer=lambda p: {"found": True, "answer": "Acme", "cited": ["F1"]})
    assert "time" not in run(firm, "Who exhibited in Expo 2020?", llm2)["reasoning"]


def test_passage_search_does_not_use_dates(firm):
    llm = ScriptedLLM(answer=lambda p: {"found": True, "answer": "x", "cited": ["P1"]})
    r = run(firm, "Who was the CTO of Acme Corp in 2021?", llm, mode="vector")
    assert "time" not in r["reasoning"] and "[dated" not in llm.prompts["answer"][0]


def test_subgraph_mode_also_leaves_out_facts_dated_outside(firm):
    llm = ScriptedLLM(answer=lambda p: {"found": True, "answer": "x", "cited": ["F1"]})
    run(firm, "Who was the CTO of Acme Corp in 2021?", llm, mode="subgraph")
    prompt = llm.prompts["answer"][0]
    assert "Dana Reyes" in prompt and "Maria Lopez" not in prompt and "Kim Soto" not in prompt


# ---------------------------------------------------------------- the API

import pytest as _pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from src.core import config  # noqa: E402
from src.core.database import get_db  # noqa: E402


@_pytest.fixture
def client(factory, firm, monkeypatch):
    import server

    def override():
        s = factory()
        try:
            yield s
        finally:
            s.close()

    server.app.dependency_overrides[get_db] = override
    monkeypatch.setattr("src.api.query.get_settings", lambda: config.Settings(_env_file=None))
    monkeypatch.setattr("src.api.query.get_embedder", lambda settings=None: FakeEmbedder())
    c = TestClient(server.app)
    c.firm = firm
    yield c
    server.app.dependency_overrides.clear()


def test_the_graph_marks_every_fact_for_a_period_and_removes_none(client):
    g = client.get("/api/graph", params={"at": "2021"}).json()
    times = sorted(e["time"] for e in g["edges"])
    assert times == ["during", "outside", "outside", "undated"]
    assert g["window"] == {"label": "2021", "kind": "in", "from": "2021-01-01", "to": "2021-12-31"}
    assert g["time_counts"] == {"during": 1, "outside": 2, "undated": 1}
    acme = next(n for n in g["nodes"] if n["name"] == "Acme Corp")
    assert acme["attributes"][0]["time"] == "undated"


def test_the_graph_without_a_period_has_no_time_fields(client):
    g = client.get("/api/graph").json()
    assert "window" not in g and all("time" not in e for e in g["edges"])


@_pytest.mark.parametrize("params", [{"at": "soon"}, {"at": "2021-13"}, {"from": "x"}, {"to": "2021-02-40"}, {"at": "2021", "from": "2019"}])
def test_a_bad_period_is_a_422_with_a_reason(client, params):
    r = client.get("/api/graph", params=params)
    assert r.status_code == 422 and r.json()["detail"]


def test_ranges_and_now_work_in_the_api(client):
    g = client.get("/api/graph", params={"from": "2018", "to": "2020"}).json()
    assert sorted(e["time"] for e in g["edges"]) == ["outside", "overlaps", "overlaps", "undated"]
    only_from = client.get("/api/graph", params={"from": "2022"}).json()
    assert only_from["window"]["kind"] == "after" and only_from["window"]["to"] is None
    only_to = client.get("/api/graph", params={"to": "2013"}).json()
    assert only_to["window"]["kind"] == "before" and only_to["window"]["from"] is None
    now = client.get("/api/graph", params={"at": "now"}).json()
    assert now["window"]["kind"] == "now" and sorted(e["time"] for e in now["edges"]) == ["open", "outside", "outside", "undated"]


def test_stats_tell_the_years_the_documents_reach(client):
    t = client.get("/api/graph/stats").json()["time"]
    assert t == {"first_year": 2012, "last_year": 2023, "dated_facts": 3, "undated_facts": 2}


def test_an_entity_timeline_is_in_time_order_with_undated_last(client):
    firm = client.firm
    r = client.get(f"/api/entities/{firm.acme.id}/timeline")
    assert r.status_code == 200
    body = r.json()
    assert body["entity"]["name"] == "Acme Corp" and "window" not in body
    assert [f["predicate"] for f in body["facts"]] == ["was CTO of", "was CTO of", "became CTO of", "advises", "has headquarters in"]
    assert [f["valid_from"] for f in body["facts"]][:3] == ["2012", "2019", "2023"]
    assert [f["direction"] for f in body["facts"]] == ["in", "in", "in", "in", "out"]
    assert all("time" not in f for f in body["facts"])


def test_a_timeline_for_a_period_says_what_each_fact_means(client):
    r = client.get(f"/api/entities/{client.firm.acme.id}/timeline", params={"at": "2021"}).json()
    assert [f["time"] for f in r["facts"]] == ["outside", "during", "outside", "undated", "undated"]
    assert r["window"]["label"] == "2021"


def test_a_timeline_of_someone_elses_or_a_missing_entity_is_a_404(client):
    assert client.get("/api/entities/nope/timeline").status_code == 404
    assert client.get(f"/api/entities/{client.firm.acme.id}/timeline", params={"at": "x"}).status_code == 422


def test_query_at_answers_who_held_a_relation_in_a_period_without_a_model(client):
    r = client.get("/api/query/at", params={"entity": "Acme Corp", "relation": "CTO of", "at": "2021"}).json()
    assert r["entity"] == "Acme Corp" and [f["subject"] for f in r["facts"]] == ["Dana Reyes"]
    assert r["facts"][0]["time"] == "during" and "holds throughout 2021" in r["facts"][0]["meaning"]
    assert r["left_out"] == 2 and any("Maria Lopez" in t for t in r["left_out_examples"])


def test_query_at_orders_sure_facts_before_doubtful_ones_and_takes_a_name_or_an_id(client):
    r = client.get("/api/query/at", params={"entity": client.firm.acme.id, "at": "2025"}).json()
    assert [f["time"] for f in r["facts"]] == ["open", "undated", "undated"]
    assert r["facts"][0]["subject"] == "Kim Soto"
    assert r["facts"][0]["meaning"].startswith("dated: began earlier, no end date stated")


def test_query_at_needs_a_period_and_a_known_entity(client):
    assert client.get("/api/query/at", params={"entity": "Acme Corp"}).status_code == 422
    assert client.get("/api/query/at", params={"entity": "Acme Corp", "at": "soon"}).status_code == 422
    assert client.get("/api/query/at", params={"entity": "Nobody Known", "at": "2021"}).status_code == 404


def test_query_at_can_look_one_way_only(client):
    out = client.get("/api/query/at", params={"entity": "Acme Corp", "at": "2021", "direction": "out"}).json()
    assert [f["predicate"] for f in out["facts"]] == ["has headquarters in"]
    inc = client.get("/api/query/at", params={"entity": "Acme Corp", "at": "2021", "direction": "in"}).json()
    assert sorted(f["subject"] for f in inc["facts"]) == ["Dana Reyes", "Omar Haddad"]
    assert client.get("/api/query/at", params={"entity": "Acme Corp", "at": "2021", "direction": "up"}).status_code == 422


def test_query_at_works_when_the_embedding_model_is_down(client, monkeypatch):
    from src.services.embedding import EmbeddingError

    def broken(settings=None):
        raise EmbeddingError("down")

    monkeypatch.setattr("src.api.query.get_embedder", broken)
    r = client.get("/api/query/at", params={"entity": "Acme Corp", "relation": "CTO", "at": "2021"})
    assert r.status_code == 200 and [f["subject"] for f in r.json()["facts"]] == ["Dana Reyes"]


def test_the_ask_endpoint_reports_the_time(client, monkeypatch):
    llm = ScriptedLLM(plan=plan_cto(), answer=lambda p: {"found": True, "answer": "Dana Reyes", "cited": ["F1"]})
    monkeypatch.setattr("src.api.query.get_llm", lambda settings=None: llm)
    body = client.post("/api/ask", json={"question": "Who was the CTO of Acme Corp in 2021?"}).json()
    assert body["found"] and body["reasoning"]["time"]["label"] == "2021" and body["citations"][0]["time"] == "during"


def test_a_neighbourhood_marks_facts_for_a_period_too(client):
    r = client.get(f"/api/entities/{client.firm.acme.id}/neighborhood", params={"at": "2021"}).json()
    assert sorted(e["time"] for e in r["edges"]) == ["during", "outside", "outside", "undated"] and r["window"]["label"] == "2021"
    assert client.get(f"/api/entities/{client.firm.acme.id}/neighborhood", params={"at": "x"}).status_code == 422
    assert "window" not in client.get(f"/api/entities/{client.firm.acme.id}/neighborhood").json()


# ---------------------------------------------------------------- what the answer may not claim

def cited(*labels, answer="x"):
    return ScriptedLLM(plan=plan_cto(), answer=lambda p: {"found": True, "answer": answer, "cited": list(labels)})


def test_an_answer_that_rests_on_an_undated_fact_says_so_in_code(firm):
    llm = ScriptedLLM(plan=lambda q: {"start": ["Omar Haddad"], "steps": [{"relation": "advises", "direction": "out"}]},
                      answer=lambda p: {"found": True, "answer": "Acme Corp", "cited": ["F1"]})
    r = run(firm, "Which company did Omar Haddad advise in 2021?", llm)
    assert r["found"] and r["citations"][0]["time"] == "undated"
    assert r["time_caveat"] == "The fact behind this answer has no date, so the documents do not show when it held."


def test_an_answer_that_rests_on_an_open_fact_says_no_end_is_stated(firm):
    r = run(firm, "Who was the CTO of Acme Corp in 2025?", cited("F1", answer="Kim Soto"))
    assert r["time_caveat"].startswith("The facts behind this answer began before 2025") and "do not confirm it" in r["time_caveat"]


def test_no_caveat_when_a_cited_fact_holds_in_the_time(firm):
    assert "time_caveat" not in run(firm, "Who was the CTO of Acme Corp in 2021?", cited("F1", answer="Dana Reyes"))
    assert "time_caveat" not in run(firm, "Who was the CTO of Acme Corp between 2018 and 2020?", cited("F1", "F2"))   # overlaps


def test_no_caveat_without_a_time_and_none_when_nothing_was_found(firm):
    assert "time_caveat" not in run(firm, "Who was the CTO of Acme Corp?", cited("F1"))
    llm = ScriptedLLM(plan=plan_cto(), answer=lambda p: {"found": False, "answer": "not found", "cited": []})
    assert "time_caveat" not in run(firm, "Who was the CTO of Acme Corp in 2025?", llm)


def test_no_caveat_when_the_model_cites_no_fact(firm):
    llm = ScriptedLLM(plan=plan_cto(), answer=lambda p: {"found": True, "answer": "Dana", "cited": []})
    assert "time_caveat" not in run(firm, "Who was the CTO of Acme Corp in 2021?", llm)
