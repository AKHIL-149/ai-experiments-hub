# Deployment Guide

Complete guide for deploying the AI Code Review & Refactoring Assistant to production environments.

## Table of Contents

- [Prerequisites](#prerequisites)
- [Deployment Options](#deployment-options)
- [Local Development Deployment](#local-development-deployment)
- [Docker Deployment](#docker-deployment)
- [Production Deployment](#production-deployment)
- [Cloud Deployments](#cloud-deployments)
- [Post-Deployment Configuration](#post-deployment-configuration)
- [Monitoring & Maintenance](#monitoring--maintenance)
- [Scaling](#scaling)
- [Troubleshooting](#troubleshooting)

## Prerequisites

### Required Software

- **Python**: 3.10 or higher
- **Redis**: 6.0 or higher (for caching and Celery)
- **PostgreSQL**: 13 or higher (recommended for production) or SQLite (development)
- **Git**: 2.30 or higher
- **Docker**: 20.10 or higher (for Docker deployment)
- **Docker Compose**: 1.29 or higher (for Docker deployment)

### Required Credentials

- **GitHub Token**: Personal access token or GitHub App credentials
  - Scopes needed: `repo`, `read:org`, `workflow`
- **LLM Provider** (Optional):
  - Ollama API URL (local)
  - Anthropic API key
  - OpenAI API key

### System Requirements

**Minimum Requirements:**
- CPU: 2 cores
- RAM: 4 GB
- Storage: 10 GB
- Network: 10 Mbps

**Recommended for Production:**
- CPU: 4+ cores
- RAM: 8+ GB
- Storage: 50+ GB SSD
- Network: 100 Mbps

## Deployment Options

### 1. Local Development
- Quick setup for development and testing
- Uses SQLite database
- Single process (no Celery workers)
- Suitable for: Local development, testing

### 2. Docker Compose
- Complete stack with all services
- Redis, PostgreSQL, Celery workers included
- Easy to manage and scale
- Suitable for: Development, staging, small production

### 3. Production Deployment
- Manual deployment with separate services
- Full control over configuration
- Suitable for: Production environments, large scale

### 4. Cloud Deployment
- Managed services (AWS, GCP, Azure)
- Auto-scaling and high availability
- Suitable for: Enterprise production, high traffic

## Local Development Deployment

### Step 1: Clone Repository

```bash
git clone https://github.com/your-org/ai-code-review-assistant.git
cd ai-code-review-assistant/python-projects/13-code-review-assistant
```

### Step 2: Create Virtual Environment

```bash
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

### Step 3: Install Dependencies

```bash
pip install --upgrade pip
pip install -r requirements.txt
```

### Step 4: Configure Environment

```bash
cp .env.example .env
```

Edit `.env` with your configuration:

```env
# Server
HOST=0.0.0.0
PORT=8000
ALLOWED_ORIGINS=http://localhost:8000

# Database (SQLite for development)
DATABASE_URL=sqlite:///./data/database.db

# Redis (optional for development)
REDIS_URL=redis://localhost:6379/0

# GitHub
GITHUB_TOKEN=ghp_your_token_here

# LLM (optional)
OLLAMA_API_URL=http://localhost:11434
OLLAMA_MODEL=llama3.2
```

### Step 5: Initialize Database

```bash
python -c "from src.core.database import init_db; init_db()"
```

### Step 6: Start Application

```bash
# Start FastAPI server
python server.py

# In another terminal (optional - for async tasks):
celery -A celery_app worker --loglevel=info
```

Access the application at: http://localhost:8000

## Docker Deployment

### Quick Start

```bash
# 1. Clone repository
git clone https://github.com/your-org/ai-code-review-assistant.git
cd ai-code-review-assistant/python-projects/13-code-review-assistant

# 2. Configure environment
cp .env.example .env
# Edit .env with your configuration

# 3. Start all services
docker-compose up -d

# 4. View logs
docker-compose logs -f app

# 5. Check status
docker-compose ps
```

### Docker Compose Services

The `docker-compose.yml` includes:

1. **redis** - Message broker and cache (port 6379)
2. **postgres** - PostgreSQL database (port 5432)
3. **app** - FastAPI application (port 8000)
4. **worker** - Celery worker for async tasks
5. **beat** - Celery beat for scheduled tasks
6. **flower** - Celery monitoring (port 5555, optional)

### Docker Commands

```bash
# Start services
docker-compose up -d

# Stop services
docker-compose down

# View logs
docker-compose logs -f [service_name]

# Restart specific service
docker-compose restart app

# Scale workers
docker-compose up -d --scale worker=3

# Access shell in container
docker-compose exec app bash

# View Celery tasks (Flower)
docker-compose --profile monitoring up -d flower
# Access at http://localhost:5555
```

### Docker Environment Variables

Key environment variables for Docker deployment:

```env
# PostgreSQL
POSTGRES_DB=codereviewer
POSTGRES_USER=reviewer
POSTGRES_PASSWORD=secure_password_here
POSTGRES_PORT=5432

# Redis
REDIS_PORT=6379

# Application
APP_PORT=8000
DATABASE_URL=postgresql://reviewer:secure_password_here@postgres:5432/codereviewer
REDIS_URL=redis://redis:6379/0
CELERY_BROKER_URL=redis://redis:6379/1
CELERY_RESULT_BACKEND=redis://redis:6379/2

# Celery
CELERY_LOG_LEVEL=info
CELERY_WORKERS=4

# Flower (monitoring)
FLOWER_PORT=5555
```

### Docker Data Persistence

Data is persisted in Docker volumes:

- `redis-data` - Redis data
- `postgres-data` - PostgreSQL database
- `app-data` - Application data (repositories, analysis results)
- `app-logs` - Application logs

To backup volumes:

```bash
# Backup PostgreSQL
docker-compose exec postgres pg_dump -U reviewer codereviewer > backup.sql

# Backup application data
docker-compose exec app tar czf /tmp/app-data.tar.gz /app/data
docker-compose cp app:/tmp/app-data.tar.gz ./app-data-backup.tar.gz
```

## Production Deployment

### Architecture Overview

```
                                  ┌─────────────┐
                                  │   Nginx     │
                                  │ (Reverse    │
                                  │  Proxy)     │
                                  └──────┬──────┘
                                         │
                    ┌────────────────────┼────────────────────┐
                    │                    │                    │
              ┌─────▼─────┐        ┌────▼─────┐       ┌─────▼─────┐
              │  FastAPI  │        │ FastAPI  │       │ FastAPI   │
              │  Instance │        │ Instance │       │ Instance  │
              │     #1    │        │    #2    │       │    #3     │
              └─────┬─────┘        └────┬─────┘       └─────┬─────┘
                    │                   │                    │
                    └───────────────────┼────────────────────┘
                                        │
                    ┌───────────────────┼────────────────────┐
                    │                   │                    │
              ┌─────▼─────┐       ┌────▼─────┐        ┌────▼──────┐
              │PostgreSQL │       │  Redis   │        │  Celery   │
              │  Primary  │       │  Cache   │        │  Workers  │
              └───────────┘       └──────────┘        ��───────────┘
```

### Step 1: Provision Server

**Cloud Provider Options:**

- **AWS**: EC2 t3.large or larger
- **GCP**: n1-standard-2 or larger
- **Azure**: Standard_D2s_v3 or larger
- **DigitalOcean**: 4GB Droplet or larger

**OS Recommendation**: Ubuntu 22.04 LTS

### Step 2: Install Dependencies

```bash
# Update system
sudo apt-get update && sudo apt-get upgrade -y

# Install Python 3.10+
sudo apt-get install -y python3.10 python3.10-venv python3-pip

# Install PostgreSQL
sudo apt-get install -y postgresql postgresql-contrib

# Install Redis
sudo apt-get install -y redis-server

# Install Nginx
sudo apt-get install -y nginx

# Install Git
sudo apt-get install -y git

# Install system dependencies
sudo apt-get install -y build-essential libpq-dev
```

### Step 3: Configure PostgreSQL

```bash
# Switch to postgres user
sudo -u postgres psql

# Create database and user
CREATE DATABASE codereviewer;
CREATE USER reviewer WITH PASSWORD 'your_secure_password';
GRANT ALL PRIVILEGES ON DATABASE codereviewer TO reviewer;
\q

# Configure PostgreSQL for remote access (if needed)
sudo nano /etc/postgresql/13/main/postgresql.conf
# Set: listen_addresses = '*'

sudo nano /etc/postgresql/13/main/pg_hba.conf
# Add: host all all 0.0.0.0/0 md5

sudo systemctl restart postgresql
```

### Step 4: Configure Redis

```bash
# Edit Redis config
sudo nano /etc/redis/redis.conf

# Set password
requirepass your_redis_password

# Set max memory
maxmemory 256mb
maxmemory-policy allkeys-lru

# Restart Redis
sudo systemctl restart redis-server
sudo systemctl enable redis-server
```

### Step 5: Deploy Application

```bash
# Create application user
sudo useradd -m -s /bin/bash codereviewer
sudo su - codereviewer

# Clone repository
git clone https://github.com/your-org/ai-code-review-assistant.git
cd ai-code-review-assistant/python-projects/13-code-review-assistant

# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install --upgrade pip
pip install -r requirements.txt

# Configure environment
cp .env.example .env
nano .env  # Edit with production values

# Initialize database
python -c "from src.core.database import init_db; init_db()"
```

### Step 6: Configure Systemd Services

**FastAPI Service** (`/etc/systemd/system/codereviewer-api.service`):

```ini
[Unit]
Description=AI Code Review FastAPI Application
After=network.target postgresql.service redis.service

[Service]
Type=simple
User=codereviewer
WorkingDirectory=/home/codereviewer/ai-code-review-assistant/python-projects/13-code-review-assistant
Environment="PATH=/home/codereviewer/ai-code-review-assistant/python-projects/13-code-review-assistant/venv/bin"
ExecStart=/home/codereviewer/ai-code-review-assistant/python-projects/13-code-review-assistant/venv/bin/uvicorn server:app --host 0.0.0.0 --port 8000 --workers 4
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

**Celery Worker Service** (`/etc/systemd/system/codereviewer-worker.service`):

```ini
[Unit]
Description=AI Code Review Celery Worker
After=network.target redis.service

[Service]
Type=simple
User=codereviewer
WorkingDirectory=/home/codereviewer/ai-code-review-assistant/python-projects/13-code-review-assistant
Environment="PATH=/home/codereviewer/ai-code-review-assistant/python-projects/13-code-review-assistant/venv/bin"
ExecStart=/home/codereviewer/ai-code-review-assistant/python-projects/13-code-review-assistant/venv/bin/celery -A celery_app worker --loglevel=info --concurrency=4
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

**Celery Beat Service** (`/etc/systemd/system/codereviewer-beat.service`):

```ini
[Unit]
Description=AI Code Review Celery Beat
After=network.target redis.service

[Service]
Type=simple
User=codereviewer
WorkingDirectory=/home/codereviewer/ai-code-review-assistant/python-projects/13-code-review-assistant
Environment="PATH=/home/codereviewer/ai-code-review-assistant/python-projects/13-code-review-assistant/venv/bin"
ExecStart=/home/codereviewer/ai-code-review-assistant/python-projects/13-code-review-assistant/venv/bin/celery -A celery_app beat --loglevel=info
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

Enable and start services:

```bash
sudo systemctl daemon-reload
sudo systemctl enable codereviewer-api codereviewer-worker codereviewer-beat
sudo systemctl start codereviewer-api codereviewer-worker codereviewer-beat

# Check status
sudo systemctl status codereviewer-api
sudo systemctl status codereviewer-worker
sudo systemctl status codereviewer-beat
```

### Step 7: Configure Nginx

Create Nginx configuration (`/etc/nginx/sites-available/codereviewer`):

```nginx
upstream codereviewer_app {
    server 127.0.0.1:8000;
    # Add more servers for load balancing:
    # server 127.0.0.1:8001;
    # server 127.0.0.1:8002;
}

server {
    listen 80;
    server_name your-domain.com;

    # Redirect HTTP to HTTPS
    return 301 https://$server_name$request_uri;
}

server {
    listen 443 ssl http2;
    server_name your-domain.com;

    # SSL certificates (use Let's Encrypt)
    ssl_certificate /etc/letsencrypt/live/your-domain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/your-domain.com/privkey.pem;

    # SSL configuration
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers HIGH:!aNULL:!MD5;
    ssl_prefer_server_ciphers on;

    # Security headers
    add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-Frame-Options "DENY" always;
    add_header X-XSS-Protection "1; mode=block" always;

    # Client max body size (for file uploads)
    client_max_body_size 100M;

    # Logging
    access_log /var/log/nginx/codereviewer-access.log;
    error_log /var/log/nginx/codereviewer-error.log;

    # Static files
    location /static/ {
        alias /home/codereviewer/ai-code-review-assistant/python-projects/13-code-review-assistant/static/;
        expires 30d;
        add_header Cache-Control "public, immutable";
    }

    # API and application
    location / {
        proxy_pass http://codereviewer_app;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # WebSocket support (for SSE)
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";

        # Timeouts
        proxy_connect_timeout 60s;
        proxy_send_timeout 60s;
        proxy_read_timeout 300s;  # 5 minutes for long-running analysis
    }
}
```

Enable site and restart Nginx:

```bash
sudo ln -s /etc/nginx/sites-available/codereviewer /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl restart nginx
```

### Step 8: Configure SSL (Let's Encrypt)

```bash
# Install certbot
sudo apt-get install -y certbot python3-certbot-nginx

# Obtain certificate
sudo certbot --nginx -d your-domain.com

# Auto-renewal is configured automatically
# Test renewal:
sudo certbot renew --dry-run
```

## Cloud Deployments

### AWS Deployment

**Using Elastic Beanstalk:**

1. Install EB CLI:
```bash
pip install awsebcli
```

2. Initialize EB application:
```bash
eb init -p python-3.10 code-reviewer
```

3. Create environment:
```bash
eb create production-env \
  --instance-type t3.medium \
  --database.engine postgres \
  --database.size 20 \
  --database.instance db.t3.micro
```

4. Deploy:
```bash
eb deploy
```

**Using ECS (Docker):**

1. Build and push Docker image:
```bash
aws ecr create-repository --repository-name code-reviewer
docker build -t code-reviewer .
docker tag code-reviewer:latest <account-id>.dkr.ecr.<region>.amazonaws.com/code-reviewer:latest
docker push <account-id>.dkr.ecr.<region>.amazonaws.com/code-reviewer:latest
```

2. Create ECS task definition and service (use AWS Console or CLI)

3. Configure Application Load Balancer

### GCP Deployment

**Using Cloud Run:**

```bash
# Build container
gcloud builds submit --tag gcr.io/PROJECT-ID/code-reviewer

# Deploy to Cloud Run
gcloud run deploy code-reviewer \
  --image gcr.io/PROJECT-ID/code-reviewer \
  --platform managed \
  --region us-central1 \
  --allow-unauthenticated \
  --memory 2Gi \
  --cpu 2
```

### Azure Deployment

**Using App Service:**

```bash
# Create resource group
az group create --name code-reviewer-rg --location eastus

# Create App Service plan
az appservice plan create \
  --name code-reviewer-plan \
  --resource-group code-reviewer-rg \
  --sku B2 \
  --is-linux

# Create web app
az webapp create \
  --resource-group code-reviewer-rg \
  --plan code-reviewer-plan \
  --name code-reviewer-app \
  --runtime "PYTHON|3.10"

# Deploy code
az webapp up \
  --resource-group code-reviewer-rg \
  --name code-reviewer-app
```

## Post-Deployment Configuration

### 1. Create Admin User

```bash
python -c "
from src.core.database import SessionLocal
from src.core.auth_manager import AuthManager

db = SessionLocal()
auth = AuthManager(db)
auth.register_user('admin', 'admin@example.com', 'secure_password', role='ADMIN')
db.close()
"
```

### 2. Configure GitHub Webhook

1. Go to your GitHub repository settings
2. Navigate to Webhooks → Add webhook
3. Set Payload URL: `https://your-domain.com/api/webhooks/github`
4. Set Content type: `application/json`
5. Set Secret: (use GITHUB_WEBHOOK_SECRET from .env)
6. Select events: Pull requests
7. Click "Add webhook"

### 3. Test Deployment

```bash
# Health check
curl https://your-domain.com/api/health

# API test
curl -X POST https://your-domain.com/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"secure_password"}'
```

## Monitoring & Maintenance

### Application Monitoring

**Prometheus + Grafana Setup:**

```bash
# Install Prometheus
wget https://github.com/prometheus/prometheus/releases/download/v2.40.0/prometheus-2.40.0.linux-amd64.tar.gz
tar xvfz prometheus-*.tar.gz
cd prometheus-*

# Configure prometheus.yml
sudo nano prometheus.yml

# Add job:
scrape_configs:
  - job_name: 'codereviewer'
    static_configs:
      - targets: ['localhost:8000']
```

**Log Monitoring:**

```bash
# View application logs
sudo journalctl -u codereviewer-api -f

# View Celery worker logs
sudo journalctl -u codereviewer-worker -f

# View Nginx logs
sudo tail -f /var/log/nginx/codereviewer-access.log
sudo tail -f /var/log/nginx/codereviewer-error.log
```

### Database Maintenance

**PostgreSQL Backup:**

```bash
# Create backup
sudo -u postgres pg_dump codereviewer > backup-$(date +%Y%m%d).sql

# Automated daily backup (crontab)
0 2 * * * /usr/bin/pg_dump codereviewer > /backup/db-$(date +\%Y\%m\%d).sql
```

**Database Optimization:**

```bash
# Analyze and vacuum
sudo -u postgres psql codereviewer -c "VACUUM ANALYZE;"

# Reindex
sudo -u postgres psql codereviewer -c "REINDEX DATABASE codereviewer;"
```

### Redis Maintenance

```bash
# Check Redis memory usage
redis-cli info memory

# Clear cache if needed
redis-cli FLUSHDB
```

## Scaling

### Horizontal Scaling (Multiple Instances)

**Add more FastAPI instances:**

1. Start additional instances on different ports:
```bash
uvicorn server:app --host 0.0.0.0 --port 8001 --workers 4
uvicorn server:app --host 0.0.0.0 --port 8002 --workers 4
```

2. Update Nginx upstream configuration:
```nginx
upstream codereviewer_app {
    server 127.0.0.1:8000;
    server 127.0.0.1:8001;
    server 127.0.0.1:8002;
}
```

**Scale Celery workers:**

```bash
# Increase worker concurrency
celery -A celery_app worker --concurrency=8

# Or run multiple worker processes
celery -A celery_app worker --concurrency=4 &
celery -A celery_app worker --concurrency=4 &
```

### Vertical Scaling

1. Increase instance size (CPU/RAM)
2. Increase uvicorn workers: `--workers 8`
3. Increase Celery concurrency: `--concurrency=8`
4. Increase database connections in connection pool

### Database Scaling

**Read Replicas:**

1. Set up PostgreSQL replication
2. Configure read/write splitting in application
3. Route read queries to replicas

**Connection Pooling:**

Update `DATABASE_URL`:
```env
DATABASE_URL=postgresql://user:pass@host:5432/db?pool_size=20&max_overflow=40
```

## Troubleshooting

### Application Won't Start

```bash
# Check logs
sudo journalctl -u codereviewer-api -n 50

# Check if port is in use
sudo lsof -i :8000

# Check permissions
ls -la /home/codereviewer/ai-code-review-assistant
```

### Database Connection Issues

```bash
# Test PostgreSQL connection
psql -h localhost -U reviewer -d codereviewer

# Check PostgreSQL logs
sudo tail -f /var/log/postgresql/postgresql-13-main.log

# Verify DATABASE_URL in .env
```

### Celery Workers Not Processing Tasks

```bash
# Check Celery worker logs
sudo journalctl -u codereviewer-worker -f

# Check Redis connection
redis-cli ping

# Purge task queue
celery -A celery_app purge
```

### High Memory Usage

```bash
# Check memory usage
free -h
docker stats  # For Docker deployment

# Restart services to free memory
sudo systemctl restart codereviewer-api
sudo systemctl restart codereviewer-worker
```

### SSL Certificate Issues

```bash
# Renew certificate manually
sudo certbot renew

# Check certificate expiry
sudo certbot certificates

# Test Nginx configuration
sudo nginx -t
```

For more troubleshooting help, see [TROUBLESHOOTING.md](TROUBLESHOOTING.md).

---

## Quick Reference

### Essential Commands

```bash
# Start services
sudo systemctl start codereviewer-api codereviewer-worker codereviewer-beat

# Stop services
sudo systemctl stop codereviewer-api codereviewer-worker codereviewer-beat

# Restart services
sudo systemctl restart codereviewer-api

# View logs
sudo journalctl -u codereviewer-api -f

# Database backup
sudo -u postgres pg_dump codereviewer > backup.sql

# Update application
cd /home/codereviewer/ai-code-review-assistant/python-projects/13-code-review-assistant
git pull
source venv/bin/activate
pip install -r requirements.txt
sudo systemctl restart codereviewer-api codereviewer-worker
```

### Health Checks

```bash
# API health
curl https://your-domain.com/api/health

# Database
psql -h localhost -U reviewer -d codereviewer -c "SELECT 1;"

# Redis
redis-cli ping

# Celery workers
celery -A celery_app inspect active
```

---

**Next Steps:**
- Review [USER_GUIDE.md](USER_GUIDE.md) for usage instructions
- Check [TROUBLESHOOTING.md](TROUBLESHOOTING.md) for common issues
- See [SECURITY.md](../SECURITY.md) for security best practices
