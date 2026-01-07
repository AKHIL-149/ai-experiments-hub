# API Reference

## REST API Endpoints

The web interface exposes a REST API for programmatic access.

### Base URL
```
http://localhost:8000/api
```

### Authentication
No authentication required for local development. Configure authentication for production deployments.

---

## Endpoints

### Health Check

Check if the API is running.

**Endpoint:** `GET /api/health`

**Response:**
```json
{
  "status": "healthy",
  "version": "0.7.3",
  "service": "code-doc-generator"
}
```

**Example:**
```bash
curl http://localhost:8000/api/health
```

---

### Get Available Formats

Retrieve available output formats, languages, and providers.

**Endpoint:** `GET /api/formats`

**Response:**
```json
{
  "formats": [
    {
      "id": "markdown",
      "name": "Markdown",
      "description": "GitHub-flavored markdown with TOC",
      "extension": ".md"
    },
    {
      "id": "html",
      "name": "HTML",
      "description": "Bootstrap 5 styled HTML with syntax highlighting",
      "extension": ".html"
    },
    {
      "id": "json",
      "name": "JSON",
      "description": "Structured JSON API reference",
      "extension": ".json"
    }
  ],
  "languages": [
    {"id": "python", "name": "Python", "extensions": [".py"]},
    {"id": "javascript", "name": "JavaScript", "extensions": [".js", ".jsx"]},
    {"id": "typescript", "name": "TypeScript", "extensions": [".ts", ".tsx"]},
    {"id": "java", "name": "Java", "extensions": [".java"]}
  ],
  "styles": [
    {"id": "auto", "name": "Auto-detect"},
    {"id": "google", "name": "Google Style"},
    {"id": "numpy", "name": "NumPy Style"},
    {"id": "sphinx", "name": "Sphinx Style"}
  ],
  "providers": [
    {"id": "ollama", "name": "Ollama (Local)", "requires_key": false},
    {"id": "anthropic", "name": "Anthropic Claude", "requires_key": true},
    {"id": "openai", "name": "OpenAI GPT", "requires_key": true}
  ]
}
```

**Example:**
```bash
curl http://localhost:8000/api/formats
```

---

### Generate Documentation

Generate documentation from code.

**Endpoint:** `POST /api/generate`

**Content-Type:** `multipart/form-data`

**Parameters:**

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `file` | File | No* | - | Code file to document |
| `code` | String | No* | - | Code as text (if no file) |
| `language` | String | No | python | Programming language |
| `format` | String | No | markdown | Output format |
| `provider` | String | No | ollama | LLM provider |
| `model` | String | No | - | Specific model name |
| `use_ai` | Boolean | No | true | Enable AI enhancement |

*Either `file` or `code` must be provided.

**Response:**
```json
{
  "status": "success",
  "code": "def example():\n    pass",
  "documentation": "# Module Documentation\n\n## Functions\n\n### `example()`...",
  "raw_documentation": "# Module Documentation...",
  "format": "markdown",
  "language": "python",
  "ai_enhanced": true,
  "stats": {
    "language": "python",
    "functions": 5,
    "classes": 2,
    "lines": 150
  },
  "metadata": {
    "timestamp": "2024-01-06 10:30:45",
    "provider": "Ollama",
    "model": "llama3.2",
    "processing_time": 2.34
  },
  "error": null
}
```

**Example (File Upload):**
```bash
curl -X POST http://localhost:8000/api/generate \
  -F "file=@example.py" \
  -F "format=markdown" \
  -F "provider=ollama" \
  -F "use_ai=true"
```

**Example (Code String):**
```bash
curl -X POST http://localhost:8000/api/generate \
  -F "code=def hello(): print('Hello')" \
  -F "language=python" \
  -F "format=json" \
  -F "use_ai=false"
```

**Example (Python):**
```python
import requests

# Upload file
with open('example.py', 'rb') as f:
    response = requests.post(
        'http://localhost:8000/api/generate',
        files={'file': f},
        data={
            'format': 'markdown',
            'provider': 'ollama',
            'use_ai': 'true'
        }
    )

result = response.json()
print(result['documentation'])
```

---

### Analyze Code

Analyze code structure without generating full documentation.

**Endpoint:** `POST /api/analyze`

**Content-Type:** `multipart/form-data`

**Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `file` | File | No* | Code file to analyze |
| `code` | String | No* | Code as text |
| `language` | String | No | Programming language |

**Response:**
```json
{
  "success": true,
  "total_functions": 5,
  "total_classes": 2,
  "functions": ["main", "helper", "process", "validate", "save"],
  "classes": ["DataProcessor", "FileHandler"],
  "language": "python",
  "error": null
}
```

**Example:**
```bash
curl -X POST http://localhost:8000/api/analyze \
  -F "file=@example.py"
```

---

### Enhance Code

Add or update docstrings in source code.

**Endpoint:** `POST /api/enhance`

**Content-Type:** `multipart/form-data`

**Parameters:**

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `file` | File | No* | - | Code file to enhance |
| `code` | String | No* | - | Code as text |
| `language` | String | No | python | Programming language |
| `style` | String | No | auto | Docstring style |
| `provider` | String | No | ollama | LLM provider |
| `model` | String | No | - | Specific model |

