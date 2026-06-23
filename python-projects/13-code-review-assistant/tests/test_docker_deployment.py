"""
Docker Deployment Tests
Tests Docker setup, multi-stage build, and docker-compose configuration
"""

import os
import re
import pytest
import yaml
from pathlib import Path


# Get project root
PROJECT_ROOT = Path(__file__).parent.parent


class TestDockerfile:
    """Test Dockerfile configuration"""

    def test_dockerfile_exists(self):
        """Test that Dockerfile exists"""
        dockerfile_path = PROJECT_ROOT / "Dockerfile"
        assert dockerfile_path.exists(), "Dockerfile not found"

    def test_dockerfile_multistage_build(self):
        """Test Dockerfile uses multi-stage build"""
        dockerfile_path = PROJECT_ROOT / "Dockerfile"
        content = dockerfile_path.read_text()

        # Check for builder stage
        assert "FROM python:3.11-slim as builder" in content, \
            "Missing builder stage in multi-stage build"

        # Check for runtime stage
        assert "FROM python:3.11-slim" in content, \
            "Missing runtime stage"

        # Check for COPY from builder
        assert "COPY --from=builder" in content, \
            "Missing COPY from builder stage"

    def test_dockerfile_virtual_environment(self):
        """Test Dockerfile uses virtual environment"""
        dockerfile_path = PROJECT_ROOT / "Dockerfile"
        content = dockerfile_path.read_text()

        assert "python -m venv /opt/venv" in content, \
            "Missing virtual environment creation"
        assert 'PATH="/opt/venv/bin:$PATH"' in content, \
            "Virtual environment not added to PATH"

    def test_dockerfile_non_root_user(self):
        """Test Dockerfile creates and uses non-root user"""
        dockerfile_path = PROJECT_ROOT / "Dockerfile"
        content = dockerfile_path.read_text()

        assert "useradd" in content, "Missing user creation"
        assert "USER appuser" in content, "Not switching to non-root user"
        assert "--chown=appuser:appuser" in content, \
            "Missing proper file ownership"

    def test_dockerfile_health_check(self):
        """Test Dockerfile includes health check"""
        dockerfile_path = PROJECT_ROOT / "Dockerfile"
        content = dockerfile_path.read_text()

        assert "HEALTHCHECK" in content, "Missing health check"
        assert "/api/health" in content, "Health check endpoint not configured"

    def test_dockerfile_exposes_port(self):
        """Test Dockerfile exposes correct port"""
        dockerfile_path = PROJECT_ROOT / "Dockerfile"
        content = dockerfile_path.read_text()

        assert "EXPOSE 8000" in content, "Port 8000 not exposed"

    def test_dockerfile_environment_variables(self):
        """Test Dockerfile sets proper environment variables"""
        dockerfile_path = PROJECT_ROOT / "Dockerfile"
        content = dockerfile_path.read_text()

        assert "PYTHONUNBUFFERED=1" in content, \
            "PYTHONUNBUFFERED not set"
        assert "PYTHONDONTWRITEBYTECODE=1" in content, \
            "PYTHONDONTWRITEBYTECODE not set"


