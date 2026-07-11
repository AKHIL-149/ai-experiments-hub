"""
API Documentation Generator

Provides automatic API documentation generation, SDK generation, and developer portal management.
"""

from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta
from collections import defaultdict
import uuid
import random
import json


class DocumentationType:
    """Documentation types"""
    OPENAPI = "openapi"
    ASYNCAPI = "asyncapi"
    MARKDOWN = "markdown"
    HTML = "html"
    POSTMAN = "postman"
    SWAGGER = "swagger"


class SDKLanguage:
    """Supported SDK languages"""
    PYTHON = "python"
    JAVASCRIPT = "javascript"
    TYPESCRIPT = "typescript"
    JAVA = "java"
    GO = "go"
    RUBY = "ruby"
    PHP = "php"
    CSHARP = "csharp"


class DocumentationFormat:
    """Documentation output formats"""
    JSON = "json"
    YAML = "yaml"
    MARKDOWN = "markdown"
    HTML = "html"
    PDF = "pdf"


class APIDocumentation:
    """API Documentation Generator service"""

    # In-memory storage
    _documentation_projects = {}
    _documentation_versions = defaultdict(list)
    _generated_docs = {}
    _sdk_packages = {}
    _code_examples = defaultdict(list)
    _changelogs = defaultdict(list)
    _api_schemas = {}

    @staticmethod
    def create_documentation_project(
        session,
        project_name: str,
        api_version: str,
        base_url: str,
        description: Optional[str] = None,
        contact_info: Optional[dict] = None,
        license_info: Optional[dict] = None,
        tags: Optional[List[str]] = None
    ) -> dict:
        """
        Create documentation project.

        Args:
            session: Database session
            project_name: Project name
            api_version: API version
            base_url: API base URL
            description: Project description
            contact_info: Contact information
            license_info: License information
            tags: Project tags

        Returns:
            Created documentation project
        """
        project_id = f"docproject_{uuid.uuid4().hex[:12]}"
        now = datetime.utcnow()

        project = {
            "id": project_id,
            "name": project_name,
            "api_version": api_version,
            "base_url": base_url,
            "description": description,
            "contact_info": contact_info or {},
            "license_info": license_info or {},
            "tags": tags or [],
            "created_at": now.isoformat(),
            "updated_at": now.isoformat(),
            "total_endpoints": 0,
            "total_versions": 0,
            "total_sdks": 0,
            "total_examples": 0,
            "published": False,
            "latest_version_id": None
        }

        APIDocumentation._documentation_projects[project_id] = project
        return project

    @staticmethod
    def generate_documentation(
        session,
        project_id: str,
        doc_type: str,
        output_format: str = DocumentationFormat.JSON,
        include_examples: bool = True,
        include_schemas: bool = True,
        include_authentication: bool = True
    ) -> dict:
        """
        Generate API documentation.

        Args:
            session: Database session
            project_id: Documentation project ID
            doc_type: Type of documentation to generate
            output_format: Output format
            include_examples: Include code examples
            include_schemas: Include request/response schemas
            include_authentication: Include auth documentation

        Returns:
            Generated documentation
        """
        project = APIDocumentation._documentation_projects.get(project_id)
        if not project:
            raise ValueError(f"Documentation project not found: {project_id}")

        doc_id = f"doc_{uuid.uuid4().hex[:12]}"
        now = datetime.utcnow()

        # Simulate documentation generation
        documentation = {
            "id": doc_id,
            "project_id": project_id,
            "doc_type": doc_type,
            "output_format": output_format,
            "generated_at": now.isoformat(),
            "version": project["api_version"],
            "metadata": {
                "total_endpoints": random.randint(50, 150),
                "total_models": random.randint(30, 80),
                "total_examples": random.randint(100, 300) if include_examples else 0,
                "has_authentication": include_authentication,
                "has_schemas": include_schemas
            },
            "content": {
                "info": {
                    "title": project["name"],
                    "version": project["api_version"],
                    "description": project["description"],
                    "contact": project["contact_info"],
                    "license": project["license_info"]
                },
                "servers": [
                    {"url": project["base_url"], "description": "Production server"}
                ],
                "paths": {},  # Would contain actual API paths
                "components": {
                    "schemas": {} if include_schemas else None,
                    "securitySchemes": {} if include_authentication else None
                }
            },
            "size_bytes": random.randint(50000, 500000),
            "download_url": f"/api/documentation/{doc_id}/download"
        }

        APIDocumentation._generated_docs[doc_id] = documentation
        return documentation

    @staticmethod
    def generate_sdk(
        session,
        project_id: str,
        language: str,
        package_name: str,
        version: str,
        include_async: bool = True,
        include_types: bool = True
    ) -> dict:
        """
        Generate SDK for specific language.

        Args:
            session: Database session
            project_id: Documentation project ID
            language: Target programming language
            package_name: Package/module name
            version: SDK version
            include_async: Include async/await support
            include_types: Include type definitions

        Returns:
            Generated SDK package
        """
        project = APIDocumentation._documentation_projects.get(project_id)
        if not project:
            raise ValueError(f"Documentation project not found: {project_id}")

        sdk_id = f"sdk_{uuid.uuid4().hex[:12]}"
        now = datetime.utcnow()

        sdk_package = {
            "id": sdk_id,
            "project_id": project_id,
            "language": language,
            "package_name": package_name,
            "version": version,
            "generated_at": now.isoformat(),
            "features": {
                "async_support": include_async,
                "type_definitions": include_types,
                "authentication": True,
                "error_handling": True,
                "retry_logic": True,
                "rate_limiting": True
            },
            "files": [
                {"name": "client.py" if language == SDKLanguage.PYTHON else "client.ts", "size_bytes": random.randint(5000, 20000)},
                {"name": "models.py" if language == SDKLanguage.PYTHON else "models.ts", "size_bytes": random.randint(10000, 30000)},
                {"name": "exceptions.py" if language == SDKLanguage.PYTHON else "exceptions.ts", "size_bytes": random.randint(2000, 5000)},
                {"name": "README.md", "size_bytes": random.randint(3000, 8000)}
            ],
            "total_size_bytes": random.randint(50000, 200000),
            "download_url": f"/api/documentation/sdk/{sdk_id}/download",
            "installation_command": APIDocumentation._get_install_command(language, package_name),
            "example_usage": APIDocumentation._get_example_usage(language, package_name)
        }

        APIDocumentation._sdk_packages[sdk_id] = sdk_package
        project["total_sdks"] += 1

        return sdk_package

    @staticmethod
    def _get_install_command(language: str, package_name: str) -> str:
        """Get installation command for SDK"""
        commands = {
            SDKLanguage.PYTHON: f"pip install {package_name}",
            SDKLanguage.JAVASCRIPT: f"npm install {package_name}",
            SDKLanguage.TYPESCRIPT: f"npm install {package_name}",
            SDKLanguage.JAVA: f"maven: <dependency>{package_name}</dependency>",
            SDKLanguage.GO: f"go get {package_name}",
            SDKLanguage.RUBY: f"gem install {package_name}",
            SDKLanguage.PHP: f"composer require {package_name}",
            SDKLanguage.CSHARP: f"dotnet add package {package_name}"
        }
        return commands.get(language, f"Install {package_name}")

    @staticmethod
    def _get_example_usage(language: str, package_name: str) -> str:
        """Get example usage code for SDK"""
        if language == SDKLanguage.PYTHON:
            return f"""
from {package_name} import Client

client = Client(api_key='your_api_key')
tasks = client.tasks.list()
"""
        elif language in [SDKLanguage.JAVASCRIPT, SDKLanguage.TYPESCRIPT]:
            return f"""
import {{ Client }} from '{package_name}';

const client = new Client({{ apiKey: 'your_api_key' }});
const tasks = await client.tasks.list();
"""
        else:
            return f"// Example usage for {package_name}"

    @staticmethod
    def create_code_example(
        session,
        project_id: str,
        endpoint_path: str,
        method: str,
        language: str,
        title: str,
        description: Optional[str] = None,
        code: Optional[str] = None
    ) -> dict:
        """
        Create code example for an endpoint.

        Args:
            session: Database session
            project_id: Documentation project ID
            endpoint_path: API endpoint path
            method: HTTP method
            language: Programming language
            title: Example title
            description: Example description
            code: Example code

        Returns:
            Created code example
        """
        project = APIDocumentation._documentation_projects.get(project_id)
        if not project:
            raise ValueError(f"Documentation project not found: {project_id}")

        example_id = f"example_{uuid.uuid4().hex[:12]}"
        now = datetime.utcnow()

        example = {
            "id": example_id,
            "project_id": project_id,
            "endpoint_path": endpoint_path,
            "method": method.upper(),
            "language": language,
            "title": title,
            "description": description,
            "code": code or f"// Example code for {method} {endpoint_path}",
            "created_at": now.isoformat(),
            "updated_at": now.isoformat(),
            "usage_count": 0,
            "rating": 0.0,
            "votes": 0
        }

        APIDocumentation._code_examples[project_id].append(example)
        project["total_examples"] += 1

        return example

    @staticmethod
    def create_version(
        session,
        project_id: str,
        version_number: str,
        changelog: str,
        breaking_changes: Optional[List[str]] = None,
        deprecated_endpoints: Optional[List[str]] = None,
        new_endpoints: Optional[List[str]] = None
    ) -> dict:
        """
        Create new documentation version.

        Args:
            session: Database session
            project_id: Documentation project ID
            version_number: Version number (semver)
            changelog: Version changelog
            breaking_changes: List of breaking changes
            deprecated_endpoints: List of deprecated endpoints
            new_endpoints: List of new endpoints

        Returns:
            Created version
        """
        project = APIDocumentation._documentation_projects.get(project_id)
        if not project:
            raise ValueError(f"Documentation project not found: {project_id}")

        version_id = f"version_{uuid.uuid4().hex[:12]}"
        now = datetime.utcnow()

        version = {
            "id": version_id,
            "project_id": project_id,
            "version_number": version_number,
            "changelog": changelog,
            "breaking_changes": breaking_changes or [],
            "deprecated_endpoints": deprecated_endpoints or [],
            "new_endpoints": new_endpoints or [],
            "created_at": now.isoformat(),
            "published_at": None,
            "is_latest": True,
            "download_count": 0,
            "status": "draft"
        }

        # Mark previous versions as not latest
        for v in APIDocumentation._documentation_versions[project_id]:
            v["is_latest"] = False

        APIDocumentation._documentation_versions[project_id].append(version)
        project["total_versions"] += 1
        project["latest_version_id"] = version_id
        project["api_version"] = version_number

        return version

    @staticmethod
    def publish_version(
        session,
        version_id: str
    ) -> dict:
        """
        Publish documentation version.

        Args:
            session: Database session
            version_id: Version ID to publish

        Returns:
            Published version
        """
        version = None
        for versions in APIDocumentation._documentation_versions.values():
            for v in versions:
                if v["id"] == version_id:
                    version = v
                    break
            if version:
                break

        if not version:
            raise ValueError(f"Version not found: {version_id}")

        now = datetime.utcnow()
        version["status"] = "published"
        version["published_at"] = now.isoformat()

        return version

    @staticmethod
    def generate_changelog(
        session,
        project_id: str,
        from_version: Optional[str] = None,
        to_version: Optional[str] = None
    ) -> dict:
        """
        Generate changelog between versions.

        Args:
            session: Database session
            project_id: Documentation project ID
            from_version: Starting version
            to_version: Ending version

        Returns:
            Generated changelog
        """
        project = APIDocumentation._documentation_projects.get(project_id)
        if not project:
            raise ValueError(f"Documentation project not found: {project_id}")

        changelog_id = f"changelog_{uuid.uuid4().hex[:12]}"
        now = datetime.utcnow()

        versions = APIDocumentation._documentation_versions.get(project_id, [])

        changelog = {
            "id": changelog_id,
            "project_id": project_id,
            "from_version": from_version or (versions[0]["version_number"] if versions else "0.1.0"),
            "to_version": to_version or (versions[-1]["version_number"] if versions else "1.0.0"),
            "generated_at": now.isoformat(),
            "changes": [
                {
                    "version": v["version_number"],
                    "date": v["created_at"],
                    "breaking_changes": v.get("breaking_changes", []),
                    "new_endpoints": v.get("new_endpoints", []),
                    "deprecated_endpoints": v.get("deprecated_endpoints", []),
                    "changelog": v["changelog"]
                }
                for v in versions
            ],
            "total_versions": len(versions),
            "markdown_content": "# Changelog\n\n" + "\n\n".join([
                f"## {v['version_number']} ({v['created_at'][:10]})\n\n{v['changelog']}"
                for v in versions
            ])
        }

        APIDocumentation._changelogs[project_id].append(changelog)
        return changelog

    @staticmethod
    def search_documentation(
        session,
        project_id: str,
        query: str,
        search_in: Optional[List[str]] = None
    ) -> dict:
        """
        Search documentation content.

        Args:
            session: Database session
            project_id: Documentation project ID
            query: Search query
            search_in: Fields to search in (endpoints, models, examples)

        Returns:
            Search results
        """
        project = APIDocumentation._documentation_projects.get(project_id)
        if not project:
            raise ValueError(f"Documentation project not found: {project_id}")

        search_in = search_in or ["endpoints", "models", "examples"]

        # Simulate search results
        results = {
            "query": query,
            "total_results": random.randint(5, 50),
            "search_time_ms": random.uniform(10, 100),
            "results": [
                {
                    "type": random.choice(search_in),
                    "title": f"Result {i+1} for '{query}'",
                    "path": f"/api/endpoint/{i+1}",
                    "relevance_score": random.uniform(0.5, 1.0),
                    "snippet": f"...matching content for {query}..."
                }
                for i in range(min(10, random.randint(5, 50)))
            ]
        }

        return results

    @staticmethod
    def get_project_statistics(
        session,
        project_id: str
    ) -> dict:
        """
        Get documentation project statistics.

        Args:
            session: Database session
            project_id: Documentation project ID

        Returns:
            Project statistics
        """
        project = APIDocumentation._documentation_projects.get(project_id)
        if not project:
            raise ValueError(f"Documentation project not found: {project_id}")

        versions = APIDocumentation._documentation_versions.get(project_id, [])
        examples = APIDocumentation._code_examples.get(project_id, [])

        # Language distribution
        lang_dist = defaultdict(int)
        for ex in examples:
            lang_dist[ex["language"]] += 1

        return {
            "project_id": project_id,
            "project_name": project["name"],
            "total_versions": len(versions),
            "total_endpoints": project["total_endpoints"],
            "total_sdks": project["total_sdks"],
            "total_examples": len(examples),
            "language_distribution": dict(lang_dist),
            "latest_version": project["api_version"],
            "published": project["published"],
            "created_at": project["created_at"],
            "updated_at": project["updated_at"]
        }

    @staticmethod
    def get_statistics(session) -> dict:
        """Get API documentation statistics"""
        projects = list(APIDocumentation._documentation_projects.values())
        all_versions = [v for versions in APIDocumentation._documentation_versions.values() for v in versions]
        all_examples = [ex for examples in APIDocumentation._code_examples.values() for ex in examples]
        sdks = list(APIDocumentation._sdk_packages.values())

        # Doc type distribution
        doc_type_dist = defaultdict(int)
        for doc in APIDocumentation._generated_docs.values():
            doc_type_dist[doc["doc_type"]] += 1

        # SDK language distribution
        sdk_lang_dist = defaultdict(int)
        for sdk in sdks:
            sdk_lang_dist[sdk["language"]] += 1

        # Example language distribution
        example_lang_dist = defaultdict(int)
        for ex in all_examples:
            example_lang_dist[ex["language"]] += 1

        return {
            "total_projects": len(projects),
            "total_versions": len(all_versions),
            "total_generated_docs": len(APIDocumentation._generated_docs),
            "total_sdks": len(sdks),
            "total_examples": len(all_examples),
            "total_changelogs": sum(len(c) for c in APIDocumentation._changelogs.values()),
            "doc_type_distribution": dict(doc_type_dist),
            "sdk_language_distribution": dict(sdk_lang_dist),
            "example_language_distribution": dict(example_lang_dist),
            "published_projects": len([p for p in projects if p["published"]]),
            "draft_projects": len([p for p in projects if not p["published"]])
        }
