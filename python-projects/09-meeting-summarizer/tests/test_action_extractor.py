import json

import pytest

from core.action_extractor import ActionExtractor, PLACEHOLDERS
from tests.helpers import FakeLLM


def extract(reply, transcript="we agreed to ship on friday and bob sends the report", **kw):
    llm = FakeLLM([reply] if isinstance(reply, str) else reply)
    extractor = ActionExtractor(llm, **kw)
    return extractor.extract_actions(transcript), llm


GOOD = json.dumps({
    "action_items": [{"description": "Send the report", "assignee": "Bob", "due_date": "Friday", "priority": "high", "category": "Docs"}],
    "decisions": [{"decision": "Ship on Friday", "context": "Launch", "impact": "Customers"}],
    "follow_ups": ["Check with legal"],
})


class TestExtraction:
    def test_well_formed_answer(self):
        result, _ = extract(GOOD)
        assert result["total_actions"] == 1 and result["parse_failed"] is False
        assert result["action_items"][0] == {
            "description": "Send the report", "assignee": "Bob", "due_date": "Friday", "priority": "high",
            "category": "Docs", "id": 1, "status": "pending",
        }
        assert result["decisions"] == [{"decision": "Ship on Friday", "context": "Launch", "impact": "Customers", "id": 1}]
        assert result["follow_ups"] == ["Check with legal"]

    def test_deterministic_json_request(self):
        _, llm = extract(GOOD)
        assert llm.calls[0]["temperature"] == 0.0 and llm.calls[0]["json_mode"] is True

    def test_summary_is_context_for_a_single_pass(self):
        llm = FakeLLM([GOOD])
        ActionExtractor(llm).extract_actions("a few words of transcript", summary="THE SUMMARY")
        assert "THE SUMMARY" in llm.calls[0]["prompt"]

    def test_prompt_forbids_invention(self):
        _, llm = extract(GOOD)
        assert "Do not invent owners, dates or decisions" in llm.calls[0]["prompt"]
        assert "not a meeting" in llm.calls[0]["system_prompt"]

    def test_empty_transcript_is_refused(self):
        with pytest.raises(ValueError, match="no transcript"):
            ActionExtractor(FakeLLM()).extract_actions("  ")


class TestMessyAnswers:
    def test_json_in_a_code_block(self):
        result, _ = extract("Sure!\n```json\n" + GOOD + "\n```\nHope that helps")
        assert result["total_actions"] == 1

    def test_json_with_text_around_it(self):
        result, _ = extract("Here you go: " + GOOD + " done")
        assert result["total_actions"] == 1

    def test_strings_instead_of_objects(self):
        result, _ = extract(json.dumps({"action_items": ["Send the budget"], "decisions": ["Ship Friday"], "follow_ups": []}))
        assert result["action_items"][0]["description"] == "Send the budget"
        assert result["action_items"][0]["assignee"] == "Unassigned"
        assert result["decisions"][0]["decision"] == "Ship Friday"

    def test_null_and_odd_values_get_defaults(self):
        result, _ = extract(json.dumps({"action_items": [
            {"description": "Book room", "assignee": None, "due_date": None, "priority": "URGENT", "category": ""},
            {"description": "Call Sam", "assignee": 42, "priority": "HIGH"},
        ]}))
        first, second = result["action_items"]
        assert (first["assignee"], first["due_date"], first["priority"], first["category"]) == ("Unassigned", "Not specified", "medium", "General")
        assert second["assignee"] == "42" and second["priority"] == "high"

    def test_garbage_items_are_dropped(self):
        result, _ = extract(json.dumps({"action_items": [5, None, [], {"description": ""}, {"nope": 1}, {"description": "Real one"}]}))
        assert [a["description"] for a in result["action_items"]] == ["Real one"]

    def test_wrong_shapes_do_not_crash(self):
        for reply in ('{"action_items": "none", "decisions": 7, "follow_ups": {"a": 1}}', '{}', '{"action_items": null}'):
            result, _ = extract(reply)
            assert result["total_actions"] == 0 and result["parse_failed"] is False

    @pytest.mark.parametrize("placeholder", sorted(PLACEHOLDERS))
    def test_prompt_example_text_is_not_reported_as_a_finding(self, placeholder):
        result, _ = extract(json.dumps({
            "action_items": [{"description": placeholder}], "decisions": [{"decision": placeholder}], "follow_ups": [placeholder],
        }))
        assert (result["total_actions"], result["decisions"], result["follow_ups"]) == (0, [], [])

    def test_follow_up_objects(self):
        result, _ = extract(json.dumps({"follow_ups": [{"description": "Call Sam"}, {"item": "Email Joe"}, ""]}))
        assert result["follow_ups"] == ["Call Sam", "Email Joe"]

    def test_unreadable_answer_is_flagged_not_reported_as_an_empty_meeting(self):
        result, _ = extract("I'm ready to help once you provide the transcript!")
        assert result["parse_failed"] is True and result["total_actions"] == 0

    def test_a_json_array_is_not_a_valid_answer(self):
        result, _ = extract('["a", "b"]')
        assert result["parse_failed"] is True


