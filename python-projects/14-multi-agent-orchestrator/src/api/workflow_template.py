"""
Agent Workflow Templates API

REST API endpoints for managing reusable workflow templates.
"""

from typing import Optional, List, Dict
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from src.core.database import get_db_session
from src.services.workflow_template import (
    WorkflowTemplate,
    TemplateCategory,
    TemplateStatus
)


router = APIRouter()


# Request/Response Models
class CreateTemplateRequest(BaseModel):
    template_name: str = Field(..., description="Template name")
    category: str = Field(..., description="Template category")
    description: str = Field(..., description="Template description")
    steps: List[dict] = Field(..., description="Workflow steps")
    required_roles: Optional[List[str]] = Field(None, description="Required roles")
    parameters: Optional[List[dict]] = Field(None, description="Template parameters")
    metadata: Optional[dict] = Field(None, description="Additional metadata")
    version: str = Field("1.0.0", description="Template version")


class InstantiateTemplateRequest(BaseModel):
    instance_name: str = Field(..., description="Instance name")
    parameter_bindings: Optional[dict] = Field(None, description="Parameter values")
    agent_assignments: Optional[Dict[str, int]] = Field(None, description="Role to agent mappings")
    metadata: Optional[dict] = Field(None, description="Instance metadata")


class ComposeTemplatesRequest(BaseModel):
    composition_name: str = Field(..., description="Composition name")
    templates: List[dict] = Field(..., description="Templates to compose")
    composition_strategy: str = Field("sequential", description="Composition strategy")
    metadata: Optional[dict] = Field(None, description="Composition metadata")


class UpdateTemplateRequest(BaseModel):
    updates: dict = Field(..., description="Fields to update")
    create_new_version: bool = Field(False, description="Create new version")


@router.post("/templates")
def create_template(
    request: CreateTemplateRequest,
    session: Session = Depends(get_db_session)
):
    """
    Create a new workflow template.

    Defines reusable workflow pattern with steps, roles, and parameters.
    Templates can be instantiated multiple times with different configurations.
    """
    try:
        template = WorkflowTemplate.create_template(
            session=session,
            template_name=request.template_name,
            category=request.category,
            description=request.description,
            steps=request.steps,
            required_roles=request.required_roles,
            parameters=request.parameters,
            metadata=request.metadata,
            version=request.version
        )

        return {
            "success": True,
            "template": template,
            "message": f"Template '{request.template_name}' created"
        }

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/templates/{template_id}/instantiate")
def instantiate_template(
    template_id: str,
    request: InstantiateTemplateRequest,
    session: Session = Depends(get_db_session)
):
    """
    Instantiate a template as a workflow.

    Binds parameters and assigns agents to roles to create
    a concrete workflow from the template.
    """
    try:
        instance = WorkflowTemplate.instantiate_template(
            session=session,
            template_id=template_id,
            instance_name=request.instance_name,
            parameter_bindings=request.parameter_bindings,
            agent_assignments=request.agent_assignments,
            metadata=request.metadata
        )

        return {
            "success": True,
            "instance": instance,
            "message": f"Template instantiated as '{request.instance_name}'"
        }

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/templates/compose")
def compose_templates(
    request: ComposeTemplatesRequest,
    session: Session = Depends(get_db_session)
):
    """
    Compose multiple templates into a new template.

    Combines templates using sequential or parallel strategies
    to create complex workflows from simpler components.
    """
    try:
        composed = WorkflowTemplate.compose_templates(
            session=session,
            composition_name=request.composition_name,
            templates=request.templates,
            composition_strategy=request.composition_strategy,
            metadata=request.metadata
        )

        return {
            "success": True,
            "template": composed,
            "message": f"Composed template '{request.composition_name}' created"
        }

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/templates/{template_id}")
def update_template(
    template_id: str,
    request: UpdateTemplateRequest,
    session: Session = Depends(get_db_session)
):
    """
    Update a template.

    Modifies template in place or creates new version
    while deprecating the old one.
    """
    try:
        template = WorkflowTemplate.update_template(
            session=session,
            template_id=template_id,
            updates=request.updates,
            create_new_version=request.create_new_version
        )

        return {
            "success": True,
            "template": template,
            "message": "Template updated"
        }

    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/templates/{template_id}/validate")
