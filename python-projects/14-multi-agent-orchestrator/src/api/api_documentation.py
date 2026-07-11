"""
API Documentation Generator API

REST API endpoints for automatic API documentation generation and SDK management.
"""

from typing import Optional, List
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from src.core.database import get_db_session
from src.services.api_documentation import (
    APIDocumentation,
    DocumentationType,
    SDKLanguage,
    DocumentationFormat
)


router = APIRouter()


# Request/Response Models
class CreateProjectRequest(BaseModel):
    project_name: str = Field(..., description="Project name")
    api_version: str = Field(..., description="API version (semver)")
    base_url: str = Field(..., description="API base URL")
    description: Optional[str] = Field(None, description="Project description")
    contact_info: Optional[dict] = Field(None, description="Contact information")
    license_info: Optional[dict] = Field(None, description="License information")
    tags: Optional[List[str]] = Field(None, description="Project tags")


class GenerateDocumentationRequest(BaseModel):
    doc_type: str = Field(DocumentationType.OPENAPI, description="Documentation type")
    output_format: str = Field(DocumentationFormat.JSON, description="Output format")
    include_examples: bool = Field(True, description="Include code examples")
    include_schemas: bool = Field(True, description="Include request/response schemas")
    include_authentication: bool = Field(True, description="Include authentication docs")


class GenerateSDKRequest(BaseModel):
    language: str = Field(..., description="Target programming language")
    package_name: str = Field(..., description="Package/module name")
    version: str = Field(..., description="SDK version")
    include_async: bool = Field(True, description="Include async/await support")
    include_types: bool = Field(True, description="Include type definitions")


class CreateCodeExampleRequest(BaseModel):
    endpoint_path: str = Field(..., description="API endpoint path")
    method: str = Field(..., description="HTTP method (GET, POST, etc.)")
    language: str = Field(..., description="Programming language")
    title: str = Field(..., description="Example title")
    description: Optional[str] = Field(None, description="Example description")
    code: Optional[str] = Field(None, description="Example code")


class CreateVersionRequest(BaseModel):
    version_number: str = Field(..., description="Version number (semver)")
    changelog: str = Field(..., description="Version changelog")
    breaking_changes: Optional[List[str]] = Field(None, description="Breaking changes")
    deprecated_endpoints: Optional[List[str]] = Field(None, description="Deprecated endpoints")
    new_endpoints: Optional[List[str]] = Field(None, description="New endpoints")


@router.post("/projects")
def create_documentation_project(
    request: CreateProjectRequest,
    session: Session = Depends(get_db_session)
):
    """
    Create a new documentation project.

    Initializes a new API documentation project with metadata and configuration.
    """
    try:
        project = APIDocumentation.create_documentation_project(
            session=session,
            project_name=request.project_name,
            api_version=request.api_version,
            base_url=request.base_url,
            description=request.description,
            contact_info=request.contact_info,
            license_info=request.license_info,
            tags=request.tags
        )

        return {
            "success": True,
            "project": project,
            "message": f"Documentation project created: {project['id']}"
        }

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/projects/{project_id}/generate")
def generate_documentation(
    project_id: str,
    request: GenerateDocumentationRequest,
    session: Session = Depends(get_db_session)
):
    """
    Generate API documentation.

    Generates comprehensive API documentation in the specified format
    with optional examples and schemas.
    """
    try:
        documentation = APIDocumentation.generate_documentation(
            session=session,
            project_id=project_id,
            doc_type=request.doc_type,
            output_format=request.output_format,
            include_examples=request.include_examples,
            include_schemas=request.include_schemas,
            include_authentication=request.include_authentication
        )

        return {
            "success": True,
            "documentation": documentation,
            "message": f"Documentation generated: {documentation['id']}"
        }

    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/projects/{project_id}/sdk")
def generate_sdk(
    project_id: str,
    request: GenerateSDKRequest,
    session: Session = Depends(get_db_session)
):
    """
    Generate SDK for a specific programming language.

    Creates a fully-functional SDK package with authentication,
    error handling, and type definitions.
    """
    try:
        sdk = APIDocumentation.generate_sdk(
            session=session,
            project_id=project_id,
            language=request.language,
            package_name=request.package_name,
            version=request.version,
            include_async=request.include_async,
            include_types=request.include_types
        )

        return {
            "success": True,
            "sdk": sdk,
            "message": f"SDK generated for {request.language}"
        }

    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/projects/{project_id}/examples")
def create_code_example(
    project_id: str,
    request: CreateCodeExampleRequest,
    session: Session = Depends(get_db_session)
):
    """
    Create a code example for an endpoint.

    Adds a code example demonstrating how to use a specific API endpoint
    in the specified programming language.
    """
    try:
        example = APIDocumentation.create_code_example(
            session=session,
            project_id=project_id,
            endpoint_path=request.endpoint_path,
            method=request.method,
            language=request.language,
            title=request.title,
            description=request.description,
            code=request.code
        )

        return {
            "success": True,
            "example": example,
            "message": "Code example created"
        }

    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/projects/{project_id}/versions")
