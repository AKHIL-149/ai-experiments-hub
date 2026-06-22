"""
Tests for Plugin System
"""

import pytest
import os
import tempfile
from pathlib import Path

from src.core.plugin_base import (
    PluginMetadata, PluginType, PluginStatus, PluginHook, PluginContext,
    BasePlugin, AnalyzerPlugin, PluginException, PluginLoadError
)
from src.core.plugin_manager import PluginManager


class TestPluginMetadata:
    """Test PluginMetadata"""

    def test_metadata_creation(self):
        """Test creating plugin metadata"""
        metadata = PluginMetadata(
            name="test-plugin",
            version="1.0.0",
            author="Test Author",
            description="Test plugin description",
            plugin_type=PluginType.ANALYZER
        )

        assert metadata.name == "test-plugin"
        assert metadata.version == "1.0.0"
        assert metadata.author == "Test Author"
        assert metadata.description == "Test plugin description"
        assert metadata.plugin_type == PluginType.ANALYZER

    def test_metadata_to_dict(self):
        """Test metadata conversion to dictionary"""
        metadata = PluginMetadata(
            name="test-plugin",
            version="1.0.0",
            author="Test Author",
            description="Test description",
            plugin_type=PluginType.ANALYZER,
            supported_languages=["python", "javascript"]
        )

        data = metadata.to_dict()
        assert data['name'] == "test-plugin"
        assert data['version'] == "1.0.0"
        assert data['type'] == "analyzer"  # Fixed: uses 'type' not 'plugin_type'
        assert data['supported_languages'] == ["python", "javascript"]


class TestPluginBase:
    """Test BasePlugin functionality"""

    def test_plugin_initialization(self):
        """Test plugin initialization"""

        class TestPlugin(BasePlugin):
            def initialize(self) -> bool:
                return True

            def shutdown(self) -> bool:
                return True

        metadata = PluginMetadata(
            name="test",
            version="1.0.0",
            author="Test",
            description="Test",
            plugin_type=PluginType.CUSTOM
        )

        plugin = TestPlugin(metadata)
        assert plugin.metadata.name == "test"
        assert plugin.status == PluginStatus.INACTIVE
        assert not plugin.is_enabled()

    def test_plugin_enable_disable(self):
        """Test plugin enable/disable"""

        class TestPlugin(BasePlugin):
            def initialize(self) -> bool:
                return True

            def shutdown(self) -> bool:
                return True

        metadata = PluginMetadata(
            name="test",
            version="1.0.0",
            author="Test",
            description="Test",
            plugin_type=PluginType.CUSTOM
        )

        plugin = TestPlugin(metadata)

        # Enable plugin
        plugin.enable()
        assert plugin.is_enabled()
        assert plugin.status == PluginStatus.ACTIVE

        # Disable plugin
        plugin.disable()
        assert not plugin.is_enabled()
        assert plugin.status == PluginStatus.DISABLED

    def test_hook_registration(self):
        """Test hook registration"""

        class TestPlugin(BasePlugin):
            def initialize(self) -> bool:
                return True

            def shutdown(self) -> bool:
                return True

        metadata = PluginMetadata(
            name="test",
            version="1.0.0",
            author="Test",
            description="Test",
            plugin_type=PluginType.CUSTOM
        )

        plugin = TestPlugin(metadata)

        # Register hook
        def callback(context, *args, **kwargs):
            return "test_result"

        plugin.register_hook(PluginHook.BEFORE_ANALYSIS, callback)
        assert PluginHook.BEFORE_ANALYSIS in plugin.hooks
        assert len(plugin.hooks[PluginHook.BEFORE_ANALYSIS]) == 1
        assert plugin.hooks[PluginHook.BEFORE_ANALYSIS][0] == callback


