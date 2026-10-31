"""AIExplainer with a fake model: prompts, caching, the circuit breaker and cleanup."""
import pytest

from src.core import ai_explainer
from src.core.ai_explainer import (AIExplainer, SYSTEM_CLASS, SYSTEM_FUNCTION, SYSTEM_MODULE, SYSTEM_PARAMETERS,
                                   trim_to_last_sentence)
from src.core.llm_client import LLMError
from src.parsers.python_parser import PythonParser


class FakeLLM:
    model = 'fake-model'

    def __init__(self, replies=None):
        self.replies = list(replies or [])
        self.calls = []
        self.truncated = False

    def generate(self, prompt, max_tokens=1000, temperature=0.7, system=None):
        self.calls.append({'prompt': prompt, 'system': system, 'max_tokens': max_tokens, 'temperature': temperature})
        reply = self.replies.pop(0) if self.replies else 'An explanation.'
        if isinstance(reply, Exception):
            raise reply
        if isinstance(reply, tuple):          # (text, truncated)
            self.truncated = reply[1]
            return reply[0]
        self.truncated = False
        return reply


class MemoryCache:
    def __init__(self):
        self.store = {}

    def get_ai_cache(self, key, model):
        return self.store.get((key, model))

    def set_ai_cache(self, key, model, value):
        self.store[(key, model)] = value


def explainer(replies=None, **kwargs):
    return AIExplainer(FakeLLM(replies), kwargs.pop('cache', None), enable_cache=kwargs.pop('enable_cache', False), **kwargs)


def parse(code):
    return PythonParser().parse_code(code, 'mod.py')


def first_func(code):
    module = parse(code)
    return (module.functions + [m for c in module.classes for m in c.methods])[0]


# ------------------------------------------------------------------ function prompts

def test_the_function_prompt_shows_the_real_code_and_says_it_is_complete():
    ex = explainer()
    ex.explain_function(first_func('async def sync(url: str, retries: int = 3) -> bool:\n    return True\n'), context='wallet')
    prompt = ex.llm.calls[0]['prompt']
    assert 'Context: wallet' in prompt
    assert 'Signature: async def sync(url: str, retries: int = 3) -> bool' in prompt
    assert 'Body (complete):\nreturn True' in prompt
    assert 'Parameters not used in the body: url, retries' in prompt
    assert prompt.rstrip().endswith('using only the information above:')


def test_a_long_body_is_labelled_as_a_preview():
    code = 'def f():\n' + ''.join(f'    x{i} = {i}\n' for i in range(9))
    prompt = explainer_prompt(code)
    assert 'Body (first 5 of 9 lines):' in prompt and 'x4 = 4' in prompt and 'x5 = 5' not in prompt


def explainer_prompt(code):
    ex = explainer()
    ex.explain_function(first_func(code))
    return ex.llm.calls[0]['prompt']


def test_an_empty_body_and_an_unknown_body_are_described_differently():
    assert 'Body: empty' in explainer_prompt('def f():\n    """Only docs."""\n')
    func = first_func('def f():\n    return 1\n')
    func.body_summary, func.body_lines = None, None           # e.g. a language whose parser gives no body
    ex = explainer()
    ex.explain_function(func)
    assert 'Body: not available' in ex.llm.calls[0]['prompt'] and 'say what is not known' in ex.llm.calls[0]['prompt']


def test_docstring_decorators_and_used_parameters():
    prompt = explainer_prompt('import functools\n@functools.cache\ndef f(a, b):\n    """Adds numbers."""\n    return a\n')
    assert 'Docstring: Adds numbers.' in prompt and 'Decorators: functools.cache' in prompt
    assert 'Parameters not used in the body: b' in prompt and 'not used in the body: a' not in prompt


def test_no_unused_line_when_everything_is_used():
    assert 'not used' not in explainer_prompt('def f(a):\n    return a\n')


def test_the_system_text_carries_the_grounding_rules():
    for system in (SYSTEM_FUNCTION, SYSTEM_CLASS, SYSTEM_MODULE, SYSTEM_PARAMETERS):
        assert 'Describe only what the code shown actually does' in system
        assert 'never on a name alone' in system and 'trivial' in system and 'unused' in system
    ex = explainer()
    ex.explain_function(first_func('def f():\n    return 1\n'))
    assert ex.llm.calls[0]['system'] == SYSTEM_FUNCTION and ex.llm.calls[0]['temperature'] <= 0.3