**Response:**
```json
{
  "success": true,
  "enhanced_code": "def example():\n    \"\"\"Example function.\"\"\" \n    pass",
  "language": "python",
  "style": "google",
  "error": null
}
```

**Example:**
```bash
curl -X POST http://localhost:8000/api/enhance \
  -F "file=@example.py" \
  -F "style=google" \
  -F "provider=ollama"
```

---

## Python Library API

### DocGenerator Class

Main class for document generation.

```python
from src import DocGenerator

generator = DocGenerator(
    llm_provider: str = 'ollama',
    model: Optional[str] = None,
    use_ai: bool = True,
    enable_cache: bool = True
)
```

**Parameters:**
- `llm_provider`: LLM provider ('ollama', 'anthropic', 'openai')
- `model`: Specific model name (optional)
- `use_ai`: Enable AI-powered explanations
- `enable_cache`: Enable caching for performance

**Methods:**

#### generate_docs()
```python
generator.generate_docs(
    input_path: str,
    output_format: str = 'markdown',
    output_dir: Optional[str] = None,
    recursive: bool = False
) -> List[str]
```

Generate documentation from code files.

**Returns:** List of output file paths

#### enhance_code()
```python
generator.enhance_code(
    input_path: str,
    output_path: Optional[str] = None
) -> str
```

Add docstrings to source code.

**Returns:** Path to enhanced code file

#### analyze_structure()
```python
generator.analyze_structure(
    input_path: str
) -> ParsedModule
```

Analyze code structure without generating documentation.

**Returns:** ParsedModule object with code structure

---

### ParserRegistry Class

Registry for language parsers.

```python
from src.parsers import ParserRegistry

registry = ParserRegistry()
```

**Methods:**

#### get_parser()
```python
parser = registry.get_parser(file_path: str)
```

Get appropriate parser for a file.

**Returns:** BaseParser instance

---

### Data Models

#### ParsedModule
```python
from src.parsers.models import ParsedModule

@dataclass
class ParsedModule:
    file_path: str
    language: str
    module_docstring: Optional[str]
    imports: List[str]
    functions: List[FunctionInfo]
    classes: List[ClassInfo]
    global_variables: List[Dict[str, Any]]
    parse_timestamp: Optional[str]
    ai_summary: Optional[str]
```

#### FunctionInfo
```python
@dataclass
class FunctionInfo:
    name: str
    line_number: int
    parameters: List[ParameterInfo]
    return_type: Optional[str]
    docstring: Optional[str]
    decorators: List[str]
    body_summary: Optional[str]
    complexity: Optional[str]
    ai_explanation: Optional[str]
```

#### ClassInfo
```python
@dataclass
class ClassInfo:
    name: str
    line_number: int
    docstring: Optional[str]
    base_classes: List[str]
    methods: List[FunctionInfo]
    attributes: List[Dict[str, Any]]
    ai_explanation: Optional[str]
```

---

## Error Handling

### HTTP Status Codes

- `200 OK`: Successful request
- `400 Bad Request`: Invalid parameters
- `500 Internal Server Error`: Server error

### Error Response Format

```json
{
  "status": "error",
  "code": "",
  "documentation": "",
  "raw_documentation": "",
  "format": "markdown",
  "language": "python",
  "ai_enhanced": false,
  "stats": {},
  "metadata": {},
  "error": "Error message here"
}
```

### Common Errors

**No Code Provided:**
```json
{
  "detail": "No code provided"
}
```

**Unsupported Language:**
```json
{
  "error": "No parser found for example.cpp"
}
```

**LLM Connection Error:**
```json
{
  "error": "Failed to connect to Ollama: Connection refused"
}
```

---

## Rate Limiting

Currently no rate limiting implemented. Consider implementing for production use:

```python
from fastapi import FastAPI
from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter

@app.post("/api/generate")
@limiter.limit("10/minute")
async def generate_docs(...):
    ...
```

---

## WebSocket Support (Future)

Real-time documentation generation updates:

```javascript
const ws = new WebSocket('ws://localhost:8000/ws/generate');

ws.onmessage = (event) => {
    const data = JSON.parse(event.data);
    console.log('Progress:', data.progress);
};

ws.send(JSON.stringify({
    code: 'def example(): pass',
    format: 'markdown'
}));
```

*Not yet implemented in version 0.7.3*

---

## Changelog

### Version 0.7.3
- Added `/results` endpoint for web interface
- Enhanced response model with stats and metadata
- Markdown to HTML conversion
- Processing time tracking

### Version 0.7.2
- Added HTML templates and frontend
- Bootstrap 5 UI components
- Drag-and-drop file upload

### Version 0.7.1
- Initial REST API implementation
- `/generate`, `/analyze`, `/enhance` endpoints
- OpenAPI documentation

---

## Interactive API Documentation

Access interactive API documentation:

- **Swagger UI**: http://localhost:8000/api/docs
- **ReDoc**: http://localhost:8000/api/redoc

Try out endpoints directly in your browser!