class TestLongTranscripts:
    def lines(self, n):
        return "\n".join(f"line {i} of the meeting with a few words" for i in range(n))

    def test_chunks_are_extracted_separately_and_merged(self):
        a = json.dumps({"action_items": [{"description": "Send report"}], "follow_ups": ["Ping Ann"]})
        b = json.dumps({"action_items": [{"description": "send report!"}, {"description": "Call Bob"}], "follow_ups": ["ping ann"]})
        c = json.dumps({"decisions": [{"decision": "Ship"}]})
        result, llm = extract([a, b, c], self.lines(9), chunk_size_words=30)
        assert len(llm.calls) == 3
        assert [x["description"] for x in result["action_items"]] == ["Send report", "Call Bob"]      # duplicate merged
        assert [x["id"] for x in result["action_items"]] == [1, 2]
        assert result["follow_ups"] == ["Ping Ann"] and result["decisions"][0]["decision"] == "Ship"

    def test_no_prompt_holds_the_whole_transcript(self):
        _, llm = extract(["{}"] * 4, self.lines(20), chunk_size_words=40)
        assert len(llm.calls) > 1
        assert all(call["prompt"].count("line ") <= 6 for call in llm.calls)

    def test_summary_is_not_attached_to_chunks_of_a_longer_meeting(self):
        llm = FakeLLM(["{}", "{}"])
        ActionExtractor(llm, chunk_size_words=20).extract_actions(self.lines(5), summary="SUMMARY OF THE WHOLE")
        assert all("SUMMARY OF THE WHOLE" not in c["prompt"] for c in llm.calls)

    def test_one_unreadable_chunk_does_not_lose_the_others(self):
        good = json.dumps({"action_items": [{"description": "Keep me"}]})
        result, _ = extract(["total nonsense", good], self.lines(6), chunk_size_words=30)
        assert [a["description"] for a in result["action_items"]] == ["Keep me"]
        assert result["parse_failed"] is False

    def test_all_chunks_unreadable_is_flagged(self):
        result, _ = extract(["nonsense", "more nonsense"], self.lines(6), chunk_size_words=30)
        assert result["parse_failed"] is True

    def test_truncation_flag_is_passed_up(self):
        llm = FakeLLM([GOOD], truncated=True)
        assert ActionExtractor(llm).extract_actions("some words in here")["truncated"] is True

    def test_tokens_are_summed(self):
        result, _ = extract(["{}", "{}", "{}"], self.lines(9), chunk_size_words=30)
        assert result["tokens_used"]["total"] == 45


class TestReportsAndHelpers:
    def test_report_lists_everything(self):
        result, _ = extract(GOOD)
        report = ActionExtractor(FakeLLM()).generate_action_report(result)
        for expected in ("**Total Actions:** 1", "### 1. Send the report", "**Assignee:** Bob", "### 1. Ship on Friday", "1. Check with legal"):
            assert expected in report

    def test_report_warns_when_the_answer_could_not_be_read(self):
        result, _ = extract("nonsense")
        assert "could not be read" in ActionExtractor(FakeLLM()).generate_action_report(result)

    def test_report_tolerates_missing_fields(self):
        report = ActionExtractor(FakeLLM()).generate_action_report({"action_items": [{}], "decisions": [{}]})
        assert "### ?. N/A" in report

    def test_validate_actions_handles_nulls(self):
        v = ActionExtractor(FakeLLM()).validate_actions([{"description": "x", "assignee": None}, {"description": None, "assignee": "Bob"}, {"description": "y", "assignee": "Ann"}])
        assert (v["valid"], v["incomplete"]) == (1, 2)

    def test_prioritize_actions_handles_nulls(self):
        ordered = ActionExtractor(FakeLLM()).prioritize_actions([{"priority": None}, {"priority": "low"}, {"priority": "HIGH"}])
        assert [a["priority"] for a in ordered] == ["HIGH", None, "low"]

    def test_assignee_names_are_deduplicated(self):
        names = ActionExtractor(FakeLLM(["Ann\nBob\nAnn"])).extract_assignees("text")
        assert sorted(names) == ["Ann", "Bob"]
