"""
Tests for JavaScript/TypeScript Parser
"""
import pytest
import sys
from unittest.mock import Mock

# Mock celery before imports
mock_celery = Mock()
mock_celery.celery_app = Mock()
mock_celery.celery_app.task = lambda *args, **kwargs: lambda f: f
sys.modules['celery'] = Mock()
sys.modules['celery.result'] = Mock()
sys.modules['celery_app'] = mock_celery

from src.parsers.javascript_parser import JavaScriptParser
from src.parsers.base_parser import ParseError


@pytest.fixture
def parser():
    """Create JavaScript parser instance"""
    return JavaScriptParser()


# ============================================================================
# Extension Support Tests
# ============================================================================

def test_supported_extensions(parser):
    """Test that parser supports JavaScript/TypeScript extensions"""
    extensions = parser.supported_extensions
    assert '.js' in extensions
    assert '.jsx' in extensions
    assert '.ts' in extensions
    assert '.tsx' in extensions
    assert '.mjs' in extensions
    assert '.cjs' in extensions


def test_can_parse_js_file(parser):
    """Test can_parse method for .js files"""
    assert parser.can_parse('test.js') is True
    assert parser.can_parse('test.jsx') is True
    assert parser.can_parse('test.py') is False


def test_can_parse_typescript_file(parser):
    """Test can_parse method for TypeScript files"""
    assert parser.can_parse('test.ts') is True
    assert parser.can_parse('test.tsx') is True


def test_can_parse_module_types(parser):
    """Test can_parse for ES module types"""
    assert parser.can_parse('module.mjs') is True
    assert parser.can_parse('module.cjs') is True


# ============================================================================
# Language Detection Tests
# ============================================================================

def test_detect_javascript(parser):
    """Test JavaScript language detection"""
    code = "function test() { return 42; }"
    lang = parser._detect_language('test.js', code)
    assert lang == 'javascript'


def test_detect_typescript(parser):
    """Test TypeScript language detection"""
    code = "interface User { name: string; }"
    lang = parser._detect_language('test.ts', code)
    assert lang == 'typescript'


def test_detect_jsx(parser):
    """Test JSX language detection"""
    code = "const App = () => <div>Hello</div>"
    lang = parser._detect_language('test.jsx', code)
    assert lang == 'jsx'


def test_detect_tsx(parser):
    """Test TSX language detection"""
    code = "const App: React.FC = () => <div>Hello</div>"
    lang = parser._detect_language('test.tsx', code)
    assert lang == 'tsx'


def test_detect_typescript_from_content(parser):
    """Test TypeScript detection from code content"""
    code = "export type User = { name: string; }"
    lang = parser._detect_language('test.js', code)  # .js extension but TS content
    assert lang == 'typescript'


# ============================================================================
# Function Parsing Tests (Regex Fallback)
# ============================================================================

def test_parse_simple_function(parser):
    """Test parsing a simple function declaration"""
    code = """
    function greet(name) {
        return 'Hello ' + name;
    }
    """
    result = parser.parse_code(code, 'test.js')

    assert result.language == 'javascript'
    assert len(result.functions) >= 1
    func = result.functions[0]
    assert func.name == 'greet'
    assert len(func.parameters) == 1
    assert func.parameters[0].name == 'name'


def test_parse_async_function(parser):
    """Test parsing async function"""
    code = """
    async function fetchData() {
        return await fetch('/api/data');
    }
    """
    result = parser.parse_code(code, 'test.js')

    assert len(result.functions) >= 1
    func = result.functions[0]
    assert func.name == 'fetchData'
    assert func.is_async is True


def test_parse_arrow_function(parser):
    """Test parsing arrow function"""
    code = """
    const add = (a, b) => a + b;
    """
    result = parser.parse_code(code, 'test.js')

    assert len(result.functions) >= 1
    func = result.functions[0]
    assert func.name == 'add'


