# Production Deployment Guide

## Overview

This guide covers deploying the Research Assistant to production with FastAPI, database management, caching, and monitoring.

## Table of Contents

1. [Prerequisites](#prerequisites)
2. [Environment Setup](#environment-setup)
3. [Database Configuration](#database-configuration)
4. [Server Deployment](#server-deployment)
5. [Performance Optimization](#performance-optimization)
6. [Monitoring & Analytics](#monitoring--analytics)
7. [Security Hardening](#security-hardening)
8. [Backup & Recovery](#backup--recovery)
9. [Scaling Strategies](#scaling-strategies)

---

## Prerequisites

### System Requirements

- **OS**: Linux (Ubuntu 20.04+ recommended) or macOS
- **Python**: 3.10 or higher
- **RAM**: Minimum 4GB, recommended 8GB+
- **Storage**: Minimum 20GB, recommended 50GB+ for caching
- **CPU**: 2+ cores recommended

### Required Services

- **Database**: PostgreSQL 13+ (production) or SQLite (development)
- **Reverse Proxy**: Nginx or Caddy
- **Process Manager**: Systemd or Supervisor
- **Optional**: Redis (for advanced caching)

---

## Environment Setup

### 1. Install Dependencies

```bash
# Update system
sudo apt update && sudo apt upgrade -y

# Install Python and pip
sudo apt install python3.10 python3-pip python3-venv -y

# Install system dependencies for PDF generation
sudo apt install libpango-1.0-0 libpangoft2-1.0-0 -y

# Install PostgreSQL (if using)
sudo apt install postgresql postgresql-contrib -y
```

### 2. Create Application User

```bash
# Create dedicated user
sudo useradd -m -s /bin/bash research-app
sudo su - research-app

# Clone repository
git clone <your-repo-url> research-assistant
cd research-assistant/python-projects/11-research-assistant
```

### 3. Python Virtual Environment

```bash
# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install --upgrade pip
pip install -r requirements.txt
```

### 4. Environment Variables

Create production `.env` file:

```bash
# Server Configuration
HOST=0.0.0.0
PORT=8000
NODE_ENV=production

# Database (PostgreSQL)
DATABASE_URL=postgresql://research_user:password@localhost/research_db

# Session Management
SESSION_TTL_DAYS=30
COOKIE_SECURE=true  # MUST be true in production with HTTPS

# CORS
ALLOWED_ORIGINS=https://yourdomain.com,https://www.yourdomain.com

# LLM Configuration
LLM_PROVIDER=anthropic  # or openai, ollama
LLM_MODEL=claude-3-5-sonnet-20241022
ANTHROPIC_API_KEY=your_api_key_here
# OPENAI_API_KEY=your_api_key_here

# Caching
CACHE_DIR=/var/lib/research-assistant/cache
ENABLE_CACHE=true

# Storage
ARXIV_CACHE_DIR=/var/lib/research-assistant/papers
OUTPUT_DIR=/var/lib/research-assistant/output

# Cost Tracking (Phase 5)
COST_LOG_FILE=/var/log/research-assistant/costs.jsonl

# Rate Limiting
RATE_LIMIT_MAX_REQUESTS=100
RATE_LIMIT_WINDOW_SECONDS=60

# Embedding Model (optional)
EMBEDDING_MODEL=all-MiniLM-L6-v2
```

**Security Note**: Never commit `.env` to version control. Use environment variable injection or secrets management.

---

## Database Configuration

### PostgreSQL Setup

#### 1. Create Database and User

```bash
sudo -u postgres psql

postgres=# CREATE DATABASE research_db;
postgres=# CREATE USER research_user WITH PASSWORD 'secure_password_here';
postgres=# GRANT ALL PRIVILEGES ON DATABASE research_db TO research_user;
postgres=# \q
```

#### 2. Configure PostgreSQL

Edit `/etc/postgresql/13/main/postgresql.conf`:

```ini
# Increase connections
max_connections = 100

# Memory settings (adjust based on available RAM)
shared_buffers = 256MB
effective_cache_size = 1GB
work_mem = 16MB

# Performance
random_page_cost = 1.1
effective_io_concurrency = 200
```

Edit `/etc/postgresql/13/main/pg_hba.conf`:

```
# Allow local connections
local   all             all                                     md5
host    all             all             127.0.0.1/32            md5
```

Restart PostgreSQL:

```bash
sudo systemctl restart postgresql
```

#### 3. Initialize Database

```bash
# Run database initialization
python research.py init
```

#### 4. Database Migrations (if schema changes)

```bash
# Backup first
pg_dump research_db > backup_$(date +%Y%m%d).sql

# Apply migrations (manual for now)
# Future: Use Alembic for migrations
```

---

## Server Deployment

### Option 1: Systemd Service (Recommended)

#### 1. Create Systemd Service File

`/etc/systemd/system/research-assistant.service`:

```ini
[Unit]
Description=Research Assistant API Server
After=network.target postgresql.service

[Service]
Type=simple
User=research-app
WorkingDirectory=/home/research-app/research-assistant/python-projects/11-research-assistant
Environment="PATH=/home/research-app/research-assistant/python-projects/11-research-assistant/venv/bin"
ExecStart=/home/research-app/research-assistant/python-projects/11-research-assistant/venv/bin/uvicorn server:app --host 0.0.0.0 --port 8000 --workers 4
Restart=always
RestartSec=10

# Security
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ReadWritePaths=/var/lib/research-assistant /var/log/research-assistant

[Install]
WantedBy=multi-user.target
```

#### 2. Enable and Start Service

```bash
# Reload systemd
sudo systemctl daemon-reload

# Enable service
sudo systemctl enable research-assistant

# Start service
sudo systemctl start research-assistant

# Check status
sudo systemctl status research-assistant

# View logs
sudo journalctl -u research-assistant -f
```

### Option 2: Docker Deployment

#### Dockerfile

```dockerfile
FROM python:3.10-slim

# Install system dependencies
RUN apt-get update && apt-get install -y \
    libpango-1.0-0 \
    libpangoft2-1.0-0 \
    postgresql-client \
    && rm -rf /var/lib/apt/lists/*

# Create app user
RUN useradd -m -s /bin/bash app

# Set working directory
WORKDIR /app

# Copy requirements
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application
COPY . .

# Create directories
RUN mkdir -p /app/data/cache /app/data/papers /app/data/output && \
    chown -R app:app /app

# Switch to app user
USER app

# Expose port
EXPOSE 8000

# Run server
CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "4"]
```

#### docker-compose.yml

```yaml
version: '3.8'

services:
  db:
    image: postgres:13
    environment:
      POSTGRES_DB: research_db
      POSTGRES_USER: research_user
      POSTGRES_PASSWORD: ${DB_PASSWORD}
    volumes:
      - postgres_data:/var/lib/postgresql/data
    ports:
      - "5432:5432"

  app:
    build: .
    ports:
      - "8000:8000"
    environment:
      DATABASE_URL: postgresql://research_user:${DB_PASSWORD}@db:5432/research_db
      ANTHROPIC_API_KEY: ${ANTHROPIC_API_KEY}
      COOKIE_SECURE: "true"
    volumes:
      - ./data:/app/data
    depends_on:
      - db

volumes:
  postgres_data:
```

Deploy:

```bash
docker-compose up -d
```

### Option 3: Gunicorn + Uvicorn Workers

```bash
# Install gunicorn
pip install gunicorn

# Run with gunicorn
gunicorn server:app \
  --workers 4 \
  --worker-class uvicorn.workers.UvicornWorker \
  --bind 0.0.0.0:8000 \
  --access-logfile /var/log/research-assistant/access.log \
  --error-logfile /var/log/research-assistant/error.log \
  --log-level info
```

---

## Nginx Reverse Proxy

### Configuration

`/etc/nginx/sites-available/research-assistant`:

```nginx
upstream research_api {
    server 127.0.0.1:8000;
}

server {
    listen 80;
    server_name yourdomain.com www.yourdomain.com;

    # Redirect to HTTPS
    return 301 https://$server_name$request_uri;
}

server {
    listen 443 ssl http2;
    server_name yourdomain.com www.yourdomain.com;

    # SSL certificates (use Let's Encrypt)
    ssl_certificate /etc/letsencrypt/live/yourdomain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/yourdomain.com/privkey.pem;

    # SSL configuration
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers HIGH:!aNULL:!MD5;
    ssl_prefer_server_ciphers on;

    # Security headers
    add_header X-Frame-Options "SAMEORIGIN" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-XSS-Protection "1; mode=block" always;
    add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;

    # Client max body size (for file uploads)
    client_max_body_size 100M;

    # Proxy settings
    location / {
        proxy_pass http://research_api;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # WebSocket support
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";

        # Timeouts
        proxy_connect_timeout 60s;
        proxy_send_timeout 60s;
        proxy_read_timeout 300s;
    }

    # Static files (if served separately)
    location /static/ {
        alias /home/research-app/research-assistant/python-projects/11-research-assistant/static/;
        expires 1y;
        add_header Cache-Control "public, immutable";
    }

    # Logs
    access_log /var/log/nginx/research-assistant-access.log;
    error_log /var/log/nginx/research-assistant-error.log;
}
```

Enable and reload:

```bash
sudo ln -s /etc/nginx/sites-available/research-assistant /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx
```

### SSL with Let's Encrypt

```bash
# Install certbot
sudo apt install certbot python3-certbot-nginx -y

# Obtain certificate
sudo certbot --nginx -d yourdomain.com -d www.yourdomain.com

# Auto-renewal
sudo systemctl enable certbot.timer
```

---

## Performance Optimization

### 1. Database Indexing

```sql
-- Add indexes for common queries
CREATE INDEX idx_research_queries_user_created ON research_queries(user_id, created_at DESC);
CREATE INDEX idx_research_queries_status ON research_queries(status);
CREATE INDEX idx_sources_query_id ON sources(query_id);
CREATE INDEX idx_findings_query_id ON findings(query_id);
CREATE INDEX idx_sessions_user_expires ON sessions(user_id, expires_at);
```

### 2. Connection Pooling

Update `.env`:

```bash
# PostgreSQL connection pool
DATABASE_URL=postgresql://user:pass@localhost/db?pool_size=20&max_overflow=0
```

### 3. Caching Strategy

- **Level 1**: Search results (7-day TTL)
- **Level 2**: Content extraction (30-day TTL)
- **Level 3**: Synthesis results (14-day TTL)

Monitor cache hit rates:

```bash
# Check cache stats via analytics endpoint
curl https://yourdomain.com/api/analytics/performance
```

### 4. Worker Processes

```bash
# Calculate workers: (2 * CPU_CORES) + 1
# For 4-core machine: (2 * 4) + 1 = 9 workers
```

### 5. Enable HTTP/2

Already configured in Nginx above. Ensures faster page loads.

---

## Monitoring & Analytics

### 1. Application Logs

```bash
# Create log directory
sudo mkdir -p /var/log/research-assistant
sudo chown research-app:research-app /var/log/research-assistant

# Logrotate configuration
cat > /etc/logrotate.d/research-assistant <<EOF
/var/log/research-assistant/*.log {
    daily
    missingok
    rotate 14
    compress
    delaycompress
    notifempty
    create 0640 research-app research-app
    sharedscripts
    postrotate
        systemctl reload research-assistant > /dev/null 2>&1 || true
    endscript
}
EOF
```

### 2. Health Checks

```bash
# Add to cron for monitoring
*/5 * * * * curl -f https://yourdomain.com/api/health || /usr/local/bin/alert-down.sh
```

### 3. Cost Tracking

Monitor API costs:

```bash
# View cost logs
tail -f /var/log/research-assistant/costs.jsonl

# Get session costs via API
curl -b cookies.txt https://yourdomain.com/api/analytics/session-costs
```

### 4. Usage Analytics

Built-in endpoints:

- `/api/analytics/usage` - User statistics
- `/api/analytics/costs` - Cost analysis
- `/api/analytics/sources` - Source effectiveness
- `/api/analytics/performance` - System metrics

---

## Security Hardening

### 1. Firewall

```bash
# UFW firewall
sudo ufw allow 22/tcp    # SSH
sudo ufw allow 80/tcp    # HTTP
sudo ufw allow 443/tcp   # HTTPS
sudo ufw enable
```

### 2. Fail2Ban

Protect against brute force:

```bash
sudo apt install fail2ban -y

# Configure for Nginx
cat > /etc/fail2ban/jail.local <<EOF
[nginx-http-auth]
enabled = true
filter = nginx-http-auth
port = http,https
logpath = /var/log/nginx/*error.log
maxretry = 5
bantime = 3600
EOF

sudo systemctl restart fail2ban
```

### 3. Environment Variables

Use secrets management:

```bash
# AWS Secrets Manager (example)
export ANTHROPIC_API_KEY=$(aws secretsmanager get-secret-value \
  --secret-id research-assistant/anthropic-key \
  --query SecretString --output text)
```

### 4. Database Security

```bash
# Restrict PostgreSQL access
sudo nano /etc/postgresql/13/main/pg_hba.conf

# Only allow localhost
host    research_db     research_user     127.0.0.1/32            scram-sha-256
```

---

## Backup & Recovery

### 1. Database Backups

```bash
# Daily automated backup script
cat > /usr/local/bin/backup-research-db.sh <<'EOF'
#!/bin/bash
BACKUP_DIR="/var/backups/research-assistant"
DATE=$(date +%Y%m%d_%H%M%S)
mkdir -p $BACKUP_DIR

# Dump database
pg_dump research_db > $BACKUP_DIR/research_db_$DATE.sql

# Compress
gzip $BACKUP_DIR/research_db_$DATE.sql

# Keep only last 30 days
find $BACKUP_DIR -name "*.gz" -mtime +30 -delete

# Upload to S3 (optional)
# aws s3 cp $BACKUP_DIR/research_db_$DATE.sql.gz s3://your-bucket/backups/
EOF

chmod +x /usr/local/bin/backup-research-db.sh

# Add to cron (daily at 2 AM)
echo "0 2 * * * /usr/local/bin/backup-research-db.sh" | sudo crontab -
```

### 2. Application Data Backup

```bash
# Backup cache and papers
tar -czf /var/backups/research-data-$(date +%Y%m%d).tar.gz \
  /var/lib/research-assistant/cache \
  /var/lib/research-assistant/papers
```

### 3. Recovery Procedure

```bash
# Restore database
gunzip < backup.sql.gz | psql research_db

# Restore application data
tar -xzf research-data-20240101.tar.gz -C /
```

---

## Scaling Strategies

### Horizontal Scaling

#### Load Balancer Configuration

```nginx
upstream research_backend {
    least_conn;  # Load balancing method
    server backend1.local:8000 weight=2;
    server backend2.local:8000 weight=2;
    server backend3.local:8000 weight=1;
}
```

#### Session Handling

Use centralized session storage (Redis):

```python
# Future enhancement: Redis session store
SESSION_BACKEND=redis
REDIS_URL=redis://localhost:6379/0
```

### Vertical Scaling

- Increase worker processes based on CPU
- Increase PostgreSQL `max_connections`
- Add more RAM for caching

### Database Scaling

- **Read Replicas**: For analytics queries
- **Partitioning**: Partition `research_queries` by date
- **Connection Pooling**: Use PgBouncer

```bash
# Install PgBouncer
sudo apt install pgbouncer -y

# Configure
DATABASE_URL=postgresql://localhost:6432/research_db  # PgBouncer port
```

---

## Production Checklist

- [ ] PostgreSQL configured with proper credentials
- [ ] All environment variables set in `.env`
- [ ] SSL certificates configured (HTTPS)
- [ ] Nginx reverse proxy running
- [ ] Systemd service enabled and running
- [ ] Firewall rules configured
- [ ] Database backups automated
- [ ] Log rotation configured
- [ ] Health monitoring in place
- [ ] Cost tracking enabled
- [ ] Rate limiting configured
- [ ] Session TTL appropriate for use case
- [ ] COOKIE_SECURE=true in production
- [ ] Analytics endpoints tested
- [ ] WebSocket connections working
- [ ] All tests passing

---

## Troubleshooting

### Common Issues

**Issue**: `sqlalchemy.exc.OperationalError: could not connect to server`

```bash
# Check PostgreSQL status
sudo systemctl status postgresql

# Check connection settings
psql -U research_user -d research_db -h localhost
```

**Issue**: 502 Bad Gateway

```bash
# Check application status
sudo systemctl status research-assistant

# Check logs
sudo journalctl -u research-assistant -n 100
```

**Issue**: High memory usage

```bash
# Reduce worker count
# Edit systemd service: --workers 2

# Or limit per-worker memory
# Add to service file:
MemoryLimit=512M
```

**Issue**: Slow queries

```bash
# Enable query logging in PostgreSQL
sudo nano /etc/postgresql/13/main/postgresql.conf

# Add:
log_min_duration_statement = 1000  # Log queries > 1s

# Check slow queries
sudo tail -f /var/log/postgresql/postgresql-13-main.log
```

---

## Support & Maintenance

### Regular Maintenance Tasks

**Daily:**
- Check application logs
- Monitor disk space
- Review error rates

**Weekly:**
- Review usage analytics
- Check backup integrity
- Update dependencies (security patches)

**Monthly:**
- Database vacuum and analyze
- Review and optimize slow queries
- Cost analysis and optimization

### Monitoring Endpoints

- Health: `GET /api/health`
- Usage: `GET /api/analytics/usage?days=30`
- Costs: `GET /api/analytics/costs?days=30`
- Performance: `GET /api/analytics/performance?days=7`

---

## Version History

- **v11.5.0** - Phase 5: Production features (analytics, cost tracking, DOCX export)
- **v11.4.0** - Phase 4: Web interface with FastAPI
- **v11.3.0** - Phase 3: Advanced synthesis
- **v11.2.0** - Phase 2: ArXiv + citations
- **v11.1.0** - Phase 1: Database + authentication

---

## Additional Resources

- [FastAPI Deployment Docs](https://fastapi.tiangolo.com/deployment/)
- [PostgreSQL Performance Tuning](https://www.postgresql.org/docs/current/performance-tips.html)
- [Nginx Best Practices](https://www.nginx.com/blog/nginx-caching-guide/)
- [Let's Encrypt SSL](https://letsencrypt.org/getting-started/)

---

**Last Updated**: 2026-02-01
**Maintainer**: Research Assistant Team
