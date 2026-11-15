import pytest

from src.models.resolution import EntityAlias
from src.services import graph_query as gq
from src.services.embedding import ensure_chunk_embeddings
from tests.conftest import FakeEmbedder


def idx(w, **kw):
    return gq.GraphIndex(w.db, **kw)


# ---------------------------------------------------------------- linking a question to entities

def test_link_finds_names_longest_first_and_ignores_question_words(story):
    seeds = idx(story).link("Which university did the founder of Soro Labs attend?")
    assert [(s.name, s.how) for s in seeds] == [("Soro Labs", "exact")]
    seeds = idx(story).link("Where is the University of Tamsen located?")
    assert [s.name for s in seeds] == ["University of Tamsen"] and seeds[0].confidence == 1.0


def test_link_is_case_accent_and_article_insensitive(story):
    story.db.add(EntityAlias(entity_id=story.tamsen.id, key="tamsen uni", name="Tamsen Uni"))
    story.db.commit()
    assert [s.name for s in idx(story).link("ABOUT THE UNIVERSITY OF TAMSEN?")] == ["University of Tamsen"]
    seeds = idx(story).link("what is tamsen uni like")
    assert [(s.name, s.how) for s in seeds] == [("University of Tamsen", "alias")]
    assert [s.name for s in idx(story).link("Où est Kellmár ?")] == ["Kellmar"]


def test_link_part_of_a_name_has_lower_confidence_and_lists_alternatives(story):
    ent = story.ent
    story.fact(ent("Bob Okafor", "person"), "works at", story.soro)
    story.db.commit()
    seeds = idx(story).link("What did Okafor do?")
    assert {s.name for s in seeds} == {"Imani Okafor", "Bob Okafor"} and all(s.how == "part_of_name" and s.confidence == 0.4 for s in seeds)
    assert "Bob Okafor" in next(s for s in seeds if s.name == "Imani Okafor").alternatives
    seeds = idx(story).link("What did Ravi do?")
    assert [(s.name, s.confidence) for s in seeds] == [("Ravi Anand", 0.6)]


def test_link_tolerates_a_misspelling_but_not_a_stranger(story):
    seeds = idx(story).link("Who founded Soro Lbas?")
    assert [(s.name, s.how) for s in seeds] == [("Soro Labs", "spelling")] or [s.name for s in seeds] == ["Soro Labs"]
    assert idx(story).link("Who founded Zorg Industries?") == []


def test_link_ignores_short_generic_and_unused_entities(story):
    story.ent("Lonely Island", "place")           # no facts: not part of the graph
    story.db.commit()
    assert idx(story).link("Tell me about Lonely Island") == []
    assert idx(story).link("what is the") == []


def test_link_skips_question_words_and_two_letter_names_even_when_an_entity_has_that_name(story):
    story.fact(story.ent("Who", "concept"), "sings", story.ent("Songs", "concept"))
    story.fact(story.ent("Up", "concept"), "is a", story.ent("Film", "concept"))
    story.fact(story.ent("Where", "concept"), "is a", story.ent("Question", "concept"))
    story.db.commit()
    assert [s.name for s in idx(story).link("Who founded Soro Labs? Up")] == ["Soro Labs"]
    assert [s.name for s in idx(story).link("Where is Soro Labs?")] == ["Soro Labs"]     # a long question word is skipped too


def test_link_does_not_double_count_words_inside_a_longer_match(story):
    story.fact(story.ent("Tamsen", "place"), "is near", story.kellmar)
    story.db.commit()
    assert [s.name for s in idx(story).link("the University of Tamsen")] == ["University of Tamsen"]
    assert {s.name for s in idx(story).link("University of Tamsen and Tamsen town")} == {"University of Tamsen", "Tamsen"}


def test_a_word_in_many_names_is_too_generic_to_link(story):
    for n in ("Alpha", "Beta", "Gamma", "Delta"):
        story.fact(story.ent(f"{n} Works"), "makes", story.ent(f"{n} Widgets"))
    story.fact(story.ent("Zeta Works"), "makes", story.ent("Zeta Widgets"))
    story.db.commit()
    assert idx(story).link("tell me about works") == []                     # five entities share it
    story.fact(story.ent("Omega Quarry"), "digs", story.ent("Stone"))
    story.fact(story.ent("Sigma Quarry"), "digs", story.ent("Sand"))
    story.fact(story.ent("Tau Quarry"), "digs", story.ent("Clay"))
    story.db.commit()
    assert len(idx(story).link("tell me about quarry")) == 3                 # three is still specific enough


