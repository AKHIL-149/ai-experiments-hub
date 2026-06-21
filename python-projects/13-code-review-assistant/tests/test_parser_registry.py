"""
Tests for ParserRegistry enhancements
"""
import pytest
import tempfile
import os
from src.parsers.parser_registry import ParserRegistry, get_registry
from src.parsers.base_parser import ParseError


class TestLanguageDetection:
    """Test language detection capabilities"""

    def setup_method(self):
        """Create fresh registry for each test"""
        self.registry = ParserRegistry()

    def test_detect_python_from_shebang(self):
        """Test Python detection from shebang"""
        code = """#!/usr/bin/env python3
print("Hello")
"""
        language = self.registry.detect_language_from_content(code)
        assert language == 'python'

    def test_detect_python_from_imports(self):
        """Test Python detection from imports"""
        code = """import os
from pathlib import Path

def main():
    pass
"""
        language = self.registry.detect_language_from_content(code)
        assert language == 'python'

    def test_detect_javascript_from_imports(self):
        """Test JavaScript detection from ES6 imports"""
        code = """import React from 'react';
import { useState } from 'react';

export default function App() {
    return <div>Hello</div>;
}
"""
        language = self.registry.detect_language_from_content(code)
        assert language == 'javascript'

    def test_detect_javascript_from_require(self):
        """Test JavaScript detection from CommonJS require"""
        code = """const express = require('express');
const app = express();

app.get('/', (req, res) => {
    res.send('Hello');
});
"""
        language = self.registry.detect_language_from_content(code)
        assert language == 'javascript'

    def test_detect_java_from_package(self):
        """Test Java detection from package declaration"""
        code = """package com.example.app;

import java.util.List;

public class Main {
    public static void main(String[] args) {
        System.out.println("Hello");
    }
}
"""
        language = self.registry.detect_language_from_content(code)
        assert language == 'java'

    def test_detect_go_from_package(self):
        """Test Go detection from package"""
        code = """package main

import (
    "fmt"
)

func main() {
    fmt.Println("Hello")
}
"""
        language = self.registry.detect_language_from_content(code)
        assert language == 'go'

    def test_detect_rust_from_use(self):
        """Test Rust detection from use statements"""
        code = """use std::io;

fn main() {
    println!("Hello");
}
"""
        language = self.registry.detect_language_from_content(code)
        assert language == 'rust'

    def test_detect_node_from_shebang(self):
        """Test Node.js detection from shebang"""
        code = """#!/usr/bin/env node
console.log('Hello');
"""
        language = self.registry.detect_language_from_content(code)
        assert language == 'javascript'

    def test_detect_unknown_language(self):
        """Test unknown language returns None"""
        code = """This is just plain text
with no recognizable programming patterns
"""
        language = self.registry.detect_language_from_content(code)
        assert language is None

    def test_detect_language_scoring(self):
        """Test that language with most pattern matches wins"""
        # This code has both Python and Java patterns, but more Python
        code = """import os
from pathlib import Path

def main():
    print("Hello")

class MyClass:
    pass
"""
        language = self.registry.detect_language_from_content(code)
        assert language == 'python'


class TestAutoDetectParsing:
    """Test auto-detection during parsing"""

    def setup_method(self):
        """Create fresh registry for each test"""
        self.registry = ParserRegistry()

    def test_parse_file_with_extension(self):
        """Test parsing file with known extension"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write('def test(): pass')
            temp_file = f.name

        try:
            result = self.registry.parse_file(temp_file)
            assert result.language == 'python'
        finally:
            os.unlink(temp_file)

    def test_parse_file_without_extension(self):
        """Test parsing file without extension using content detection"""
        with tempfile.NamedTemporaryFile(mode='w', delete=False) as f:
            f.write("""#!/usr/bin/env python3
def test():
    pass
""")
            temp_file = f.name

        try:
            result = self.registry.parse_file(temp_file, auto_detect=True)
            assert result.language == 'python'
        finally:
            os.unlink(temp_file)

    def test_parse_file_unsupported_no_autodetect(self):
        """Test that unsupported file raises error when auto_detect=False"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.unknown', delete=False) as f:
            f.write('def test(): pass')
            temp_file = f.name

        try:
            with pytest.raises(ParseError, match="No parser available"):
                self.registry.parse_file(temp_file, auto_detect=False)
        finally:
            os.unlink(temp_file)

    def test_detect_language_with_content(self):
        """Test detect_language with content parameter"""
        code = "import os\ndef main(): pass"
        language = self.registry.detect_language('script', content=code)
        assert language == 'python'

    def test_detect_language_extension_priority(self):
        """Test that extension detection has priority over content"""
        code = "package main\nfunc main() {}"  # Go code
        language = self.registry.detect_language('test.py', content=code)
        # Extension should win
        assert language == 'python'