def create_version(
    project_id: str,
    request: CreateVersionRequest,
    session: Session = Depends(get_db_session)
):
    """
    Create a new documentation version.

    Creates a new version of the API documentation with changelog
    and information about breaking changes.
    """
    try:
        version = APIDocumentation.create_version(
            session=session,
            project_id=project_id,
            version_number=request.version_number,
            changelog=request.changelog,
            breaking_changes=request.breaking_changes,
            deprecated_endpoints=request.deprecated_endpoints,
            new_endpoints=request.new_endpoints
        )

        return {
            "success": True,
            "version": version,
            "message": f"Version {request.version_number} created"
        }

    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/versions/{version_id}/publish")
def publish_version(
    version_id: str,
    session: Session = Depends(get_db_session)
):
    """
    Publish a documentation version.

    Makes a documentation version publicly available and marks it as published.
    """
    try:
        version = APIDocumentation.publish_version(
            session=session,
            version_id=version_id
        )

        return {
            "success": True,
            "version": version,
            "message": f"Version published: {version['version_number']}"
        }

    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/projects/{project_id}/changelog")
def generate_changelog(
    project_id: str,
    from_version: Optional[str] = None,
    to_version: Optional[str] = None,
    session: Session = Depends(get_db_session)
):
    """
    Generate changelog between versions.

    Creates a comprehensive changelog showing all changes between
    two versions of the API.
    """
    try:
        changelog = APIDocumentation.generate_changelog(
            session=session,
            project_id=project_id,
            from_version=from_version,
            to_version=to_version
        )

        return {
            "success": True,
            "changelog": changelog
        }

    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/projects/{project_id}/search")
def search_documentation(
    project_id: str,
    query: str,
    search_in: Optional[List[str]] = None,
    session: Session = Depends(get_db_session)
):
    """
    Search documentation content.

    Searches through endpoints, models, and examples to find
    relevant documentation.
    """
    try:
        results = APIDocumentation.search_documentation(
            session=session,
            project_id=project_id,
            query=query,
            search_in=search_in
        )

        return {
            "success": True,
            **results
        }

    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/projects/{project_id}/statistics")
def get_project_statistics(
    project_id: str,
    session: Session = Depends(get_db_session)
):
    """
    Get documentation project statistics.

    Returns comprehensive statistics about a documentation project
    including versions, examples, and SDKs.
    """
    try:
        stats = APIDocumentation.get_project_statistics(
            session=session,
            project_id=project_id
        )

        return {
            "success": True,
            "statistics": stats
        }

    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/statistics")
def get_statistics(
    session: Session = Depends(get_db_session)
):
    """
    Get API documentation statistics.

    Returns aggregate statistics across all documentation projects,
    SDKs, and examples.
    """
    try:
        stats = APIDocumentation.get_statistics(session=session)

        return {
            "success": True,
            "statistics": stats
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/doc-types")
def list_documentation_types():
    """
    List all documentation types.

    Returns all available documentation type options.
    """
    return {
        "success": True,
        "documentation_types": [
            {"type": DocumentationType.OPENAPI, "description": "OpenAPI/Swagger specification"},
            {"type": DocumentationType.ASYNCAPI, "description": "AsyncAPI specification for async APIs"},
            {"type": DocumentationType.MARKDOWN, "description": "Markdown documentation"},
            {"type": DocumentationType.HTML, "description": "HTML documentation website"},
            {"type": DocumentationType.POSTMAN, "description": "Postman collection"},
            {"type": DocumentationType.SWAGGER, "description": "Swagger UI documentation"}
        ]
    }


@router.get("/sdk-languages")
def list_sdk_languages():
    """
    List all supported SDK languages.

    Returns all programming languages available for SDK generation.
    """
    return {
        "success": True,
        "sdk_languages": [
            {"language": SDKLanguage.PYTHON, "description": "Python SDK with async support"},
            {"language": SDKLanguage.JAVASCRIPT, "description": "JavaScript SDK"},
            {"language": SDKLanguage.TYPESCRIPT, "description": "TypeScript SDK with type definitions"},
            {"language": SDKLanguage.JAVA, "description": "Java SDK"},
            {"language": SDKLanguage.GO, "description": "Go SDK"},
            {"language": SDKLanguage.RUBY, "description": "Ruby SDK"},
            {"language": SDKLanguage.PHP, "description": "PHP SDK"},
            {"language": SDKLanguage.CSHARP, "description": "C# .NET SDK"}
        ]
    }


@router.get("/output-formats")
def list_output_formats():
    """
    List all output formats.

    Returns all available documentation output formats.
    """
    return {
        "success": True,
        "output_formats": [
            {"format": DocumentationFormat.JSON, "description": "JSON format"},
            {"format": DocumentationFormat.YAML, "description": "YAML format"},
            {"format": DocumentationFormat.MARKDOWN, "description": "Markdown format"},
            {"format": DocumentationFormat.HTML, "description": "HTML format"},
            {"format": DocumentationFormat.PDF, "description": "PDF format"}
        ]
    }
