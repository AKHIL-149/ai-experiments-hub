"""
Documentation Tests
Tests to ensure documentation is complete and up-to-date
"""

import pytest
from pathlib import Path


PROJECT_ROOT = Path(__file__).parent.parent


class TestDocumentationFiles:
    """Test that all required documentation exists"""

    def test_readme_exists(self):
        """Test README.md exists"""
        readme = PROJECT_ROOT / "README.md"
        assert readme.exists(), "README.md not found"

    def test_security_md_exists(self):
        """Test SECURITY.md exists"""
        security = PROJECT_ROOT / "SECURITY.md"
        assert security.exists(), "SECURITY.md not found"

    def test_deployment_guide_exists(self):
        """Test deployment guide exists"""
        deployment = PROJECT_ROOT / "docs" / "DEPLOYMENT.md"
        assert deployment.exists(), "docs/DEPLOYMENT.md not found"

    def test_user_guide_exists(self):
        """Test user guide exists"""
        user_guide = PROJECT_ROOT / "docs" / "USER_GUIDE.md"
        assert user_guide.exists(), "docs/USER_GUIDE.md not found"

    def test_troubleshooting_guide_exists(self):
        """Test troubleshooting guide exists"""
        troubleshooting = PROJECT_ROOT / "docs" / "TROUBLESHOOTING.md"
        assert troubleshooting.exists(), "docs/TROUBLESHOOTING.md not found"

    def test_api_reference_exists(self):
        """Test API reference exists"""
        api_ref = PROJECT_ROOT / "docs" / "API_REFERENCE.md"
        assert api_ref.exists(), "docs/API_REFERENCE.md not found"


class TestREADMEContent:
    """Test README.md content"""

    def test_readme_has_version(self):
        """Test README has version number"""
        readme = PROJECT_ROOT / "README.md"
        content = readme.read_text()
        assert "Version" in content
        assert "0.5." in content or "1.0." in content

    def test_readme_has_features_section(self):
        """Test README has features section"""
        readme = PROJECT_ROOT / "README.md"
        content = readme.read_text()
        assert "Features" in content or "## 🚀" in content

    def test_readme_has_installation_instructions(self):
        """Test README has installation section"""
        readme = PROJECT_ROOT / "README.md"
        content = readme.read_text()
        assert "install" in content.lower() or "setup" in content.lower()

    def test_readme_has_usage_examples(self):
        """Test README has usage examples"""
        readme = PROJECT_ROOT / "README.md"
        content = readme.read_text()
        assert "```" in content  # Code blocks
        assert "python" in content.lower()

    def test_readme_has_recent_updates(self):
        """Test README has recent updates section"""
        readme = PROJECT_ROOT / "README.md"
        content = readme.read_text()
        assert "Recent Updates" in content or "Changelog" in content or "Updates" in content


class TestDeploymentGuide:
    """Test deployment guide content"""

    def test_deployment_has_prerequisites(self):
        """Test deployment guide has prerequisites"""
        deployment = PROJECT_ROOT / "docs" / "DEPLOYMENT.md"
        content = deployment.read_text()
        assert "Prerequisites" in content or "Requirements" in content

    def test_deployment_has_docker_instructions(self):
        """Test deployment guide has Docker instructions"""
        deployment = PROJECT_ROOT / "docs" / "DEPLOYMENT.md"
        content = deployment.read_text()
        assert "Docker" in content
        assert "docker-compose" in content

    def test_deployment_has_production_section(self):
        """Test deployment guide has production deployment"""
        deployment = PROJECT_ROOT / "docs" / "DEPLOYMENT.md"
        content = deployment.read_text()
        assert "Production" in content
        assert "Nginx" in content or "nginx" in content

    def test_deployment_has_environment_config(self):
        """Test deployment guide has environment configuration"""
        deployment = PROJECT_ROOT / "docs" / "DEPLOYMENT.md"
        content = deployment.read_text()
        assert ".env" in content
        assert "environment" in content.lower()

    def test_deployment_has_troubleshooting(self):
        """Test deployment guide has troubleshooting section"""
        deployment = PROJECT_ROOT / "docs" / "DEPLOYMENT.md"
        content = deployment.read_text()
        assert "Troubleshooting" in content or "troubleshooting" in content


