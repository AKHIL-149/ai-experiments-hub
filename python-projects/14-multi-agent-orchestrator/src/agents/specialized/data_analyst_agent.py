"""
Data Analyst Agent

Specialized agent for data analysis and insights generation.
"""

from typing import Any, Dict, List
from datetime import datetime

from src.agents.base import BaseAgent, AgentConfig, AgentContext, AgentResult, AgentStatus
from src.agents.base import LLMProvider, LLMMessage, LLMRole
from src.core.logging import logger


class DataAnalystAgent(BaseAgent):
    """
    Data Analyst Agent

    Specializes in:
    - Data analysis and interpretation
    - Statistical analysis
    - Trend identification
    - Insight generation
    - Report creation
    """

    def __init__(self, llm_provider: LLMProvider, config: AgentConfig = None):
        """
        Initialize data analyst agent

        Args:
            llm_provider: LLM provider instance
            config: Agent configuration (optional)
        """
        if config is None:
            config = AgentConfig(
                name="Data Analyst Agent",
                description="Analyzes data and generates insights",
                model="gpt-4",
                temperature=0.3,  # Lower for more analytical output
                max_tokens=2000,
                tools=["pandas", "numpy", "statistics"],
                memory_enabled=True,
                max_memory_items=12
            )

        super().__init__(config)
        self.llm = llm_provider

    async def execute(self, context: AgentContext) -> AgentResult:
        """
        Execute data analysis task

        Args:
            context: Execution context

        Returns:
            AgentResult: Analysis results
        """
        started_at = datetime.utcnow()

        try:
            # Process analysis request
            result = await self.process(context.input_data)

            return AgentResult(
                status=AgentStatus.COMPLETED,
                output=result,
                started_at=started_at,
                completed_at=datetime.utcnow(),
                metadata={"analysis_type": context.input_data.get("analysis_type", "general")}
            )

        except Exception as e:
            logger.error(f"Data analyst agent error: {e}")
            return await self.handle_error(e, context)

    async def process(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Process data analysis request

        Args:
            input_data: Input with 'data', 'analysis_type', 'questions'

        Returns:
            Analysis results with insights
        """
        data = input_data.get("data", {})
        analysis_type = input_data.get("analysis_type", "descriptive")
        questions = input_data.get("questions", [])

        # Build analysis prompt
        messages = [
            LLMMessage(role=LLMRole.SYSTEM, content=self.get_system_prompt()),
            LLMMessage(
                role=LLMRole.USER,
                content=self._build_analysis_prompt(data, analysis_type, questions)
            )
        ]

        # Call LLM
        response = await self.llm.generate(messages, temperature=self.config.temperature)

        # Parse insights
        insights = self._parse_insights(response.content)

        return {
            "analysis_type": analysis_type,
            "insights": insights,
            "summary": response.content,
            "recommendations": self._extract_recommendations(response.content),
            "tokens_used": response.tokens_used,
            "cost": response.cost
        }

    def get_system_prompt(self) -> str:
        """Get data analyst system prompt"""
        return """You are a Data Analyst Agent specializing in data analysis and insights generation.

Your capabilities:
- Descriptive analysis (summarize data characteristics)
- Diagnostic analysis (explain why trends occur)
- Predictive analysis (forecast future trends)
- Prescriptive analysis (recommend actions)
- Statistical analysis

Guidelines:
1. Provide data-driven insights
2. Identify patterns, trends, and anomalies
3. Use statistical concepts appropriately
4. Explain findings in clear, business-friendly language
5. Support conclusions with evidence
6. Highlight limitations and uncertainties

Format your analysis with:
- Executive Summary
- Key Findings (with data support)
- Detailed Analysis
- Trends and Patterns
- Recommendations
- Next Steps"""

    def _build_analysis_prompt(
        self,
        data: Dict[str, Any],
        analysis_type: str,
        questions: List[str]
    ) -> str:
        """Build analysis prompt"""
        prompt = f"Perform {analysis_type} analysis on the following data:\n\n"

        # Format data
        if isinstance(data, dict):
            prompt += "Data:\n"
            for key, value in data.items():
                prompt += f"- {key}: {value}\n"
        else:
            prompt += f"Data: {data}\n"

        prompt += "\n"

        # Add specific questions if provided
        if questions:
            prompt += "Answer these specific questions:\n"
            for i, question in enumerate(questions, 1):
                prompt += f"{i}. {question}\n"
            prompt += "\n"

        # Add analysis type instructions
        analysis_instructions = {
            "descriptive": "Summarize the data characteristics, central tendencies, and distributions.",
            "diagnostic": "Explain the underlying causes and relationships in the data.",
            "predictive": "Identify trends and forecast likely future outcomes.",
            "prescriptive": "Recommend specific actions based on the data.",
            "exploratory": "Discover patterns, anomalies, and interesting relationships."
        }

        prompt += analysis_instructions.get(analysis_type, analysis_instructions["descriptive"])

        return prompt

    def _parse_insights(self, content: str) -> List[Dict[str, str]]:
        """Parse insights from analysis"""
        insights = []
        lines = content.split('\n')

        current_insight = None

        for line in lines:
            stripped = line.strip()
            if not stripped:
                continue

            # Look for numbered insights or key findings
            if any(stripped.startswith(prefix) for prefix in ['1.', '2.', '3.', '4.', '5.', '-', '•', '*']):
                if current_insight:
                    insights.append(current_insight)

                # Extract the insight text
                text = stripped.lstrip('0123456789.-•* ').strip()
                current_insight = {
                    "insight": text,
                    "type": "finding"
                }

        if current_insight:
            insights.append(current_insight)

        return insights if insights else [{"insight": content, "type": "general"}]

    def _extract_recommendations(self, content: str) -> List[str]:
        """Extract recommendations from analysis"""
        recommendations = []

        # Look for recommendations section
        if "recommendation" in content.lower():
            lines = content.lower().split('\n')
            in_recommendations = False

            for i, line in enumerate(lines):
                if "recommendation" in line:
                    in_recommendations = True
                    continue

                if in_recommendations:
                    stripped = line.strip()
                    if stripped and any(stripped.startswith(p) for p in ['-', '•', '*', '1.', '2.', '3.']):
                        rec = stripped.lstrip('-•*0123456789. ').strip()
                        if rec:
                            recommendations.append(rec)

        return recommendations

    async def validate_input(self, input_data: Dict[str, Any]) -> bool:
        """Validate analysis input"""
        if "data" not in input_data:
            logger.error("Data analyst requires 'data' in input")
            return False

        # Validate analysis type
        if "analysis_type" in input_data:
            valid_types = ["descriptive", "diagnostic", "predictive", "prescriptive", "exploratory"]
            if input_data["analysis_type"] not in valid_types:
                logger.error(f"Invalid analysis_type. Must be one of: {valid_types}")
                return False

        return True
