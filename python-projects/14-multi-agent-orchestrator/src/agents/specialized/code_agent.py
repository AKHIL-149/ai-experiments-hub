"""
Code Agent

Specialized agent for code generation, analysis, and debugging.
"""

from typing import Any, Dict
from datetime import datetime

from src.agents.base import BaseAgent, AgentConfig, AgentContext, AgentResult, AgentStatus
from src.agents.base import LLMProvider, LLMMessage, LLMRole
from src.core.logging import logger


class CodeAgent(BaseAgent):
    """
    Code Agent

    Specializes in:
    - Code generation
    - Code review and analysis
    - Bug fixing
    - Code refactoring
    - Documentation generation
    """

    def __init__(self, llm_provider: LLMProvider, config: AgentConfig = None):
        """
        Initialize code agent

        Args:
            llm_provider: LLM provider instance
            config: Agent configuration (optional)
        """
        if config is None:
            config = AgentConfig(
                name="Code Agent",
                description="Generates and analyzes code",
                model="gpt-4",
                temperature=0.2,  # Lower for more deterministic code
                max_tokens=2000,
                tools=["ast_parser", "linter", "formatter"],
                memory_enabled=True,
                max_memory_items=10
            )

        super().__init__(config)
        self.llm = llm_provider

    async def execute(self, context: AgentContext) -> AgentResult:
        """
        Execute code task

        Args:
            context: Execution context

        Returns:
            AgentResult: Code generation/analysis results
        """
        started_at = datetime.utcnow()

        try:
            # Process code request
            result = await self.process(context.input_data)

            return AgentResult(
                status=AgentStatus.COMPLETED,
                output=result,
                started_at=started_at,
                completed_at=datetime.utcnow(),
                metadata={"task_type": context.input_data.get("task_type", "generate")}
            )

        except Exception as e:
            logger.error(f"Code agent error: {e}")
            return await self.handle_error(e, context)

    async def process(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Process code request

        Args:
            input_data: Input with 'task_type', 'requirements', 'language', 'code'

        Returns:
            Code generation/analysis results
        """
        task_type = input_data.get("task_type", "generate")  # generate, review, debug, refactor
        requirements = input_data.get("requirements", "")
        language = input_data.get("language", "python")
        code = input_data.get("code", "")

        # Build code prompt based on task type
        messages = [
            LLMMessage(role=LLMRole.SYSTEM, content=self.get_system_prompt()),
            LLMMessage(
                role=LLMRole.USER,
                content=self._build_code_prompt(task_type, requirements, language, code)
            )
        ]

        # Call LLM with low temperature for consistency
        response = await self.llm.generate(messages, temperature=0.2)

        # Extract code from response
        generated_code = self._extract_code(response.content, language)

        return {
            "task_type": task_type,
            "language": language,
            "code": generated_code,
            "explanation": response.content,
            "tokens_used": response.tokens_used,
            "cost": response.cost
        }

    def get_system_prompt(self) -> str:
        """Get code agent system prompt"""
        return """You are a Code Agent specializing in software development tasks.

Your capabilities:
- Generate clean, efficient, well-documented code
- Perform code reviews focusing on quality, security, and performance
- Debug and fix code issues
- Refactor code for better maintainability
- Generate comprehensive documentation

Guidelines:
1. Write production-quality code
2. Follow best practices and design patterns
3. Include error handling
4. Add clear comments for complex logic
5. Consider security implications
6. Optimize for readability and maintainability

When generating code:
- Use appropriate data structures and algorithms
- Include input validation
- Handle edge cases
- Write testable code
- Follow language-specific conventions"""

    def _build_code_prompt(
        self,
        task_type: str,
        requirements: str,
        language: str,
        code: str = ""
    ) -> str:
        """Build code prompt based on task type"""
        prompts = {
            "generate": f"""Generate {language} code for the following requirements:

{requirements}

Provide clean, well-documented code with error handling.""",

            "review": f"""Review the following {language} code:

```{language}
{code}
```

Analyze:
1. Code quality and style
2. Security vulnerabilities
3. Performance issues
4. Best practices violations
5. Potential bugs

Provide specific recommendations for improvement.""",

            "debug": f"""Debug the following {language} code:

```{language}
{code}
```

Problem: {requirements}

Identify the bug and provide a fixed version with explanation.""",

            "refactor": f"""Refactor the following {language} code:

```{language}
{code}
```

Goals: {requirements}

Improve code structure, readability, and maintainability.""",

            "document": f"""Generate comprehensive documentation for this {language} code:

```{language}
{code}
```

Include:
- Function/class descriptions
- Parameter explanations
- Return value descriptions
- Usage examples
- Edge cases"""
        }

        return prompts.get(task_type, prompts["generate"])

    def _extract_code(self, content: str, language: str) -> str:
        """Extract code from markdown code blocks"""
        # Look for code blocks with language identifier
        marker = f"```{language}"
        if marker in content:
            start = content.find(marker) + len(marker)
            end = content.find("```", start)
            if end != -1:
                return content[start:end].strip()

        # Look for generic code blocks
        if "```" in content:
            start = content.find("```") + 3
            # Skip language identifier if present
            newline = content.find('\n', start)
            if newline != -1:
                start = newline + 1
            end = content.find("```", start)
            if end != -1:
                return content[start:end].strip()

        # Return full content if no code blocks found
        return content.strip()

    async def validate_input(self, input_data: Dict[str, Any]) -> bool:
        """Validate code input"""
        task_type = input_data.get("task_type", "generate")

        valid_task_types = ["generate", "review", "debug", "refactor", "document"]
        if task_type not in valid_task_types:
            logger.error(f"Invalid task_type. Must be one of: {valid_task_types}")
            return False

        # For generate, requirements are needed
        if task_type == "generate" and not input_data.get("requirements"):
            logger.error("Code generation requires 'requirements'")
            return False

        # For review/debug/refactor, code is needed
        if task_type in ["review", "debug", "refactor", "document"]:
            if not input_data.get("code"):
                logger.error(f"Task type '{task_type}' requires 'code'")
                return False

        return True