class TestUserGuide:
    """Test user guide content"""

    def test_user_guide_has_getting_started(self):
        """Test user guide has getting started section"""
        user_guide = PROJECT_ROOT / "docs" / "USER_GUIDE.md"
        content = user_guide.read_text()
        assert "Getting Started" in content

    def test_user_guide_has_authentication_section(self):
        """Test user guide has authentication section"""
        user_guide = PROJECT_ROOT / "docs" / "USER_GUIDE.md"
        content = user_guide.read_text()
        assert "Authentication" in content or "Login" in content

    def test_user_guide_has_repository_management(self):
        """Test user guide has repository management"""
        user_guide = PROJECT_ROOT / "docs" / "USER_GUIDE.md"
        content = user_guide.read_text()
        assert "Repository" in content or "repository" in content
        assert "Adding" in content or "adding" in content

    def test_user_guide_has_analysis_section(self):
        """Test user guide has analysis section"""
        user_guide = PROJECT_ROOT / "docs" / "USER_GUIDE.md"
        content = user_guide.read_text()
        assert "Analysis" in content or "Analyzing" in content

    def test_user_guide_has_screenshots_or_examples(self):
        """Test user guide has examples"""
        user_guide = PROJECT_ROOT / "docs" / "USER_GUIDE.md"
        content = user_guide.read_text()
        assert "```" in content or "Example" in content


class TestTroubleshootingGuide:
    """Test troubleshooting guide content"""

    def test_troubleshooting_has_table_of_contents(self):
        """Test troubleshooting has table of contents"""
        troubleshooting = PROJECT_ROOT / "docs" / "TROUBLESHOOTING.md"
        content = troubleshooting.read_text()
        assert "Table of Contents" in content

    def test_troubleshooting_has_common_issues(self):
        """Test troubleshooting covers common issues"""
        troubleshooting = PROJECT_ROOT / "docs" / "TROUBLESHOOTING.md"
        content = troubleshooting.read_text()
        assert "Application" in content
        assert "Database" in content
        assert "Redis" in content or "Celery" in content

    def test_troubleshooting_has_solutions(self):
        """Test troubleshooting provides solutions"""
        troubleshooting = PROJECT_ROOT / "docs" / "TROUBLESHOOTING.md"
        content = troubleshooting.read_text()
        assert "Solution" in content or "solution" in content
        assert "```" in content  # Code blocks for commands

    def test_troubleshooting_has_error_messages(self):
        """Test troubleshooting includes error messages"""
        troubleshooting = PROJECT_ROOT / "docs" / "TROUBLESHOOTING.md"
        content = troubleshooting.read_text()
        assert "Error" in content or "error" in content
        assert "Symptoms" in content or "symptoms" in content


class TestAPIReference:
    """Test API reference content"""

    def test_api_ref_has_base_url(self):
        """Test API reference has base URL"""
        api_ref = PROJECT_ROOT / "docs" / "API_REFERENCE.md"
        content = api_ref.read_text()
        assert "Base URL" in content
        assert "localhost:8000" in content or "your-domain" in content

    def test_api_ref_has_authentication_section(self):
        """Test API reference has authentication"""
        api_ref = PROJECT_ROOT / "docs" / "API_REFERENCE.md"
        content = api_ref.read_text()
        assert "Authentication" in content
        assert "session" in content.lower() or "token" in content.lower()

    def test_api_ref_has_endpoints(self):
        """Test API reference lists endpoints"""
        api_ref = PROJECT_ROOT / "docs" / "API_REFERENCE.md"
        content = api_ref.read_text()
        assert "/api/" in content
        assert "POST" in content or "GET" in content
        assert "Request" in content and "Response" in content

    def test_api_ref_has_examples(self):
        """Test API reference has code examples"""
        api_ref = PROJECT_ROOT / "docs" / "API_REFERENCE.md"
        content = api_ref.read_text()
        assert "```" in content
        assert "curl" in content or "python" in content or "javascript" in content.lower()

    def test_api_ref_has_error_handling(self):
        """Test API reference documents error handling"""
        api_ref = PROJECT_ROOT / "docs" / "API_REFERENCE.md"
        content = api_ref.read_text()
        assert "Error" in content
        assert "400" in content or "401" in content or "404" in content or "500" in content


class TestSecurityDocumentation:
    """Test security documentation"""

    def test_security_has_reporting_process(self):
        """Test SECURITY.md has vulnerability reporting"""
        security = PROJECT_ROOT / "SECURITY.md"
        content = security.read_text()
        assert "Reporting" in content or "reporting" in content
        assert "vulnerability" in content.lower()

    def test_security_has_supported_versions(self):
        """Test SECURITY.md lists supported versions"""
        security = PROJECT_ROOT / "SECURITY.md"
        content = security.read_text()
        assert "Supported" in content or "supported" in content
        assert "Version" in content or "version" in content

    def test_security_has_best_practices(self):
        """Test SECURITY.md has security best practices"""
        security = PROJECT_ROOT / "SECURITY.md"
        content = security.read_text()
        assert "Best Practices" in content or "best practices" in content or "Security Controls" in content