class TestAnalyzerPlugin:
    """Test AnalyzerPlugin"""

    def test_analyzer_plugin(self):
        """Test analyzer plugin creation"""

        class TestAnalyzer(AnalyzerPlugin):
            def initialize(self) -> bool:
                return True

            def shutdown(self) -> bool:
                return True

            def analyze(self, code: str, language: str, file_path: str):
                return [
                    {
                        'type': 'test',
                        'message': 'Test issue',
                        'line': 1
                    }
                ]

        metadata = PluginMetadata(
            name="test-analyzer",
            version="1.0.0",
            author="Test",
            description="Test analyzer",
            plugin_type=PluginType.ANALYZER
        )

        analyzer = TestAnalyzer(metadata)
        analyzer.enable()

        results = analyzer.analyze("test code", "python", "test.py")
        assert len(results) == 1
        assert results[0]['type'] == 'test'
        assert results[0]['message'] == 'Test issue'


class TestPluginManager:
    """Test PluginManager"""

    @pytest.fixture
    def plugin_manager(self):
        """Create a fresh PluginManager instance"""
        # Reset singleton
        PluginManager._instance = None
        return PluginManager()

    @pytest.fixture
    def temp_plugin_file(self):
        """Create a temporary plugin file"""
        content = '''
from src.core.plugin_base import AnalyzerPlugin, PluginMetadata, PluginType

class TempTestAnalyzer(AnalyzerPlugin):
    def __init__(self):
        metadata = PluginMetadata(
            name="temp-test-analyzer",
            version="1.0.0",
            author="Test",
            description="Temporary test analyzer",
            plugin_type=PluginType.ANALYZER,
            supported_languages=["python"]
        )
        super().__init__(metadata)

    def initialize(self) -> bool:
        return True

    def shutdown(self) -> bool:
        return True

    def analyze(self, code: str, language: str, file_path: str):
        # Simple test: find "TODO" comments
        issues = []
        lines = code.split('\\n')
        for line_num, line in enumerate(lines, 1):
            if 'TODO' in line:
                issues.append({
                    'type': 'info',
                    'message': 'TODO comment found',
                    'line': line_num,
                    'code_snippet': line.strip()
                })
        return issues

def get_plugin():
    return TempTestAnalyzer()
'''

        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write(content)
            temp_path = f.name

        yield temp_path

        # Cleanup
        if os.path.exists(temp_path):
            os.remove(temp_path)

    def test_singleton_pattern(self):
        """Test that PluginManager is a singleton"""
        manager1 = PluginManager()
        manager2 = PluginManager()
        assert manager1 is manager2

    def test_register_plugin(self, plugin_manager):
        """Test plugin registration"""

        class TestPlugin(BasePlugin):
            def initialize(self) -> bool:
                return True

            def shutdown(self) -> bool:
                return True

        metadata = PluginMetadata(
            name="test-register",
            version="1.0.0",
            author="Test",
            description="Test",
            plugin_type=PluginType.CUSTOM
        )

        plugin = TestPlugin(metadata)
        plugin_manager.register_plugin(plugin)

        assert plugin_manager.get_plugin("test-register") is plugin
        assert len(plugin_manager.get_all_plugins()) >= 1

    def test_unregister_plugin(self, plugin_manager):
        """Test plugin unregistration"""

        class TestPlugin(BasePlugin):
            def initialize(self) -> bool:
                return True

            def shutdown(self) -> bool:
                return True

        metadata = PluginMetadata(
            name="test-unregister",
            version="1.0.0",
            author="Test",
            description="Test",
            plugin_type=PluginType.CUSTOM
        )

        plugin = TestPlugin(metadata)
        plugin_manager.register_plugin(plugin)
        assert plugin_manager.get_plugin("test-unregister") is not None

        plugin_manager.unregister_plugin("test-unregister")
        assert plugin_manager.get_plugin("test-unregister") is None

    def test_load_plugin_from_file(self, plugin_manager, temp_plugin_file):
        """Test loading plugin from file"""
        plugin = plugin_manager.load_plugin_from_file(temp_plugin_file)

        assert plugin is not None
        assert plugin.metadata.name == "temp-test-analyzer"
        assert plugin.metadata.version == "1.0.0"

    def test_load_nonexistent_file(self, plugin_manager):
        """Test loading from nonexistent file"""
        with pytest.raises(PluginLoadError):
            plugin_manager.load_plugin_from_file("/nonexistent/plugin.py")

    def test_get_plugins_by_type(self, plugin_manager):
        """Test filtering plugins by type"""

        class TestAnalyzer(AnalyzerPlugin):
            def initialize(self) -> bool:
                return True

            def shutdown(self) -> bool:
                return True

            def analyze(self, code, language, file_path):
                return []

        metadata = PluginMetadata(
            name="test-analyzer-filter",
            version="1.0.0",
            author="Test",
            description="Test",
            plugin_type=PluginType.ANALYZER
        )

        analyzer = TestAnalyzer(metadata)
        plugin_manager.register_plugin(analyzer)

        analyzers = plugin_manager.get_plugins_by_type(PluginType.ANALYZER)
        assert len(analyzers) >= 1
        assert all(p.metadata.plugin_type == PluginType.ANALYZER for p in analyzers)

    def test_execute_hook(self, plugin_manager):
        """Test hook execution"""

        class TestPlugin(BasePlugin):
            def __init__(self):
                metadata = PluginMetadata(
                    name="hook-test",
                    version="1.0.0",
                    author="Test",
                    description="Test",
                    plugin_type=PluginType.CUSTOM
                )
                super().__init__(metadata)
                self.register_hook(PluginHook.BEFORE_ANALYSIS, self.before_analysis_callback)
                self.callback_called = False

            def initialize(self) -> bool:
                return True

            def shutdown(self) -> bool:
                return True

            def before_analysis_callback(self, context, *args, **kwargs):
                self.callback_called = True
                return "callback_result"

        plugin = TestPlugin()
        plugin_manager.register_plugin(plugin)
        plugin.enable()

        context = PluginContext()
        results = plugin_manager.execute_hook(PluginHook.BEFORE_ANALYSIS, context)

        assert plugin.callback_called
        assert "callback_result" in results

    def test_run_analyzers(self, plugin_manager):
        """Test running all analyzer plugins"""

        class TestAnalyzer(AnalyzerPlugin):
            def initialize(self) -> bool:
                return True

            def shutdown(self) -> bool:
                return True

            def analyze(self, code, language, file_path):
                return [
                    {
                        'type': 'test',
                        'message': 'Test issue from plugin',
                        'line': 1
                    }
                ]

        metadata = PluginMetadata(
            name="test-run-analyzer",
            version="1.0.0",
            author="Test",
            description="Test",
            plugin_type=PluginType.ANALYZER,
            supported_languages=["python"]
        )

        analyzer = TestAnalyzer(metadata)
        plugin_manager.register_plugin(analyzer)
        analyzer.enable()

        context = PluginContext()
        issues = plugin_manager.run_analyzers("test code", "python", "test.py", context)

        assert len(issues) >= 1
        # Find our test issue
        test_issues = [i for i in issues if i.get('message') == 'Test issue from plugin']
        assert len(test_issues) >= 1

    def test_get_plugin_statistics(self, plugin_manager):
        """Test getting plugin statistics"""

        class TestPlugin(BasePlugin):
            def initialize(self) -> bool:
                return True

            def shutdown(self) -> bool:
                return True

        metadata = PluginMetadata(
            name="stats-test",
            version="1.0.0",
            author="Test",
            description="Test",
            plugin_type=PluginType.CUSTOM
        )

        plugin = TestPlugin(metadata)
        plugin_manager.register_plugin(plugin)

        stats = plugin_manager.get_plugin_statistics()
        assert 'total_plugins' in stats
        assert 'by_type' in stats
        assert stats['total_plugins'] >= 1

    def test_export_plugin_manifest(self, plugin_manager):
        """Test exporting plugin manifest"""

        class TestPlugin(BasePlugin):
            def initialize(self) -> bool:
                return True

            def shutdown(self) -> bool:
                return True

        metadata = PluginMetadata(
            name="manifest-test",
            version="1.0.0",
            author="Test",
            description="Test",
            plugin_type=PluginType.CUSTOM
        )

        plugin = TestPlugin(metadata)
        plugin_manager.register_plugin(plugin)

        manifest = plugin_manager.export_plugin_manifest("manifest-test")
        assert manifest is not None
        assert manifest['id'] == 'manifest-test'
        assert manifest['metadata']['name'] == 'manifest-test'
        assert manifest['metadata']['version'] == '1.0.0'


