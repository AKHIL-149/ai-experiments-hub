"""AI-powered code explanation generator using LLMs"""
import re
from pathlib import Path
from typing import Dict, List, Optional
from .llm_client import LLMClient, LLMError
from .cache_manager import CacheManager
from ..parsers.models import FunctionInfo, ClassInfo, ParsedModule, ParameterInfo


# Bump when prompts or response cleaning change so stale cache entries
# (e.g. ones containing "Here is a summary of...") are not served again.
CACHE_VERSION = "v3"

# Shared by every prompt: the model describes the code it is shown, not what the names suggest.
_GROUNDING_RULES = (
    "Describe only what the code shown actually does.\n"
    "- Base every statement on the signature, docstring and code given, never on a name alone.\n"
    "- If the body is trivial (returns a constant or its own input, does nothing, only prints), say exactly "
    "that in plain words, even when the name suggests more.\n"
    "- Do not mention networks, files, databases, security, retries or any other behaviour unless the code does it.\n"
    "- Never describe a parameter as used when it is listed as unused.\n"
    "- Write plain sentences with no introduction, no headings and no advice."
)
SYSTEM_FUNCTION = "You document source code. " + _GROUNDING_RULES + "\nAnswer in 1 or 2 sentences."
SYSTEM_CLASS = ("You document source code. " + _GROUNDING_RULES +
                "\nSay what the class holds and what it offers, using its attributes and methods. Answer in 2 or 3 sentences.")
SYSTEM_MODULE = ("You document source code. " + _GROUNDING_RULES +
                 "\nSummarise what the module contains. Do not guess what application it belongs to. Answer in 2 or 3 sentences.")
SYSTEM_PARAMETERS = ("You document source code. " + _GROUNDING_RULES +
                     "\nOutput only lines in the form `name: description`, one per parameter, with no introduction.")

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


def trim_to_last_sentence(text: str) -> str:
    """Cut a reply that hit the token limit back to its last complete sentence."""
    text = text.rstrip()
    if re.search(r"[.!?][\"')\]`]*$", text):
        return text
    match = re.match(r"(?s)^(.*[.!?][\"')\]`]*)(?:\s|$)", text)
    if match and len(match.group(1)) >= 8:      # a shorter fragment is not worth keeping on its own
        return match.group(1)
    return text + "\u2026"


def _first_line(text: Optional[str]) -> str:
    return (text or "").strip().split("\n")[0].strip()


def _render_parameter(p: ParameterInfo) -> str:
    text = f"{p.name}: {p.type_hint}" if p.type_hint else p.name
    return f"{text} = {p.default_value}" if p.default_value is not None else text


def _render_signature(func: FunctionInfo) -> str:
    params = ", ".join(_render_parameter(p) for p in func.parameters)
    ret = f" -> {func.return_type}" if func.return_type else ""
    return f"{'async ' if func.is_async else ''}def {func.name}({params}){ret}"


def _body_block(func: FunctionInfo) -> str:
    """The function body as the model should see it, saying whether it is the whole body."""
    if func.body_summary:
        shown = len(func.body_summary.split("\n"))
        total = func.body_lines if func.body_lines else shown
        if total <= shown:
            return "Body (complete):\n" + func.body_summary
        return f"Body (first {shown} of {total} lines):\n{func.body_summary}"
    if func.body_lines == 0:
        return "Body: empty (it has no statements besides a docstring)"
    return "Body: not available. Describe only from the signature and docstring, and say what is not known."


