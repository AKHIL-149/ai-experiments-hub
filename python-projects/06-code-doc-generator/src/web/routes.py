"""API routes for code documentation generator web interface"""
import os
import tempfile
import time
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Tuple

try:
    from fastapi import APIRouter, UploadFile, File, Form, HTTPException
    from pydantic import BaseModel
    FASTAPI_AVAILABLE = True
except ImportError:
    FASTAPI_AVAILABLE = False
    APIRouter = None
    BaseModel = object

from src.core import DocGenerator
from src.core.doc_generator import AIUnavailableError
from src.core.llm_client import default_provider
from src.parsers.base_parser import ParseError, decode_source
from src.parsers.parser_registry import ParserRegistry
from src.version import __version__
from starlette.concurrency import run_in_threadpool

# Language -> extension used for pasted code (parsers pick the language from the extension)
EXTENSION_MAP = {
    'python': '.py',
    'javascript': '.js',
    'typescript': '.ts',
    'java': '.java'
}
# File extension -> language, for uploads (the file name wins over the language field)
LANGUAGE_BY_EXTENSION = {
    '.py': 'python', '.js': 'javascript', '.jsx': 'javascript', '.mjs': 'javascript',
    '.ts': 'typescript', '.tsx': 'typescript', '.java': 'java',
}
WEB_FORMATS = ('markdown', 'html', 'json')
PROVIDERS = ('ollama', 'anthropic', 'openai')


def detect_language(code: str) -> str:
    """Guess the language of pasted code (used for "auto"); Python when nothing else fits."""
    import ast
    import re
    try:
        ast.parse(code)
        if not re.search(r'^\s*(?:public\s+|private\s+)?(?:class|interface)\s+\w+[^:\n]*\{', code, re.M):
            return 'python'
    except (SyntaxError, ValueError, RecursionError):
        pass
    if re.search(r'\b(?:public|private|protected)\s+(?:static\s+)?(?:final\s+)?[\w<>\[\],]+\s+\w+\s*\(', code) \
            or re.search(r'^\s*(?:package|import)\s+[\w.]+\s*;', code, re.M) \
            or 'System.out.' in code:
        return 'java'
    if re.search(r'\binterface\s+\w+\s*\{|\):\s*\w+\s*(?:\{|=>)|\b\w+\s*:\s*(?:string|number|boolean)\b|\benum\s+\w+\s*\{|\bas\s+(?:string|number|any)\b|\bimplements\b', code):
        return 'typescript'
    if re.search(r'\bfunction\b|=>|\b(?:const|let|var)\s+\w+|\bmodule\.exports\b|\brequire\(|^\s*import\s+.*\sfrom\s', code, re.M):
        return 'javascript'
    return 'python'


def max_code_bytes() -> int:
    """Largest source accepted (MAX_CODE_BYTES, default 1 MB): bigger input is not a single source file"""
    try:
        return int(os.getenv("MAX_CODE_BYTES", "1000000"))
    except ValueError:
        return 1000000


# Create router
if FASTAPI_AVAILABLE:
    router = APIRouter(prefix="/api", tags=["api"])
else:
    router = None


# Request/Response models
if FASTAPI_AVAILABLE:
    class GenerateResponse(BaseModel):
        """Response model for generate endpoint"""
        status: str  # "success"; failures are HTTP errors with a "detail" message
        code: str
        documentation: str
        raw_documentation: str
        format: str
        language: str
        ai_enhanced: bool
        stats: dict
        metadata: dict
        warnings: List[str] = []
        error: Optional[str] = None

    class AnalyzeResponse(BaseModel):
        """Response model for analyze endpoint"""
        success: bool
        total_functions: int
        total_classes: int
        functions: List[str]
        classes: List[str]
        language: str
        error: Optional[str] = None

    class EnhanceResponse(BaseModel):
        """Response model for enhance endpoint"""
        success: bool
        enhanced_code: str
        language: str
        style: str
        warnings: List[str] = []
        error: Optional[str] = None


def _one_line(text: object, limit: int = 300) -> str:
    return " ".join(str(text).split())[:limit]


def _fail(status_code: int, message: str):
    raise HTTPException(status_code=status_code, detail=_one_line(message))