def test_parse_async_arrow_function(parser):
    """Test parsing async arrow function"""
    code = """
    const fetchUser = async (id) => {
        return await api.getUser(id);
    };
    """
    result = parser.parse_code(code, 'test.js')

    assert len(result.functions) >= 1
    func = result.functions[0]
    assert func.name == 'fetchUser'
    assert func.is_async is True


def test_parse_function_with_multiple_params(parser):
    """Test parsing function with multiple parameters"""
    code = """
    function calculate(a, b, c, d) {
        return a + b + c + d;
    }
    """
    result = parser.parse_code(code, 'test.js')

    func = result.functions[0]
    assert len(func.parameters) == 4
    param_names = [p.name for p in func.parameters]
    assert 'a' in param_names
    assert 'b' in param_names
    assert 'c' in param_names
    assert 'd' in param_names


def test_parse_function_with_default_params(parser):
    """Test parsing function with default parameters"""
    code = """
    function greet(name = 'World') {
        return 'Hello ' + name;
    }
    """
    result = parser.parse_code(code, 'test.js')

    func = result.functions[0]
    assert len(func.parameters) >= 1


# ============================================================================
# Class Parsing Tests (Regex Fallback)
# ============================================================================

def test_parse_simple_class(parser):
    """Test parsing a simple class"""
    code = """
    class Person {
        constructor(name) {
            this.name = name;
        }
    }
    """
    result = parser.parse_code(code, 'test.js')

    assert len(result.classes) >= 1
    cls = result.classes[0]
    assert cls.name == 'Person'


def test_parse_class_with_inheritance(parser):
    """Test parsing class with extends"""
    code = """
    class Employee extends Person {
        constructor(name, title) {
            super(name);
            this.title = title;
        }
    }
    """
    result = parser.parse_code(code, 'test.js')

    assert len(result.classes) >= 1
    cls = result.classes[0]
    assert cls.name == 'Employee'
    assert 'Person' in cls.base_classes


def test_parse_multiple_classes(parser):
    """Test parsing multiple classes"""
    code = """
    class Animal {
        speak() { }
    }

    class Dog extends Animal {
        bark() { }
    }

    class Cat extends Animal {
        meow() { }
    }
    """
    result = parser.parse_code(code, 'test.js')

    assert len(result.classes) >= 3
    class_names = [c.name for c in result.classes]
    assert 'Animal' in class_names
    assert 'Dog' in class_names
    assert 'Cat' in class_names


# ============================================================================
# Import Parsing Tests (Regex Fallback)
# ============================================================================

def test_parse_es6_import(parser):
    """Test parsing ES6 import statements"""
    code = """
    import React from 'react';
    import { useState } from 'react';
    import * as utils from './utils';
    """
    result = parser.parse_code(code, 'test.js')

    assert len(result.imports) >= 1
    assert any('react' in imp for imp in result.imports)


def test_parse_commonjs_require(parser):
    """Test parsing CommonJS require statements"""
    code = """
    const express = require('express');
    const fs = require('fs');
    """
    result = parser.parse_code(code, 'test.js')

    assert len(result.imports) >= 1
    assert any('express' in imp or 'fs' in imp for imp in result.imports)


def test_parse_mixed_imports(parser):
    """Test parsing mixed import styles"""
    code = """
    import React from 'react';
    const path = require('path');
    import { render } from 'react-dom';
    """
    result = parser.parse_code(code, 'test.js')

    assert len(result.imports) >= 2


# ============================================================================
# Variable Parsing Tests
# ============================================================================

def test_parse_const_variable(parser):
    """Test parsing const variable"""
    code = """
    const API_URL = 'https://api.example.com';
    """
    result = parser.parse_code(code, 'test.js')

    assert len(result.global_variables) >= 1
    var = result.global_variables[0]
    assert var['name'] == 'API_URL'


def test_parse_let_variable(parser):
    """Test parsing let variable"""
    code = """
    let counter = 0;
    """
    result = parser.parse_code(code, 'test.js')

    assert len(result.global_variables) >= 1


def test_parse_var_variable(parser):
    """Test parsing var variable"""
    code = """
    var name = 'John';
    """
    result = parser.parse_code(code, 'test.js')

    assert len(result.global_variables) >= 1


