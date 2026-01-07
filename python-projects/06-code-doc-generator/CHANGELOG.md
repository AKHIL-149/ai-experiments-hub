# Changelog

All notable changes to the Code Documentation Generator will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.7.4] - 2024-01-06

### Added
- Comprehensive USAGE.md guide with CLI and API examples
- API.md reference documentation for REST API
- Example files for testing (example.py, example.js)
- CHANGELOG.md for version tracking
- Integration documentation for Python library usage

### Documentation
- Complete usage documentation with examples
- REST API endpoint documentation
- Python library API reference
- Troubleshooting guide
- Configuration examples

## [0.7.3] - 2024-01-06

### Added
- Enhanced API response model with comprehensive metadata
- Markdown to HTML conversion utility
- Code statistics tracking (functions, classes, lines)
- Processing time measurement
- `/results` POST endpoint for web interface
- Stats and metadata in API responses

### Changed
- Updated `GenerateResponse` model to include code, stats, and metadata
- Improved error handling in generate endpoint
- Enhanced results display with detailed information

### Fixed
- Markdown rendering in web interface
- Response format consistency across endpoints

## [0.7.2] - 2024-01-06

### Added
- HTML templates for web interface
  - base.html with Bootstrap 5 navigation
  - index.html with upload and paste interfaces
  - result.html with split-pane documentation view
- Static assets
  - Custom CSS with animations and responsive design
  - Main JavaScript for form handling and file upload
  - Drag-and-drop file upload functionality
- Interactive code examples (Python, JavaScript, Java)
- Features showcase section
- Responsive mobile design

### UI/UX
- Bootstrap 5 themed interface
- Drag-and-drop upload area
- Tabbed interface for file upload vs code paste
- Syntax highlighting with Prism.js
- Progress indicators and error handling
- Settings persistence in localStorage

## [0.7.1] - 2024-01-06

### Added
- FastAPI web application (`src/web/app.py`)
- REST API routes (`src/web/routes.py`)
- API endpoints:
  - `GET /api/health` - Health check
  - `GET /api/formats` - Available formats and options
  - `POST /api/generate` - Generate documentation
  - `POST /api/analyze` - Analyze code structure
  - `POST /api/enhance` - Enhance code with docstrings
- Pydantic models for request/response validation
- CORS middleware for development
- Automatic API documentation (Swagger UI, ReDoc)
- CLI `serve` command to start web server

### Infrastructure
- Template and static files directory structure
- Graceful dependency handling for optional features
- Comprehensive error handling in routes

## [0.6.5.4] - 2024-01-05

### Added
- Python package setup with `setup.py`
- Installable package with entry points
- Optional dependency groups:
  - `[ai]` - AI provider dependencies
  - `[web]` - Web interface dependencies
  - `[utils]` - Utility dependencies
  - `[all]` - All optional dependencies

### Changed
- Made package importable as library
- Exposed public API via `src/__init__.py`
- Version tracking in package metadata

## [0.6.5] - 2024-01-05

### Added
- CLI interface with argparse (`doc_gen.py`)
- Command structure:
  - `generate` - Generate documentation
  - `enhance` - Add docstrings to code
  - `analyze` - Analyze code structure
  - `serve` - Start web server (placeholder)
- Progress bars using tqdm
- Colored console output
- Directory processing with recursion
- Multiple format support (markdown, html, json)
- Error handling per file
- Summary reporting

### Features
- Batch processing of multiple files
- Format selection (markdown, html, json, all)
- LLM provider selection
- Cache control
- Verbose logging option

## [0.6.0] - 2024-01-04

### Added
- Output formatters:
  - MarkdownFormatter - GitHub-flavored markdown
  - HTMLFormatter - Bootstrap 5 styled HTML
  - JSONFormatter - Structured JSON API reference
  - DocstringFormatter - Code enhancement with docstrings
- Base formatter abstract class
- Template system for HTML output
- Syntax highlighting in HTML output
- Table of contents generation
- Collapsible sections in HTML

### Features
- Multiple output formats from single parse
- Customizable formatting options
- Support for different docstring styles
- Code backup before enhancement

## [0.5.0] - 2024-01-03

### Added
- AI explanation generation (`AIExplainer`)
- LLM integration (Ollama, Anthropic, OpenAI)
- Cache manager for AST and AI results
- Lazy loading of AI dependencies
- Batch processing for efficiency
- Prompt engineering for code explanation

### Features
- Function and class explanations
- Module summaries
- Parameter descriptions
- Caching with expiry (7 days default)
- Multi-level caching (AST + AI)

### Performance
- Reduced API calls through caching
- Batch AI requests when possible
- Hash-based cache keys

## [0.4.0] - 2024-01-02

### Added
- Java parser using `javalang` library
- JavaScript/TypeScript parser using esprima
- Node.js bridge for JavaScript parsing
- Language auto-detection from file extensions
- Support for:
  - Java classes, methods, fields, Javadoc
  - JavaScript/ES6 classes, functions, JSDoc
  - TypeScript type annotations

### Infrastructure
- Parser registry system
- Auto-discovery of parsers
- Subprocess handling for Node.js
- JSON communication protocol

## [0.3.0] - 2024-01-01

### Added
- Python AST parser (`PythonParser`)
- Parser registry with auto-discovery
- Base parser abstract class
- Data models:
  - ParsedModule
  - FunctionInfo
  - ClassInfo
  - ParameterInfo

### Features
- Function extraction with parameters
- Class parsing with methods and attributes
- Type hint extraction
- Decorator detection
- Complexity estimation
- Import tracking

## [0.2.0] - 2023-12-31

### Added
- Core DocGenerator orchestrator
- LLMClient for AI providers
- File discovery utilities
- Cache directory structure
- Configuration system

### Infrastructure
- Project directory structure
- Data directories (cache, output)
- Environment configuration
- Dependency management

## [0.1.0] - 2023-12-30

### Added
- Initial project setup
- README with project overview
- Requirements file
- Basic directory structure
- MIT License

---

## Release Types

- **Major** (x.0.0): Breaking changes, major features
- **Minor** (0.x.0): New features, backwards compatible
- **Patch** (0.0.x): Bug fixes, minor improvements

## Upgrade Guide

### From 0.6.x to 0.7.x

The 0.7.x series adds web interface support:

```bash
# Install web dependencies
pip install -e ".[web]"

# Start web interface
python doc_gen.py serve
```

No breaking changes to CLI or Python API.

### From 0.5.x to 0.6.x

The 0.6.x series adds CLI and packaging:

```bash
# Install as package
pip install -e .

# Use CLI instead of direct imports
python doc_gen.py generate src/
```

Python API remains compatible.

## Future Roadmap

### Version 0.8.0 (Planned)
- Incremental documentation updates
- Git integration for changed files only
- Custom template support
- Plugin system for parsers and formatters

### Version 0.9.0 (Planned)
- Multi-file project documentation
- Cross-reference linking
- API change detection
- Documentation versioning

### Version 1.0.0 (Planned)
- Production-ready web interface
- Authentication and authorization
- Rate limiting
- Docker containerization
- Comprehensive test coverage (>90%)
- Performance benchmarks
- Security audit

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for development guidelines.

## Support

- **Issues**: https://github.com/AKHIL-149/ai-experiments-hub/issues
- **Documentation**: [README.md](README.md), [USAGE.md](USAGE.md), [API.md](API.md)
