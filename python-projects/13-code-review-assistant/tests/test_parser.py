"""
Tests for Python parser functionality
"""

import pytest
from pathlib import Path
from src.parsers.python_parser import PythonParser
from src.parsers.parser_registry import ParserRegistry, get_registry
from src.parsers.base_parser import ParseError


@pytest.fixture
def python_parser():
    """Create Python parser instance"""
    return PythonParser()


@pytest.fixture
def sample_code_path():
    """Get path to sample clean code"""
    return str(Path(__file__).parent / 'fixtures' / 'sample_code.py')


@pytest.fixture
def vulnerable_code_path():
    """Get path to vulnerable code"""
    return str(Path(__file__).parent / 'fixtures' / 'vulnerable_code.py')


def test_parser_supported_extensions(python_parser):
    """Test parser reports correct supported extensions"""
    extensions = python_parser.supported_extensions
    assert '.py' in extensions
    assert '.pyw' in extensions


def test_parser_can_parse_python_file(python_parser):
    """Test parser can identify Python files"""
    assert python_parser.can_parse('test.py') is True
    assert python_parser.can_parse('test.pyw') is True
    assert python_parser.can_parse('test.js') is False
    assert python_parser.can_parse('test.txt') is False


def test_parse_clean_code_file(python_parser, sample_code_path):
    """Test parsing clean code file"""
    result = python_parser.parse_file(sample_code_path)

    assert result is not None
    assert result.language == 'python'
    assert result.file_path == sample_code_path
    assert result.module_docstring is not None


def test_parse_clean_code_extracts_imports(python_parser, sample_code_path):
    """Test parser extracts import statements"""
    result = python_parser.parse_file(sample_code_path)

    assert len(result.imports) > 0
    assert any('typing' in imp for imp in result.imports)
    assert any('dataclass' in imp for imp in result.imports)


def test_parse_clean_code_extracts_functions(python_parser, sample_code_path):
    """Test parser extracts functions"""
    result = python_parser.parse_file(sample_code_path)

    assert len(result.functions) > 0

    # Find specific functions
    func_names = [f.name for f in result.functions]
    assert 'calculate_total' in func_names
    assert 'validate_email' in func_names
    assert 'fetch_data' in func_names

    # Check calculate_total details
    calc_func = next(f for f in result.functions if f.name == 'calculate_total')
    assert calc_func.line_number > 0
    assert len(calc_func.parameters) == 2
    assert calc_func.return_type == 'float'
    assert calc_func.docstring is not None
    assert calc_func.is_async is False

    # Check async function
    fetch_func = next(f for f in result.functions if f.name == 'fetch_data')
    assert fetch_func.is_async is True


def test_parse_clean_code_extracts_classes(python_parser, sample_code_path):
    """Test parser extracts classes"""
    result = python_parser.parse_file(sample_code_path)

    assert len(result.classes) > 0

    # Find UserManager class
    class_names = [c.name for c in result.classes]
    assert 'User' in class_names
    assert 'UserManager' in class_names

    # Check UserManager details
    user_manager = next(c for c in result.classes if c.name == 'UserManager')
    assert user_manager.docstring is not None
    assert len(user_manager.methods) > 0

    method_names = [m.name for m in user_manager.methods]
    assert '__init__' in method_names
    assert 'add_user' in method_names
    assert 'find_user' in method_names


def test_parse_clean_code_extracts_decorators(python_parser, sample_code_path):
    """Test parser extracts decorators"""
    result = python_parser.parse_file(sample_code_path)

    # User class should have dataclass decorator
    user_class = next(c for c in result.classes if c.name == 'User')
    assert len(user_class.decorators) > 0
    assert any('dataclass' in dec for dec in user_class.decorators)


def test_parse_vulnerable_code_file(python_parser, vulnerable_code_path):
    """Test parsing vulnerable code file"""
    result = python_parser.parse_file(vulnerable_code_path)

    assert result is not None
    assert result.language == 'python'
    assert len(result.functions) > 0
    assert len(result.classes) > 0


def test_parse_vulnerable_code_extracts_global_variables(python_parser, vulnerable_code_path):
    """Test parser extracts global variables"""
    result = python_parser.parse_file(vulnerable_code_path)

    assert len(result.global_variables) > 0

    var_names = [v['name'] for v in result.global_variables]
    assert 'API_KEY' in var_names
    assert 'PASSWORD' in var_names
    assert 'SECRET_TOKEN' in var_names