def test_link_returns_at_most_five_seeds(story):
    names = [story.ent(f"Zork{c}x", "place") for c in "abcdefgh"]
    for n in names:
        story.fact(n, "near", story.kellmar)
    story.db.commit()
    assert len(idx(story).link(" ".join(f"Zork{c}x" for c in "abcdefgh"))) == 5


def test_document_scope_hides_other_documents(story):
    scoped = idx(story, document_id=story.docs["d02"][0])
    assert {f.text() for f in scoped.facts.values()} == {"Imani Okafor founded Soro Labs (2011..)", "Soro Labs employs 40 people"}
    assert scoped.link("Kellmar") == [] and [s.name for s in scoped.link("Soro Labs")] == ["Soro Labs"]


# ---------------------------------------------------------------- looking around

def test_around_follows_links_both_ways_up_to_the_distance(story):
    g = idx(story)
    d = g.around([story.imani.id], 2)
    assert {g.name(e): n for e, n in d.items()} == {"Imani Okafor": 0, "Soro Labs": 1, "University of Tamsen": 1, "Veltra Dynamics": 2, "Kellmar": 2}
    assert len(g.around([story.imani.id], 6)) == len(g.used)
    assert g.around(["nope"], 3) == {}


def test_facts_within_reach_include_value_facts_and_skip_dangling_ones(story):
    g = idx(story)
    facts = {f.text(): d for f, d in g.facts_within(g.around([story.soro.id], 1))}
    assert facts == {"Veltra Dynamics acquired Soro Labs (2018..)": 0, "Imani Okafor founded Soro Labs (2011..)": 0, "Soro Labs employs 40 people": 0}


# ---------------------------------------------------------------- paths

def test_paths_run_in_either_direction_and_report_facts_in_order(story):
    g = idx(story)
    [p] = g.paths(story.imani.id, story.veltra.id)
    assert [f.text() for f in p] == ["Imani Okafor founded Soro Labs (2011..)", "Veltra Dynamics acquired Soro Labs (2018..)"]
    [p] = g.paths(story.dravia.id, story.imani.id)
    assert [f.text() for f in p] == ["Kellmar is a city in Dravia", "University of Tamsen located in Kellmar", "Imani Okafor studied at University of Tamsen"]


def test_paths_respect_the_hop_limit_and_return_the_shortest_first(story):
    g = idx(story)
    assert g.paths(story.imani.id, story.dravia.id, max_hops=2) == []
    assert len(g.paths(story.imani.id, story.dravia.id, max_hops=3)[0]) == 3
    assert g.paths(story.imani.id, story.ravi.id, max_hops=6, limit=5)
    lengths = [len(p) for p in g.paths(story.veltra.id, story.kellmar.id, max_hops=6, limit=5)]
    assert lengths == sorted(lengths)
    assert g.paths(story.imani.id, story.imani.id) == [] and g.paths("a", "b") == []


def test_no_path_between_separate_islands(story):
    lone = story.ent("Island Co")
    story.fact(lone, "owns", story.ent("Islet"))
    story.db.commit()
    assert idx(story).paths(lone.id, story.veltra.id, max_hops=6) == []


# ---------------------------------------------------------------- word similarity

@pytest.mark.parametrize("hint,pred,expected", [
    ("founded", "founded", 1.0), ("founder", "founded", 1.0), ("work at", "works at", 1.0),
    ("studied at", "studied", 1.0), ("acquired", "invested in", 0.0), ("located in", "is a city in", 0.0),
    ("", "founded", 0.0), ("the of", "founded", 0.0),
])
def test_lexical_match(hint, pred, expected):
    assert gq.lexical_match(hint, pred) == expected


def test_lexical_match_divides_by_the_longer_phrase():
    assert gq.lexical_match("acquired", "acquired stake") == 0.5
    assert gq.lexical_match("acquired stake", "acquired") == 0.5


def test_a_shared_word_stem_outranks_a_weak_embedding_match(story):
    m = gq.PredicateMatcher(FakeEmbedder(), ["worked at", "studied at"])
    s = m.scores("works at")
    assert s["worked at"] == 1.0 and s["studied at"] < 1.0