async def read_input(file, code: Optional[str], language: str) -> Tuple[bytes, str, str, str, str]:
    """The source to document: (bytes, text, language, display name, file suffix).

    A file's own extension decides the language; pasted code uses the language field.
    """
    language = (language or "python").strip().lower()
    if file is not None and file.filename:
        data = await file.read()
        name = Path(file.filename).name
        suffix = Path(name).suffix.lower()
        if suffix in LANGUAGE_BY_EXTENSION:
            language = LANGUAGE_BY_EXTENSION[suffix]
        elif suffix:
            _fail(400, f"Unsupported file type '{suffix}'. Supported: {', '.join(sorted(LANGUAGE_BY_EXTENSION))}")
        else:
            if language == 'auto':
                language = detect_language(data.decode('utf-8', errors='replace'))
            if language not in EXTENSION_MAP:
                _fail(400, f"Unsupported language '{language}'. Choose from: {', '.join(EXTENSION_MAP)}")
        display = name
        suffix = suffix or EXTENSION_MAP[language]
    elif code is not None and code.strip():
        if language == 'auto':
            language = detect_language(code)
        if language not in EXTENSION_MAP:
            _fail(400, f"Unsupported language '{language}'. Choose from: {', '.join(EXTENSION_MAP)}")
        data = code.encode("utf-8")
        suffix = EXTENSION_MAP[language]
        display = f"pasted_code{suffix}"
    else:
        _fail(400, "No code provided")

    if not data.strip():
        _fail(400, "The file is empty")
    limit = max_code_bytes()
    if len(data) > limit:
        _fail(413, f"The source is {len(data):,} bytes; the limit is {limit:,} bytes")
    try:
        text = decode_source(data)
    except ParseError as error:
        _fail(400, error.message)
    return data, text, language, display, suffix


@contextmanager
def temp_source(data: bytes, suffix: str):
    """The source written to a temporary file (bytes as given, so the parser sees the real encoding)"""
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(data)
        path = tmp.name
    try:
        yield path
    finally:
        Path(path).unlink(missing_ok=True)


def scrub(message: object, tmp_path: str, display: str) -> str:
    """An error message as one line, without the server's temp path"""
    text = _one_line(message)
    for ref in (str(Path(tmp_path).resolve()), tmp_path, Path(tmp_path).name):
        text = text.replace(ref, display)
    return text


def check_provider(provider: str) -> str:
    provider = (provider or default_provider()).strip().lower()
    if provider not in PROVIDERS:
        _fail(400, f"Unsupported provider '{provider}'. Choose from: {', '.join(PROVIDERS)}")
    return provider


