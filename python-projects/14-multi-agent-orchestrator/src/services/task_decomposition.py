"""
Task Decomposition Service

Decomposes complex tasks into manageable subtasks with dependencies.
"""

from typing import Dict, Any, List, Optional
from datetime import datetime
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_, desc
import json

from src.models.database import Task, Agent
from src.core.logging import logger


class DecompositionStrategy:
    """Task decomposition strategy constants"""
    SEQUENTIAL = "sequential"
    PARALLEL = "parallel"
    HIERARCHICAL = "hierarchical"
    PIPELINE = "pipeline"
    MAP_REDUCE = "map_reduce"


class TaskComplexity:
    """Task complexity levels"""
    SIMPLE = "simple"
    MODERATE = "moderate"
    COMPLEX = "complex"
    VERY_COMPLEX = "very_complex"


class TaskDecomposition:
    """Service for decomposing complex tasks into subtasks"""

    @staticmethod
    def decompose_task(
        session: Session,
        task_id: int,
        strategy: str = DecompositionStrategy.PARALLEL,
        subtask_definitions: Optional[List[Dict[str, Any]]] = None,
        auto_generate: bool = False
    ) -> Dict[str, Any]:
        """
        Decompose a task into subtasks.

        Args:
            session: Database session
            task_id: Parent task ID
            strategy: Decomposition strategy
            subtask_definitions: List of subtask definitions
            auto_generate: Auto-generate subtasks based on description

        Returns:
            Decomposition result with subtask IDs
        """
        parent_task = session.query(Task).filter(Task.id == task_id).first()
        if not parent_task:
            raise ValueError(f"Task {task_id} not found")

        # Generate subtasks if auto mode
        if auto_generate and not subtask_definitions:
            subtask_definitions = TaskDecomposition._auto_generate_subtasks(
                parent_task, strategy
            )

        if not subtask_definitions:
            raise ValueError("No subtask definitions provided or generated")

        # Create subtasks
        subtasks = []
        for i, subtask_def in enumerate(subtask_definitions):
            subtask = Task(
                title=subtask_def.get("title", f"{parent_task.title} - Subtask {i+1}"),
                description=subtask_def.get("description", ""),
                type=subtask_def.get("type", parent_task.type),
                status="pending",
                metadata={
                    "parent_task_id": task_id,
                    "subtask_index": i,
                    "decomposition_strategy": strategy,
                    "complexity": subtask_def.get("complexity", TaskComplexity.SIMPLE),
                    "estimated_duration_minutes": subtask_def.get("estimated_duration_minutes", 30),
                    "required_capabilities": subtask_def.get("required_capabilities", []),
                    "depends_on": subtask_def.get("depends_on", [])
                }
            )
            session.add(subtask)
            session.flush()
            subtasks.append(subtask)

        # Update parent task metadata
        if not parent_task.metadata:
            parent_task.metadata = {}

        parent_task.metadata["decomposed"] = True
        parent_task.metadata["decomposition_strategy"] = strategy
        parent_task.metadata["subtask_ids"] = [st.id for st in subtasks]
        parent_task.metadata["decomposed_at"] = datetime.utcnow().isoformat()
        parent_task.metadata["total_subtasks"] = len(subtasks)

        from sqlalchemy.orm.attributes import flag_modified
        flag_modified(parent_task, "metadata")

        session.commit()

        # Generate dependencies based on strategy
        dependencies = TaskDecomposition._generate_dependencies(
            session, subtasks, strategy
        )

        logger.info(f"Task {task_id} decomposed into {len(subtasks)} subtasks using {strategy} strategy")

        return {
            "parent_task_id": task_id,
            "strategy": strategy,
            "subtask_count": len(subtasks),
            "subtasks": [
                {
                    "id": st.id,
                    "title": st.title,
                    "description": st.description,
                    "complexity": st.metadata.get("complexity"),
                    "estimated_duration_minutes": st.metadata.get("estimated_duration_minutes")
                }
                for st in subtasks
            ],
            "dependencies": dependencies
        }

    @staticmethod
    def _auto_generate_subtasks(
        parent_task: Task,
        strategy: str
    ) -> List[Dict[str, Any]]:
        """
        Auto-generate subtask definitions based on parent task.

        This is a simplified implementation. In production, this would use
        LLM/AI to intelligently decompose tasks.
        """
        subtasks = []

        # Example patterns based on task type
        if parent_task.type == "code_review":
            subtasks = [
                {
                    "title": f"{parent_task.title} - Analyze Code Structure",
                    "description": "Analyze code structure and architecture",
                    "type": "analyzer",
                    "complexity": TaskComplexity.MODERATE,
                    "estimated_duration_minutes": 20,
                    "required_capabilities": ["code_analysis"]
                },
                {
                    "title": f"{parent_task.title} - Check Code Quality",
                    "description": "Check code quality and best practices",
                    "type": "reviewer",
                    "complexity": TaskComplexity.MODERATE,
                    "estimated_duration_minutes": 25,
                    "required_capabilities": ["quality_check"],
                    "depends_on": [0] if strategy == DecompositionStrategy.SEQUENTIAL else []
                },
                {
                    "title": f"{parent_task.title} - Generate Report",
                    "description": "Generate comprehensive review report",
                    "type": "reporter",
                    "complexity": TaskComplexity.SIMPLE,
                    "estimated_duration_minutes": 15,
                    "required_capabilities": ["reporting"],
                    "depends_on": [0, 1] if strategy == DecompositionStrategy.SEQUENTIAL else []
                }
            ]
        elif parent_task.type == "data_processing":
            subtasks = [
                {
                    "title": f"{parent_task.title} - Extract Data",
                    "description": "Extract data from sources",
                    "type": "extractor",
                    "complexity": TaskComplexity.SIMPLE,
                    "estimated_duration_minutes": 15
                },
                {
                    "title": f"{parent_task.title} - Transform Data",
                    "description": "Transform and clean data",
                    "type": "transformer",
                    "complexity": TaskComplexity.MODERATE,
                    "estimated_duration_minutes": 30,
                    "depends_on": [0]
                },
                {
                    "title": f"{parent_task.title} - Load Data",
                    "description": "Load processed data",
                    "type": "loader",
                    "complexity": TaskComplexity.SIMPLE,
                    "estimated_duration_minutes": 10,
                    "depends_on": [1]
                }
            ]
        else:
            # Generic decomposition
            num_subtasks = 3
            for i in range(num_subtasks):
                depends_on = []
                if strategy == DecompositionStrategy.SEQUENTIAL and i > 0:
                    depends_on = [i-1]

                subtasks.append({
                    "title": f"{parent_task.title} - Part {i+1}",
                    "description": f"Subtask {i+1} of {parent_task.title}",
                    "type": parent_task.type,
                    "complexity": TaskComplexity.MODERATE,
                    "estimated_duration_minutes": 20,
                    "depends_on": depends_on
                })

        return subtasks

    @staticmethod
    def _generate_dependencies(
        session: Session,
        subtasks: List[Task],
        strategy: str
    ) -> List[Dict[str, Any]]:
        """Generate dependencies between subtasks based on strategy"""
        dependencies = []

        if strategy == DecompositionStrategy.SEQUENTIAL:
            # Each task depends on the previous one
            for i in range(1, len(subtasks)):
                dependencies.append({
                    "task_id": subtasks[i].id,
                    "depends_on_id": subtasks[i-1].id,
                    "type": "sequential"
                })

        elif strategy == DecompositionStrategy.PIPELINE:
            # Similar to sequential but with explicit pipeline stages
            for i in range(1, len(subtasks)):
                dependencies.append({
                    "task_id": subtasks[i].id,
                    "depends_on_id": subtasks[i-1].id,
                    "type": "pipeline",
                    "stage": i
                })

        elif strategy == DecompositionStrategy.HIERARCHICAL:
            # First subtask is root, others depend on it
            if len(subtasks) > 1:
                for i in range(1, len(subtasks)):
                    dependencies.append({
                        "task_id": subtasks[i].id,
                        "depends_on_id": subtasks[0].id,
                        "type": "hierarchical"
                    })

        elif strategy == DecompositionStrategy.MAP_REDUCE:
            # Map phase (parallel), then reduce phase
            map_count = len(subtasks) - 1  # Last task is reduce
            if map_count > 0:
                for i in range(map_count):
                    dependencies.append({
                        "task_id": subtasks[-1].id,  # Reduce depends on all maps
                        "depends_on_id": subtasks[i].id,
                        "type": "map_reduce"
                    })

        # PARALLEL strategy has no dependencies

        return dependencies

    @staticmethod
    def get_subtasks(
        session: Session,
        parent_task_id: int,
        include_status: bool = True
    ) -> Dict[str, Any]:
        """
        Get all subtasks for a parent task.

        Args:
            session: Database session
            parent_task_id: Parent task ID
            include_status: Include execution status

        Returns:
            Dictionary with subtask information
        """
        parent_task = session.query(Task).filter(Task.id == parent_task_id).first()
        if not parent_task:
            raise ValueError(f"Task {parent_task_id} not found")

        if not parent_task.metadata or not parent_task.metadata.get("decomposed"):
            return {
                "parent_task_id": parent_task_id,
                "decomposed": False,
                "subtasks": []
            }

        subtask_ids = parent_task.metadata.get("subtask_ids", [])
        subtasks = session.query(Task).filter(Task.id.in_(subtask_ids)).all()

        result = {
            "parent_task_id": parent_task_id,
            "decomposed": True,
            "strategy": parent_task.metadata.get("decomposition_strategy"),
            "total_subtasks": len(subtasks),
            "subtasks": []
        }

        if include_status:
            completed = sum(1 for st in subtasks if st.status == "completed")
            failed = sum(1 for st in subtasks if st.status == "failed")
            running = sum(1 for st in subtasks if st.status == "running")
            pending = sum(1 for st in subtasks if st.status == "pending")

            result["progress"] = {
                "completed": completed,
                "failed": failed,
                "running": running,
                "pending": pending,
                "completion_percentage": (completed / len(subtasks) * 100) if subtasks else 0
            }

        for subtask in subtasks:
            result["subtasks"].append({
                "id": subtask.id,
                "title": subtask.title,
                "description": subtask.description,
                "status": subtask.status,
                "type": subtask.type,
                "complexity": subtask.metadata.get("complexity") if subtask.metadata else None,
                "estimated_duration_minutes": subtask.metadata.get("estimated_duration_minutes") if subtask.metadata else None,
                "subtask_index": subtask.metadata.get("subtask_index") if subtask.metadata else None
            })

        return result

    @staticmethod
    def estimate_complexity(
        session: Session,
        task_id: int
    ) -> Dict[str, Any]:
        """
        Estimate task complexity.

        Args:
            session: Database session
            task_id: Task ID

        Returns:
            Complexity estimation
        """
        task = session.query(Task).filter(Task.id == task_id).first()
        if not task:
            raise ValueError(f"Task {task_id} not found")

        # Simplified complexity estimation
        # In production, this would use more sophisticated analysis
        description_length = len(task.description) if task.description else 0
        title_length = len(task.title) if task.title else 0

        # Estimate based on description length and keywords
        complexity_score = 0

        if description_length < 100:
            complexity_score += 1
        elif description_length < 300:
            complexity_score += 2
        elif description_length < 600:
            complexity_score += 3
        else:
            complexity_score += 4

        # Check for complexity keywords
        complex_keywords = ["integrate", "refactor", "migrate", "optimize", "design", "architect"]
        description_lower = task.description.lower() if task.description else ""

        for keyword in complex_keywords:
            if keyword in description_lower:
                complexity_score += 1

        # Determine complexity level
        if complexity_score <= 2:
            complexity = TaskComplexity.SIMPLE
            estimated_subtasks = 1
        elif complexity_score <= 4:
            complexity = TaskComplexity.MODERATE
            estimated_subtasks = 3
        elif complexity_score <= 6:
            complexity = TaskComplexity.COMPLEX
            estimated_subtasks = 5
        else:
            complexity = TaskComplexity.VERY_COMPLEX
            estimated_subtasks = 8

        return {
            "task_id": task_id,
            "complexity": complexity,
            "complexity_score": complexity_score,
            "estimated_subtasks": estimated_subtasks,
            "recommended_strategy": DecompositionStrategy.PARALLEL if estimated_subtasks <= 3 else DecompositionStrategy.HIERARCHICAL
        }

    @staticmethod
    def merge_subtask_results(
        session: Session,
        parent_task_id: int
    ) -> Dict[str, Any]:
        """
        Merge results from completed subtasks.

        Args:
            session: Database session
            parent_task_id: Parent task ID

        Returns:
            Merged results
        """
        subtasks_info = TaskDecomposition.get_subtasks(
            session, parent_task_id, include_status=True
        )

        if not subtasks_info.get("decomposed"):
            raise ValueError(f"Task {parent_task_id} has not been decomposed")

        # Get all subtasks
        subtask_ids = [st["id"] for st in subtasks_info["subtasks"]]
        subtasks = session.query(Task).filter(Task.id.in_(subtask_ids)).all()

        # Check if all subtasks are completed
        all_completed = all(st.status == "completed" for st in subtasks)

        merged_results = {
            "parent_task_id": parent_task_id,
            "all_subtasks_completed": all_completed,
            "subtask_results": []
        }

        for subtask in subtasks:
            result = {
                "subtask_id": subtask.id,
                "title": subtask.title,
                "status": subtask.status,
                "result": subtask.metadata.get("result") if subtask.metadata else None
            }
            merged_results["subtask_results"].append(result)

        # If all completed, update parent task
        if all_completed:
            parent_task = session.query(Task).filter(Task.id == parent_task_id).first()
            if parent_task:
                parent_task.status = "completed"
                if not parent_task.metadata:
                    parent_task.metadata = {}
                parent_task.metadata["all_subtasks_completed"] = True
                parent_task.metadata["completed_at"] = datetime.utcnow().isoformat()

                from sqlalchemy.orm.attributes import flag_modified
                flag_modified(parent_task, "metadata")
                session.commit()

                merged_results["parent_task_updated"] = True

        return merged_results

    @staticmethod
    def recommend_agents(
        session: Session,
        subtask_id: int
    ) -> Dict[str, Any]:
        """
        Recommend agents for a subtask based on capabilities.

        Args:
            session: Database session
            subtask_id: Subtask ID

        Returns:
            List of recommended agents
        """
        subtask = session.query(Task).filter(Task.id == subtask_id).first()
        if not subtask:
            raise ValueError(f"Subtask {subtask_id} not found")

        required_capabilities = []
        if subtask.metadata:
            required_capabilities = subtask.metadata.get("required_capabilities", [])

        # Get all active agents
        agents = session.query(Agent).filter(Agent.status == "active").all()

        recommendations = []
        for agent in agents:
            agent_capabilities = agent.metadata.get("capabilities", []) if agent.metadata else []

            # Calculate match score
            if not required_capabilities:
                match_score = 50  # Neutral score if no requirements
            else:
                matched = sum(1 for cap in required_capabilities if cap in agent_capabilities)
                match_score = (matched / len(required_capabilities)) * 100

            recommendations.append({
                "agent_id": agent.id,
                "agent_name": agent.name,
                "agent_type": agent.type,
                "match_score": match_score,
                "capabilities": agent_capabilities
            })

        # Sort by match score
        recommendations.sort(key=lambda x: x["match_score"], reverse=True)

        return {
            "subtask_id": subtask_id,
            "required_capabilities": required_capabilities,
            "recommendations": recommendations[:5]  # Top 5
        }

    @staticmethod
    def list_strategies() -> Dict[str, Any]:
        """
        List all decomposition strategies.

        Returns:
            Dictionary with strategy descriptions
        """
        strategies = [
            {
                "strategy": DecompositionStrategy.SEQUENTIAL,
                "description": "Subtasks execute one after another",
                "use_case": "When tasks must be done in order"
            },
            {
                "strategy": DecompositionStrategy.PARALLEL,
                "description": "Subtasks execute simultaneously",
                "use_case": "When tasks are independent"
            },
            {
                "strategy": DecompositionStrategy.HIERARCHICAL,
                "description": "Root task followed by dependent subtasks",
                "use_case": "When one task enables multiple others"
            },
            {
                "strategy": DecompositionStrategy.PIPELINE,
                "description": "Data flows through processing stages",
                "use_case": "Data transformation workflows"
            },
            {
                "strategy": DecompositionStrategy.MAP_REDUCE,
                "description": "Parallel processing followed by aggregation",
                "use_case": "Processing large datasets"
            }
        ]

        return {
            "total_strategies": len(strategies),
            "strategies": strategies
        }