class TestDockerCompose:
    """Test docker-compose.yml configuration"""

    def test_docker_compose_exists(self):
        """Test that docker-compose.yml exists"""
        compose_path = PROJECT_ROOT / "docker-compose.yml"
        assert compose_path.exists(), "docker-compose.yml not found"

    def test_docker_compose_valid_yaml(self):
        """Test docker-compose.yml is valid YAML"""
        compose_path = PROJECT_ROOT / "docker-compose.yml"
        with open(compose_path, 'r') as f:
            try:
                yaml.safe_load(f)
            except yaml.YAMLError as e:
                pytest.fail(f"Invalid YAML: {e}")

    def test_docker_compose_services(self):
        """Test docker-compose.yml defines required services"""
        compose_path = PROJECT_ROOT / "docker-compose.yml"
        with open(compose_path, 'r') as f:
            config = yaml.safe_load(f)

        services = config.get('services', {})
        required_services = ['redis', 'app', 'worker', 'beat']

        for service in required_services:
            assert service in services, f"Missing service: {service}"

    def test_docker_compose_redis_configuration(self):
        """Test Redis service configuration"""
        compose_path = PROJECT_ROOT / "docker-compose.yml"
        with open(compose_path, 'r') as f:
            config = yaml.safe_load(f)

        redis = config['services']['redis']
        assert redis['image'].startswith('redis:'), \
            "Redis image not configured"
        assert 'volumes' in redis, "Redis volumes not configured"
        assert 'healthcheck' in redis, "Redis health check missing"

    def test_docker_compose_app_configuration(self):
        """Test app service configuration"""
        compose_path = PROJECT_ROOT / "docker-compose.yml"
        with open(compose_path, 'r') as f:
            config = yaml.safe_load(f)

        app = config['services']['app']
        assert 'build' in app, "App build configuration missing"
        assert 'ports' in app, "App ports not exposed"
        assert 'environment' in app, "App environment variables missing"
        assert 'depends_on' in app, "App dependencies not configured"
        assert 'healthcheck' in app, "App health check missing"

    def test_docker_compose_worker_configuration(self):
        """Test Celery worker configuration"""
        compose_path = PROJECT_ROOT / "docker-compose.yml"
        with open(compose_path, 'r') as f:
            config = yaml.safe_load(f)

        worker = config['services']['worker']
        assert 'command' in worker, "Worker command missing"
        assert 'celery' in worker['command'], \
            "Worker not running Celery"
        assert 'depends_on' in worker, "Worker dependencies not configured"

    def test_docker_compose_beat_configuration(self):
        """Test Celery beat configuration"""
        compose_path = PROJECT_ROOT / "docker-compose.yml"
        with open(compose_path, 'r') as f:
            config = yaml.safe_load(f)

        beat = config['services']['beat']
        assert 'command' in beat, "Beat command missing"
        assert 'celery' in beat['command'], "Beat not running Celery"
        assert 'beat' in beat['command'], "Beat not configured as scheduler"

    def test_docker_compose_volumes(self):
        """Test volumes are defined for data persistence"""
        compose_path = PROJECT_ROOT / "docker-compose.yml"
        with open(compose_path, 'r') as f:
            config = yaml.safe_load(f)

        volumes = config.get('volumes', {})
        required_volumes = ['redis-data', 'app-data', 'app-logs']

        for volume in required_volumes:
            assert volume in volumes, f"Missing volume: {volume}"

    def test_docker_compose_networks(self):
        """Test custom network is defined"""
        compose_path = PROJECT_ROOT / "docker-compose.yml"
        with open(compose_path, 'r') as f:
            config = yaml.safe_load(f)

        networks = config.get('networks', {})
        assert 'code-review-network' in networks, \
            "Custom network not defined"

    def test_docker_compose_environment_variables(self):
        """Test environment variables are properly configured"""
        compose_path = PROJECT_ROOT / "docker-compose.yml"
        with open(compose_path, 'r') as f:
            config = yaml.safe_load(f)

        app_env = config['services']['app']['environment']

        # Check critical environment variables
        assert 'DATABASE_URL' in app_env, "DATABASE_URL not set"
        assert 'REDIS_URL' in app_env, "REDIS_URL not set"
        assert 'CELERY_BROKER_URL' in app_env, \
            "CELERY_BROKER_URL not set"

    def test_docker_compose_logging_configuration(self):
        """Test logging is configured for services"""
        compose_path = PROJECT_ROOT / "docker-compose.yml"
        with open(compose_path, 'r') as f:
            config = yaml.safe_load(f)

        for service_name in ['app', 'worker', 'beat']:
            service = config['services'][service_name]
            assert 'logging' in service, \
                f"{service_name} missing logging configuration"

            logging = service['logging']
            assert logging['driver'] == 'json-file', \
                f"{service_name} logging driver incorrect"
            assert 'max-size' in logging['options'], \
                f"{service_name} missing log rotation"


class TestDockerScripts:
    """Test Docker management scripts"""

    def test_start_script_exists(self):
        """Test start.sh script exists"""
        script_path = PROJECT_ROOT / "scripts" / "docker" / "start.sh"
        assert script_path.exists(), "start.sh not found"
        assert os.access(script_path, os.X_OK), "start.sh not executable"

    def test_stop_script_exists(self):
        """Test stop.sh script exists"""
        script_path = PROJECT_ROOT / "scripts" / "docker" / "stop.sh"
        assert script_path.exists(), "stop.sh not found"
        assert os.access(script_path, os.X_OK), "stop.sh not executable"

    def test_logs_script_exists(self):
        """Test logs.sh script exists"""
        script_path = PROJECT_ROOT / "scripts" / "docker" / "logs.sh"
        assert script_path.exists(), "logs.sh not found"
        assert os.access(script_path, os.X_OK), "logs.sh not executable"

    def test_reset_script_exists(self):
        """Test reset.sh script exists"""
        script_path = PROJECT_ROOT / "scripts" / "docker" / "reset.sh"
        assert script_path.exists(), "reset.sh not found"
        assert os.access(script_path, os.X_OK), "reset.sh not executable"

    def test_start_script_has_shebang(self):
        """Test scripts have proper shebang"""
        for script_name in ['start.sh', 'stop.sh', 'logs.sh', 'reset.sh']:
            script_path = PROJECT_ROOT / "scripts" / "docker" / script_name
            first_line = script_path.read_text().split('\n')[0]
            assert first_line.startswith('#!'), \
                f"{script_name} missing shebang"
            assert 'bash' in first_line, \
                f"{script_name} not a bash script"

    def test_start_script_handles_env_file(self):
        """Test start script handles .env file"""
        script_path = PROJECT_ROOT / "scripts" / "docker" / "start.sh"
        content = script_path.read_text()

        assert '.env' in content, "start.sh doesn't handle .env file"
        assert '.env.example' in content, \
            "start.sh doesn't fallback to .env.example"

    def test_reset_script_has_warning(self):
        """Test reset script warns about data loss"""
        script_path = PROJECT_ROOT / "scripts" / "docker" / "reset.sh"
        content = script_path.read_text()

        assert 'WARNING' in content or 'warning' in content.lower(), \
            "reset.sh missing warning"
        assert 'delete' in content.lower() or 'remove' in content.lower(), \
            "reset.sh doesn't warn about deletion"


