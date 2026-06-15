"""Tests for analyzer configuration"""
import os
import pytest
from src.core.config import AnalyzerConfig, get_config, reload_config
from src.analyzers import (
    ComplexityAnalyzer,
    SecurityAnalyzer,
    SmellAnalyzer,
    get_registry,
    IssueSeverity
)
from src.parsers.python_parser import PythonParser


@pytest.fixture
def parser():
    return PythonParser()


@pytest.fixture
def clean_env(monkeypatch):
    """Clear environment variables for clean state"""
    env_vars = [
        'COMPLEXITY_CC_WARN',
        'COMPLEXITY_CC_ERROR',
        'COMPLEXITY_MI_WARN',
        'COMPLEXITY_MI_ERROR',
        'COMPLEXITY_COGNITIVE_WARN',
        'COMPLEXITY_COGNITIVE_ERROR',
        'DISABLED_RULES',
        'SEVERITY_OVERRIDE_SEC002'
    ]
    for var in env_vars:
        monkeypatch.delenv(var, raising=False)
    reload_config()


def test_default_config(clean_env):
    """Test that config loads default values when no environment variables set"""
    config = get_config()

    assert config.cc_warning == 10
    assert config.cc_error == 15
    assert config.mi_warning == 20
    assert config.mi_error == 10
    assert config.cognitive_warning == 15
    assert config.cognitive_error == 25
    assert len(config.disabled_rules) == 0
    assert len(config.severity_overrides) == 0


def test_custom_thresholds(monkeypatch):
    """Test loading custom thresholds from environment"""
    monkeypatch.setenv('COMPLEXITY_CC_WARN', '5')
    monkeypatch.setenv('COMPLEXITY_CC_ERROR', '10')
    monkeypatch.setenv('COMPLEXITY_MI_WARN', '15')
    monkeypatch.setenv('COMPLEXITY_MI_ERROR', '5')
    monkeypatch.setenv('COMPLEXITY_COGNITIVE_WARN', '10')
    monkeypatch.setenv('COMPLEXITY_COGNITIVE_ERROR', '20')

    config = reload_config()

    assert config.cc_warning == 5
    assert config.cc_error == 10
    assert config.mi_warning == 15
    assert config.mi_error == 5
    assert config.cognitive_warning == 10
    assert config.cognitive_error == 20


def test_disabled_rules(monkeypatch):
    """Test disabling specific rules"""
    monkeypatch.setenv('DISABLED_RULES', 'SEC002,SMELL001,COMPLEX003')

    config = reload_config()

    assert 'SEC002' in config.disabled_rules
    assert 'SMELL001' in config.disabled_rules
    assert 'COMPLEX003' in config.disabled_rules
    assert 'SEC003' not in config.disabled_rules


def test_is_rule_enabled(monkeypatch):
    """Test checking if rules are enabled"""
    monkeypatch.setenv('DISABLED_RULES', 'SEC002,COMPLEX001')

    config = reload_config()

    assert not config.is_rule_enabled('SEC002')
    assert not config.is_rule_enabled('COMPLEX001')
    assert config.is_rule_enabled('SEC003')
    assert config.is_rule_enabled('SMELL001')


def test_severity_overrides(monkeypatch):
    """Test severity override loading"""
    monkeypatch.setenv('SEVERITY_OVERRIDE_SEC002', 'CRITICAL')
    monkeypatch.setenv('SEVERITY_OVERRIDE_SMELL001', 'WARNING')
    monkeypatch.setenv('SEVERITY_OVERRIDE_COMPLEX001', 'INFO')

    config = reload_config()

    assert config.get_severity_override('SEC002') == 'CRITICAL'
    assert config.get_severity_override('SMELL001') == 'WARNING'
    assert config.get_severity_override('COMPLEX001') == 'INFO'
    assert config.get_severity_override('SEC003') is None


def test_invalid_severity_ignored(monkeypatch):
    """Test that invalid severity values are ignored"""
    monkeypatch.setenv('SEVERITY_OVERRIDE_SEC002', 'INVALID_SEVERITY')

    config = reload_config()

    assert config.get_severity_override('SEC002') is None


def test_complexity_analyzer_uses_config(monkeypatch, parser):
    """Test that complexity analyzer respects configuration"""
    monkeypatch.setenv('COMPLEXITY_CC_WARN', '3')
    monkeypatch.setenv('COMPLEXITY_CC_ERROR', '5')

    reload_config()
    analyzer = ComplexityAnalyzer()

    # This code has cyclomatic complexity of 4
    code = '''
def test(a, b, c):
    if a:
        if b:
            if c:
                return True
    return False
'''

    parsed = parser.parse_code(code)
    issues = analyzer.analyze(parsed, code)

    # Should trigger warning with threshold of 3
    cc_issues = [i for i in issues if i.rule_id == 'COMPLEX001']
    assert len(cc_issues) > 0


