"""AI-powered code explanation generator using LLMs"""
import re
from pathlib import Path
from typing import Dict, List, Optional
from .llm_client import LLMClient
from .cache_manager import CacheManager
from ..parsers.models import FunctionInfo, ClassInfo, ParsedModule, ParameterInfo


# Bump when prompts or response cleaning change so stale cache entries
# (e.g. ones containing "Here is a summary of...") are not served again.
CACHE_VERSION = "v2"

_PREAMBLE_RE = re.compile(
    r"^\s*(here\s+(is|are)|sure|certainly|of course|okay|below (is|are))\b[^\n]*:\s*$",
    re.IGNORECASE,
)
_PREAMBLE_INLINE_RE = re.compile(
    r"^\s*(here\s+(is|are)|sure|certainly|of course)\b[^\n:]*:\s+(?=\S)",
    re.IGNORECASE,
)
_BASED_ON_RE = re.compile(
    r"^\s*based on (?:the )?(?:provided |given )?(?:context|code|information|details|snippet)[^,]{0,40},\s*",
    re.IGNORECASE,
)
_EDITORIAL_RE = re.compile(r"^\s*(note\b|please note|i hope|let me know)", re.IGNORECASE)


def clean_llm_text(text: str) -> str:
    """Strip chatty framing the model wraps around the actual explanation.

    Removes a leading "Here is ...:" line and trailing "Note that ..." style
    paragraphs, which otherwise end up inside the generated documentation.
    """
    text = (text or "").strip()
    lines = text.split("\n")
    while lines and (not lines[0].strip() or _PREAMBLE_RE.match(lines[0])):
        lines.pop(0)
    text = "\n".join(lines).strip()
    text = _PREAMBLE_INLINE_RE.sub("", text, count=1)
    stripped = _BASED_ON_RE.sub("", text, count=1)
    if stripped != text:
        text = stripped[:1].upper() + stripped[1:]

    paragraphs = [p for p in re.split(r"\n\s*\n", text)]
    # Only drop editorial paragraphs that follow real content.
    kept = paragraphs[:1] + [p for p in paragraphs[1:] if not _EDITORIAL_RE.match(p)]
    return "\n\n".join(kept).strip()


def parse_parameter_descriptions(response: str, names: List[str]) -> Dict[str, str]:
    """Map parameter name -> description from an LLM list-style response.

    Matches lines like "- `x`: desc", "x - desc" or "1. x: desc" by name, so
    preamble lines and reordering cannot shift descriptions onto the wrong
    parameter.
    """
    found: Dict[str, str] = {}
    for line in (response or "").split("\n"):
        line = line.strip()
        for name in names:
            if name in found:
                continue
            m = re.match(
                r"^(?:[-*\u2022]|\d+[.)])?\s*[`*_]*" + re.escape(name) + r"[`*_]*"
                r"(?:\s*\([^)]*\))?\s*[:\-\u2013\u2014]+\s*(.+)$",
                line,
            )
            if m:
                found[name] = m.group(1).strip().strip("*_ ")
                break
    return found


