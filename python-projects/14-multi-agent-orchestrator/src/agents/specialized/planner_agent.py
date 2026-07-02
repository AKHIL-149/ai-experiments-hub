"""
Planner Agent

Specialized agent for task planning and decomposition.
"""

from typing import Any, Dict, List
from datetime import datetime

from src.agents.base import BaseAgent, AgentConfig, AgentContext, AgentResult, AgentStatus
from src.agents.base import LLMProvider, LLMMessage, LLMRole
from src.core.logging import logger


class PlannerAgent(BaseAgent):
    """
    Planner Agent

    Specializes in:
    - Task decomposition
    - Project planning
    - Workflow design
    - Resource allocation
    - Timeline estimation
    """

    def __init__(self, llm_provider: LLMProvider, config: AgentConfig = None):
        """
        Initialize planner agent

        Args:
            llm_provider: LLM provider instance
            config: Agent configuration (optional)
        """
        if config is None:
            config = AgentConfig(
                name="Planner Agent",
                description="Plans tasks and decomposes complex goals",
                model="gpt-4",
                temperature=0.4,  # Balanced for structured planning
                max_tokens=2000,
                tools=["task_analyzer", "dependency_mapper"],
                memory_enabled=True,
                max_memory_items=15
            )

        super().__init__(config)
        self.llm = llm_provider

    async def execute(self, context: AgentContext) -> AgentResult:
        """
        Execute planning task

        Args:
            context: Execution context

        Returns:
            AgentResult: Planning results
        """
        started_at = datetime.utcnow()

        try:
            # Process planning request
            result = await self.process(context.input_data)

            return AgentResult(
                status=AgentStatus.COMPLETED,
                output=result,
                started_at=started_at,
                completed_at=datetime.utcnow(),
                metadata={"plan_type": context.input_data.get("plan_type", "task_breakdown")}
            )

        except Exception as e:
            logger.error(f"Planner agent error: {e}")
            return await self.handle_error(e, context)

    async def process(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Process planning request

        Args:
            input_data: Input with 'goal', 'plan_type', 'constraints'

        Returns:
            Planning results with tasks and dependencies
        """
        goal = input_data.get("goal", "")
        plan_type = input_data.get("plan_type", "task_breakdown")
        constraints = input_data.get("constraints", {})
        context_info = input_data.get("context", "")

        # Build planning prompt
        messages = [
            LLMMessage(role=LLMRole.SYSTEM, content=self.get_system_prompt()),
            LLMMessage(
                role=LLMRole.USER,
                content=self._build_planning_prompt(goal, plan_type, constraints, context_info)
            )
        ]

        # Call LLM
        response = await self.llm.generate(messages, temperature=self.config.temperature)

        # Parse plan
        tasks = self._parse_tasks(response.content)
        dependencies = self._extract_dependencies(response.content)

        return {
            "goal": goal,
            "plan_type": plan_type,
            "tasks": tasks,
            "dependencies": dependencies,
            "full_plan": response.content,
            "estimated_total_time": self._estimate_total_time(tasks),
            "tokens_used": response.tokens_used,
            "cost": response.cost
        }

    def get_system_prompt(self) -> str:
        """Get planner agent system prompt"""
        return """You are a Planner Agent specializing in task planning and decomposition.

Your capabilities:
- Break down complex goals into actionable tasks
- Identify task dependencies and sequencing
- Estimate effort and timelines
- Allocate resources effectively
- Design efficient workflows
- Identify risks and mitigation strategies

Guidelines:
1. Create specific, actionable tasks
2. Identify dependencies clearly
3. Consider resource constraints
4. Prioritize tasks appropriately
5. Provide realistic estimates
6. Include contingency planning

Plan Format:
- Overview (goal and approach)
- Tasks (with details, priority, estimated time)
- Dependencies (what depends on what)
- Timeline (sequence and milestones)
- Resources (what's needed)
- Risks (potential issues and mitigation)"""

    def _build_planning_prompt(
        self,
        goal: str,
        plan_type: str,
        constraints: Dict[str, Any],
        context_info: str
    ) -> str:
        """Build planning prompt"""
        prompt = f"Create a {plan_type} for the following goal:\n\n"
        prompt += f"Goal: {goal}\n\n"

        if context_info:
            prompt += f"Context: {context_info}\n\n"

        if constraints:
            prompt += "Constraints:\n"
            for key, value in constraints.items():
                prompt += f"- {key}: {value}\n"
            prompt += "\n"

        # Add plan-type specific instructions
        type_instructions = {
            "task_breakdown": """Break down the goal into specific, actionable tasks.
For each task, provide:
- Task name and description
- Priority (High/Medium/Low)
- Estimated time
- Dependencies
- Required resources""",

            "project_plan": """Create a comprehensive project plan including:
- Project phases
- Key milestones
- Task assignments
- Resource allocation
- Timeline with dependencies
- Risk assessment""",

            "workflow_design": """Design an efficient workflow with:
- Process steps
- Decision points
- Parallel vs sequential tasks
- Handoff points
- Quality checks
- Feedback loops""",

            "strategy": """Develop a strategic plan with:
- Approach and methodology
- Key initiatives
- Success metrics
- Resource requirements
- Timeline and phases
- Risk mitigation"""
        }

        prompt += type_instructions.get(plan_type, type_instructions["task_breakdown"])

        return prompt

    def _parse_tasks(self, content: str) -> List[Dict[str, Any]]:
        """Parse tasks from plan"""
        tasks = []
        lines = content.split('\n')

        current_task = None
        task_counter = 0

        for line in lines:
            stripped = line.strip()
            if not stripped:
                continue

            # Look for task indicators
            if any(stripped.startswith(prefix) for prefix in ['Task', '###', 'Step', '-']):
                if current_task:
                    tasks.append(current_task)
                    task_counter += 1

                # Extract task name
                task_name = stripped.lstrip('#-* 0123456789.').strip()
                if task_name.lower().startswith('task'):
                    task_name = task_name.split(':', 1)[-1].strip()

                current_task = {
                    "id": f"task_{task_counter + 1}",
                    "name": task_name,
                    "description": "",
                    "priority": "medium",
                    "estimated_time": "TBD"
                }

            elif current_task:
                # Look for task details
                lower_stripped = stripped.lower()

                if "priority:" in lower_stripped:
                    priority = stripped.split(':', 1)[1].strip().lower()
                    current_task["priority"] = priority

                elif "time:" in lower_stripped or "duration:" in lower_stripped:
                    time_est = stripped.split(':', 1)[1].strip()
                    current_task["estimated_time"] = time_est

                elif "description:" in lower_stripped:
                    desc = stripped.split(':', 1)[1].strip()
                    current_task["description"] = desc

                else:
                    # Add to description
                    if current_task["description"]:
                        current_task["description"] += " " + stripped
                    else:
                        current_task["description"] = stripped

        if current_task:
            tasks.append(current_task)

        return tasks

    def _extract_dependencies(self, content: str) -> List[Dict[str, str]]:
        """Extract task dependencies"""
        dependencies = []

        # Look for dependency section or keywords
        lines = content.lower().split('\n')

        for i, line in enumerate(lines):
            if "depend" in line or "prerequisite" in line or "after" in line:
                # Extract dependency relationships
                # This is a simplified parser
                if "->" in line or "→" in line:
                    parts = line.replace("->", "→").split("→")
                    if len(parts) == 2:
                        dependencies.append({
                            "from": parts[0].strip(),
                            "to": parts[1].strip()
                        })

        return dependencies

    def _estimate_total_time(self, tasks: List[Dict[str, Any]]) -> str:
        """Estimate total time for all tasks"""
        # Simple heuristic: count tasks and estimate
        if not tasks:
            return "Unknown"

        # This would be more sophisticated in production
        task_count = len(tasks)
        if task_count <= 3:
            return "1-2 days"
        elif task_count <= 7:
            return "3-5 days"
        elif task_count <= 15:
            return "1-2 weeks"
        else:
            return "2+ weeks"

    async def validate_input(self, input_data: Dict[str, Any]) -> bool:
        """Validate planning input"""
        if "goal" not in input_data:
            logger.error("Planner agent requires 'goal' in input")
            return False

        if not isinstance(input_data["goal"], str):
            logger.error("Goal must be a string")
            return False

        if not input_data["goal"].strip():
            logger.error("Goal cannot be empty")
            return False

        # Validate plan type
        if "plan_type" in input_data:
            valid_types = ["task_breakdown", "project_plan", "workflow_design", "strategy"]
            if input_data["plan_type"] not in valid_types:
                logger.error(f"Invalid plan_type. Must be one of: {valid_types}")
                return False

        return True