def test_disabled_rule_filters_issues(monkeypatch, parser):
    """Test that disabled rules don't show up in results"""
    monkeypatch.setenv('DISABLED_RULES', 'SEC004')

    reload_config()
    analyzer = SecurityAnalyzer()

    code = '''
password = "hardcoded123"
api_key = "sk_live_abc123def456"
'''

    parsed = parser.parse_code(code)
    issues = analyzer.analyze(parsed, code)

    # SEC004 should be filtered out
    rule_ids = [i.rule_id for i in issues]
    assert 'SEC004' not in rule_ids


def test_severity_override_changes_severity(monkeypatch, parser):
    """Test that severity overrides actually change issue severity"""
    monkeypatch.setenv('SEVERITY_OVERRIDE_SEC004', 'CRITICAL')

    reload_config()
    analyzer = SecurityAnalyzer()

    code = '''
password = "hardcoded123"
'''

    parsed = parser.parse_code(code)
    issues = analyzer.analyze(parsed, code)

    # Find SEC004 issue
    sec004_issues = [i for i in issues if i.rule_id == 'SEC004']
    assert len(sec004_issues) > 0

    # Should have CRITICAL severity
    assert sec004_issues[0].severity == IssueSeverity.CRITICAL


def test_registry_respects_disabled_rules(monkeypatch, parser):
    """Test that registry applies config across all analyzers"""
    monkeypatch.setenv('DISABLED_RULES', 'COMPLEX001,SEC004,SMELL001')

    reload_config()
    registry = get_registry()

    code = '''
password = "secret123"  # SEC004

def long_function():  # SMELL001
    x = 0
    for i in range(10):
        if i > 5:
            if i < 8:  # COMPLEX001
                x += i
    return x
'''

    parsed = parser.parse_code(code)
    issues = registry.analyze(parsed, code)

    # None of the disabled rules should appear
    rule_ids = [i.rule_id for i in issues]
    assert 'COMPLEX001' not in rule_ids
    assert 'SEC004' not in rule_ids
    assert 'SMELL001' not in rule_ids


def test_multiple_severity_overrides(monkeypatch, parser):
    """Test multiple severity overrides working together"""
    monkeypatch.setenv('SEVERITY_OVERRIDE_SEC002', 'INFO')
    monkeypatch.setenv('SEVERITY_OVERRIDE_SEC004', 'CRITICAL')

    reload_config()
    registry = get_registry()

    code = '''
import os
password = "secret"
os.system(user_input)
'''

    parsed = parser.parse_code(code)
    issues = registry.analyze(parsed, code)

    # Check severities were overridden
    for issue in issues:
        if issue.rule_id == 'SEC004':
            assert issue.severity == IssueSeverity.CRITICAL
        elif issue.rule_id == 'SEC002':
            assert issue.severity == IssueSeverity.INFO


def test_config_get_complexity_config():
    """Test getting complexity configuration as dict"""
    config = get_config()
    complexity_config = config.get_complexity_config()

    assert 'cc_warning' in complexity_config
    assert 'cc_error' in complexity_config
    assert 'mi_warning' in complexity_config
    assert 'mi_error' in complexity_config
    assert 'cognitive_warning' in complexity_config
    assert 'cognitive_error' in complexity_config


def test_whitespace_in_disabled_rules(monkeypatch):
    """Test that whitespace in disabled rules is handled correctly"""
    monkeypatch.setenv('DISABLED_RULES', ' SEC002 , SMELL001 , COMPLEX001 ')

    config = reload_config()

    assert 'SEC002' in config.disabled_rules
    assert 'SMELL001' in config.disabled_rules
    assert 'COMPLEX001' in config.disabled_rules
    assert '' not in config.disabled_rules


def test_empty_disabled_rules(monkeypatch):
    """Test empty disabled rules string"""
    monkeypatch.setenv('DISABLED_RULES', '')

    config = reload_config()

    assert len(config.disabled_rules) == 0


def test_config_affects_new_analyzer_instances(monkeypatch, parser):
    """Test that config affects analyzers created after config change"""
    # First set low thresholds
    monkeypatch.setenv('COMPLEXITY_CC_WARN', '2')
    reload_config()

    analyzer1 = ComplexityAnalyzer()

    code = '''
def test():
    if True:
        if True:
            pass
'''

    parsed = parser.parse_code(code)
    issues1 = analyzer1.analyze(parsed, code)

    # Should find issues with low threshold
    cc_issues = [i for i in issues1 if i.rule_id == 'COMPLEX001']
    assert len(cc_issues) > 0