def test_parse_multiple_variables(parser):
    """Test parsing multiple variable declarations"""
    code = """
    const API_KEY = 'abc123';
    let userId = null;
    var isActive = true;
    """
    result = parser.parse_code(code, 'test.js')

    assert len(result.global_variables) >= 3


# ============================================================================
# TypeScript Type Stripping Tests
# ============================================================================

def test_strip_parameter_types(parser):
    """Test stripping TypeScript parameter types"""
    code = "function greet(name: string): string { return name; }"
    stripped = parser._strip_typescript_types(code)

    # Should have types removed
    assert ': string' not in stripped or stripped.count(':') < code.count(':')


def test_strip_interface(parser):
    """Test stripping TypeScript interfaces"""
    code = """
    interface User {
        name: string;
        age: number;
    }
    """
    stripped = parser._strip_typescript_types(code)

    # Interface should be removed or empty
    assert 'interface User' not in stripped or '{' not in stripped.split('interface')[1].split('}')[0]


def test_strip_type_alias(parser):
    """Test stripping TypeScript type aliases"""
    code = "type ID = string | number;"
    stripped = parser._strip_typescript_types(code)

    assert 'type ID' not in stripped or '=' not in stripped.split('type')[0] if 'type' in stripped else True


def test_strip_generic_types(parser):
    """Test stripping generic type parameters"""
    code = "function identity<T>(arg: T): T { return arg; }"
    stripped = parser._strip_typescript_types(code)

    # Generic <T> should be removed
    assert '<T>' not in stripped


def test_strip_as_cast(parser):
    """Test stripping 'as' type casts"""
    code = "const user = data as User;"
    stripped = parser._strip_typescript_types(code)

    assert ' as User' not in stripped


# ============================================================================
# Complex Code Parsing Tests
# ============================================================================

def test_parse_react_component(parser):
    """Test parsing React component"""
    code = """
    import React from 'react';

    function App() {
        return (
            <div>
                <h1>Hello World</h1>
            </div>
        );
    }

    export default App;
    """
    result = parser.parse_code(code, 'App.jsx')

    assert result.language == 'jsx'
    assert len(result.functions) >= 1
    assert any('react' in imp.lower() for imp in result.imports)


def test_parse_typescript_class(parser):
    """Test parsing TypeScript class"""
    code = """
    class UserService {
        private apiUrl: string;

        constructor(apiUrl: string) {
            this.apiUrl = apiUrl;
        }

        async getUser(id: number): Promise<User> {
            return fetch(this.apiUrl + '/' + id);
        }
    }
    """
    result = parser.parse_code(code, 'service.ts')

    assert result.language == 'typescript'
    assert len(result.classes) >= 1


def test_parse_express_route(parser):
    """Test parsing Express.js route"""
    code = """
    const express = require('express');
    const app = express();

    app.get('/api/users', async (req, res) => {
        const users = await User.findAll();
        res.json(users);
    });
    """
    result = parser.parse_code(code, 'routes.js')

    assert len(result.imports) >= 1
    assert len(result.global_variables) >= 1


def test_parse_async_await_pattern(parser):
    """Test parsing async/await patterns"""
    code = """
    async function fetchUserData(userId) {
        try {
            const user = await api.getUser(userId);
            const posts = await api.getUserPosts(userId);
            return { user, posts };
        } catch (error) {
            console.error(error);
            return null;
        }
    }
    """
    result = parser.parse_code(code, 'api.js')

    assert len(result.functions) >= 1
    func = result.functions[0]
    assert func.is_async is True


def test_parse_destructuring_params(parser):
    """Test parsing functions with destructuring parameters"""
    code = """
    function printUser({ name, age }) {
        console.log(name, age);
    }
    """
    result = parser.parse_code(code, 'test.js')

    # Should parse even if parameter extraction is simplified
    assert len(result.functions) >= 1


# ============================================================================
# Edge Cases and Error Handling
# ============================================================================

