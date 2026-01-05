"""AI-powered code explanation generator using LLMs"""
from typing import List, Optional
from .llm_client import LLMClient
from .cache_manager import CacheManager
from ..parsers.models import FunctionInfo, ClassInfo, ParsedModule, ParameterInfo


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
        # Build function signature for cache key
        params = ", ".join([p.name for p in func_info.parameters])
        signature = f"{func_info.name}({params})"

        # Check cache
        if self.enable_cache and self.cache:
            cached = self.cache.get_ai_cache(signature, self.llm.model)
            if cached:
                return cached

        # Build prompt
        prompt = self._build_function_prompt(func_info, context)

        # Generate explanation
        try:
            explanation = self.llm.generate(
                prompt=prompt,
                max_tokens=max_tokens,
                temperature=0.3,  # Lower temperature for more focused explanations
                system="You are a code documentation expert. Provide clear, concise explanations of code functions. Focus on WHAT the function does and WHY, not HOW (the code shows that). Be technical but accessible."
            )

            # Cache the result
            if self.enable_cache and self.cache:
                self.cache.set_ai_cache(signature, self.llm.model, explanation)

            return explanation.strip()

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
        # Build class signature for cache key
        inheritance = f" extends {', '.join(class_info.base_classes)}" if class_info.base_classes else ""
        signature = f"class {class_info.name}{inheritance}"

        # Check cache
        if self.enable_cache and self.cache:
            cached = self.cache.get_ai_cache(signature, self.llm.model)
            if cached:
                return cached

        # Build prompt
        prompt = self._build_class_prompt(class_info, context)

        # Generate explanation
        try:
            explanation = self.llm.generate(
                prompt=prompt,
                max_tokens=max_tokens,
                temperature=0.3,
                system="You are a code documentation expert. Explain what this class represents and its main responsibilities. Focus on the purpose and design, not implementation details."
            )

            # Cache the result
            if self.enable_cache and self.cache:
                self.cache.set_ai_cache(signature, self.llm.model, explanation)

            return explanation.strip()

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
        # Use file path as cache key
        cache_key = f"module:{parsed_module.file_path}"

        # Check cache
        if self.enable_cache and self.cache:
            cached = self.cache.get_ai_cache(cache_key, self.llm.model)
            if cached:
                return cached

        # Build prompt
        prompt = self._build_module_prompt(parsed_module)

        # Generate summary
        try:
            summary = self.llm.generate(
                prompt=prompt,
                max_tokens=max_tokens,
                temperature=0.3,
                system="You are a code documentation expert. Provide a high-level summary of what this module does. Explain its purpose and main components in 2-3 sentences."
            )

            # Cache the result
            if self.enable_cache and self.cache:
                self.cache.set_ai_cache(cache_key, self.llm.model, summary)

            return summary.strip()

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

        # Build cache key
        param_names = ", ".join([p.name for p in parameters])
        cache_key = f"params:{param_names}:{function_context}"

        # Check cache
        cached_descriptions = None
        if self.enable_cache and self.cache:
            cached = self.cache.get_ai_cache(cache_key, self.llm.model)
            if cached:
                cached_descriptions = cached.split("\n")

        # Generate descriptions if not cached
        if not cached_descriptions:
            prompt = self._build_parameter_prompt(parameters, function_context)

            try:
                response = self.llm.generate(
                    prompt=prompt,
                    max_tokens=50 * len(parameters),  # ~50 tokens per parameter
                    temperature=0.3,
                    system="You are a code documentation expert. Provide brief descriptions for function parameters. One line per parameter."
                )

                cached_descriptions = response.strip().split("\n")

                # Cache the result
                if self.enable_cache and self.cache:
                    self.cache.set_ai_cache(cache_key, self.llm.model, response.strip())

            except Exception:
                # If AI fails, return original parameters
                return parameters

        # Apply descriptions to parameters
        enhanced = []
        for i, param in enumerate(parameters):
            if i < len(cached_descriptions):
                param.description = cached_descriptions[i].strip()
            enhanced.append(param)

        return enhanced

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
        prompt += "\n\nProvide a brief description for each parameter (one line each):"

        return prompt


# Import Path for module prompt
from pathlib import Path