class TestDocumentationLinks:
    """Test that documentation links are valid"""

    def test_readme_links_to_docs(self):
        """Test README links to documentation"""
        readme = PROJECT_ROOT / "README.md"
        content = readme.read_text()

        # Should link to security, deployment, or troubleshooting
        has_links = (
            "SECURITY.md" in content or
            "DEPLOYMENT.md" in content or
            "TROUBLESHOOTING.md" in content or
            "docs/" in content
        )
        assert has_links, "README should link to documentation files"

    def test_deployment_links_to_troubleshooting(self):
        """Test deployment guide links to troubleshooting"""
        deployment = PROJECT_ROOT / "docs" / "DEPLOYMENT.md"
        content = deployment.read_text()
        assert "TROUBLESHOOTING" in content or "troubleshooting" in content.lower()

    def test_user_guide_links_to_api_reference(self):
        """Test user guide links to API reference"""
        user_guide = PROJECT_ROOT / "docs" / "USER_GUIDE.md"
        content = user_guide.read_text()
        has_api_link = (
            "API_REFERENCE" in content or
            "/docs" in content or  # OpenAPI docs
            "api reference" in content.lower()
        )
        assert has_api_link, "User guide should link to API reference"


class TestDocumentationCompleteness:
    """Test documentation coverage"""

    def test_all_features_documented(self):
        """Test major features are documented"""
        user_guide = PROJECT_ROOT / "docs" / "USER_GUIDE.md"
        content = user_guide.read_text().lower()

        required_features = [
            "repository",
            "pull request",
            "analysis",
            "issue",
            "refactoring",
            "team",
            "analytics",
            "notification",
        ]

        for feature in required_features:
            assert feature in content, f"Feature '{feature}' not documented in user guide"

    def test_all_deployment_options_documented(self):
        """Test deployment options are documented"""
        deployment = PROJECT_ROOT / "docs" / "DEPLOYMENT.md"
        content = deployment.read_text().lower()

        deployment_options = [
            "local",
            "docker",
            "production",
            "aws" or "cloud",
        ]

        documented_options = sum(1 for option in deployment_options if option in content)
        assert documented_options >= 3, "Not all deployment options documented"

    def test_common_errors_documented(self):
        """Test common errors are documented"""
        troubleshooting = PROJECT_ROOT / "docs" / "TROUBLESHOOTING.md"
        content = troubleshooting.read_text().lower()

        common_issues = [
            "database",
            "redis",
            "celery",
            "github",
            "authentication",
            "docker",
        ]

        documented_issues = sum(1 for issue in common_issues if issue in content)
        assert documented_issues >= 5, "Not enough common issues documented"


class TestCodeExamples:
    """Test code examples in documentation"""

    def test_api_reference_has_curl_examples(self):
        """Test API reference has curl examples"""
        api_ref = PROJECT_ROOT / "docs" / "API_REFERENCE.md"
        content = api_ref.read_text()
        assert "```bash" in content or "```sh" in content
        assert "curl" in content

    def test_api_reference_has_python_examples(self):
        """Test API reference has Python examples"""
        api_ref = PROJECT_ROOT / "docs" / "API_REFERENCE.md"
        content = api_ref.read_text()
        assert "```python" in content
        assert "requests" in content or "import" in content

    def test_deployment_guide_has_commands(self):
        """Test deployment guide has shell commands"""
        deployment = PROJECT_ROOT / "docs" / "DEPLOYMENT.md"
        content = deployment.read_text()
        assert "```bash" in content or "```sh" in content or "```" in content


class TestDocumentationStructure:
    """Test documentation structure and organization"""

    def test_all_guides_have_table_of_contents(self):
        """Test all major guides have table of contents"""
        guides = [
            PROJECT_ROOT / "docs" / "DEPLOYMENT.md",
            PROJECT_ROOT / "docs" / "USER_GUIDE.md",
            PROJECT_ROOT / "docs" / "TROUBLESHOOTING.md",
            PROJECT_ROOT / "docs" / "API_REFERENCE.md",
        ]

        for guide in guides:
            content = guide.read_text()
            assert "Table of Contents" in content, f"{guide.name} missing table of contents"

    def test_guides_use_proper_markdown_headings(self):
        """Test guides use proper markdown heading hierarchy"""
        guides = [
            PROJECT_ROOT / "docs" / "DEPLOYMENT.md",
            PROJECT_ROOT / "docs" / "USER_GUIDE.md",
        ]

        for guide in guides:
            content = guide.read_text()
            # Should have h1 (title)
            assert content.startswith("# "), f"{guide.name} should start with h1 heading"
            # Should have h2 sections
            assert "\n## " in content, f"{guide.name} should have h2 sections"