def test_stem():
    assert [gq.stem(w) for w in ("founded", "founder", "acquired", "acquires", "works", "go", "is")] == ["found", "found", "acquir", "acquir", "work", "go", "is"]


# ---------------------------------------------------------------- following a chain

def matcher(world, embedder=None):
    index = gq.GraphIndex(world.db)
    return index, gq.PredicateMatcher(embedder, [f.predicate for f in index.facts.values()])


def test_a_chain_is_followed_step_by_step(story):
    index, m = matcher(story, FakeEmbedder())
    w = gq.walk(index, [story.veltra.id], [{"relation": "acquired", "direction": "out"}, {"relation": "founded", "direction": "in"}], m, 0.62)
    assert w.ok and [index.name(e) for e in w.final_entities] == ["Imani Okafor"] and w.final_values == []
    assert [f.id for f in w.facts] == [story.f_acq.id, story.f_found.id]           # in the order they were used
    assert [s.relation for s in w.steps] == ["acquired", "founded"] and not any(s.flipped for s in w.steps)
    assert [(index.name(e), f.predicate, index.name(t)) for e, f, t, v in w.steps[0].links] == [("Veltra Dynamics", "acquired", "Soro Labs")]


def test_a_long_chain_across_five_facts(story):
    index, m = matcher(story, FakeEmbedder())
    steps = [{"relation": "founded", "direction": "in"}, {"relation": "studied at", "direction": "out"}, {"relation": "located in", "direction": "out"}, {"relation": "is a city in", "direction": "out"}]
    w = gq.walk(index, [story.soro.id], steps, m, 0.62)
    assert w.ok and [index.name(e) for e in w.final_entities] == ["Dravia"] and len(w.facts) == 4


def test_a_wrong_direction_is_flipped_and_reported(story):
    index, m = matcher(story, None)
    w = gq.walk(index, [story.soro.id], [{"relation": "founded", "direction": "out"}], m, 0.62)   # Soro did not found anything
    assert w.ok and w.final_entities == [story.imani.id] and w.steps[0].flipped and w.steps[0].direction == "in"


def test_direction_any_looks_both_ways(story):
    index, m = matcher(story, None)
    w = gq.walk(index, [story.tamsen.id], [{"relation": "studied at", "direction": "any"}, {"relation": "founded", "direction": "any"}], m, 0.62)
    assert w.ok and [index.name(e) for e in w.final_entities] == ["Soro Labs"] and w.steps[0].direction == "in"


def test_synonyms_need_the_embedder_but_word_stems_do_not(story):
    index, m = matcher(story, None)
    assert not gq.walk(index, [story.soro.id], [{"relation": "bought", "direction": "in"}], m, 0.62).ok
    index, m = matcher(story, FakeEmbedder())
    w = gq.walk(index, [story.soro.id], [{"relation": "bought", "direction": "in"}], m, 0.62)
    assert w.ok and [index.name(e) for e in w.final_entities] == ["Veltra Dynamics"]
    index, m = matcher(story, None)
    assert gq.walk(index, [story.soro.id], [{"relation": "founder", "direction": "in"}], m, 0.62).ok


def test_a_chain_that_breaks_says_where(story):
    index, m = matcher(story, None)
    w = gq.walk(index, [story.soro.id], [{"relation": "founded", "direction": "in"}, {"relation": "married to", "direction": "out"}], m, 0.62)
    assert not w.ok and "step 2" in w.reason and "married to" in w.reason and len(w.steps) == 1
    assert not gq.walk(index, [], [{"relation": "x", "direction": "out"}], m, 0.62).ok
    assert gq.walk(index, [story.soro.id], [], m, 0.62).reason == "no steps"


def test_only_chains_that_reach_the_end_are_kept(story):
    index, m = matcher(story, None)
    # Veltra acquired Soro and invested in Pennant; only Pennant's founder studied somewhere
    steps = [{"relation": "invested in", "direction": "out"}, {"relation": "founded", "direction": "in"}]
    w = gq.walk(index, [story.veltra.id], steps, m, 0.62)
    assert w.ok and [index.name(e) for e in w.final_entities] == ["Ravi Anand"] and {f.id for f in w.facts} == {story.f_inv.id, story.f_ravi.id}
    steps = [{"relation": "acquired", "direction": "out"}, {"relation": "invested in", "direction": "out"}]
    assert not gq.walk(index, [story.veltra.id], steps, m, 0.62).ok