def validate_template(
    template_id: str,
    session: Session = Depends(get_db_session)
):
    """
    Validate template structure.

    Checks template for errors and warnings including
    missing fields, duplicates, and structural issues.
    """
    try:
        validation = WorkflowTemplate.validate_template(
            session=session,
            template_id=template_id
        )

        return {
            "success": True,
            **validation
        }

    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/templates/{template_id}")
def get_template(
    template_id: str,
    session: Session = Depends(get_db_session)
):
    """
    Get template details.

    Returns template definition with usage statistics
    and recent instances.
    """
    try:
        template = WorkflowTemplate.get_template(
            session=session,
            template_id=template_id
        )

        return {
            "success": True,
            "template": template
        }

    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/templates")
def list_templates(
    category: Optional[str] = None,
    status: Optional[str] = None,
    search: Optional[str] = None,
    session: Session = Depends(get_db_session)
):
    """
    List templates with filtering.

    Search and filter templates by category, status, or text search.
    Results sorted by usage count.
    """
    try:
        result = WorkflowTemplate.list_templates(
            session=session,
            category=category,
            status=status,
            search=search
        )

        return {
            "success": True,
            **result
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/templates/name/{template_name}/versions")
def get_template_versions(
    template_name: str,
    session: Session = Depends(get_db_session)
):
    """
    Get all versions of a template.

    Returns version history sorted by version number.
    """
    try:
        versions = WorkflowTemplate.get_template_versions(
            session=session,
            template_name=template_name
        )

        return {
            "success": True,
            **versions
        }

    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/templates/popular")
def get_popular_templates(
    limit: int = 10,
    session: Session = Depends(get_db_session)
):
    """
    Get most popular templates.

    Returns templates sorted by usage count.
    """
    try:
        result = WorkflowTemplate.get_popular_templates(
            session=session,
            limit=limit
        )

        return {
            "success": True,
            **result
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/templates/statistics")
def get_statistics(
    session: Session = Depends(get_db_session)
):
    """
    Get template system statistics.

    Returns aggregate data on templates, instances, and usage.
    """
    try:
        stats = WorkflowTemplate.get_template_statistics(session=session)

        return {
            "success": True,
            "statistics": stats
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/categories")
def list_categories():
    """
    List all template categories.

    Returns available workflow pattern categories.
    """
    return {
        "success": True,
        "categories": [
            {"category": TemplateCategory.SEQUENTIAL, "description": "Sequential execution of steps"},
            {"category": TemplateCategory.PARALLEL, "description": "Parallel execution of steps"},
            {"category": TemplateCategory.HIERARCHICAL, "description": "Hierarchical task decomposition"},
            {"category": TemplateCategory.ITERATIVE, "description": "Iterative/loop-based execution"},
            {"category": TemplateCategory.CONDITIONAL, "description": "Conditional branching logic"},
            {"category": TemplateCategory.MAP_REDUCE, "description": "Map-reduce pattern"},
            {"category": TemplateCategory.PIPELINE, "description": "Data pipeline pattern"},
            {"category": TemplateCategory.BROADCAST, "description": "Broadcast to multiple agents"}
        ]
    }


@router.get("/statuses")
def list_statuses():
    """
    List all template statuses.

    Returns possible template lifecycle statuses.
    """
    return {
        "success": True,
        "statuses": [
            {"status": TemplateStatus.DRAFT, "description": "Draft/under development"},
            {"status": TemplateStatus.ACTIVE, "description": "Active and available for use"},
            {"status": TemplateStatus.DEPRECATED, "description": "Deprecated, newer version available"},
            {"status": TemplateStatus.ARCHIVED, "description": "Archived/no longer available"}
        ]
    }
