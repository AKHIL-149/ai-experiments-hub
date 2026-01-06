"""API routes for code documentation generator web interface"""
import tempfile
import shutil
from pathlib import Path
from typing import Optional, List

try:
    from fastapi import APIRouter, UploadFile, File, Form, HTTPException
    from fastapi.responses import JSONResponse, FileResponse
    from pydantic import BaseModel
    FASTAPI_AVAILABLE = True
except ImportError:
    FASTAPI_AVAILABLE = False
    APIRouter = None
    BaseModel = object

from src.core import DocGenerator
from src.utils import FileDiscovery

# Create router
if FASTAPI_AVAILABLE:
    router = APIRouter(prefix="/api", tags=["api"])
else:
    router = None


# Request/Response models
if FASTAPI_AVAILABLE:
    class GenerateRequest(BaseModel):
        """Request model for generate endpoint"""
        code: str
        language: str = "python"
        format: str = "markdown"
        provider: str = "ollama"
        model: Optional[str] = None
        use_ai: bool = True
        
    class GenerateResponse(BaseModel):
        """Response model for generate endpoint"""
        status: str  # "success" or "error"
        code: str
        documentation: str
        raw_documentation: str
        format: str
        language: str
        ai_enhanced: bool
        stats: dict
        metadata: dict
        error: Optional[str] = None
        
    class AnalyzeRequest(BaseModel):
        """Request model for analyze endpoint"""
        code: str
        language: str = "python"
        
    class AnalyzeResponse(BaseModel):
        """Response model for analyze endpoint"""
        success: bool
        total_functions: int
        total_classes: int
        functions: List[str]
        classes: List[str]
        language: str
        error: Optional[str] = None
        
    class EnhanceRequest(BaseModel):
        """Request model for enhance endpoint"""
        code: str
        language: str = "python"
        style: str = "auto"
        provider: str = "ollama"
        model: Optional[str] = None
        
    class EnhanceResponse(BaseModel):
        """Response model for enhance endpoint"""
        success: bool
        enhanced_code: str
        language: str
        style: str
        error: Optional[str] = None