def test_branches_that_die_before_the_end_are_dropped_from_the_evidence(story):
    story.fact(story.imani, "founded", story.ent("Second Startup"), title="d20")      # Imani founded two companies
    story.fact(story.imani, "studied at", story.north, title="d21")                   # and attended two colleges
    story.db.commit()
    index, m = matcher(story, None)
    steps = [{"relation": "founded", "direction": "in"}, {"relation": "studied at", "direction": "out"}, {"relation": "located in", "direction": "out"}]
    w = gq.walk(index, [story.soro.id], steps, m, 0.62)
    assert w.ok and [index.name(e) for e in w.final_entities] == ["Kellmar"]
    assert story.f_loc.id in {f.id for f in w.facts} and story.f_loc2.id in {f.id for f in w.facts}
    w2 = gq.walk(index, [story.soro.id], steps[:2], m, 0.62)
    assert {index.name(e) for e in w2.final_entities} == {"University of Tamsen", "Northfield College"}


def test_a_chain_can_end_in_a_value_but_not_pass_through_one(story):
    index, m = matcher(story, None)
    w = gq.walk(index, [story.soro.id], [{"relation": "employs", "direction": "out"}], m, 0.62)
    assert w.ok and w.final_values == ["40 people"] and w.final_entities == [] and [f.text() for f in w.facts] == ["Soro Labs employs 40 people"]
    w = gq.walk(index, [story.soro.id], [{"relation": "employs", "direction": "out"}, {"relation": "founded", "direction": "in"}], m, 0.62)
    assert not w.ok and "plain values" in w.reason


def test_several_start_entities_are_followed_together(story):
    index, m = matcher(story, None)
    w = gq.walk(index, [story.soro.id, story.pennant.id], [{"relation": "founded", "direction": "in"}], m, 0.62)
    assert w.ok and {index.name(e) for e in w.final_entities} == {"Imani Okafor", "Ravi Anand"}


def test_the_threshold_decides_what_counts_as_the_same_relation(story):
    index, m = matcher(story, FakeEmbedder())
    s = m.scores("acquired")
    assert s["acquired"] == 1.0 and s["invested in"] < 0.62
    assert not gq.walk(index, [story.pennant.id], [{"relation": "acquired", "direction": "in"}], m, 0.62).ok
    assert gq.walk(index, [story.pennant.id], [{"relation": "acquired", "direction": "in"}], m, 0.0).ok


# ---------------------------------------------------------------- ranking facts

def test_rank_facts_prefers_closer_and_better_worded_facts(story):
    index, e = idx(story), FakeEmbedder()
    dist = index.around([story.soro.id], 3)
    cands = index.facts_within(dist)
    ranked = gq.rank_facts(index, story.db, e, "who founded Soro Labs", cands, 3)
    assert ranked[0].text().startswith("Imani Okafor founded Soro Labs") and len(ranked) == 3
    plain = gq.rank_facts(index, story.db, None, "anything", cands, 3)
    assert [f.id for f in plain] == [f.id for f, _ in sorted(cands, key=lambda t: (t[1], t[0].text()))[:3]]
    assert gq.rank_facts(index, story.db, e, "q", [], 3) == []


def test_equally_good_facts_are_ordered_by_distance(story):
    index, e = idx(story), FakeEmbedder()
    far = story.fact(story.ent("Acme"), "owns", story.ent("Beta"))
    near = story.fact(story.ent("Beta2"), "owns", story.ent("Acme2"))        # same words in the question's eyes
    story.db.commit()
    index = idx(story)
    a, b = index.facts[far.id], index.facts[near.id]
    ranked = gq.rank_facts(index, story.db, e, "owns", [(a, 2), (b, 0)], 2)
    assert ranked[0].id == near.id


def test_global_search_finds_facts_by_wording_when_no_entity_is_named(story):
    index, e = idx(story), FakeEmbedder()
    found = gq.global_fact_search(story.db, e, "which university did somebody attend", index, 2)
    assert {f.id for f in found} <= {story.f_att.id, story.f_ravi_att.id, story.f_loc.id, story.f_loc2.id}
    assert found[0].id in {story.f_att.id, story.f_ravi_att.id}
