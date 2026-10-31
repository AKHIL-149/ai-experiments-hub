"""DocGenerator end to end with a fake model: formats, bad files, warnings and AI outages."""
import json

import pytest

from src.core.ai_explainer import AIExplainer
from src.core.doc_generator import DocGenerator
from src.core.llm_client import LLMError


class FakeLLM:
    model = 'fake'
    truncated = False

    def __init__(self, reply='It adds numbers.'):
        self.reply = reply
        self.calls = 0

    def generate(self, prompt, max_tokens=1000, temperature=0.7, system=None):
        self.calls += 1
        if isinstance(self.reply, Exception):
            raise self.reply
        return self.reply


def project(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    (src / "good.py").write_text('def add(a, b):\n    """Add."""\n    return a + b\n')
    return src


def with_ai(gen, llm):
    gen.ai_explainer = AIExplainer(llm, None, enable_cache=False)
    gen.use_ai = True
    return gen


# ------------------------------------------------------------------ formats

def test_unknown_format_is_rejected_with_the_choices(tmp_path):
    gen = DocGenerator(use_ai=False)
    with pytest.raises(ValueError) as error:
        gen.generate_docs(str(project(tmp_path)), output_format='pdf', output_dir=str(tmp_path / "out"))
    assert "pdf" in str(error.value) and "markdown" in str(error.value)


def test_one_bad_name_in_a_list_stops_the_run_before_anything_is_written(tmp_path):
    gen = DocGenerator(use_ai=False)
    out = tmp_path / "out"
    with pytest.raises(ValueError):
        gen.generate_docs(str(project(tmp_path)), output_format=['markdown', 'nope'], output_dir=str(out))
    assert not list(out.glob("*"))


def test_format_names_are_case_insensitive_and_deduplicated(tmp_path):
    gen = DocGenerator(use_ai=False)
    files = gen.generate_docs(str(project(tmp_path)), output_format=['Markdown', 'markdown', 'JSON'],
                              output_dir=str(tmp_path / "out"))
    assert sorted(f.rsplit('.', 1)[1] for f in files) == ['json', 'md']


def test_all_means_markdown_html_json(tmp_path):
    gen = DocGenerator(use_ai=False)
    files = gen.generate_docs(str(project(tmp_path)), output_format='all', output_dir=str(tmp_path / "out"))
    assert sorted(f.rsplit('.', 1)[1] for f in files) == ['html', 'json', 'md']


def test_empty_format_list_is_an_error(tmp_path):
    with pytest.raises(ValueError):
        DocGenerator(use_ai=False).generate_docs(str(project(tmp_path)), output_format=[], output_dir=str(tmp_path / "o"))


# ------------------------------------------------------------------ bad files

def test_a_file_that_does_not_parse_is_skipped_and_reported(tmp_path):
    src = project(tmp_path)
    (src / "broken.py").write_text("def oops(:\n")
    gen = DocGenerator(use_ai=False)
    files = gen.generate_docs(str(src), output_format='json', output_dir=str(tmp_path / "out"))
    data = json.load(open(files[0]))
    assert data['module']['file_path'].endswith('good.py')      # one parseable file: the single-module shape
    assert len(gen.warnings) == 1
    assert "broken.py" in gen.warnings[0] and "\n" not in gen.warnings[0]


def test_nothing_parseable_is_an_error_that_says_why(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    (src / "broken.py").write_text("def oops(:\n")
    with pytest.raises(ValueError) as error:
        DocGenerator(use_ai=False).generate_docs(str(src), output_dir=str(tmp_path / "out"))
    assert "broken.py" in str(error.value)


def test_warnings_do_not_carry_over_to_the_next_run(tmp_path):
    src = project(tmp_path)
    (src / "broken.py").write_text("def oops(:\n")
    gen = DocGenerator(use_ai=False)
    gen.generate_docs(str(src), output_format='json', output_dir=str(tmp_path / "out"))
    assert gen.warnings
    (src / "broken.py").unlink()
    gen.generate_docs(str(src), output_format='json', output_dir=str(tmp_path / "out"))
    assert gen.warnings == []


def test_output_that_cannot_be_written_is_an_error_not_an_empty_success(tmp_path):
    blocker = tmp_path / "out"
    blocker.write_text("a file where the output folder should be")
    with pytest.raises(Exception):
        DocGenerator(use_ai=False).generate_docs(str(project(tmp_path)), output_dir=str(blocker))


def test_failing_formatter_alone_is_reported_when_another_format_worked(tmp_path):
    gen = DocGenerator(use_ai=False)

    class Broken:
        def format(self, *a, **k):
            raise OSError("disk full")

    gen.formatters['html'] = Broken()
    files = gen.generate_docs(str(project(tmp_path)), output_format=['html', 'json'], output_dir=str(tmp_path / "out"))
    assert len(files) == 1 and files[0].endswith('.json')
    assert any("html" in w and "disk full" in w for w in gen.warnings)


def test_every_format_failing_raises(tmp_path):
    gen = DocGenerator(use_ai=False)

    class Broken:
        def format(self, *a, **k):
            raise OSError("disk full")

    gen.formatters['json'] = Broken()
    with pytest.raises(RuntimeError, match="disk full"):
        gen.generate_docs(str(project(tmp_path)), output_format='json', output_dir=str(tmp_path / "out"))


# ------------------------------------------------------------------ AI

def test_ai_text_lands_in_the_json_output(tmp_path):
    gen = with_ai(DocGenerator(use_ai=False), FakeLLM('It adds numbers.'))
    files = gen.generate_docs(str(project(tmp_path)), output_format='json', output_dir=str(tmp_path / "out"))
    module = json.load(open(files[0]))['module']
    assert module['functions'][0]['ai_explanation'] == 'It adds numbers.'


def test_ai_outage_becomes_one_warning_and_docs_still_come_out(tmp_path):
    llm = FakeLLM(LLMError('unavailable', 'Cannot reach Ollama. Start it with: ollama serve'))
    gen = with_ai(DocGenerator(use_ai=False), llm)
    files = gen.generate_docs(str(project(tmp_path)), output_format='markdown', output_dir=str(tmp_path / "out"))
    md = open(files[0]).read()
    assert "Cannot reach" not in md and "Error" not in md      # the failure is a warning, never document text
    assert "Add." in md                                        # the docstring is the fallback
    assert any("ollama serve" in w for w in gen.warnings)
    assert llm.calls == 1                                      # permanent failure: stop asking


def test_empty_ai_answers_do_not_hide_the_docstring(tmp_path):
    gen = with_ai(DocGenerator(use_ai=False), FakeLLM('   '))
    files = gen.generate_docs(str(project(tmp_path)), output_format='json', output_dir=str(tmp_path / "out"))
    module = json.load(open(files[0]))['module']
    func = module['functions'][0]
    assert module['ai_summary'] is None
    assert func['ai_explanation'] is None
    assert func['docstring'] == 'Add.'


def test_a_second_run_tries_the_model_again_after_an_outage(tmp_path):
    llm = FakeLLM(LLMError('unavailable', 'down'))
    gen = with_ai(DocGenerator(use_ai=False), llm)
    src = project(tmp_path)
    gen.generate_docs(str(src), output_format='json', output_dir=str(tmp_path / "out"))
    assert gen.warnings
    llm.reply = 'Back again.'
    files = gen.generate_docs(str(src), output_format='json', output_dir=str(tmp_path / "out"))
    assert gen.warnings == []
    assert json.load(open(files[0]))['module']['functions'][0]['ai_explanation'] == 'Back again.'


# ------------------------------------------------------------------ analyze

def test_analyze_reports_failed_files_with_one_line_reasons(tmp_path):
    src = project(tmp_path)
    (src / "broken.py").write_text("def oops(:\n")
    result = DocGenerator(use_ai=False).analyze_structure(str(src))
    assert result['total_functions'] == 1
    assert len(result['failed_files']) == 1
    assert "\n" not in result['failed_files'][0]['error']


def test_multi_line_error_text_is_squeezed_into_one_line(tmp_path):
    gen = DocGenerator(use_ai=False)
    src = project(tmp_path)
    (src / "second.py").write_text("x = 1\n")
    real = gen._parse_file

    def parse(path):
        if path.endswith("second.py"):
            raise RuntimeError("line one\n   line two\n\nline three")
        return real(path)

    gen._parse_file = parse
    gen.generate_docs(str(src), output_format='json', output_dir=str(tmp_path / "out"))
    assert gen.warnings == ["Skipped second.py: line one line two line three"]


# ------------------------------------------------------------------ enhance_code

def test_enhance_writes_nothing_when_the_model_is_unreachable(tmp_path):
    from src.core.doc_generator import AIUnavailableError
    gen = with_ai(DocGenerator(use_ai=False), FakeLLM(LLMError('unavailable', 'Cannot reach Ollama')))
    src = project(tmp_path) / "good.py"
    out = tmp_path / "enhanced.py"
    with pytest.raises(AIUnavailableError, match="Cannot reach Ollama"):
        gen.enhance_code(str(src), output_path=str(out))
    assert not out.exists()


def test_enhance_of_a_file_with_nothing_to_explain_is_not_an_error(tmp_path):
    gen = with_ai(DocGenerator(use_ai=False), FakeLLM())
    src = tmp_path / "consts.py"
    src.write_text("X = 1\n")
    out = tmp_path / "out.py"
    gen.enhance_code(str(src), output_path=str(out))
    assert out.exists()


def test_enhance_adds_the_docstring_the_model_wrote(tmp_path):
    gen = with_ai(DocGenerator(use_ai=False), FakeLLM('Doubles the number.'))
    src = tmp_path / "m.py"
    src.write_text("def double(n):\n    return n * 2\n")
    out = tmp_path / "out.py"
    gen.enhance_code(str(src), output_path=str(out))
    text = out.read_text()
    assert "Doubles the number." in text and "return n * 2" in text
    compile(text, "out.py", "exec")           # still valid Python
