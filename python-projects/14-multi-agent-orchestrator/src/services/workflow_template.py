"""
Agent Workflow Templates Service

Provides reusable workflow patterns for common multi-agent scenarios.
Enables template creation, instantiation, composition, and versioning.
"""

from typing import Dict, List, Optional
from datetime import datetime
from collections import defaultdict
import copy


class TemplateCategory:
    """Workflow template categories"""
    SEQUENTIAL = "sequential"
    PARALLEL = "parallel"
    HIERARCHICAL = "hierarchical"
    ITERATIVE = "iterative"
    CONDITIONAL = "conditional"
    MAP_REDUCE = "map_reduce"
    PIPELINE = "pipeline"
    BROADCAST = "broadcast"


class TemplateStatus:
    """Template statuses"""
    DRAFT = "draft"
    ACTIVE = "active"
    DEPRECATED = "deprecated"
    ARCHIVED = "archived"


class WorkflowTemplate:
    """
    Agent Workflow Templates System

    Manages reusable workflow patterns, template library, instantiation,
    and composition.
    """

    # In-memory storage
    _templates = {}
    _template_counter = 0

    _template_versions = defaultdict(list)  # template_name -> [versions]
    _template_instances = defaultdict(list)  # template_id -> [instances]
    _template_usage = defaultdict(int)  # template_id -> usage_count

    _categories = defaultdict(list)  # category -> [template_ids]

    @staticmethod
    def create_template(
        session,
        template_name: str,
        category: str,
        description: str,
        steps: List[dict],
        required_roles: Optional[List[str]] = None,
        parameters: Optional[List[dict]] = None,
        metadata: Optional[dict] = None,
        version: str = "1.0.0"
    ) -> dict:
        """
        Create a new workflow template.

        Args:
            session: Database session
            template_name: Template name
            category: Template category
            description: Template description
            steps: Workflow steps definition
            required_roles: Roles needed to execute
            parameters: Template parameters with defaults
            metadata: Additional metadata
            version: Template version

        Returns:
            Template record
        """
        WorkflowTemplate._template_counter += 1
        template_id = f"template_{WorkflowTemplate._template_counter}"

        template = {
            "id": template_id,
            "template_name": template_name,
            "category": category,
            "description": description,
            "steps": steps,
            "required_roles": required_roles or [],
            "parameters": parameters or [],
            "metadata": metadata or {},
            "version": version,
            "status": TemplateStatus.ACTIVE,
            "created_at": datetime.utcnow().isoformat(),
            "updated_at": datetime.utcnow().isoformat(),
            "created_by": None,
            "usage_count": 0
        }

        WorkflowTemplate._templates[template_id] = template
        WorkflowTemplate._template_versions[template_name].append(template)
        WorkflowTemplate._categories[category].append(template_id)

        return template

    @staticmethod
    def instantiate_template(
        session,
        template_id: str,
        instance_name: str,
        parameter_bindings: Optional[dict] = None,
        agent_assignments: Optional[Dict[str, int]] = None,
        metadata: Optional[dict] = None
    ) -> dict:
        """
        Instantiate a template as a workflow.

        Args:
            session: Database session
            template_id: Template ID
            instance_name: Name for instance
            parameter_bindings: Parameter values
            agent_assignments: Role to agent_id mappings
            metadata: Instance metadata

        Returns:
            Workflow instance
        """
        if template_id not in WorkflowTemplate._templates:
            raise ValueError(f"Template {template_id} not found")

        template = WorkflowTemplate._templates[template_id]

        if template["status"] != TemplateStatus.ACTIVE:
            raise ValueError(f"Template {template_id} is not active (status: {template['status']})")

        # Validate parameters
        param_bindings = parameter_bindings or {}
        for param in template["parameters"]:
            if param.get("required", False) and param["name"] not in param_bindings:
                if "default" not in param:
                    raise ValueError(f"Required parameter '{param['name']}' not provided")

        # Validate role assignments
        role_assignments = agent_assignments or {}
        missing_roles = set(template["required_roles"]) - set(role_assignments.keys())
        if missing_roles:
            raise ValueError(f"Missing agent assignments for roles: {missing_roles}")

        # Create instance by substituting parameters
        instance_steps = WorkflowTemplate._substitute_parameters(
            template["steps"],
            param_bindings,
            role_assignments
        )

        instance = {
            "instance_name": instance_name,
            "template_id": template_id,
            "template_name": template["template_name"],
            "template_version": template["version"],
            "steps": instance_steps,
            "parameter_bindings": param_bindings,
            "agent_assignments": role_assignments,
            "metadata": metadata or {},
            "created_at": datetime.utcnow().isoformat(),
            "status": "ready"
        }

        WorkflowTemplate._template_instances[template_id].append(instance)
        WorkflowTemplate._template_usage[template_id] += 1
        WorkflowTemplate._templates[template_id]["usage_count"] += 1

        return instance

    @staticmethod
    def compose_templates(
        session,
        composition_name: str,
        templates: List[dict],
        composition_strategy: str = "sequential",
        metadata: Optional[dict] = None
    ) -> dict:
        """
        Compose multiple templates into a new template.

        Args:
            session: Database session
            composition_name: Name for composed template
            templates: List of template specs with template_id and config
            composition_strategy: How to compose (sequential, parallel)
            metadata: Composition metadata

        Returns:
            New composed template
        """
        if not templates:
            raise ValueError("At least one template required for composition")

        composed_steps = []
        combined_roles = set()
        combined_parameters = []

        if composition_strategy == "sequential":
            # Execute templates in sequence
            for i, template_spec in enumerate(templates):
                template_id = template_spec["template_id"]
                if template_id not in WorkflowTemplate._templates:
                    raise ValueError(f"Template {template_id} not found")

                template = WorkflowTemplate._templates[template_id]

                # Add steps with prefixed IDs
                for step in template["steps"]:
                    composed_step = copy.deepcopy(step)
                    composed_step["id"] = f"t{i}_{step['id']}"
                    composed_step["template_source"] = template_id
                    composed_steps.append(composed_step)

                # Collect roles and parameters
                combined_roles.update(template["required_roles"])
                combined_parameters.extend(template["parameters"])

        elif composition_strategy == "parallel":
            # Execute templates in parallel
            parallel_group = {
                "id": "parallel_group",
                "type": "parallel",
                "parallel_steps": []
            }

            for i, template_spec in enumerate(templates):
                template_id = template_spec["template_id"]
                template = WorkflowTemplate._templates[template_id]

                parallel_group["parallel_steps"].append({
                    "template_id": template_id,
                    "steps": template["steps"]
                })

                combined_roles.update(template["required_roles"])
                combined_parameters.extend(template["parameters"])

            composed_steps.append(parallel_group)

        # Create new template
        composed_template = WorkflowTemplate.create_template(
            session=session,
            template_name=composition_name,
            category=TemplateCategory.PIPELINE,
            description=f"Composed from {len(templates)} templates",
            steps=composed_steps,
            required_roles=list(combined_roles),
            parameters=combined_parameters,
            metadata={
                **(metadata or {}),
                "composition_strategy": composition_strategy,
                "source_templates": [t["template_id"] for t in templates]
            }
        )

        return composed_template

    @staticmethod
    def update_template(
        session,
        template_id: str,
        updates: dict,
        create_new_version: bool = False
    ) -> dict:
        """
        Update a template.

        Args:
            session: Database session
            template_id: Template ID
            updates: Fields to update
            create_new_version: Create new version instead of updating

        Returns:
            Updated or new template
        """
        if template_id not in WorkflowTemplate._templates:
            raise ValueError(f"Template {template_id} not found")

        template = WorkflowTemplate._templates[template_id]

        if create_new_version:
            # Create new version
            current_version = template["version"]
            major, minor, patch = map(int, current_version.split("."))
            new_version = f"{major}.{minor + 1}.{patch}"

            new_template = WorkflowTemplate.create_template(
                session=session,
                template_name=template["template_name"],
                category=template["category"],
                description=updates.get("description", template["description"]),
                steps=updates.get("steps", template["steps"]),
                required_roles=updates.get("required_roles", template["required_roles"]),
                parameters=updates.get("parameters", template["parameters"]),
                metadata=updates.get("metadata", template["metadata"]),
                version=new_version
            )

            # Deprecate old version
            template["status"] = TemplateStatus.DEPRECATED

            return new_template
        else:
            # Update in place
            allowed_fields = ["description", "steps", "required_roles", "parameters", "metadata", "status"]
            for field in allowed_fields:
                if field in updates:
                    template[field] = updates[field]

            template["updated_at"] = datetime.utcnow().isoformat()

            return template

    @staticmethod
    def validate_template(
        session,
        template_id: str
    ) -> dict:
        """
        Validate template structure and dependencies.

        Args:
            session: Database session
            template_id: Template ID

        Returns:
            Validation result
        """
        if template_id not in WorkflowTemplate._templates:
            raise ValueError(f"Template {template_id} not found")

        template = WorkflowTemplate._templates[template_id]
        errors = []
        warnings = []

        # Validate steps
        if not template["steps"]:
            errors.append("Template has no steps")

        step_ids = set()
        for step in template["steps"]:
            if "id" not in step:
                errors.append("Step missing 'id' field")
            elif step["id"] in step_ids:
                errors.append(f"Duplicate step ID: {step['id']}")
            else:
                step_ids.add(step["id"])

            if "type" not in step:
                errors.append(f"Step {step.get('id', 'unknown')} missing 'type' field")

        # Validate parameters
        param_names = set()
        for param in template["parameters"]:
            if "name" not in param:
                errors.append("Parameter missing 'name' field")
            elif param["name"] in param_names:
                errors.append(f"Duplicate parameter: {param['name']}")
            else:
                param_names.add(param["name"])

            if param.get("required", False) and "default" not in param:
                warnings.append(f"Required parameter '{param['name']}' has no default")

        # Validate roles
        if not template["required_roles"]:
            warnings.append("Template has no required roles")

        is_valid = len(errors) == 0

        return {
            "template_id": template_id,
            "is_valid": is_valid,
            "errors": errors,
            "warnings": warnings
        }

    @staticmethod
    def get_template(
        session,
        template_id: str
    ) -> dict:
        """
        Get template details.

        Args:
            session: Database session
            template_id: Template ID

        Returns:
            Template with usage statistics
        """
        if template_id not in WorkflowTemplate._templates:
            raise ValueError(f"Template {template_id} not found")

        template = WorkflowTemplate._templates[template_id]
        instances = WorkflowTemplate._template_instances.get(template_id, [])

        return {
            **template,
            "total_instances": len(instances),
            "recent_instances": instances[-5:]  # Last 5
        }

    @staticmethod
    def list_templates(
        session,
        category: Optional[str] = None,
        status: Optional[str] = None,
        search: Optional[str] = None
    ) -> dict:
        """
        List templates with filtering.

        Args:
            session: Database session
            category: Filter by category
            status: Filter by status
            search: Search in name/description

        Returns:
            Filtered template list
        """
        templates = list(WorkflowTemplate._templates.values())

        if category:
            templates = [t for t in templates if t["category"] == category]

        if status:
            templates = [t for t in templates if t["status"] == status]

        if search:
            search_lower = search.lower()
            templates = [
                t for t in templates
                if search_lower in t["template_name"].lower()
                or search_lower in t["description"].lower()
            ]

        # Sort by usage
        templates.sort(key=lambda t: t["usage_count"], reverse=True)

        return {
            "total": len(templates),
            "templates": templates
        }

    @staticmethod
    def get_template_versions(
        session,
        template_name: str
    ) -> dict:
        """
        Get all versions of a template.

        Args:
            session: Database session
            template_name: Template name

        Returns:
            Template versions
        """
        versions = WorkflowTemplate._template_versions.get(template_name, [])

        if not versions:
            raise ValueError(f"No templates found with name '{template_name}'")

        # Sort by version
        versions.sort(key=lambda t: t["version"], reverse=True)

        return {
            "template_name": template_name,
            "total_versions": len(versions),
            "versions": versions,
            "latest_version": versions[0] if versions else None
        }

    @staticmethod
    def get_popular_templates(
        session,
        limit: int = 10
    ) -> dict:
        """
        Get most popular templates.

        Args:
            session: Database session
            limit: Maximum templates to return

        Returns:
            Popular templates
        """
        templates = list(WorkflowTemplate._templates.values())
        templates.sort(key=lambda t: t["usage_count"], reverse=True)

        return {
            "limit": limit,
            "popular_templates": templates[:limit]
        }

    @staticmethod
    def get_template_statistics(session) -> dict:
        """
        Get template system statistics.

        Args:
            session: Database session

        Returns:
            System statistics
        """
        total_templates = len(WorkflowTemplate._templates)
        total_instances = sum(len(instances) for instances in WorkflowTemplate._template_instances.values())

        # Count by category
        by_category = defaultdict(int)
        for template in WorkflowTemplate._templates.values():
            by_category[template["category"]] += 1

        # Count by status
        by_status = defaultdict(int)
        for template in WorkflowTemplate._templates.values():
            by_status[template["status"]] += 1

        return {
            "total_templates": total_templates,
            "total_instances": total_instances,
            "templates_by_category": dict(by_category),
            "templates_by_status": dict(by_status),
            "average_usage": total_instances / total_templates if total_templates > 0 else 0
        }

    # Helper methods

    @staticmethod
    def _substitute_parameters(
        steps: List[dict],
        param_bindings: dict,
        role_assignments: dict
    ) -> List[dict]:
        """Substitute parameters and role assignments in steps"""
        substituted_steps = []

        for step in steps:
            step_copy = copy.deepcopy(step)

            # Substitute in step definition
            step_str = str(step_copy)

            # Replace parameters
            for param_name, param_value in param_bindings.items():
                step_str = step_str.replace(f"${{{param_name}}}", str(param_value))

            # Replace role assignments
            for role_name, agent_id in role_assignments.items():
                step_str = step_str.replace(f"@{{{role_name}}}", str(agent_id))

            # Convert back to dict (simplified - would need proper parsing in production)
            # For now, just update the copy with assignments
            if "assigned_agent" in step_copy and step_copy["assigned_agent"].startswith("@{"):
                role = step_copy["assigned_agent"][2:-1]
                if role in role_assignments:
                    step_copy["assigned_agent"] = role_assignments[role]

            substituted_steps.append(step_copy)

        return substituted_steps
