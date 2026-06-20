# Deployment Guide - AI Code Review Assistant

**Version**: 0.1.0
**Status**: Production-Ready

This guide covers deployment of the AI Code Review Assistant in production environments.

## Table of Contents

1. [Prerequisites](#prerequisites)
2. [Docker Compose Deployment (Recommended)](#docker-compose-deployment-recommended)
3. [Manual Docker Deployment](#manual-docker-deployment)
4. [Traditional Deployment](#traditional-deployment)
5. [Environment Configuration](#environment-configuration)
6. [Database Setup](#database-setup)
7. [Health Checks & Monitoring](#health-checks--monitoring)
8. [Security Considerations](#security-considerations)
9. [Scaling & Performance](#scaling--performance)
10. [Troubleshooting](#troubleshooting)

## Prerequisites

### Required
- Docker 20.10+ and Docker Compose 2.0+ (for Docker deployment)
- Python 3.10+ (for traditional deployment)
- Redis 6.0+ (for caching and Celery)
- Git 2.30+

### Optional
- PostgreSQL 13+ (recommended for production, SQLite works for small deployments)
- Nginx or Caddy (for reverse proxy)
- SSL certificates (Let's Encrypt recommended)

## Docker Compose Deployment (Recommended)

This is the easiest way to deploy all services together.

### Step 1: Clone Repository

```bash
cd /opt
git clone https://github.com/yourusername/ai-experiments-hub.git
cd ai-experiments-hub/python-projects/13-code-review-assistant
```

### Step 2: Configure Environment

```bash
cp .env.example .env
nano .env
```

**Minimal Production Configuration**:
```env
# Server
HOST=0.0.0.0
PORT=8000
ALLOWED_ORIGINS=https://yourapp.com

# Database (PostgreSQL recommended)
DATABASE_URL=postgresql://reviewer:your_strong_password@postgres:5432/codereviewer

# Authentication
SESSION_TTL_DAYS=30
COOKIE_SECURE=true

# GitHub Integration
GITHUB_TOKEN=ghp_your_production_token_here
GITHUB_WEBHOOK_SECRET=your_webhook_secret

# LLM (Choose one)
ANTHROPIC_API_KEY=sk-ant-your_key
# OR
OPENAI_API_KEY=sk-your_key
# OR
OLLAMA_API_URL=http://host.docker.internal:11434
OLLAMA_MODEL=llama3.2

# Celery/Redis
CELERY_BROKER_URL=redis://redis:6379/0
CELERY_RESULT_BACKEND=redis://redis:6379/1
REDIS_URL=redis://redis:6379/2
```

### Step 3: Update docker-compose.yml

Uncomment PostgreSQL configuration if using PostgreSQL:

```yaml
# In docker-compose.yml
services:
  postgres:
    # Uncomment this entire section

  app:
    environment:
      # Comment out SQLite line
      # DATABASE_URL: sqlite:///./data/database.db
      # Uncomment PostgreSQL line
      DATABASE_URL: postgresql://reviewer:${POSTGRES_PASSWORD:-changeme}@postgres:5432/codereviewer
    depends_on:
      redis:
        condition: service_healthy
      postgres:  # Uncomment this
        condition: service_healthy

  worker:
    environment:
      # Same as app
      DATABASE_URL: postgresql://reviewer:${POSTGRES_PASSWORD:-changeme}@postgres:5432/codereviewer
    depends_on:
      redis:
        condition: service_healthy
      postgres:  # Uncomment this
        condition: service_healthy
```

### Step 4: Build and Deploy

```bash
# Build images
docker-compose build

# Start all services
docker-compose up -d

# View logs
docker-compose logs -f app

# Check status
docker-compose ps
```

### Step 5: Verify Deployment

```bash
# Test health endpoints
curl http://localhost:8000/health
curl http://localhost:8000/api/health/db
curl http://localhost:8000/api/health/celery
curl http://localhost:8000/api/health/redis

# Create admin user
docker-compose exec app python -c "
from src.core.database import DatabaseManager
from src.core.auth_manager import AuthManager
db_manager = DatabaseManager()
with db_manager.get_session() as db:
    auth = AuthManager(db)
    success, user, error = auth.register_user('admin', 'admin@yourapp.com', 'your_secure_password', is_admin=True)
    print(f'Admin created: {success}')
"

# Access application
open http://localhost:8000
```

### Step 6: Set Up Reverse Proxy (Nginx Example)

```nginx
# /etc/nginx/sites-available/code-review
server {
    listen 80;
    server_name yourapp.com;

    # Redirect to HTTPS
    return 301 https://$server_name$request_uri;
}

server {
    listen 443 ssl http2;
    server_name yourapp.com;

    # SSL Configuration
    ssl_certificate /etc/letsencrypt/live/yourapp.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/yourapp.com/privkey.pem;

    # Security headers
    add_header X-Frame-Options "SAMEORIGIN" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-XSS-Protection "1; mode=block" always;

    # Proxy to FastAPI
    location / {
        proxy_pass http://localhost:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # WebSocket support (for SSE)
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
    }

    # Static files (optional caching)
    location /static {
        proxy_pass http://localhost:8000/static;
        expires 30d;
        add_header Cache-Control "public, immutable";
    }
}
```

Enable and restart Nginx:

```bash
sudo ln -s /etc/nginx/sites-available/code-review /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl restart nginx
```

## Manual Docker Deployment

For more control over individual components.

### Build Image

```bash
docker build -t code-review-assistant:latest .
```

### Run Redis

```bash
docker run -d \
  --name code-review-redis \
  --restart unless-stopped \
  -p 6379:6379 \
  -v code-review-redis-data:/data \
  redis:7-alpine redis-server --appendonly yes
```

### Run PostgreSQL

```bash
docker run -d \
  --name code-review-postgres \
  --restart unless-stopped \
  -p 5432:5432 \
  -e POSTGRES_DB=codereviewer \
  -e POSTGRES_USER=reviewer \
  -e POSTGRES_PASSWORD=your_strong_password \
  -v code-review-postgres-data:/var/lib/postgresql/data \
  postgres:15-alpine
```

### Run Application

```bash
docker run -d \
  --name code-review-app \
  --restart unless-stopped \
  -p 8000:8000 \
  --link code-review-redis:redis \
  --link code-review-postgres:postgres \
  -e DATABASE_URL=postgresql://reviewer:your_strong_password@postgres:5432/codereviewer \
  -e REDIS_URL=redis://redis:6379/2 \
  -e CELERY_BROKER_URL=redis://redis:6379/0 \
  -e CELERY_RESULT_BACKEND=redis://redis:6379/1 \
  -e GITHUB_TOKEN=ghp_your_token \
  -e ANTHROPIC_API_KEY=sk-ant-your_key \
  -v code-review-app-data:/app/data \
  code-review-assistant:latest
```

### Run Celery Worker

```bash
docker run -d \
  --name code-review-worker \
  --restart unless-stopped \
  --link code-review-redis:redis \
  --link code-review-postgres:postgres \
  -e DATABASE_URL=postgresql://reviewer:your_strong_password@postgres:5432/codereviewer \
  -e REDIS_URL=redis://redis:6379/2 \
  -e CELERY_BROKER_URL=redis://redis:6379/0 \
  -e CELERY_RESULT_BACKEND=redis://redis:6379/1 \
  -e GITHUB_TOKEN=ghp_your_token \
  -e ANTHROPIC_API_KEY=sk-ant-your_key \
  -v code-review-app-data:/app/data \
  code-review-assistant:latest \
  celery -A celery_app worker --loglevel=info --concurrency=2
```

## Traditional Deployment

Without Docker (Ubuntu/Debian example).

### Step 1: System Dependencies

```bash
sudo apt update
sudo apt install -y python3.10 python3.10-venv python3-pip git redis-server postgresql postgresql-contrib nginx
```

### Step 2: Create Application User

```bash
sudo useradd -r -m -s /bin/bash codereview
sudo su - codereview
```

### Step 3: Clone and Setup

```bash
cd /opt
git clone https://github.com/yourusername/ai-experiments-hub.git
cd ai-experiments-hub/python-projects/13-code-review-assistant

python3.10 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### Step 4: Configure Environment

```bash
cp .env.example .env
nano .env
```

### Step 5: Setup PostgreSQL

```bash
sudo -u postgres psql

CREATE DATABASE codereviewer;
CREATE USER reviewer WITH PASSWORD 'your_strong_password';
GRANT ALL PRIVILEGES ON DATABASE codereviewer TO reviewer;
\q
```

### Step 6: Create Systemd Services

**FastAPI Service** (`/etc/systemd/system/code-review-app.service`):

```ini
[Unit]
Description=AI Code Review Assistant
After=network.target postgresql.service redis.service

[Service]
Type=simple
User=codereview
WorkingDirectory=/opt/ai-experiments-hub/python-projects/13-code-review-assistant
Environment="PATH=/opt/ai-experiments-hub/python-projects/13-code-review-assistant/venv/bin"
ExecStart=/opt/ai-experiments-hub/python-projects/13-code-review-assistant/venv/bin/python server.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

**Celery Worker Service** (`/etc/systemd/system/code-review-worker.service`):

```ini
[Unit]
Description=Code Review Celery Worker
After=network.target redis.service

[Service]
Type=simple
User=codereview
WorkingDirectory=/opt/ai-experiments-hub/python-projects/13-code-review-assistant
Environment="PATH=/opt/ai-experiments-hub/python-projects/13-code-review-assistant/venv/bin"
ExecStart=/opt/ai-experiments-hub/python-projects/13-code-review-assistant/venv/bin/celery -A celery_app worker --loglevel=info
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

### Step 7: Enable and Start Services

```bash
sudo systemctl daemon-reload
sudo systemctl enable code-review-app code-review-worker
sudo systemctl start code-review-app code-review-worker

# Check status
sudo systemctl status code-review-app
sudo systemctl status code-review-worker
```

## Environment Configuration

### Required Variables

| Variable | Description | Example |
|----------|-------------|---------|
| `DATABASE_URL` | Database connection string | `postgresql://user:pass@localhost/db` |
| `REDIS_URL` | Redis connection string | `redis://localhost:6379/2` |
| `CELERY_BROKER_URL` | Celery broker URL | `redis://localhost:6379/0` |
| `CELERY_RESULT_BACKEND` | Celery results backend | `redis://localhost:6379/1` |

### Optional Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `HOST` | `0.0.0.0` | Server bind address |
| `PORT` | `8000` | Server port |
| `ALLOWED_ORIGINS` | `http://localhost:8000` | CORS origins |
| `SESSION_TTL_DAYS` | `30` | Session expiration |
| `COOKIE_SECURE` | `false` | Secure cookies (HTTPS) |
| `GITHUB_TOKEN` | - | GitHub API token |
| `ANTHROPIC_API_KEY` | - | Anthropic API key |
| `OPENAI_API_KEY` | - | OpenAI API key |
| `OLLAMA_API_URL` | `http://localhost:11434` | Ollama URL |
| `COMPLEXITY_THRESHOLD_WARN` | `10` | Complexity warning threshold |
| `COMPLEXITY_THRESHOLD_ERROR` | `15` | Complexity error threshold |

## Database Setup

### PostgreSQL (Recommended)

**Advantages**:
- Better performance for concurrent users
- Full ACID compliance
- Advanced indexing and query optimization
- Production-ready

**Connection String**:
```env
DATABASE_URL=postgresql://reviewer:password@localhost:5432/codereviewer
```

### SQLite (Development/Small Deployments)

**Advantages**:
- Zero configuration
- Single file database
- Good for low-traffic deployments

**Connection String**:
```env
DATABASE_URL=sqlite:///./data/database.db
```

### Database Migrations

The application auto-creates tables on first run. For manual migrations:

```bash
# Install Alembic (if not in requirements.txt)
pip install alembic

# Initialize Alembic
alembic init alembic

# Generate migration
alembic revision --autogenerate -m "Initial migration"

# Apply migration
alembic upgrade head
```

## Health Checks & Monitoring

### Health Check Endpoints

| Endpoint | Purpose | Response Codes |
|----------|---------|----------------|
| `GET /health` | Overall health | 200 = healthy |
| `GET /api/health/db` | Database connectivity | 200/503 |
| `GET /api/health/celery` | Celery worker status | 200/503 |
| `GET /api/health/redis` | Redis connectivity | 200/503 |

### Monitoring with Docker

Docker Compose includes health checks:

```bash
# Check service health
docker-compose ps

# View health check logs
docker inspect code-review-app | jq '.[0].State.Health'
```

### Monitoring with Systemd

```bash
# Check service status
systemctl status code-review-app
systemctl status code-review-worker

# View logs
journalctl -u code-review-app -f
journalctl -u code-review-worker -f
```

### Application Logs

Structured logs are available via the logging API:

```bash
# Get recent logs
curl http://localhost:8000/api/logs?limit=100

# Get errors only
curl http://localhost:8000/api/logs/errors

# Get statistics
curl http://localhost:8000/api/logs/statistics
```

### Monitoring Metrics

Key metrics to monitor:
- Health check endpoint response times
- Celery queue length: `celery -A celery_app inspect active`
- Redis memory usage: `redis-cli info memory`
- Database connection pool: Check PostgreSQL `pg_stat_activity`
- Cache hit rate: `GET /api/analytics/cache-stats`

## Security Considerations

### 1. Change Default Credentials

```bash
# Change admin password immediately after deployment
docker-compose exec app python -c "
from src.core.database import DatabaseManager
from src.core.auth_manager import AuthManager
db_manager = DatabaseManager()
with db_manager.get_session() as db:
    auth = AuthManager(db)
    # Update admin password
"
```

### 2. Use Strong Passwords

Generate secure passwords:

```bash
openssl rand -base64 32
```

### 3. Enable HTTPS

Always use HTTPS in production:
- Set `COOKIE_SECURE=true` in .env
- Use Let's Encrypt for free SSL certificates
- Configure reverse proxy (Nginx/Caddy) for SSL termination

### 4. Secure GitHub Tokens

- Use environment variables, never hardcode
- Use repository-scoped tokens (not personal access tokens)
- Rotate tokens regularly
- Enable webhook secrets for GitHub integration

### 5. Database Security

- Use strong database passwords
- Restrict database access to localhost or private network
- Enable SSL connections for PostgreSQL
- Regular backups

### 6. Network Security

```bash
# Firewall rules (UFW example)
sudo ufw allow 22/tcp    # SSH
sudo ufw allow 80/tcp    # HTTP
sudo ufw allow 443/tcp   # HTTPS
sudo ufw enable

# Block direct access to Redis/PostgreSQL from outside
sudo ufw deny 6379/tcp
sudo ufw deny 5432/tcp
```

## Scaling & Performance

### Horizontal Scaling

**Multiple Celery Workers**:

```bash
# Run 4 worker instances
docker-compose up -d --scale worker=4
```

**Load Balancing FastAPI**:

```nginx
# Nginx upstream
upstream code_review_backend {
    server localhost:8000;
    server localhost:8001;
    server localhost:8002;
}

server {
    location / {
        proxy_pass http://code_review_backend;
    }
}
```

### Vertical Scaling

**Increase Celery Concurrency**:

```bash
# In docker-compose.yml
worker:
  command: celery -A celery_app worker --loglevel=info --concurrency=8
```

**Increase Database Connections**:

```python
# In database.py
engine = create_engine(
    database_url,
    pool_size=20,        # Default: 5
    max_overflow=40      # Default: 10
)
```

### Performance Tuning

**Redis Configuration** (`redis.conf`):

```conf
maxmemory 2gb
maxmemory-policy allkeys-lru
save 900 1
save 300 10
```

**PostgreSQL Tuning** (`postgresql.conf`):

```conf
shared_buffers = 256MB
effective_cache_size = 1GB
work_mem = 16MB
maintenance_work_mem = 128MB
```

## Troubleshooting

### Application Won't Start

**Check logs**:
```bash
docker-compose logs app
# OR
journalctl -u code-review-app -n 100
```

**Common issues**:
- Database connection failed: Verify DATABASE_URL
- Redis connection failed: Ensure Redis is running
- Port already in use: Change PORT in .env

### Celery Workers Not Processing

**Check worker status**:
```bash
celery -A celery_app inspect active
celery -A celery_app inspect stats
```

**Common issues**:
- Redis not accessible: Check CELERY_BROKER_URL
- Worker not running: Check systemd/docker status
- Tasks stuck: Restart worker

### Database Errors

**SQLite locked**:
- Switch to PostgreSQL for production
- Reduce concurrent connections

**PostgreSQL connection pool exhausted**:
- Increase `pool_size` and `max_overflow`
- Check for connection leaks

### High Memory Usage

**Redis memory**:
```bash
redis-cli info memory
# Clear cache if needed
redis-cli FLUSHDB
```

**Python memory leaks**:
- Restart workers periodically
- Monitor with `docker stats`

### GitHub API Rate Limits

**Check rate limit**:
```bash
curl -H "Authorization: token YOUR_TOKEN" https://api.github.com/rate_limit
```

**Solutions**:
- Use authenticated token (higher limits)
- Implement caching for GitHub API responses
- Use webhooks instead of polling

## Backup & Recovery

### Database Backup

**PostgreSQL**:
```bash
# Backup
docker-compose exec postgres pg_dump -U reviewer codereviewer > backup.sql

# Restore
docker-compose exec -T postgres psql -U reviewer codereviewer < backup.sql
```

**SQLite**:
```bash
# Backup
docker-compose exec app cp /app/data/database.db /app/data/backup.db

# Restore
docker-compose exec app cp /app/data/backup.db /app/data/database.db
```

### Automated Backups

**Cron job**:
```bash
# Add to crontab
0 2 * * * /opt/scripts/backup-code-review.sh

# backup-code-review.sh
#!/bin/bash
DATE=$(date +%Y%m%d)
docker-compose exec postgres pg_dump -U reviewer codereviewer | gzip > /backups/codereviewer-$DATE.sql.gz
find /backups -name "codereviewer-*.sql.gz" -mtime +30 -delete
```

## Production Checklist

- [ ] Changed default admin password
- [ ] Set strong DATABASE_URL password
- [ ] Configured HTTPS/SSL certificates
- [ ] Set `COOKIE_SECURE=true`
- [ ] Configured `ALLOWED_ORIGINS` correctly
- [ ] Set up reverse proxy (Nginx/Caddy)
- [ ] Enabled firewall rules
- [ ] Configured automated backups
- [ ] Set up monitoring/health checks
- [ ] Configured log rotation
- [ ] Tested disaster recovery procedures
- [ ] Documented runbook for operations team
- [ ] Load tested with expected traffic
- [ ] Reviewed and secured GitHub tokens
- [ ] Set up alerting for critical errors

## Support

For issues or questions:
- GitHub Issues: https://github.com/yourusername/ai-experiments-hub/issues
- Documentation: See README.md
- Logs: Check structured logs via `/api/logs`

---

**Last Updated**: Week 4 Completion
**Deployment Version**: 0.1.0