def test_parse_vulnerable_code_finds_long_function(python_parser, vulnerable_code_path):
    """Test parser can identify long functions"""
    result = python_parser.parse_file(vulnerable_code_path)

    # process_order should be a long function
    process_order = next((f for f in result.functions if f.name == 'process_order'), None)
    assert process_order is not None
    assert len(process_order.parameters) > 5  # Long parameter list


def test_parse_vulnerable_code_finds_god_class(python_parser, vulnerable_code_path):
    """Test parser can identify classes with many methods"""
    result = python_parser.parse_file(vulnerable_code_path)

    # ApplicationManager should have many methods
    app_manager = next((c for c in result.classes if c.name == 'ApplicationManager'), None)
    assert app_manager is not None
    assert len(app_manager.methods) > 10


def test_parse_code_string(python_parser):
    """Test parsing code from string"""
    code = """
def hello(name: str) -> str:
    '''Say hello'''
    return f"Hello, {name}!"
"""

    result = python_parser.parse_code(code, '<test>')

    assert result.language == 'python'
    assert len(result.functions) == 1
    assert result.functions[0].name == 'hello'
    assert result.functions[0].return_type == 'str'


def test_parse_invalid_syntax_raises_error(python_parser):
    """Test parsing invalid syntax raises ParseError"""
    code = """
def broken_function(
    # Missing closing parenthesis and colon
"""

    with pytest.raises(ParseError) as exc_info:
        python_parser.parse_code(code)

    assert 'Syntax error' in str(exc_info.value)


def test_parse_nonexistent_file_raises_error(python_parser):
    """Test parsing non-existent file raises error"""
    with pytest.raises(ParseError):
        python_parser.parse_file('/nonexistent/file.py')


def test_parser_registry_initialization():
    """Test parser registry is initialized with Python parser"""
    registry = ParserRegistry()

    assert 'python' in registry.get_supported_languages()
    assert '.py' in registry.get_supported_extensions()


def test_parser_registry_detect_language():
    """Test registry can detect language from file extension"""
    registry = get_registry()

    assert registry.detect_language('test.py') == 'python'
    assert registry.detect_language('test.pyw') == 'python'
    assert registry.detect_language('test.js') is None


def test_parser_registry_get_parser_for_file():
    """Test registry returns correct parser for file"""
    registry = get_registry()

    parser = registry.get_parser_for_file('test.py')
    assert parser is not None
    assert isinstance(parser, PythonParser)

    parser = registry.get_parser_for_file('test.unknown')
    assert parser is None


def test_parser_registry_parse_file(sample_code_path):
    """Test registry can parse file using appropriate parser"""
    registry = get_registry()

    result = registry.parse_file(sample_code_path)
    assert result is not None
    assert result.language == 'python'


def test_parser_registry_is_supported():
    """Test registry can check if file is supported"""
    registry = get_registry()

    assert registry.is_supported('test.py') is True
    assert registry.is_supported('test.pyw') is True
    assert registry.is_supported('test.unknown') is False


def test_function_parameter_extraction(python_parser):
    """Test parser correctly extracts function parameters"""
    code = """
def example(a: int, b: str = "default", *args, **kwargs):
    pass
"""

    result = python_parser.parse_code(code)
    func = result.functions[0]

    assert len(func.parameters) == 4
    assert func.parameters[0].name == 'a'
    assert func.parameters[0].type_hint == 'int'
    assert func.parameters[1].name == 'b'
    assert func.parameters[1].default_value == '"default"'
    assert func.parameters[2].name == '*args'
    assert func.parameters[3].name == '**kwargs'


def test_complexity_calculation(python_parser):
    """Test parser calculates function complexity"""
    simple_code = """
def simple():
    return 1 + 1
"""

    complex_code = """
def complex(x):
    if x > 0:
        for i in range(x):
            if i % 2 == 0:
                while i > 0:
                    i -= 1
    return x
"""

    simple_result = python_parser.parse_code(simple_code)
    complex_result = python_parser.parse_code(complex_code)

    assert simple_result.functions[0].complexity in ['Simple', 'Medium']
    assert complex_result.functions[0].complexity in ['Medium', 'Complex']


def test_parse_result_to_dict(python_parser, sample_code_path):
    """Test parsed module can be converted to dictionary"""
    result = python_parser.parse_file(sample_code_path)
    data = result.to_dict()

    assert isinstance(data, dict)
    assert 'file_path' in data
    assert 'language' in data
    assert 'functions' in data
    assert 'classes' in data
    assert 'imports' in data
    assert isinstance(data['functions'], list)
    assert isinstance(data['classes'], list)