class TestDockerignore:
    """Test .dockerignore configuration"""

    def test_dockerignore_exists(self):
        """Test .dockerignore file exists"""
        dockerignore_path = PROJECT_ROOT / ".dockerignore"
        assert dockerignore_path.exists(), ".dockerignore not found"

    def test_dockerignore_excludes_git(self):
        """Test .dockerignore excludes .git"""
        dockerignore_path = PROJECT_ROOT / ".dockerignore"
        content = dockerignore_path.read_text()

        assert '.git' in content, ".dockerignore doesn't exclude .git"

    def test_dockerignore_excludes_pycache(self):
        """Test .dockerignore excludes __pycache__"""
        dockerignore_path = PROJECT_ROOT / ".dockerignore"
        content = dockerignore_path.read_text()

        assert '__pycache__' in content, \
            ".dockerignore doesn't exclude __pycache__"

    def test_dockerignore_excludes_data(self):
        """Test .dockerignore excludes data directories"""
        dockerignore_path = PROJECT_ROOT / ".dockerignore"
        content = dockerignore_path.read_text()

        assert 'data/' in content or '*.db' in content, \
            ".dockerignore doesn't exclude data files"

    def test_dockerignore_excludes_env(self):
        """Test .dockerignore excludes .env files"""
        dockerignore_path = PROJECT_ROOT / ".dockerignore"
        content = dockerignore_path.read_text()

        assert '.env' in content, ".dockerignore doesn't exclude .env"


class TestProductionReadiness:
    """Test production-ready configurations"""

    def test_dockerfile_minimal_layers(self):
        """Test Dockerfile minimizes layers"""
        dockerfile_path = PROJECT_ROOT / "Dockerfile"
        content = dockerfile_path.read_text()

        # Count RUN commands (should be optimized with &&)
        run_count = len(re.findall(r'^RUN ', content, re.MULTILINE))
        assert run_count < 10, \
            "Too many RUN layers, consider combining with &&"

    def test_dockerfile_cleanup_apt_cache(self):
        """Test Dockerfile cleans up apt cache"""
        dockerfile_path = PROJECT_ROOT / "Dockerfile"
        content = dockerfile_path.read_text()

        if 'apt-get install' in content:
            assert 'rm -rf /var/lib/apt/lists/*' in content, \
                "Dockerfile doesn't clean up apt cache"

    def test_dockerfile_no_cache_pip(self):
        """Test Dockerfile uses --no-cache-dir for pip"""
        dockerfile_path = PROJECT_ROOT / "Dockerfile"
        content = dockerfile_path.read_text()

        pip_installs = re.findall(r'pip install.*', content)
        for pip_cmd in pip_installs:
            assert '--no-cache-dir' in pip_cmd, \
                f"pip install missing --no-cache-dir: {pip_cmd}"

    def test_docker_compose_restart_policy(self):
        """Test services have restart policies"""
        compose_path = PROJECT_ROOT / "docker-compose.yml"
        with open(compose_path, 'r') as f:
            config = yaml.safe_load(f)

        for service_name in ['redis', 'app', 'worker', 'beat']:
            service = config['services'][service_name]
            assert 'restart' in service, \
                f"{service_name} missing restart policy"

    def test_docker_compose_health_checks(self):
        """Test critical services have health checks"""
        compose_path = PROJECT_ROOT / "docker-compose.yml"
        with open(compose_path, 'r') as f:
            config = yaml.safe_load(f)

        for service_name in ['redis', 'app']:
            service = config['services'][service_name]
            assert 'healthcheck' in service, \
                f"{service_name} missing health check"
