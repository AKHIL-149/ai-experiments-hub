"""
Task Dependency Management Service
Handles task dependencies, DAG validation, and execution ordering
"""

from typing import List, Dict, Any, Optional, Set, Tuple
from collections import defaultdict, deque
from sqlalchemy.orm import Session

from src.models.task import Task, TaskStatus
from src.core.logging import logger


class DependencyType:
    """Dependency relationship types"""
    BLOCKS = "blocks"           # Task A blocks task B (A must complete before B)
    REQUIRES = "requires"       # Task B requires task A (same as blocks, reverse direction)
    RELATED = "related"         # Tasks are related but not blocking


class TaskDependency:
    """
    Task Dependency Management Service

    Manages task dependencies, validates dependency graphs,
    and provides execution ordering.
    """

    @staticmethod
    def add_dependency(
        session: Session,
        task_id: int,
        depends_on_task_id: int,
        dependency_type: str = DependencyType.BLOCKS
    ) -> Dict[str, Any]:
        """
        Add a dependency between tasks.

        Args:
            session: Database session
            task_id: Task that has the dependency
            depends_on_task_id: Task that must complete first
            dependency_type: Type of dependency

        Returns:
            Dependency information
        """
        task = session.query(Task).filter(Task.id == task_id).first()
        if not task:
            raise ValueError(f"Task {task_id} not found")

        depends_on_task = session.query(Task).filter(Task.id == depends_on_task_id).first()
        if not depends_on_task:
            raise ValueError(f"Task {depends_on_task_id} not found")

        # Can't depend on yourself
        if task_id == depends_on_task_id:
            raise ValueError("Task cannot depend on itself")

        # Initialize dependencies in metadata
        if not task.metadata:
            task.metadata = {}

        if "dependencies" not in task.metadata:
            task.metadata["dependencies"] = []

        # Check if dependency already exists
        existing = [
            d for d in task.metadata["dependencies"]
            if d.get("task_id") == depends_on_task_id
        ]
        if existing:
            raise ValueError(f"Dependency already exists: task {task_id} -> {depends_on_task_id}")

        # Check for cycles before adding
        temp_dependencies = task.metadata["dependencies"].copy()
        temp_dependencies.append({
            "task_id": depends_on_task_id,
            "type": dependency_type
        })

        # Temporarily set dependencies to check for cycles
        original_deps = task.metadata["dependencies"]
        task.metadata["dependencies"] = temp_dependencies

        if TaskDependency._has_cycle(session, task_id):
            task.metadata["dependencies"] = original_deps
            raise ValueError("Adding this dependency would create a cycle")

        # Add the dependency
        task.metadata["dependencies"] = temp_dependencies
        session.commit()

        logger.info(f"Added dependency: task {task_id} depends on task {depends_on_task_id}")

        return {
            "task_id": task_id,
            "depends_on_task_id": depends_on_task_id,
            "dependency_type": dependency_type,
            "task_title": task.title,
            "depends_on_task_title": depends_on_task.title
        }

    @staticmethod
    def add_dependency_chain(
        session: Session,
        task_ids: List[int]
    ) -> List[Dict[str, Any]]:
        """
        Add dependencies in a chain (A -> B -> C -> D).

        Args:
            session: Database session
            task_ids: List of task IDs in execution order

        Returns:
            List of created dependencies
        """
        if len(task_ids) < 2:
            raise ValueError("Need at least 2 tasks for a dependency chain")

        dependencies = []
        for i in range(len(task_ids) - 1):
            dep = TaskDependency.add_dependency(
                session=session,
                task_id=task_ids[i + 1],
                depends_on_task_id=task_ids[i],
                dependency_type=DependencyType.BLOCKS
            )
            dependencies.append(dep)

        return dependencies

    @staticmethod
    def remove_dependency(
        session: Session,
        task_id: int,
        depends_on_task_id: int
    ) -> bool:
        """
        Remove a dependency between tasks.

        Args:
            session: Database session
            task_id: Task that has the dependency
            depends_on_task_id: Task to remove from dependencies

        Returns:
            True if removed, False if not found
        """
        task = session.query(Task).filter(Task.id == task_id).first()
        if not task:
            raise ValueError(f"Task {task_id} not found")

        if not task.metadata or "dependencies" not in task.metadata:
            return False

        original_count = len(task.metadata["dependencies"])
        task.metadata["dependencies"] = [
            d for d in task.metadata["dependencies"]
            if d.get("task_id") != depends_on_task_id
        ]

        removed = len(task.metadata["dependencies"]) < original_count
        if removed:
            session.commit()
            logger.info(f"Removed dependency: task {task_id} -> {depends_on_task_id}")

        return removed

    @staticmethod
    def get_task_dependencies(
        session: Session,
        task_id: int
    ) -> Dict[str, Any]:
        """
        Get all dependencies for a task.

        Args:
            session: Database session
            task_id: Task ID

        Returns:
            Dependencies information
        """
        task = session.query(Task).filter(Task.id == task_id).first()
        if not task:
            raise ValueError(f"Task {task_id} not found")

        dependencies = []
        if task.metadata and "dependencies" in task.metadata:
            for dep in task.metadata["dependencies"]:
                dep_task_id = dep.get("task_id")
                dep_task = session.query(Task).filter(Task.id == dep_task_id).first()

                if dep_task:
                    dependencies.append({
                        "task_id": dep_task_id,
                        "task_title": dep_task.title,
                        "task_status": dep_task.status.value,
                        "dependency_type": dep.get("type", DependencyType.BLOCKS),
                        "is_completed": dep_task.status == TaskStatus.COMPLETED
                    })

        # Also find tasks that depend on this task
        dependent_tasks = []
        all_tasks = session.query(Task).filter(Task.metadata.isnot(None)).all()

        for t in all_tasks:
            if t.metadata and "dependencies" in t.metadata:
                for dep in t.metadata["dependencies"]:
                    if dep.get("task_id") == task_id:
                        dependent_tasks.append({
                            "task_id": t.id,
                            "task_title": t.title,
                            "task_status": t.status.value
                        })

        return {
            "task_id": task_id,
            "task_title": task.title,
            "task_status": task.status.value,
            "depends_on": dependencies,
            "dependent_tasks": dependent_tasks,
            "total_dependencies": len(dependencies),
            "total_dependents": len(dependent_tasks)
        }

    @staticmethod
    def is_task_ready(
        session: Session,
        task_id: int
    ) -> Dict[str, Any]:
        """
        Check if a task is ready to execute (all dependencies completed).

        Args:
            session: Database session
            task_id: Task ID

        Returns:
            Readiness information
        """
        task = session.query(Task).filter(Task.id == task_id).first()
        if not task:
            raise ValueError(f"Task {task_id} not found")

        if not task.metadata or "dependencies" not in task.metadata:
            return {
                "task_id": task_id,
                "is_ready": True,
                "blocking_tasks": [],
                "total_dependencies": 0,
                "completed_dependencies": 0,
                "message": "No dependencies - ready to execute"
            }

        blocking_tasks = []
        completed_count = 0

        for dep in task.metadata["dependencies"]:
            dep_task_id = dep.get("task_id")
            dep_task = session.query(Task).filter(Task.id == dep_task_id).first()

            if dep_task:
                if dep_task.status == TaskStatus.COMPLETED:
                    completed_count += 1
                else:
                    blocking_tasks.append({
                        "task_id": dep_task_id,
                        "task_title": dep_task.title,
                        "task_status": dep_task.status.value
                    })

        total_dependencies = len(task.metadata["dependencies"])
        is_ready = len(blocking_tasks) == 0

        return {
            "task_id": task_id,
            "task_title": task.title,
            "is_ready": is_ready,
            "blocking_tasks": blocking_tasks,
            "total_dependencies": total_dependencies,
            "completed_dependencies": completed_count,
            "completion_percentage": (completed_count / total_dependencies * 100) if total_dependencies > 0 else 100,
            "message": "Ready to execute" if is_ready else f"Blocked by {len(blocking_tasks)} tasks"
        }

    @staticmethod
    def get_execution_order(
        session: Session,
        task_ids: Optional[List[int]] = None
    ) -> List[List[int]]:
        """
        Get topological execution order for tasks.

        Returns tasks grouped by execution level (tasks at same level can run in parallel).

        Args:
            session: Database session
            task_ids: Optional list of task IDs to order (if None, orders all tasks)

        Returns:
            List of task ID groups (each group can execute in parallel)
        """
        # Get tasks to order
        if task_ids:
            tasks = session.query(Task).filter(Task.id.in_(task_ids)).all()
        else:
            tasks = session.query(Task).all()

        # Build adjacency list
        graph = defaultdict(list)
        in_degree = defaultdict(int)
        task_map = {t.id: t for t in tasks}

        for task in tasks:
            in_degree[task.id] = 0  # Initialize

        for task in tasks:
            if task.metadata and "dependencies" in task.metadata:
                for dep in task.metadata["dependencies"]:
                    dep_task_id = dep.get("task_id")
                    if dep_task_id in task_map:
                        graph[dep_task_id].append(task.id)
                        in_degree[task.id] += 1

        # Topological sort using Kahn's algorithm
        queue = deque([task_id for task_id in task_map.keys() if in_degree[task_id] == 0])
        result = []

        while queue:
            # All tasks in current level (can execute in parallel)
            level = list(queue)
            result.append(level)

            # Process current level
            next_queue = deque()
            for task_id in level:
                for neighbor in graph[task_id]:
                    in_degree[neighbor] -= 1
                    if in_degree[neighbor] == 0:
                        next_queue.append(neighbor)

            queue = next_queue

        # Check if all tasks were processed (no cycles)
        processed_count = sum(len(level) for level in result)
        if processed_count < len(tasks):
            logger.warning(f"Cycle detected in dependency graph. Processed {processed_count}/{len(tasks)} tasks")

        return result

    @staticmethod
    def _has_cycle(session: Session, start_task_id: int) -> bool:
        """
        Check if adding a dependency creates a cycle using DFS.

        Args:
            session: Database session
            start_task_id: Task ID to start checking from

        Returns:
            True if cycle detected
        """
        visited = set()
        rec_stack = set()

        def dfs(task_id: int) -> bool:
            visited.add(task_id)
            rec_stack.add(task_id)

            task = session.query(Task).filter(Task.id == task_id).first()
            if task and task.metadata and "dependencies" in task.metadata:
                for dep in task.metadata["dependencies"]:
                    dep_task_id = dep.get("task_id")

                    if dep_task_id not in visited:
                        if dfs(dep_task_id):
                            return True
                    elif dep_task_id in rec_stack:
                        return True

            rec_stack.remove(task_id)
            return False

        return dfs(start_task_id)

    @staticmethod
    def validate_dependency_graph(
        session: Session,
        task_ids: Optional[List[int]] = None
    ) -> Dict[str, Any]:
        """
        Validate the dependency graph for cycles and orphaned dependencies.

        Args:
            session: Database session
            task_ids: Optional list of task IDs to validate

        Returns:
            Validation results
        """
        if task_ids:
            tasks = session.query(Task).filter(Task.id.in_(task_ids)).all()
        else:
            tasks = session.query(Task).filter(Task.metadata.isnot(None)).all()

        errors = []
        warnings = []
        task_map = {t.id: t for t in tasks}

        # Check for orphaned dependencies
        for task in tasks:
            if task.metadata and "dependencies" in task.metadata:
                for dep in task.metadata["dependencies"]:
                    dep_task_id = dep.get("task_id")
                    if dep_task_id not in task_map:
                        errors.append({
                            "type": "orphaned_dependency",
                            "task_id": task.id,
                            "missing_dependency_id": dep_task_id,
                            "message": f"Task {task.id} depends on non-existent task {dep_task_id}"
                        })

        # Check for cycles
        try:
            execution_order = TaskDependency.get_execution_order(session, task_ids)
            total_in_order = sum(len(level) for level in execution_order)

            if total_in_order < len(tasks):
                errors.append({
                    "type": "cycle_detected",
                    "message": f"Dependency cycle detected. Only {total_in_order}/{len(tasks)} tasks can be ordered",
                    "unordered_tasks": len(tasks) - total_in_order
                })
        except Exception as e:
            errors.append({
                "type": "validation_error",
                "message": f"Failed to validate execution order: {str(e)}"
            })

        # Check for long dependency chains
        for task in tasks:
            chain_length = TaskDependency._get_dependency_chain_length(session, task.id, set())
            if chain_length > 10:
                warnings.append({
                    "type": "long_chain",
                    "task_id": task.id,
                    "chain_length": chain_length,
                    "message": f"Task {task.id} has a dependency chain of {chain_length} tasks"
                })

        return {
            "valid": len(errors) == 0,
            "total_tasks": len(tasks),
            "total_errors": len(errors),
            "total_warnings": len(warnings),
            "errors": errors,
            "warnings": warnings
        }

    @staticmethod
    def _get_dependency_chain_length(
        session: Session,
        task_id: int,
        visited: Set[int]
    ) -> int:
        """Get the maximum dependency chain length for a task"""
        if task_id in visited:
            return 0

        visited.add(task_id)

        task = session.query(Task).filter(Task.id == task_id).first()
        if not task or not task.metadata or "dependencies" not in task.metadata:
            return 0

        max_length = 0
        for dep in task.metadata["dependencies"]:
            dep_task_id = dep.get("task_id")
            length = 1 + TaskDependency._get_dependency_chain_length(session, dep_task_id, visited.copy())
            max_length = max(max_length, length)

        return max_length

    @staticmethod
    def get_dependency_graph(
        session: Session,
        task_ids: Optional[List[int]] = None
    ) -> Dict[str, Any]:
        """
        Get dependency graph data for visualization.

        Args:
            session: Database session
            task_ids: Optional list of task IDs to include

        Returns:
            Graph data with nodes and edges
        """
        if task_ids:
            tasks = session.query(Task).filter(Task.id.in_(task_ids)).all()
        else:
            tasks = session.query(Task).filter(Task.metadata.isnot(None)).all()

        nodes = []
        edges = []

        for task in tasks:
            nodes.append({
                "id": task.id,
                "label": task.title,
                "status": task.status.value,
                "priority": task.priority.value if task.priority else "normal"
            })

            if task.metadata and "dependencies" in task.metadata:
                for dep in task.metadata["dependencies"]:
                    dep_task_id = dep.get("task_id")
                    edges.append({
                        "from": dep_task_id,
                        "to": task.id,
                        "type": dep.get("type", DependencyType.BLOCKS)
                    })

        return {
            "nodes": nodes,
            "edges": edges,
            "total_nodes": len(nodes),
            "total_edges": len(edges)
        }

    @staticmethod
    def get_ready_tasks(
        session: Session,
        task_ids: Optional[List[int]] = None
    ) -> List[Dict[str, Any]]:
        """
        Get all tasks that are ready to execute (dependencies satisfied).

        Args:
            session: Database session
            task_ids: Optional list of task IDs to check

        Returns:
            List of ready tasks
        """
        if task_ids:
            tasks = session.query(Task).filter(Task.id.in_(task_ids)).all()
        else:
            tasks = session.query(Task).filter(
                Task.status.in_([TaskStatus.PENDING, TaskStatus.QUEUED])
            ).all()

        ready_tasks = []

        for task in tasks:
            readiness = TaskDependency.is_task_ready(session, task.id)
            if readiness["is_ready"]:
                ready_tasks.append({
                    "task_id": task.id,
                    "task_title": task.title,
                    "task_status": task.status.value,
                    "priority": task.priority.value if task.priority else "normal"
                })

        return ready_tasks