class AIExplainer:
    """
    Generates human-friendly explanations for code elements using LLMs.

    Uses a two-level caching strategy to minimize API calls.
    """

    def __init__(
        self,
        llm_client: Optional[LLMClient] = None,
        cache_manager: Optional[CacheManager] = None,
        enable_cache: bool = True
    ):
        """
        Initialize AI explainer.

        Args:
            llm_client: LLM client instance (creates default Ollama client if None)
            cache_manager: Cache manager instance (creates default if None)
            enable_cache: Whether to use caching
        """
        self.llm = llm_client or LLMClient(backend="ollama")
        self.cache = cache_manager or CacheManager() if enable_cache else None
        self.enable_cache = enable_cache

    def explain_function(
        self,
        func_info: FunctionInfo,
        context: str = "",
        max_tokens: int = 200
    ) -> str:
        """
        Generate explanation for a function.

        Args:
            func_info: Function information
            context: Additional context (module name, class name, etc.)
            max_tokens: Maximum tokens for explanation

        Returns:
            Human-friendly explanation
        """
        # Build prompt; it carries the signature, context, docstring and body
        # preview, so keying on it keeps same-named methods in different
        # classes apart and invalidates the entry when the code changes.
        prompt = self._build_function_prompt(func_info, context)
        signature = f"{CACHE_VERSION}:function:{prompt}"

        # Check cache
        if self.enable_cache and self.cache:
            cached = self.cache.get_ai_cache(signature, self.llm.model)
            if cached:
                return cached

        # Generate explanation
        try:
            explanation = self.llm.generate(
                prompt=prompt,
                max_tokens=max_tokens,
                temperature=0.3,  # Lower temperature for more focused explanations
                system="You are a code documentation expert. Provide clear, concise explanations of code functions. Focus on WHAT the function does and WHY, not HOW (the code shows that). Be technical but accessible."
            )

            explanation = clean_llm_text(explanation)

            # Cache the result
            if self.enable_cache and self.cache:
                self.cache.set_ai_cache(signature, self.llm.model, explanation)

            return explanation

        except Exception as e:
            return f"[AI explanation unavailable: {str(e)}]"

    def explain_class(
        self,
        class_info: ClassInfo,
        context: str = "",
        max_tokens: int = 250
    ) -> str:
        """
        Generate explanation for a class.

        Args:
            class_info: Class information
            context: Additional context (module name, etc.)
            max_tokens: Maximum tokens for explanation

        Returns:
            Human-friendly explanation
        """
        prompt = self._build_class_prompt(class_info, context)
        signature = f"{CACHE_VERSION}:class:{prompt}"

        # Check cache
        if self.enable_cache and self.cache:
            cached = self.cache.get_ai_cache(signature, self.llm.model)
            if cached:
                return cached

        # Generate explanation
        try:
            explanation = self.llm.generate(
                prompt=prompt,
                max_tokens=max_tokens,
                temperature=0.3,
                system="You are a code documentation expert. Explain what this class represents and its main responsibilities. Focus on the purpose and design, not implementation details."
            )

            explanation = clean_llm_text(explanation)

            # Cache the result
            if self.enable_cache and self.cache:
                self.cache.set_ai_cache(signature, self.llm.model, explanation)

            return explanation

        except Exception as e:
            return f"[AI explanation unavailable: {str(e)}]"

    def generate_module_summary(
        self,
        parsed_module: ParsedModule,
        max_tokens: int = 300
    ) -> str:
        """
        Generate high-level module summary.

        Args:
            parsed_module: Parsed module data
            max_tokens: Maximum tokens for summary

        Returns:
            Module-level summary
        """
        prompt = self._build_module_prompt(parsed_module)
        cache_key = f"{CACHE_VERSION}:module:{parsed_module.file_path}:{prompt}"

        # Check cache
        if self.enable_cache and self.cache:
            cached = self.cache.get_ai_cache(cache_key, self.llm.model)
            if cached:
                return cached

        # Generate summary
        try:
            summary = self.llm.generate(
                prompt=prompt,
                max_tokens=max_tokens,
                temperature=0.3,
                system="You are a code documentation expert. Provide a high-level summary of what this module does. Explain its purpose and main components in 2-3 sentences."
            )

            summary = clean_llm_text(summary)

            # Cache the result
            if self.enable_cache and self.cache:
                self.cache.set_ai_cache(cache_key, self.llm.model, summary)

            return summary

        except Exception as e:
            return f"[AI summary unavailable: {str(e)}]"

    def enhance_parameter_descriptions(
        self,
        parameters: List[ParameterInfo],
        function_context: str = ""
    ) -> List[ParameterInfo]:
        """
        Add descriptions to parameters using AI.

        Args:
            parameters: List of parameters
            function_context: Context about the function

        Returns:
            Parameters with AI-generated descriptions
        """
        if not parameters:
            return parameters

        prompt = self._build_parameter_prompt(parameters, function_context)
        cache_key = f"{CACHE_VERSION}:params:{prompt}"
        names = [p.name for p in parameters]

        response = None
        if self.enable_cache and self.cache:
            response = self.cache.get_ai_cache(cache_key, self.llm.model)

        if not response:
            try:
                response = self.llm.generate(
                    prompt=prompt,
                    max_tokens=50 * len(parameters),  # ~50 tokens per parameter
                    temperature=0.3,
                    system="You are a code documentation expert. Provide brief descriptions for function parameters. Output only lines in the form `name: description`, one per parameter, with no introduction."
                )
            except Exception:
                # If AI fails, return original parameters
                return parameters

            response = response.strip()
            if self.enable_cache and self.cache:
                self.cache.set_ai_cache(cache_key, self.llm.model, response)

        # Apply descriptions by parameter name so preambles or reordering
        # cannot attach text to the wrong parameter
        descriptions = parse_parameter_descriptions(response, names)
        for param in parameters:
            if param.name in descriptions:
                param.description = descriptions[param.name]

        return parameters

    def _build_function_prompt(self, func_info: FunctionInfo, context: str) -> str:
        """Build prompt for function explanation."""
        params = ", ".join([
            f"{p.name}: {p.type_hint}" if p.type_hint else p.name
            for p in func_info.parameters
        ])

        return_type = f" -> {func_info.return_type}" if func_info.return_type else ""
        async_marker = "async " if func_info.is_async else ""

        prompt_parts = []

        if context:
            prompt_parts.append(f"Context: {context}")

        prompt_parts.append(f"Function: {async_marker}def {func_info.name}({params}){return_type}")

        if func_info.docstring:
            prompt_parts.append(f"Existing docstring: {func_info.docstring[:200]}")

        if func_info.decorators:
            prompt_parts.append(f"Decorators: {', '.join(func_info.decorators)}")

        if func_info.body_summary:
            prompt_parts.append(f"Code preview:\n{func_info.body_summary[:300]}")

        prompt_parts.append("\nExplain what this function does in 1-2 clear sentences:")

        return "\n".join(prompt_parts)

    def _build_class_prompt(self, class_info: ClassInfo, context: str) -> str:
        """Build prompt for class explanation."""
        prompt_parts = []

        if context:
            prompt_parts.append(f"Context: {context}")

        inheritance = ""
        if class_info.base_classes:
            inheritance = f"({', '.join(class_info.base_classes)})"

        prompt_parts.append(f"Class: {class_info.name}{inheritance}")

        if class_info.docstring:
            prompt_parts.append(f"Existing docstring: {class_info.docstring[:200]}")

        if class_info.methods:
            method_names = [m.name for m in class_info.methods[:5]]  # First 5 methods
            prompt_parts.append(f"Methods: {', '.join(method_names)}")

        if class_info.attributes:
            attr_names = [a['name'] for a in class_info.attributes[:5]]  # First 5 attributes
            prompt_parts.append(f"Attributes: {', '.join(attr_names)}")

        prompt_parts.append("\nExplain what this class represents and its main purpose in 2-3 sentences:")

        return "\n".join(prompt_parts)

    def _build_module_prompt(self, parsed_module: ParsedModule) -> str:
        """Build prompt for module summary."""
        prompt_parts = [f"Module: {Path(parsed_module.file_path).name}"]

        if parsed_module.module_docstring:
            prompt_parts.append(f"Existing docstring: {parsed_module.module_docstring[:200]}")

        if parsed_module.functions:
            func_names = [f.name for f in parsed_module.functions[:5]]
            prompt_parts.append(f"Functions: {', '.join(func_names)}")

        if parsed_module.classes:
            class_names = [c.name for c in parsed_module.classes[:5]]
            prompt_parts.append(f"Classes: {', '.join(class_names)}")

        prompt_parts.append("\nProvide a brief summary of what this module does:")

        return "\n".join(prompt_parts)

    def _build_parameter_prompt(
        self,
        parameters: List[ParameterInfo],
        function_context: str
    ) -> str:
        """Build prompt for parameter descriptions."""
        param_list = []
        for p in parameters:
            type_info = f": {p.type_hint}" if p.type_hint else ""
            default = f" = {p.default_value}" if p.default_value else ""
            param_list.append(f"  - {p.name}{type_info}{default}")

        prompt = f"Function context: {function_context}\n\nParameters:\n" + "\n".join(param_list)
        prompt += "\n\nProvide a brief description for each parameter, formatted as `name: description`, one per line:"

        return prompt