# ------------------------------------------------------------------ class and module prompts

WALLET = ('class Wallet(Base):\n    """A wallet."""\n    kind = "w"\n    def __init__(self, owner: str, balance: float = 0.0):\n'
          '        self.owner = owner\n        self.balance = balance\n    def deposit(self, amount):\n        """Add money."""\n        self.balance += amount\n'
          '    async def sync(self, url):\n        return True\n    def noop(self):\n        pass\n')


def test_the_class_prompt_lists_attributes_and_what_each_method_does():
    ex = explainer()
    ex.explain_class(parse(WALLET).classes[0], context='mod')
    prompt = ex.llm.calls[0]['prompt']
    assert 'Class: Wallet(Base)' in prompt and 'Docstring: A wallet.' in prompt
    assert 'kind = \'w\' (class attribute)' in prompt.replace('"', "'") or "kind = 'w' (class attribute)" in prompt
    assert 'owner = owner (set in __init__)' in prompt and 'balance = balance (set in __init__)' in prompt
    assert 'def deposit(self, amount)  [Add money.]' in prompt                      # docstring first line when there is one
    assert 'async def sync(self, url)  [body: return True]' in prompt                # otherwise the first body lines
    assert 'def noop(self)  [body: pass]' in prompt
    assert ex.llm.calls[0]['system'] == SYSTEM_CLASS


@pytest.mark.parametrize('decorators,label', [
    (['interface'], 'Interface'), (['@interface'], 'Interface'), (['enum'], 'Enum'), (['@enum', '@static'], 'Enum'),
    (['@static'], 'Class'), ([], 'Class'),
])
def test_the_prompt_names_interfaces_and_enums_as_such(decorators, label):
    from src.parsers.models import ClassInfo
    ex = explainer()
    ex.explain_class(ClassInfo(name='Thing', line_number=1, decorators=decorators), context='mod')
    prompt = ex.llm.calls[0]['prompt']
    assert f'{label}: Thing' in prompt
    assert f'what this {label.lower()} holds and offers' in prompt


def test_attributes_without_a_scope_carry_no_python_specific_label():
    from src.parsers.models import ClassInfo
    ex = explainer()
    ex.explain_class(ClassInfo(name='T', line_number=1, attributes=[{'name': 'x', 'type': 'number', 'default_value': None}]), 'm')
    prompt = ex.llm.calls[0]['prompt']
    assert '  - x: number\n' in prompt + '\n' and '__init__' not in prompt and 'class attribute' not in prompt


def test_a_class_with_many_methods_says_how_many_were_left_out():
    methods = ''.join(f'    def m{i}(self):\n        return {i}\n' for i in range(15))
    ex = explainer()
    ex.explain_class(parse(f'class Big:\n{methods}').classes[0])
    prompt = ex.llm.calls[0]['prompt']
    assert 'm11(' in prompt and 'm12(' not in prompt and '(and 3 more methods)' in prompt


def test_the_module_prompt_uses_docstrings_and_imports_and_forbids_guessing_the_application():
    code = '"""Interest maths."""\nimport math\n\ndef rate(x):\n    """Return the rate."""\n    return x\n\nclass Account:\n    """Holds money."""\n'
    ex = explainer()
    ex.generate_module_summary(parse(code))
    prompt = ex.llm.calls[0]['prompt']
    assert 'Module: mod.py' in prompt and 'Docstring: Interest maths.' in prompt and 'Imports: import math' in prompt
    assert 'def rate(x)  [Return the rate.]' in prompt and 'Account  [Holds money.]' in prompt
    assert 'Do not guess what application it belongs to' in SYSTEM_MODULE


@pytest.mark.parametrize('code', ['', '# only a comment\n', 'import os\nX = 1\n'])
def test_a_module_with_nothing_to_summarise_gets_no_summary_and_no_model_call(code):
    ex = explainer()
    assert ex.generate_module_summary(parse(code)) == '' and ex.llm.calls == []


# ------------------------------------------------------------------ parameters

def test_unused_parameters_are_described_without_asking_the_model():
    func = first_func('def f(a, b):\n    pass\n')
    ex = explainer()
    ex.enhance_parameter_descriptions(func.parameters, 'f', func)
    assert [p.description for p in func.parameters] == ['Not used by the current implementation.'] * 2
    assert ex.llm.calls == []