if FASTAPI_AVAILABLE:
    
    @router.get("/health")
    async def health_check():
        """Health check endpoint"""
        return {
            "status": "healthy",
            "version": "0.7.3",
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
        provider: str = Form("ollama"),
        model: Optional[str] = Form(None),
        use_ai: bool = Form(True)
    ):
        """
        Generate documentation from code.

        Accepts either file upload or direct code input.
        """
        import time
        from datetime import datetime

        start_time = time.time()

        try:
            # Get code content
            if file:
                code_content = await file.read()
                code_content = code_content.decode('utf-8')
                # Detect language from extension if not provided
                if file.filename:
                    ext = Path(file.filename).suffix
                    if ext == '.py':
                        language = 'python'
                    elif ext in ['.js', '.ts', '.jsx', '.tsx']:
                        language = 'javascript'
                    elif ext == '.java':
                        language = 'java'
            elif code:
                code_content = code
            else:
                raise HTTPException(status_code=400, detail="No code provided")

            # Create temporary file
            with tempfile.NamedTemporaryFile(mode='w', suffix=f'.{language}', delete=False) as tmp_file:
                tmp_file.write(code_content)
                tmp_path = tmp_file.name

            try:
                # Initialize generator
                generator = DocGenerator(
                    llm_provider=provider,
                    model=model,
                    use_ai=use_ai,
                    enable_cache=True
                )

                # First, analyze the code to get stats
                from src.parsers.parser_registry import ParserRegistry
                registry = ParserRegistry()
                parser = registry.get_parser(tmp_path)
                parsed = parser.parse_file(tmp_path)

                # Calculate stats
                stats = {
                    "language": parsed.language,
                    "functions": len(parsed.functions),
                    "classes": len(parsed.classes),
                    "lines": code_content.count('\n') + 1
                }

                # Create temporary output directory
                with tempfile.TemporaryDirectory() as tmp_dir:
                    # Generate documentation
                    output_files = generator.generate_docs(
                        input_path=tmp_path,
                        output_format=format,
                        output_dir=tmp_dir,
                        recursive=False
                    )

                    if output_files:
                        # Read generated documentation
                        doc_content = Path(output_files[0]).read_text()

                        # Calculate processing time
                        processing_time = round(time.time() - start_time, 2)

                        # Create metadata
                        metadata = {
                            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                            "provider": provider.title(),
                            "model": model or "Default",
                            "processing_time": processing_time
                        }

                        return GenerateResponse(
                            status="success",
                            code=code_content,
                            documentation=doc_content,
                            raw_documentation=doc_content,
                            format=format,
                            language=language,
                            ai_enhanced=use_ai,
                            stats=stats,
                            metadata=metadata
                        )
                    else:
                        raise Exception("No documentation generated")

            finally:
                # Clean up temporary file
                Path(tmp_path).unlink(missing_ok=True)

        except Exception as e:
            return GenerateResponse(
                status="error",
                code=code or "",
                documentation="",
                raw_documentation="",
                format=format,
                language=language,
                ai_enhanced=use_ai,
                stats={},
                metadata={},
                error=str(e)
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
        try:
            # Get code content
            if file:
                code_content = await file.read()
                code_content = code_content.decode('utf-8')
                if file.filename:
                    ext = Path(file.filename).suffix
                    if ext == '.py':
                        language = 'python'
                    elif ext in ['.js', '.ts', '.jsx', '.tsx']:
                        language = 'javascript'
                    elif ext == '.java':
                        language = 'java'
            elif code:
                code_content = code
            else:
                raise HTTPException(status_code=400, detail="No code provided")
            
            # Create temporary file
            with tempfile.NamedTemporaryFile(mode='w', suffix=f'.{language}', delete=False) as tmp_file:
                tmp_file.write(code_content)
                tmp_path = tmp_file.name
            
            try:
                # Initialize generator (no AI needed)
                generator = DocGenerator(use_ai=False)
                
                # Analyze structure
                analysis = generator.analyze_structure(tmp_path, show_details=True)
                
                # Extract function and class names
                functions = []
                classes = []
                
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
                
            finally:
                # Clean up temporary file
                Path(tmp_path).unlink(missing_ok=True)
                
        except Exception as e:
            return AnalyzeResponse(
                success=False,
                total_functions=0,
                total_classes=0,
                functions=[],
                classes=[],
                language=language,
                error=str(e)
            )
    
    
    @router.post("/enhance")
    async def enhance_code(
        file: Optional[UploadFile] = File(None),
        code: Optional[str] = Form(None),
        language: str = Form("python"),
        style: str = Form("auto"),
        provider: str = Form("ollama"),
        model: Optional[str] = Form(None)
    ):
        """
        Enhance code with AI-generated docstrings.
        """
        try:
            # Get code content
            if file:
                code_content = await file.read()
                code_content = code_content.decode('utf-8')
                if file.filename:
                    ext = Path(file.filename).suffix
                    if ext == '.py':
                        language = 'python'
                    elif ext in ['.js', '.ts', '.jsx', '.tsx']:
                        language = 'javascript'
                    elif ext == '.java':
                        language = 'java'
            elif code:
                code_content = code
            else:
                raise HTTPException(status_code=400, detail="No code provided")
            
            # Create temporary file
            with tempfile.NamedTemporaryFile(mode='w', suffix=f'.{language}', delete=False) as tmp_file:
                tmp_file.write(code_content)
                tmp_path = tmp_file.name
            
            try:
                # Initialize generator with AI
                generator = DocGenerator(
                    llm_provider=provider,
                    model=model,
                    use_ai=True,
                    enable_cache=True
                )
                
                # Create temporary output file
                with tempfile.NamedTemporaryFile(mode='w', suffix=f'_documented.{language}', delete=False) as tmp_out:
                    tmp_out_path = tmp_out.name
                
                try:
                    # Enhance code
                    output_path = generator.enhance_code(
                        input_path=tmp_path,
                        output_path=tmp_out_path,
                        style=style
                    )
                    
                    # Read enhanced code
                    enhanced_content = Path(output_path).read_text()
                    
                    return EnhanceResponse(
                        success=True,
                        enhanced_code=enhanced_content,
                        language=language,
                        style=style
                    )
                    
                finally:
                    # Clean up output file
                    Path(tmp_out_path).unlink(missing_ok=True)
                    
            finally:
                # Clean up input file
                Path(tmp_path).unlink(missing_ok=True)
                
        except Exception as e:
            return EnhanceResponse(
                success=False,
                enhanced_code="",
                language=language,
                style=style,
                error=str(e)
            )