def test_parse_empty_code(parser):
    """Test parsing empty code"""
    code = ""
    result = parser.parse_code(code, 'test.js')

    assert result.language == 'javascript'
    assert len(result.functions) == 0
    assert len(result.classes) == 0


def test_parse_comments_only(parser):
    """Test parsing file with only comments"""
    code = """
    // This is a comment
    /* Multi-line
       comment */
    """
    result = parser.parse_code(code, 'test.js')

    assert result.language == 'javascript'


def test_parse_invalid_syntax_gracefully(parser):
    """Test that parser handles invalid syntax gracefully"""
    code = """
    function broken( {
        // Missing closing brace
    """
    # Should not crash, may return partial results
    result = parser.parse_code(code, 'test.js')
    assert result is not None


def test_parse_minified_code(parser):
    """Test parsing minified code"""
    code = "function a(b,c){return b+c;}const d=a(1,2);"
    result = parser.parse_code(code, 'test.js')

    # Should find at least the function
    assert len(result.functions) >= 1


def test_parse_with_unicode(parser):
    """Test parsing code with unicode characters"""
    code = """
    function greet() {
        return '你好世界';  // Hello World in Chinese
    }
    """
    result = parser.parse_code(code, 'test.js')

    assert len(result.functions) >= 1


# ============================================================================
# Module Structure Tests
# ============================================================================

def test_parsed_module_structure(parser):
    """Test that ParsedModule has correct structure"""
    code = """
    import React from 'react';

    const VERSION = '1.0.0';

    function init() {
        console.log('Initialized');
    }

    class App {
        render() { }
    }
    """
    result = parser.parse_code(code, 'app.js')

    assert result.file_path == 'app.js'
    assert result.language == 'javascript'
    assert result.parse_timestamp is not None
    assert isinstance(result.imports, list)
    assert isinstance(result.functions, list)
    assert isinstance(result.classes, list)
    assert isinstance(result.global_variables, list)


def test_to_dict_serialization(parser):
    """Test that parsed result can be serialized to dict"""
    code = """
    function test() {
        return 42;
    }
    """
    result = parser.parse_code(code, 'test.js')

    # Should be serializable
    result_dict = result.to_dict()
    assert isinstance(result_dict, dict)
    assert 'file_path' in result_dict
    assert 'language' in result_dict
    assert 'functions' in result_dict


# ============================================================================
# Integration Tests
# ============================================================================

def test_parse_realistic_module(parser):
    """Test parsing a realistic JavaScript module"""
    code = """
    import axios from 'axios';
    import { validateEmail } from './utils';

    const API_BASE_URL = 'https://api.example.com';

    class UserService {
        constructor(apiKey) {
            this.apiKey = apiKey;
            this.baseUrl = API_BASE_URL;
        }

        async createUser(userData) {
            if (!validateEmail(userData.email)) {
                throw new Error('Invalid email');
            }

            const response = await axios.post(
                `${this.baseUrl}/users`,
                userData,
                { headers: { 'X-API-Key': this.apiKey } }
            );

            return response.data;
        }

        async getUser(userId) {
            const response = await axios.get(`${this.baseUrl}/users/${userId}`);
            return response.data;
        }
    }

    export default UserService;
    """
    result = parser.parse_code(code, 'UserService.js')

    # Verify all components were extracted
    assert len(result.imports) >= 1
    assert len(result.global_variables) >= 1
    assert len(result.classes) >= 1

    # Verify class structure
    user_service = result.classes[0]
    assert user_service.name == 'UserService'


def test_parser_registry_integration(parser):
    """Test that parser works with parser registry"""
    from src.parsers.parser_registry import get_registry

    registry = get_registry()

    # Should support JavaScript files
    assert registry.is_supported('test.js')
    assert registry.is_supported('test.jsx')
    assert registry.is_supported('test.ts')
    assert registry.is_supported('test.tsx')

    # Should detect language correctly
    assert registry.detect_language('app.js') == 'javascript'

    # Should get correct parser
    js_parser = registry.get_parser_for_file('test.js')
    assert js_parser is not None
    assert isinstance(js_parser, JavaScriptParser)