class AIExplainer:
    """
    Generates human-friendly explanations for code elements using LLMs.

    Prompts are built from what the code really contains, and a failing backend is reported once
    (see ``warnings``) instead of once per function. Explanations that cannot be produced come
    back as an empty string, never as an error message pretending to be documentation.
    """

    def __init__(
        self,
        llm_client: Optional[LLMClient] = None,
        cache_manager: Optional[CacheManager] = None,
        enable_cache: bool = True,
        max_failures: int = 3
    ):
        """
        Initialize AI explainer.

        Args:
            llm_client: LLM client instance (creates default Ollama client if None)
            cache_manager: Cache manager instance (creates default if None)
            enable_cache: Whether to use caching
            max_failures: Failures in a row (not counting permanent ones) before AI is switched off
        """
        self.llm = llm_client or LLMClient(backend="ollama")
        self.cache = (cache_manager or CacheManager()) if enable_cache else None
        self.enable_cache = enable_cache
        self.max_failures = max_failures
        self.warnings: List[str] = []
        self.available = True
        self.answers = 0        # explanations delivered in this run (fresh or from the cache)
        self._failures = 0

    def reset(self) -> None:
        """Start a new run: forget old warnings and give AI that was switched off a fresh chance."""
        self.warnings.clear()
        self.available = True
        self.answers = 0
        self._failures = 0

    # ------------------------------------------------------------------ talking to the model

    def _warn(self, message: str) -> None:
        if message not in self.warnings:
            self.warnings.append(message)

    def _ask(self, prompt: str, system: str, max_tokens: int) -> Optional[str]:
        """One model call. None when AI is off or the call failed (the reason is recorded in warnings)."""
        if not self.available:
            return None
        try:
            text = self.llm.generate(prompt=prompt, max_tokens=max_tokens, temperature=0.2, system=system)
        except LLMError as error:
            self._failures += 1
            if error.permanent or self._failures >= self.max_failures:
                self.available = False
                self._warn(f"AI explanations were switched off: {error}")
            else:
                self._warn(f"An AI explanation could not be generated: {error}")
            return None
        except Exception as error:  # an unexpected client bug must not take the whole run down
            self._failures += 1
            self._warn(f"An AI explanation could not be generated: {' '.join(str(error).split())[:200]}")
            if self._failures >= self.max_failures:
                self.available = False
                self._warn("AI explanations were switched off after repeated failures")
            return None

        self._failures = 0
        text = clean_llm_text(text)
        if getattr(self.llm, "truncated", False):
            text = trim_to_last_sentence(text)
        return text or None

    def _cached(self, key: str) -> Optional[str]:
        if self.enable_cache and self.cache:
            return self.cache.get_ai_cache(key, self.llm.model) or None
        return None

    def _remember(self, key: str, text: str) -> None:
        if self.enable_cache and self.cache and text:
            self.cache.set_ai_cache(key, self.llm.model, text)

    def _generate(self, kind: str, prompt: str, system: str, max_tokens: int) -> str:
        key = f"{CACHE_VERSION}:{kind}:{prompt}"
        cached = self._cached(key)
        if cached:
            self.answers += 1
            return cached
        text = self._ask(prompt, system, max_tokens)
        if not text:
            return ""
        self.answers += 1
        self._remember(key, text)
        return text

    # ------------------------------------------------------------------ public API

    def explain_function(self, func_info: FunctionInfo, context: str = "", max_tokens: int = 200) -> str:
        """Explain a function in 1-2 sentences ("" if no explanation could be produced)."""
        return self._generate("function", self._build_function_prompt(func_info, context), SYSTEM_FUNCTION, max_tokens)

    def explain_class(self, class_info: ClassInfo, context: str = "", max_tokens: int = 250) -> str:
        """Explain a class in 2-3 sentences ("" if no explanation could be produced)."""
        return self._generate("class", self._build_class_prompt(class_info, context), SYSTEM_CLASS, max_tokens)

    def generate_module_summary(self, parsed_module: ParsedModule, max_tokens: int = 300) -> str:
        """Summarise a module. An empty module (no docstring, functions or classes) gets no summary."""
        if not (parsed_module.module_docstring or parsed_module.functions or parsed_module.classes):
            return ""
        prompt = self._build_module_prompt(parsed_module)
        return self._generate(f"module:{parsed_module.file_path}", prompt, SYSTEM_MODULE, max_tokens)

    def enhance_parameter_descriptions(
        self,
        parameters: List[ParameterInfo],
        function_context: str = "",
        func_info: Optional[FunctionInfo] = None
    ) -> List[ParameterInfo]:
        """
        Add descriptions to parameters.

        A parameter the body never uses is described as such directly (no model needed, and no
        chance of it being invented). The rest are described by the model from the function's code.
        """
        if not parameters:
            return parameters

        for param in parameters:
            if param.used is False and not param.description:
                param.description = "Not used by the current implementation."

        pending = [p for p in parameters if not p.description and p.used is not None]
        if not pending:
            return parameters

        prompt = self._build_parameter_prompt(pending, function_context, func_info)
        names = [p.name for p in pending]
        response = self._generate("params", prompt, SYSTEM_PARAMETERS, 50 * len(pending) + 50)
        if not response:
            return parameters

        descriptions = parse_parameter_descriptions(response, names)
        for param in pending:
            if param.name in descriptions:
                param.description = descriptions[param.name]
        return parameters

    # ------------------------------------------------------------------ prompts

    def _build_function_prompt(self, func_info: FunctionInfo, context: str) -> str:
        """Prompt for a function: signature, docstring, the real body and which parameters are unused."""
        parts = []
        if context:
            parts.append(f"Context: {context}")
        parts.append(f"Signature: {_render_signature(func_info)}")
        if func_info.decorators:
            parts.append(f"Decorators: {', '.join(func_info.decorators)}")
        if func_info.docstring:
            parts.append(f"Docstring: {func_info.docstring[:300]}")
        parts.append(_body_block(func_info))
        unused = [p.name for p in func_info.parameters if p.used is False]
        if unused:
            parts.append(f"Parameters not used in the body: {', '.join(unused)}")
        parts.append("\nIn 1 or 2 sentences, say what this function does, using only the information above:")
        return "\n".join(parts)

    def _build_class_prompt(self, class_info: ClassInfo, context: str) -> str:
        """Prompt for a class: docstring, attributes and what each method's body does."""
        parts = []
        if context:
            parts.append(f"Context: {context}")
        inheritance = f"({', '.join(class_info.base_classes)})" if class_info.base_classes else ""
        kind = next((k for k in ("interface", "enum") if k in {d.lstrip("@") for d in class_info.decorators}), "class")
        parts.append(f"{kind.capitalize()}: {class_info.name}{inheritance}")
        if class_info.docstring:
            parts.append(f"Docstring: {class_info.docstring[:300]}")

        if class_info.attributes:
            lines = []
            for a in class_info.attributes[:12]:
                detail = f": {a['type']}" if a.get("type") else ""
                value = f" = {a['default_value']}" if a.get("default_value") else ""
                where = {"instance": " (set in __init__)", "class": " (class attribute)"}.get(a.get("scope"), "")
                lines.append(f"  - {a['name']}{detail}{value}{where}")
            parts.append("Attributes:\n" + "\n".join(lines))

        if class_info.methods:
            lines = []
            for m in class_info.methods[:12]:
                doc = _first_line(m.docstring)
                body = "; ".join((m.body_summary or "").split("\n")[:3])[:160]
                detail = doc or (f"body: {body}" if body else ("body: empty" if m.body_lines == 0 else ""))
                lines.append(f"  - {_render_signature(m)}" + (f"  [{detail}]" if detail else ""))
            more = f"\n  (and {len(class_info.methods) - 12} more methods)" if len(class_info.methods) > 12 else ""
            parts.append("Methods:\n" + "\n".join(lines) + more)

        parts.append(f"\nIn 2 or 3 sentences, say what this {kind} holds and offers, using only the information above:")
        return "\n".join(parts)

    def _build_module_prompt(self, parsed_module: ParsedModule) -> str:
        """Prompt for a module: its docstring, imports and what it defines."""
        parts = [f"Module: {Path(parsed_module.file_path).name}"]
        if parsed_module.module_docstring:
            parts.append(f"Docstring: {parsed_module.module_docstring[:300]}")
        if parsed_module.imports:
            parts.append(f"Imports: {', '.join(parsed_module.imports[:8])}")
        if parsed_module.functions:
            lines = [f"  - {_render_signature(f)}" + (f"  [{_first_line(f.docstring)}]" if f.docstring else "")
                     for f in parsed_module.functions[:10]]
            parts.append("Functions:\n" + "\n".join(lines))
        if parsed_module.classes:
            lines = [f"  - {c.name}" + (f"  [{_first_line(c.docstring)}]" if c.docstring else "")
                     for c in parsed_module.classes[:10]]
            parts.append("Classes:\n" + "\n".join(lines))
        parts.append("\nIn 2 or 3 sentences, say what this module contains, using only the information above:")
        return "\n".join(parts)

    def _build_parameter_prompt(
        self,
        parameters: List[ParameterInfo],
        function_context: str,
        func_info: Optional[FunctionInfo] = None
    ) -> str:
        """Prompt for parameter descriptions, with the function's code so they come from real usage."""
        parts = [f"Function: {function_context}"]
        if func_info is not None:
            parts.append(f"Signature: {_render_signature(func_info)}")
            if func_info.docstring:
                parts.append(f"Docstring: {func_info.docstring[:300]}")
            parts.append(_body_block(func_info))
        parts.append("\nDescribe these parameters, one per line, as `name: description` (what it is for, judging by the code):")
        parts.extend(f"  - {_render_parameter(p)}" for p in parameters)
        return "\n".join(parts)
