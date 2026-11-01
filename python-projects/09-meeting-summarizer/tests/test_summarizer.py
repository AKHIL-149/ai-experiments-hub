import pytest

from core.summarizer import Summarizer, GROUNDING_RULES
from tests.helpers import FakeLLM


def words(n, prefix="w"):
    return " ".join(f"{prefix}{i}" for i in range(n))


class TestSummarize:
    def test_empty_transcript_is_refused(self):
        for blank in ("", "   \n  ", None):
            with pytest.raises(ValueError, match="no transcript"):
                Summarizer(FakeLLM()).summarize(blank)

    def test_unknown_level_is_refused(self):
        with pytest.raises(ValueError, match="Unknown summary level"):
            Summarizer(FakeLLM()).summarize("some words here", level="epic")

    def test_short_transcript_is_summarized_directly(self):
        llm = FakeLLM(["the summary"])
        result = Summarizer(llm).summarize("alpha beta gamma delta")
        assert result["summary"] == "the summary" and result["chunks_processed"] == 1
        assert len(llm.calls) == 1 and "alpha beta gamma delta" in llm.calls[0]["prompt"]

    def test_long_transcript_is_map_reduced(self):
        llm = FakeLLM(default="section summary")
        result = Summarizer(llm, chunk_size_words=50).summarize(words(120))
        assert result["chunks_processed"] == 3
        assert len(llm.calls) == 4                      # three chunk summaries + the final one
        assert "Section 1" in llm.calls[-1]["prompt"] and "Section 3" in llm.calls[-1]["prompt"]

    @pytest.mark.parametrize("level,limit", [("brief", 500), ("standard", 1500), ("detailed", 3000)])
    def test_level_sets_the_length_budget(self, level, limit):
        llm = FakeLLM()
        Summarizer(llm).summarize("some words in here", level=level)
        assert llm.calls[0]["max_tokens"] == limit

    @pytest.mark.parametrize("level", ["brief", "standard", "detailed"])
    def test_every_prompt_forbids_invention(self, level):
        llm = FakeLLM()
        Summarizer(llm).summarize("some words in here", level=level)
        assert GROUNDING_RULES in llm.calls[0]["system_prompt"]
        assert "Never invent participants" in llm.calls[0]["system_prompt"]
        assert "not a meeting" in llm.calls[0]["system_prompt"]

    def test_chunk_prompts_are_grounded_too(self):
        llm = FakeLLM()
        Summarizer(llm, chunk_size_words=20).summarize(words(60))
        assert all(GROUNDING_RULES in call["system_prompt"] for call in llm.calls)

    def test_multi_level_summary(self):
        llm = FakeLLM()
        out = Summarizer(llm).generate_multi_level_summary("some words in here")
        assert set(out) == {"brief", "standard", "detailed", "total_cost"}


class TestChunking:
    def test_breaks_between_lines_not_inside_them(self):
        text = "a b c d e\nf g h i j\nk l\n\nm n o p q r s t u v w x y z a b c"
        chunks = Summarizer(FakeLLM(), chunk_size_words=10)._split_into_chunks(text)
        assert chunks == ["a b c d e\nf g h i j", "k l", "m n o p q r s t u v", "w x y z a b c"]

    def test_every_word_is_kept_exactly_once(self):
        text = "\n".join(words(7, f"l{i}x") for i in range(40))
        chunks = Summarizer(FakeLLM(), chunk_size_words=25)._split_into_chunks(text)
        assert " ".join(chunks).split() == text.split()
        assert all(len(c.split()) <= 25 for c in chunks)

    def test_empty_text(self):
        assert Summarizer(FakeLLM())._split_into_chunks("") == []
        assert Summarizer(FakeLLM())._split_into_chunks("\n\n  \n") == []

    def test_one_huge_line_is_split_by_words(self):
        chunks = Summarizer(FakeLLM(), chunk_size_words=10)._split_into_chunks(words(25))
        assert [len(c.split()) for c in chunks] == [10, 10, 5]


class TestTopics:
    P = staticmethod(Summarizer._parse_topic_lines)

    def test_bullets_numbers_and_bold_are_stripped_not_dropped(self):
        raw = "- Budget review\n* Hiring plan\n1. Launch date\n2) Risks\n**Customer feedback**\n• Roadmap"
        assert self.P(raw, 10) == ["Budget review", "Hiring plan", "Launch date", "Risks", "Customer feedback", "Roadmap"]

    def test_introductions_are_dropped(self):
        raw = "Here are the 10 most important topics discussed:\nBudget\nSure! Here is the list:\nHiring\nTopics:\nThe main topics are:"
        assert self.P(raw, 10) == ["Budget", "Hiring"]

    def test_topics_that_start_with_digits_survive(self):
        assert self.P("3D printing plans\n2024 budget", 10) == ["3D printing plans", "2024 budget"]

    def test_quotes_and_blank_lines(self):
        assert self.P('\n"Quoted topic"\n\n', 10) == ["Quoted topic"]

    def test_limit(self):
        assert len(self.P("\n".join(f"t{i}" for i in range(30)), 10)) == 10

    def test_one_call_for_a_short_transcript(self):
        llm = FakeLLM(["Budget\nHiring"])
        assert Summarizer(llm).extract_key_topics("a few words in here") == ["Budget", "Hiring"]
        assert len(llm.calls) == 1

    def test_long_transcripts_are_processed_chunk_by_chunk_and_merged(self):
        llm = FakeLLM(["Budget\nHiring", "hiring!\nLaunch", "Risks\nBudget"])
        topics = Summarizer(llm, chunk_size_words=30).extract_key_topics(words(80), max_topics=10)
        assert len(llm.calls) == 3
        assert all(len(c["prompt"].split()) < 200 for c in llm.calls)     # the model never gets the whole transcript
        assert topics == ["Budget", "Hiring", "Launch", "Risks"]           # duplicates (case/punctuation) merged

    def test_empty_transcript(self):
        assert Summarizer(FakeLLM()).extract_key_topics("  ") == []

    def test_topic_prompt_is_grounded_too(self):
        llm = FakeLLM(["Budget"])
        Summarizer(llm).extract_key_topics("a few words in here")
        assert GROUNDING_RULES in llm.calls[0]["system_prompt"]
        assert "no introduction" in llm.calls[0]["prompt"]


class TestSpeakerKeyPoints:
    def segs(self):
        return [{"speaker": "Speaker 1", "text": "We will fund the trip"}, {"speaker": "Speaker 2", "text": "ok"},
                {"speaker": "Speaker 1", "text": "and buy banners"}]

    def test_preamble_and_bullets_are_cleaned(self):
        llm = FakeLLM(["Here are three of the most important points Speaker 1 made:\n\n1. Fund the trip\n2) Buy banners", "NONE"])
        assert Summarizer(llm).extract_speaker_key_points(self.segs()) == {"Speaker 1": ["Fund the trip", "Buy banners"]}

    def test_a_speaker_with_no_substance_is_omitted(self):
        assert Summarizer(FakeLLM(["NONE", "NONE"])).extract_speaker_key_points(self.segs()) == {}

    def test_each_speakers_lines_are_grouped(self):
        llm = FakeLLM(["a", "b"])
        Summarizer(llm).extract_speaker_key_points(self.segs())
        assert "We will fund the trip and buy banners" in llm.calls[0]["prompt"]

    def test_blank_segments_are_skipped(self):
        llm = FakeLLM()
        Summarizer(llm).extract_speaker_key_points([{"speaker": "Speaker 1", "text": "  "}])
        assert llm.calls == []
