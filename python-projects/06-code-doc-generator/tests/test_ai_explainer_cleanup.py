"""Regression tests for LLM response cleaning and cache keys (no LLM needed)."""
from src.core.ai_explainer import AIExplainer, clean_llm_text, parse_parameter_descriptions
from src.parsers.models import FunctionInfo, ParameterInfo


class FakeLLM:
    model = "fake"

    def __init__(self):
        self.calls = 0

    def generate(self, **kwargs):
        self.calls += 1
        return f"Here is the explanation:\n\nResult {self.calls}.\n\nNote that this is a guess."


def test_clean_strips_preamble_and_editorial_note():
    assert clean_llm_text("Here is a summary of `m`:\n\nDoes X.") == "Does X."
    assert clean_llm_text("Here is a summary: Does X.") == "Does X."
    assert clean_llm_text("Does X.\n\nNote that the docstring is off.") == "Does X."


def test_clean_strips_based_on_context_lead_in():
    assert clean_llm_text("Based on the provided context, the Cart class holds items.") == "The Cart class holds items."


def test_parameter_descriptions_match_by_name():
    resp = "Here are the brief descriptions:\n- `n`: the count\n2. limit (int) - upper bound"
    assert parse_parameter_descriptions(resp, ["limit", "n", "other"]) == {
        "n": "the count",
        "limit": "upper bound",
    }


def test_same_named_methods_do_not_share_cache(tmp_path):
    from src.core.cache_manager import CacheManager

    llm = FakeLLM()
    explainer = AIExplainer(llm, CacheManager(cache_dir=str(tmp_path)), True)
    f = FunctionInfo(name="__init__", parameters=[ParameterInfo(name="self")], line_number=1)
    a = explainer.explain_function(f, context="A.__init__")
    b = explainer.explain_function(f, context="B.__init__")
    assert a != b and llm.calls == 2
    assert explainer.explain_function(f, context="A.__init__") == a and llm.calls == 2
