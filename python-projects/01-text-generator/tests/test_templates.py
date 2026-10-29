import pytest

from templates import TEMPLATES, apply_template, get_template


def test_all_templates_contain_prompt_placeholder():
    for name, text in TEMPLATES.items():
        assert "{prompt}" in text, name


@pytest.mark.parametrize("name", list(TEMPLATES))
def test_apply_template_inserts_prompt(name):
    out = apply_template(name, "my special request")
    assert "my special request" in out
    assert "{prompt}" not in out


def test_braces_in_user_prompt_are_safe():
    out = apply_template("code", "explain {x} and {} and {0} and {{y}}")
    assert "explain {x} and {} and {0} and {{y}}" in out


def test_unknown_template_lists_available():
    with pytest.raises(ValueError) as exc:
        get_template("nope")
    for name in TEMPLATES:
        assert name in str(exc.value)
