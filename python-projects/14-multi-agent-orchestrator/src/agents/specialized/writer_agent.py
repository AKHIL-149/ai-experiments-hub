"""
Writer Agent

Specialized agent for content creation and writing tasks.
"""

from typing import Any, Dict, List
from datetime import datetime

from src.agents.base import BaseAgent, AgentConfig, AgentContext, AgentResult, AgentStatus
from src.agents.base import LLMProvider, LLMMessage, LLMRole
from src.core.logging import logger


class WriterAgent(BaseAgent):
    """
    Writer Agent

    Specializes in:
    - Content writing
    - Copywriting
    - Technical documentation
    - Creative writing
    - Content editing and improvement
    """

    def __init__(self, llm_provider: LLMProvider, config: AgentConfig = None):
        """
        Initialize writer agent

        Args:
            llm_provider: LLM provider instance
            config: Agent configuration (optional)
        """
        if config is None:
            config = AgentConfig(
                name="Writer Agent",
                description="Creates and edits written content",
                model="gpt-4",
                temperature=0.7,  # Higher for more creative output
                max_tokens=2000,
                tools=["grammar_checker", "style_analyzer"],
                memory_enabled=True,
                max_memory_items=10
            )

        super().__init__(config)
        self.llm = llm_provider

    async def execute(self, context: AgentContext) -> AgentResult:
        """
        Execute writing task

        Args:
            context: Execution context

        Returns:
            AgentResult: Written content
        """
        started_at = datetime.utcnow()

        try:
            # Process writing request
            result = await self.process(context.input_data)

            return AgentResult(
                status=AgentStatus.COMPLETED,
                output=result,
                started_at=started_at,
                completed_at=datetime.utcnow(),
                metadata={"content_type": context.input_data.get("content_type", "general")}
            )

        except Exception as e:
            logger.error(f"Writer agent error: {e}")
            return await self.handle_error(e, context)

    async def process(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Process writing request

        Args:
            input_data: Input with 'content_type', 'topic', 'style', 'audience'

        Returns:
            Written content
        """
        content_type = input_data.get("content_type", "article")
        topic = input_data.get("topic", "")
        style = input_data.get("style", "professional")
        audience = input_data.get("audience", "general")
        length = input_data.get("length", "medium")  # short, medium, long
        existing_content = input_data.get("existing_content", "")

        # Build writing prompt
        messages = [
            LLMMessage(role=LLMRole.SYSTEM, content=self.get_system_prompt()),
            LLMMessage(
                role=LLMRole.USER,
                content=self._build_writing_prompt(
                    content_type, topic, style, audience, length, existing_content
                )
            )
        ]

        # Call LLM with appropriate temperature
        temperature = self._get_temperature_for_style(style)
        response = await self.llm.generate(messages, temperature=temperature)

        # Extract sections
        sections = self._parse_sections(response.content)

        return {
            "content_type": content_type,
            "topic": topic,
            "style": style,
            "content": response.content,
            "sections": sections,
            "word_count": len(response.content.split()),
            "tokens_used": response.tokens_used,
            "cost": response.cost
        }

    def get_system_prompt(self) -> str:
        """Get writer agent system prompt"""
        return """You are a Writer Agent specializing in content creation and editing.

Your capabilities:
- Write engaging, well-structured content
- Adapt tone and style to audience
- Create compelling narratives
- Write technical documentation
- Edit and improve existing content
- Optimize content for clarity and impact

Guidelines:
1. Match the requested style and tone
2. Consider the target audience
3. Use clear, concise language
4. Structure content logically
5. Include relevant examples and details
6. Maintain consistency throughout
7. Proofread for grammar and clarity

Content Types:
- Articles: Informative, well-researched pieces
- Blog Posts: Engaging, conversational content
- Technical Docs: Clear, detailed instructions
- Marketing Copy: Persuasive, benefit-focused
- Creative Writing: Imaginative, compelling narratives
- Reports: Structured, analytical content"""

    def _build_writing_prompt(
        self,
        content_type: str,
        topic: str,
        style: str,
        audience: str,
        length: str,
        existing_content: str = ""
    ) -> str:
        """Build writing prompt"""
        if existing_content:
            prompt = f"""Edit and improve the following {content_type}:

{existing_content}

Improvements needed:
- Topic: {topic}
- Style: {style}
- Target Audience: {audience}

Enhance clarity, engagement, and effectiveness."""
        else:
            prompt = f"""Write a {length} {content_type} about: {topic}

Requirements:
- Style: {style}
- Target Audience: {audience}
- Length: {length}

"""
            # Add content-type specific instructions
            type_instructions = {
                "article": "Include an introduction, body with key points, and conclusion.",
                "blog_post": "Make it engaging and conversational with a strong hook.",
                "documentation": "Be clear, detailed, and include examples where helpful.",
                "marketing_copy": "Focus on benefits and include a call-to-action.",
                "report": "Use a structured format with sections and data-driven insights.",
                "email": "Be concise, clear, and action-oriented.",
                "social_media": "Be brief, engaging, and shareable."
            }

            prompt += type_instructions.get(content_type, "Create engaging, well-structured content.")

        return prompt

    def _get_temperature_for_style(self, style: str) -> float:
        """Get appropriate temperature based on style"""
        temperatures = {
            "creative": 0.9,
            "conversational": 0.8,
            "professional": 0.6,
            "technical": 0.3,
            "formal": 0.4,
            "casual": 0.7
        }
        return temperatures.get(style, 0.7)

    def _parse_sections(self, content: str) -> List[Dict[str, str]]:
        """Parse content into sections"""
        sections = []
        lines = content.split('\n')

        current_section = None

        for line in lines:
            stripped = line.strip()
            if not stripped:
                continue

            # Check for section headings (markdown format)
            if stripped.startswith('#'):
                if current_section:
                    sections.append(current_section)

                heading = stripped.lstrip('#').strip()
                current_section = {
                    "heading": heading,
                    "content": ""
                }
            elif current_section:
                current_section["content"] += line + "\n"

        if current_section:
            sections.append(current_section)

        # If no sections found, create a single section
        if not sections:
            sections.append({
                "heading": "Content",
                "content": content
            })

        return sections

    async def validate_input(self, input_data: Dict[str, Any]) -> bool:
        """Validate writing input"""
        # Must have topic or existing content
        if not input_data.get("topic") and not input_data.get("existing_content"):
            logger.error("Writer agent requires either 'topic' or 'existing_content'")
            return False

        # Validate content type
        if "content_type" in input_data:
            valid_types = [
                "article", "blog_post", "documentation", "marketing_copy",
                "report", "email", "social_media", "creative"
            ]
            if input_data["content_type"] not in valid_types:
                logger.error(f"Invalid content_type. Must be one of: {valid_types}")
                return False

        # Validate style
        if "style" in input_data:
            valid_styles = ["creative", "conversational", "professional", "technical", "formal", "casual"]
            if input_data["style"] not in valid_styles:
                logger.error(f"Invalid style. Must be one of: {valid_styles}")
                return False

        return True