def test_used_parameters_are_described_from_the_model_by_name_and_unused_ones_stay_deterministic():
    func = first_func('def f(a, b, c):\n    return a + b\n')
    ex = explainer(['- `b`: the second addend\n- a: the first addend'])
    ex.enhance_parameter_descriptions(func.parameters, 'f', func)
    assert [p.description for p in func.parameters] == ['the first addend', 'the second addend', 'Not used by the current implementation.']
    prompt = ex.llm.calls[0]['prompt']
    assert '- a' in prompt and '- b' in prompt and '- c' not in prompt and 'Body (complete):' in prompt


def test_self_and_unknown_usage_parameters_are_not_described():
    module = parse('class A:\n    def m(self, x):\n        return x\n')
    method = module.classes[0].methods[0]
    ex = explainer(['x: the value'])
    ex.enhance_parameter_descriptions(method.parameters, 'm', method)
    assert [p.description for p in method.parameters] == [None, 'the value']
    assert 'self' not in ex.llm.calls[0]['prompt'].split('judging by the code):')[1]


def test_existing_descriptions_are_kept():
    func = first_func('def f(a):\n    return a\n')
    func.parameters[0].description = 'already described'
    ex = explainer()
    ex.enhance_parameter_descriptions(func.parameters, 'f', func)
    assert func.parameters[0].description == 'already described' and ex.llm.calls == []


def test_a_failed_parameter_call_leaves_the_parameters_alone():
    func = first_func('def f(a, b):\n    return a\n')
    ex = explainer([LLMError('other', 'boom')])
    ex.enhance_parameter_descriptions(func.parameters, 'f', func)
    assert [p.description for p in func.parameters] == [None, 'Not used by the current implementation.']


# ------------------------------------------------------------------ cleanup and truncation

def test_replies_are_cleaned_of_chatty_framing():
    ex = explainer(['Here is a summary:\nIt adds two numbers.\n\nNote that this is simple.'])
    assert ex.explain_function(first_func('def f(a, b):\n    return a + b\n')) == 'It adds two numbers.'


@pytest.mark.parametrize('text, expected', [
    ('One. Two. Thr', 'One. Two.'),
    ('One sentence that is complete.', 'One sentence that is complete.'),
    ('A complete sentence here! And a cut', 'A complete sentence here!'),
    ('Does "x." Then cut', 'Does "x."'),
    ('no punctuation at all in this reply', 'no punctuation at all in this reply\u2026'),
    ('Hi. cut', 'Hi. cut\u2026'),                                  # too short to be worth keeping alone
    ('Ends with a closing quote."', 'Ends with a closing quote."'),
])
def test_trim_to_last_sentence(text, expected):
    assert trim_to_last_sentence(text) == expected


def test_a_truncated_reply_is_cut_back_to_a_whole_sentence():
    ex = explainer([('It adds two numbers. It then retur', True)])
    assert ex.explain_function(first_func('def f(a, b):\n    return a + b\n')) == 'It adds two numbers.'


def test_a_complete_reply_is_not_trimmed():
    ex = explainer([('It adds two numbers and then', False)])
    assert ex.explain_function(first_func('def f(a, b):\n    return a + b\n')) == 'It adds two numbers and then'


# ------------------------------------------------------------------ caching

def test_a_repeated_prompt_is_answered_from_the_cache():
    cache = MemoryCache()
    ex = explainer(['First answer.'], cache=cache, enable_cache=True)
    func = first_func('def f(a):\n    return a\n')
    assert ex.explain_function(func) == 'First answer.'
    assert ex.explain_function(func) == 'First answer.'
    assert len(ex.llm.calls) == 1 and len(cache.store) == 1


def test_a_change_in_the_code_is_a_different_cache_entry():
    cache = MemoryCache()
    ex = explainer(['A.', 'B.'], cache=cache, enable_cache=True)
    assert ex.explain_function(first_func('def f(a):\n    return a\n')) == 'A.'
    assert ex.explain_function(first_func('def f(a):\n    return a + 1\n')) == 'B.'


def test_failures_and_empty_replies_are_never_cached():
    cache = MemoryCache()
    ex = explainer([LLMError('other', 'boom'), 'Now it works.'], cache=cache, enable_cache=True)
    func = first_func('def f(a):\n    return a\n')
    assert ex.explain_function(func) == '' and cache.store == {}
    assert ex.explain_function(func) == 'Now it works.' and len(cache.store) == 1