if FASTAPI_AVAILABLE:

    @router.get("/health")
    async def health_check():
        """Health check endpoint"""
        return {
            "status": "healthy",
            "version": __version__,
            "service": "code-doc-generator"
        }


    @router.get("/formats")
    async def get_formats():
        """Get available output formats"""
        return {
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
                {"id": "javascript", "name": "JavaScript/TypeScript", "extensions": [".js", ".ts", ".jsx", ".tsx"]},
                {"id": "java", "name": "Java", "extensions": [".java"]}
            ],
            "styles": [
                {"id": "auto", "name": "Auto-detect"},
                {"id": "google", "name": "Google Style"},
                {"id": "numpy", "name": "NumPy Style"},
                {"id": "jsdoc", "name": "JSDoc"},
                {"id": "javadoc", "name": "Javadoc"}
            ],
            "providers": [
                {"id": "ollama", "name": "Ollama (Local)", "requires_key": False},
                {"id": "anthropic", "name": "Anthropic Claude", "requires_key": True},
                {"id": "openai", "name": "OpenAI GPT", "requires_key": True}
            ]
        }


    @router.post("/generate")
    async def generate_docs(
        file: Optional[UploadFile] = File(None),
        code: Optional[str] = Form(None),
        language: str = Form("python"),
        format: str = Form("markdown"),
        provider: str = Form(default_provider()),
        model: Optional[str] = Form(None),
        use_ai: bool = Form(True)
    ):
        """
        Generate documentation from code.

        Accepts either file upload or direct code input. Problems with the request are 4xx errors
        with a one-line "detail"; things that went wrong along the way (a model that was down) are
        returned as "warnings" next to the documentation.
        """
        start_time = time.time()
        data, code_content, language, display, suffix = await read_input(file, code, language)
        format = (format or "markdown").strip().lower()
        if format not in WEB_FORMATS:
            _fail(400, f"Unsupported format '{format}'. Choose from: {', '.join(WEB_FORMATS)}")
        provider = check_provider(provider)
        model = (model or "").strip() or None

        with temp_source(data, suffix) as tmp_path:
            try:
                parsed = await run_in_threadpool(ParserRegistry().get_parser(tmp_path).parse_file, tmp_path)
            except Exception as error:
                _fail(422, f"Could not parse {display}: {scrub(error, tmp_path, display)}")

            stats = {
                "language": parsed.language,
                "functions": len(parsed.functions),
                "classes": len(parsed.classes),
                "lines": len(code_content.splitlines()),
            }

            generator = DocGenerator(llm_provider=provider, model=model, use_ai=use_ai)
            with tempfile.TemporaryDirectory() as tmp_dir:
                try:
                    # Blocking LLM calls: keep them off the event loop
                    output_files = await run_in_threadpool(
                        generator.generate_docs,
                        input_path=tmp_path,
                        output_format=format,
                        output_dir=tmp_dir,
                        recursive=False
                    )
                except Exception as error:
                    _fail(500, f"Could not generate documentation: {scrub(error, tmp_path, display)}")
                doc_content = Path(output_files[0]).read_text(encoding="utf-8")

        # Don't expose the server's temp path / random file name
        for temp_ref in (str(Path(tmp_path).resolve()), tmp_path, Path(tmp_path).name):
            doc_content = doc_content.replace(temp_ref, display)

        explainer = generator.ai_explainer
        ai_enhanced = bool(explainer and explainer.answers)
        metadata = {
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "provider": provider.title(),
            "model": explainer.llm.model if ai_enhanced else "n/a (AI off)",
            "processing_time": round(time.time() - start_time, 2),
        }
        return GenerateResponse(
            status="success",
            code=code_content,
            documentation=doc_content,
            raw_documentation=doc_content,
            format=format,
            language=language,
            ai_enhanced=ai_enhanced,
            stats=stats,
            metadata=metadata,
            warnings=[scrub(w, tmp_path, display) for w in generator.warnings],
        )


    @router.post("/analyze")
    async def analyze_code(
        file: Optional[UploadFile] = File(None),
        code: Optional[str] = Form(None),
        language: str = Form("python")
    ):
        """
        Analyze code structure without generating documentation.
        """
        data, _text, language, display, suffix = await read_input(file, code, language)
        with temp_source(data, suffix) as tmp_path:
            generator = DocGenerator(use_ai=False)
            analysis = await run_in_threadpool(generator.analyze_structure, tmp_path, True)

        if analysis.get('failed_files'):
            _fail(422, f"Could not parse {display}: {scrub(analysis['failed_files'][0]['error'], tmp_path, display)}")

        functions: List[str] = []
        classes: List[str] = []
        for lang_stats in analysis.get('languages', {}).values():
            for file_info in lang_stats.get('files', []):
                functions.extend(file_info.get('function_names', []))
                classes.extend(file_info.get('class_names', []))

        return AnalyzeResponse(
            success=True,
            total_functions=analysis.get('total_functions', 0),
            total_classes=analysis.get('total_classes', 0),
            functions=functions,
            classes=classes,
            language=language
        )


    @router.post("/enhance")
    async def enhance_code(
        file: Optional[UploadFile] = File(None),
        code: Optional[str] = Form(None),
        language: str = Form("python"),
        style: str = Form("auto"),
        provider: str = Form(default_provider()),
        model: Optional[str] = Form(None)
    ):
        """
        Enhance code with AI-generated docstrings.
        """
        data, _text, language, display, suffix = await read_input(file, code, language)
        provider = check_provider(provider)
        model = (model or "").strip() or None
        style = (style or "auto").strip().lower()

        generator = DocGenerator(llm_provider=provider, model=model, use_ai=True)
        if not generator.use_ai:
            _fail(503, "AI is not available: " + (generator.warnings[0] if generator.warnings else "no model configured"))

        with temp_source(data, suffix) as tmp_path:
            out_path = str(Path(tmp_path).with_name(Path(tmp_path).stem + "_documented" + suffix))
            try:
                try:
                    await run_in_threadpool(
                        generator.enhance_code, input_path=tmp_path, output_path=out_path, style=style
                    )
                except ParseError as error:
                    _fail(422, f"Could not parse {display}: {scrub(error, tmp_path, display)}")
                except AIUnavailableError as error:
                    _fail(503, scrub(error, tmp_path, display))
                except ValueError as error:
                    _fail(400, scrub(error, tmp_path, display))
                except HTTPException:
                    raise
                except Exception as error:
                    _fail(500, f"Could not enhance the code: {scrub(error, tmp_path, display)}")
                enhanced = Path(out_path).read_text(encoding="utf-8")
            finally:
                Path(out_path).unlink(missing_ok=True)

        warnings = [scrub(w, tmp_path, display) for w in generator.warnings]
        return EnhanceResponse(
            success=True,
            enhanced_code=enhanced,
            language=language,
            style=style,
            warnings=warnings,
        )