class TestExamplePlugin:
    """Test the example analyzer plugin"""

    @pytest.fixture
    def example_plugin(self):
        """Load the example plugin"""
        from plugins.example_analyzer import ExampleSecurityAnalyzer
        return ExampleSecurityAnalyzer()

    def test_example_plugin_metadata(self, example_plugin):
        """Test example plugin metadata"""
        assert example_plugin.metadata.name == "example-security-analyzer"
        assert example_plugin.metadata.plugin_type == PluginType.ANALYZER
        assert "python" in example_plugin.metadata.supported_languages
        assert "javascript" in example_plugin.metadata.supported_languages

    def test_detect_hardcoded_password(self, example_plugin):
        """Test detecting hardcoded passwords"""
        code = '''
password = "hardcoded123"
api_key = "secret_key_123"
'''

        issues = example_plugin.analyze(code, "python", "test.py")

        # Should find both issues
        assert len(issues) >= 2

        # Check for password issue
        password_issues = [i for i in issues if 'password' in i['message'].lower()]
        assert len(password_issues) >= 1
        assert password_issues[0]['severity'] == 'critical'

    def test_detect_dangerous_eval(self, example_plugin):
        """Test detecting dangerous eval usage"""
        code = '''
result = eval(user_input)
exec(malicious_code)
'''

        issues = example_plugin.analyze(code, "python", "test.py")

        # Should find both issues
        assert len(issues) >= 2

        # Check for eval issue
        eval_issues = [i for i in issues if 'eval' in i['message'].lower()]
        assert len(eval_issues) >= 1
        assert eval_issues[0]['severity'] == 'error'

    def test_detect_command_injection(self, example_plugin):
        """Test detecting command injection"""
        code = '''
import os
os.system(user_input)
'''

        issues = example_plugin.analyze(code, "python", "test.py")

        # Should find the issue
        command_issues = [i for i in issues if 'command injection' in i['message'].lower()]
        assert len(command_issues) >= 1
        assert command_issues[0]['severity'] == 'error'

    def test_javascript_detection(self, example_plugin):
        """Test JavaScript vulnerability detection"""
        code = '''
document.getElementById('output').innerHTML = userInput;
eval(untrusted_code);
'''

        issues = example_plugin.analyze(code, "javascript", "test.js")

        # Should find both issues
        assert len(issues) >= 2

    def test_get_rules(self, example_plugin):
        """Test getting plugin rules"""
        rules = example_plugin.get_rules()

        assert len(rules) >= 3
        assert any(r['id'] == 'PLUGIN_HARDCODED_PASSWORD' for r in rules)
        assert any(r['id'] == 'PLUGIN_DANGEROUS_EVAL' for r in rules)
        assert any(r['id'] == 'PLUGIN_COMMAND_INJECTION' for r in rules)

    def test_no_issues_in_clean_code(self, example_plugin):
        """Test that clean code produces no issues"""
        code = '''
def calculate_sum(a, b):
    return a + b

result = calculate_sum(5, 10)
'''

        issues = example_plugin.analyze(code, "python", "test.py")
        assert len(issues) == 0