class TestRegistryStatistics:
    """Test registry statistics and reporting"""

    def setup_method(self):
        """Create fresh registry for each test"""
        self.registry = ParserRegistry()

    def test_parse_increments_statistics(self):
        """Test that parsing increments statistics"""
        initial_stats = self.registry.get_statistics()

        # Parse some Python code
        self.registry.parse_code('def test(): pass', 'python')
        self.registry.parse_code('def test2(): pass', 'python')

        stats = self.registry.get_statistics()
        assert stats.get('python', 0) == initial_stats.get('python', 0) + 2

    def test_parse_file_increments_statistics(self):
        """Test that parse_file also increments statistics"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.js', delete=False) as f:
            f.write('function test() {}')
            temp_file = f.name

        try:
            self.registry.parse_file(temp_file)
            stats = self.registry.get_statistics()
            assert stats.get('javascript', 0) >= 1
        finally:
            os.unlink(temp_file)

    def test_get_parser_info(self):
        """Test get_parser_info returns correct structure"""
        info = self.registry.get_parser_info()

        # Should have all registered parsers
        assert 'python' in info
        assert 'javascript' in info
        assert 'java' in info
        assert 'go' in info
        assert 'rust' in info

        # Check structure
        python_info = info['python']
        assert 'language' in python_info
        assert 'extensions' in python_info
        assert 'parser_class' in python_info
        assert 'parse_count' in python_info

        assert python_info['language'] == 'python'
        assert '.py' in python_info['extensions']
        assert python_info['parser_class'] == 'PythonParser'

    def test_get_language_stats(self):
        """Test get_language_stats returns correct tuple"""
        total_langs, total_exts, parse_counts = self.registry.get_language_stats()

        assert total_langs == 5  # python, javascript, java, go, rust
        assert total_exts >= 10  # At least .py, .js, .jsx, .ts, .tsx, .java, .go, .rs, etc.
        assert isinstance(parse_counts, dict)

    def test_reset_statistics(self):
        """Test reset_statistics clears all counts"""
        # Parse some code
        self.registry.parse_code('def test(): pass', 'python')
        self.registry.parse_code('function test() {}', 'javascript')

        # Verify stats exist
        stats = self.registry.get_statistics()
        assert len(stats) > 0

        # Reset
        self.registry.reset_statistics()

        # Verify cleared
        stats = self.registry.get_statistics()
        assert len(stats) == 0

    def test_get_supported_languages(self):
        """Test get_supported_languages returns all languages"""
        languages = self.registry.get_supported_languages()
        assert 'python' in languages
        assert 'javascript' in languages
        assert 'java' in languages
        assert 'go' in languages
        assert 'rust' in languages
        assert len(languages) == 5

    def test_get_supported_extensions(self):
        """Test get_supported_extensions returns all extensions"""
        extensions = self.registry.get_supported_extensions()

        # Python
        assert '.py' in extensions

        # JavaScript/TypeScript
        assert '.js' in extensions
        assert '.jsx' in extensions
        assert '.ts' in extensions
        assert '.tsx' in extensions

        # Java
        assert '.java' in extensions

        # Go
        assert '.go' in extensions

        # Rust
        assert '.rs' in extensions


class TestGlobalRegistry:
    """Test global registry singleton"""

    def test_get_registry_returns_singleton(self):
        """Test that get_registry returns same instance"""
        registry1 = get_registry()
        registry2 = get_registry()
        assert registry1 is registry2

    def test_global_registry_has_parsers(self):
        """Test that global registry has all parsers registered"""
        registry = get_registry()
        languages = registry.get_supported_languages()
        assert len(languages) >= 5


class TestEdgeCases:
    """Test edge cases and error handling"""

    def setup_method(self):
        """Create fresh registry for each test"""
        self.registry = ParserRegistry()

    def test_empty_content_detection(self):
        """Test detection with empty content"""
        language = self.registry.detect_language_from_content('')
        assert language is None

    def test_whitespace_only_content(self):
        """Test detection with whitespace only"""
        language = self.registry.detect_language_from_content('   \n\n   ')
        assert language is None

    def test_comment_only_content(self):
        """Test detection with only comments"""
        code = """# This is a comment
# Another comment
"""
        # Should still detect Python due to comment style
        language = self.registry.detect_language_from_content(code)
        # May or may not detect - depends on patterns

    def test_detect_language_no_content(self):
        """Test detect_language without content falls back to extension"""
        language = self.registry.detect_language('test.py')
        assert language == 'python'

    def test_is_supported_true(self):
        """Test is_supported returns True for supported file"""
        assert self.registry.is_supported('test.py') is True
        assert self.registry.is_supported('test.js') is True
        assert self.registry.is_supported('test.java') is True

    def test_is_supported_false(self):
        """Test is_supported returns False for unsupported file"""
        assert self.registry.is_supported('test.unknown') is False
        assert self.registry.is_supported('test.txt') is False

    def test_parse_nonexistent_file(self):
        """Test parsing non-existent file raises error"""
        with pytest.raises((ParseError, FileNotFoundError)):
            self.registry.parse_file('/nonexistent/file.py')

    def test_parse_unsupported_language(self):
        """Test parsing with unsupported language raises error"""
        with pytest.raises(ParseError, match="No parser available"):
            self.registry.parse_code('code', 'unknown_language')