def test_cache_keys_carry_the_prompt_version(monkeypatch):
    cache = MemoryCache()
    ex = explainer(['X.'], cache=cache, enable_cache=True)
    ex.explain_function(first_func('def f():\n    return 1\n'))
    assert all(key.startswith(f'{ai_explainer.CACHE_VERSION}:function:') for key, _ in cache.store)
    assert ai_explainer.CACHE_VERSION != 'v2'


def test_caching_can_be_turned_off():
    cache = MemoryCache()
    ex = explainer(['A.', 'B.'], cache=cache, enable_cache=False)
    func = first_func('def f(a):\n    return a\n')
    ex.explain_function(func)
    ex.explain_function(func)
    assert len(ex.llm.calls) == 2 and cache.store == {}


# ------------------------------------------------------------------ failures: reported once, never pasted into the docs

FUNC = 'def f(a):\n    return a\n'


def test_a_failed_explanation_is_empty_not_an_error_message_in_the_docs():
    ex = explainer([LLMError('timeout', 'fake-model did not answer within 120s')])
    assert ex.explain_function(first_func(FUNC)) == ''
    assert ex.warnings == ['An AI explanation could not be generated: fake-model did not answer within 120s']


def test_a_permanent_failure_switches_ai_off_at_once_and_stops_calling_the_model():
    ex = explainer([LLMError('unavailable', 'Cannot reach Ollama at http://x. Is it running? Start it with: ollama serve')])
    func = first_func(FUNC)
    for _ in range(6):
        assert ex.explain_function(func) == ''
    assert len(ex.llm.calls) == 1 and ex.available is False
    assert ex.warnings == ['AI explanations were switched off: Cannot reach Ollama at http://x. Is it running? Start it with: ollama serve']


@pytest.mark.parametrize('kind', ['auth', 'model'])
def test_bad_keys_and_missing_models_also_stop_everything(kind):
    ex = explainer([LLMError(kind, 'nope')])
    ex.explain_function(first_func(FUNC))
    assert ex.available is False


def test_repeated_transient_failures_switch_ai_off_but_a_success_resets_the_count():
    ex = explainer([LLMError('timeout', 't'), LLMError('timeout', 't'), 'Fine.', LLMError('timeout', 't'), LLMError('timeout', 't')], max_failures=3)
    func = first_func(FUNC)
    for _ in range(5):
        ex.explain_function(func)
    assert ex.available is True and len(ex.llm.calls) == 5                       # never three in a row
    ex.llm.replies = ['Fine again.'] + [LLMError('timeout', 't')] * 3             # a success first: the count starts again
    for _ in range(4):
        ex.explain_function(func)
    assert ex.available is False
    ex.explain_function(func)
    assert len(ex.llm.calls) == 9                                                  # no call once it is off
    assert any('switched off' in w for w in ex.warnings)


def test_the_same_warning_is_not_repeated():
    ex = explainer([LLMError('empty', 'fake-model returned an empty reply')] * 2, max_failures=5)
    func = first_func(FUNC)
    ex.explain_function(func)
    ex.explain_function(func)
    assert ex.warnings == ['An AI explanation could not be generated: fake-model returned an empty reply']


def test_an_unexpected_client_bug_does_not_crash_the_run():
    ex = explainer([RuntimeError('bug\nwith  newlines')], max_failures=2)
    assert ex.explain_function(first_func(FUNC)) == ''
    assert ex.warnings == ['An AI explanation could not be generated: bug with newlines']
    ex.llm.replies = [RuntimeError('again')]
    ex.explain_function(first_func(FUNC))
    assert ex.available is False and ex.warnings[-1] == 'AI explanations were switched off after repeated failures'


def test_ai_is_off_means_every_method_returns_empty_without_calls():
    ex = explainer()
    ex.available = False
    module = parse(WALLET)
    assert ex.explain_function(module.classes[0].methods[0]) == '' and ex.explain_class(module.classes[0]) == ''
    assert ex.generate_module_summary(module) == '' and ex.llm.calls == []


def test_a_description_already_on_an_unused_parameter_is_kept():
    func = first_func('def f(a):\n    pass\n')
    func.parameters[0].description = 'Reserved for later.'
    explainer().enhance_parameter_descriptions(func.parameters, 'f', func)
    assert func.parameters[0].description == 'Reserved for later.'
