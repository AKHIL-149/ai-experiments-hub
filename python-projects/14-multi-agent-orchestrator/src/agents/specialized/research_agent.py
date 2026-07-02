"""
Research Agent

Specialized agent for information gathering and research tasks.
"""

from typing import Any, Dict, List
from datetime import datetime

from src.agents.base import BaseAgent, AgentConfig, AgentContext, AgentResult, AgentStatus
from src.agents.base import LLMProvider, LLMMessage, LLMRole
from src.core.logging import logger


class ResearchAgent(BaseAgent):
    """
    Research Agent

    Specializes in:
    - Information gathering
    - Topic research
    - Fact verification
    - Source synthesis
    - Summary generation
    """

    def __init__(self, llm_provider: LLMProvider, config: AgentConfig = None):
        """
        Initialize research agent

        Args:
            llm_provider: LLM provider instance
            config: Agent configuration (optional)
        """
        if config is None:
            config = AgentConfig(
                name="Research Agent",
                description="Researches topics and gathers information",
                model="gpt-4",
                temperature=0.5,
                max_tokens=2000,
                tools=["web_search", "knowledge_base"],
                memory_enabled=True,
                max_memory_items=15
            )

        super().__init__(config)
        self.llm = llm_provider

    async def execute(self, context: AgentContext) -> AgentResult:
        """
        Execute research task

        Args:
            context: Execution context

        Returns:
            AgentResult: Research results
        """
        started_at = datetime.utcnow()

        try:
            # Process research request
            result = await self.process(context.input_data)

            return AgentResult(
                status=AgentStatus.COMPLETED,
                output=result,
                started_at=started_at,
                completed_at=datetime.utcnow(),
                metadata={"research_type": context.input_data.get("research_type", "general")}
            )

        except Exception as e:
            logger.error(f"Research agent error: {e}")
            return await self.handle_error(e, context)

    async def process(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Process research request

        Args:
            input_data: Input with 'topic', 'depth', 'focus_areas'

        Returns:
            Research results with findings and sources
        """
        topic = input_data.get("topic", "")
        depth = input_data.get("depth", "medium")  # shallow, medium, deep
        focus_areas = input_data.get("focus_areas", [])

        # Build research prompt
        messages = [
            LLMMessage(role=LLMRole.SYSTEM, content=self.get_system_prompt()),
            LLMMessage(
                role=LLMRole.USER,
                content=self._build_research_prompt(topic, depth, focus_areas)
            )
        ]

        # Call LLM
        response = await self.llm.generate(messages, temperature=self.config.temperature)

        # Parse research results
        findings = self._parse_research_results(response.content)

        return {
            "topic": topic,
            "depth": depth,
            "findings": findings,
            "summary": response.content,
            "tokens_used": response.tokens_used,
            "cost": response.cost
        }

    def get_system_prompt(self) -> str:
        """Get research agent system prompt"""
        return """You are a Research Agent specializing in information gathering and analysis.

Your capabilities:
- Comprehensive topic research
- Fact verification and validation
- Source synthesis
- Structured summary generation
- Identifying key insights and trends

Guidelines:
1. Provide well-researched, accurate information
2. Cite sources when possible
3. Identify conflicting information or uncertainties
4. Organize findings logically
5. Highlight key takeaways

Format your research with clear sections:
- Overview
- Key Findings
- Details (organized by subtopic)
- Conclusions
- Sources (if available)"""

    def _build_research_prompt(self, topic: str, depth: str, focus_areas: List[str]) -> str:
        """Build research prompt"""
        prompt = f"Research the following topic: {topic}\n\n"
        prompt += f"Depth: {depth}\n\n"

        if focus_areas:
            prompt += f"Focus on these areas:\n"
            for area in focus_areas:
                prompt += f"- {area}\n"
            prompt += "\n"

        depth_instructions = {
            "shallow": "Provide a high-level overview with key points.",
            "medium": "Provide detailed information with examples and context.",
            "deep": "Provide comprehensive analysis with multiple perspectives, examples, and implications."
        }

        prompt += depth_instructions.get(depth, depth_instructions["medium"])
        return prompt

    def _parse_research_results(self, content: str) -> List[Dict[str, str]]:
        """Parse research results into structured findings"""
        # Simple parsing - split by sections
        findings = []

        # Look for bulleted lists or numbered points
        lines = content.split('\n')
        current_finding = None

        for line in lines:
            stripped = line.strip()
            if not stripped:
                continue

            # Check if it's a heading or key point
            if stripped.startswith('#') or stripped.startswith('**'):
                if current_finding:
                    findings.append(current_finding)
                current_finding = {"title": stripped.strip('#* '), "content": ""}

            elif stripped.startswith('-') or stripped.startswith('•'):
                point = stripped.lstrip('-• ').strip()
                if current_finding:
                    current_finding["content"] += point + " "
                else:
                    findings.append({"title": "Finding", "content": point})

        if current_finding:
            findings.append(current_finding)

        return findings if findings else [{"title": "Research Results", "content": content}]

    async def validate_input(self, input_data: Dict[str, Any]) -> bool:
        """Validate research input"""
        if "topic" not in input_data:
            logger.error("Research agent requires 'topic' in input")
            return False

        if not isinstance(input_data["topic"], str):
            logger.error("Topic must be a string")
            return False

        if not input_data["topic"].strip():
            logger.error("Topic cannot be empty")
            return False

        # Validate depth if provided
        if "depth" in input_data:
            valid_depths = ["shallow", "medium", "deep"]
            if input_data["depth"] not in valid_depths:
                logger.error(f"Invalid depth. Must be one of: {valid_depths}")
                return False

        return True
