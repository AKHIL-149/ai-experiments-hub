# Troubleshooting Guide

Common issues and solutions for the AI Code Review & Refactoring Assistant.

## Table of Contents

- [Application Issues](#application-issues)
- [Database Issues](#database-issues)
- [Redis & Celery Issues](#redis--celery-issues)
- [GitHub Integration Issues](#github-integration-issues)
- [Analysis Issues](#analysis-issues)
- [Performance Issues](#performance-issues)
- [Docker Issues](#docker-issues)
- [Authentication Issues](#authentication-issues)
- [Network Issues](#network-issues)
- [LLM Integration Issues](#llm-integration-issues)

## Application Issues

### Application Won't Start

**Symptoms:**
- Server fails to start
- "Address already in use" error
- Import errors
- Database connection errors

**Solutions:**

1. **Check if port is already in use:**
```bash
# Find process using port 8000
lsof -i :8000
# Or on Windows:
netstat -ano | findstr :8000

# Kill the process
kill -9 <PID>
```

2. **Verify Python version:**
```bash
python --version
# Should be 3.10 or higher
```

3. **Check for missing dependencies:**
```bash
pip install -r requirements.txt
```

4. **Verify environment file:**
```bash
# Check .env exists
ls -la .env

# Validate required variables
cat .env | grep -E "DATABASE_URL|REDIS_URL"
```

5. **Check application logs:**
```bash
# Development
python server.py 2>&1 | tee app.log

# Production (systemd)
sudo journalctl -u codereviewer-api -n 50 --no-pager
```

### Import Errors

**Symptoms:**
```
ModuleNotFoundError: No module named 'src'
ImportError: cannot import name 'X' from 'Y'
```

**Solutions:**

1. **Ensure correct working directory:**
```bash
pwd
# Should be: .../python-projects/13-code-review-assistant
```

2. **Check virtual environment:**
```bash
which python
# Should be: .../venv/bin/python
```

3. **Reinstall dependencies:**
```bash
pip install --upgrade pip
pip install -r requirements.txt --force-reinstall
```

4. **Check PYTHONPATH:**
```bash
export PYTHONPATH="${PYTHONPATH}:$(pwd)"
```

### Application Crashes

**Symptoms:**
- Server stops unexpectedly
- Out of memory errors
- Segmentation faults

**Solutions:**

1. **Check system resources:**
```bash
# Memory usage
free -h

# Disk space
df -h

# CPU usage
top
```

2. **Review error logs:**
```bash
# Check for stack traces
tail -n 100 data/logs/app.log

# System logs
dmesg | tail
```

3. **Reduce worker count:**
```bash
# Reduce uvicorn workers
uvicorn server:app --workers 2

# Reduce Celery concurrency
celery -A celery_app worker --concurrency=2
```

4. **Increase memory limits (Docker):**
```yaml
# docker-compose.yml
services:
  app:
    deploy:
      resources:
        limits:
          memory: 4G
```

## Database Issues

### Cannot Connect to Database

**Symptoms:**
```
sqlalchemy.exc.OperationalError: could not connect to server
Connection refused
```

**Solutions:**

1. **Verify database is running:**
```bash
# PostgreSQL
sudo systemctl status postgresql

# Check if accepting connections
psql -h localhost -U reviewer -d codereviewer -c "SELECT 1;"
```

2. **Check DATABASE_URL format:**
```env
# PostgreSQL
DATABASE_URL=postgresql://user:pass@host:5432/dbname

# SQLite
DATABASE_URL=sqlite:///./data/database.db
```

3. **Verify database exists:**
```bash
sudo -u postgres psql -l | grep codereviewer
```

4. **Check PostgreSQL logs:**
```bash
sudo tail -f /var/log/postgresql/postgresql-13-main.log
```

5. **Reset database connection:**
```bash
# Restart PostgreSQL
sudo systemctl restart postgresql

# Restart application
sudo systemctl restart codereviewer-api
```

### Database Locked (SQLite)

**Symptoms:**
```
sqlite3.OperationalError: database is locked
```

**Solutions:**

1. **Close other connections:**
```bash
# Find processes accessing database
lsof data/database.db

# Kill processes if needed
kill <PID>
```

2. **Increase timeout:**
```python
# In database.py
engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False, "timeout": 30}
)
```

3. **Switch to PostgreSQL for production**
   - SQLite is not recommended for concurrent access

### Slow Database Queries

**Symptoms:**
- Slow page loads
- Timeouts
- High CPU usage

**Solutions:**

1. **Add missing indexes:**
```bash
python -c "from src.core.database import add_indexes; add_indexes()"
```

2. **Analyze and vacuum:**
```sql
-- PostgreSQL
VACUUM ANALYZE;

-- SQLite
VACUUM;
ANALYZE;
```

3. **Check query performance:**
```sql
-- Enable query logging
SET log_statement = 'all';
SET log_min_duration_statement = 100;  -- Log queries > 100ms
```

4. **Increase connection pool:**
```python
# In database.py
engine = create_engine(
    DATABASE_URL,
    pool_size=20,
    max_overflow=40
)
```

### Database Migration Issues

**Symptoms:**
- Table doesn't exist
- Column not found
- Schema mismatch

**Solutions:**

1. **Recreate database (Development only):**
```bash
# Backup first!
rm data/database.db
python -c "from src.core.database import init_db; init_db()"
```

2. **For PostgreSQL:**
```bash
# Drop and recreate
sudo -u postgres psql -c "DROP DATABASE codereviewer;"
sudo -u postgres psql -c "CREATE DATABASE codereviewer;"
python -c "from src.core.database import init_db; init_db()"
```

## Redis & Celery Issues

### Cannot Connect to Redis

**Symptoms:**
```
redis.exceptions.ConnectionError: Error connecting to Redis
```

**Solutions:**

1. **Check Redis is running:**
```bash
# Check service status
sudo systemctl status redis-server

# Test connection
redis-cli ping
# Should return: PONG
```

2. **Start Redis:**
```bash
sudo systemctl start redis-server
sudo systemctl enable redis-server
```

3. **Check Redis configuration:**
```bash
# Verify bind address
grep bind /etc/redis/redis.conf
# Should include: bind 127.0.0.1 or 0.0.0.0

# Check if password is required
grep requirepass /etc/redis/redis.conf
```

4. **Update REDIS_URL:**
```env
# No password
REDIS_URL=redis://localhost:6379/0

# With password
REDIS_URL=redis://:password@localhost:6379/0
```

### Celery Workers Not Processing Tasks

**Symptoms:**
- Tasks stay in PENDING state
- No worker output
- Tasks never complete

**Solutions:**

1. **Check workers are running:**
```bash
# List active workers
celery -A celery_app inspect active

# Check worker status
celery -A celery_app inspect stats
```

2. **Start workers:**
```bash
celery -A celery_app worker --loglevel=info
```

3. **Check task queue:**
```bash
# View pending tasks
celery -A celery_app inspect reserved

# Purge all tasks (caution!)
celery -A celery_app purge
```

4. **Check worker logs:**
```bash
# If using systemd
sudo journalctl -u codereviewer-worker -f

# If running manually
# Check terminal output
```

5. **Restart workers:**
```bash
sudo systemctl restart codereviewer-worker
sudo systemctl restart codereviewer-beat
```

### Celery Tasks Failing

**Symptoms:**
- Tasks complete with FAILURE status
- Exception tracebacks in logs

**Solutions:**

1. **View task errors:**
```bash
# Check worker logs
celery -A celery_app events

# Or Flower (if installed)
celery -A celery_app flower
# Access at http://localhost:5555
```

2. **Common task failures:**

**File not found:**
```python
# Ensure file paths are absolute
file_path = os.path.abspath(file_path)
```

**Import errors:**
```bash
# Ensure virtual environment is activated in worker
which python
```

**Memory issues:**
```bash
# Reduce concurrency
celery -A celery_app worker --concurrency=2 --max-tasks-per-child=100
```

3. **Retry failed tasks:**
```python
# In celery_app.py
@app.task(bind=True, max_retries=3, default_retry_delay=60)
def my_task(self):
    try:
        # task code
    except Exception as exc:
        self.retry(exc=exc)
```

### Redis Memory Issues

**Symptoms:**
```
OOM command not allowed when used memory > 'maxmemory'
```

**Solutions:**

1. **Check memory usage:**
```bash
redis-cli info memory
```

2. **Increase max memory:**
```bash
# Edit redis.conf
sudo nano /etc/redis/redis.conf

# Set max memory
maxmemory 512mb
maxmemory-policy allkeys-lru

# Restart Redis
sudo systemctl restart redis-server
```

3. **Clear cache:**
```bash
# Clear all cache (caution!)
redis-cli FLUSHDB

# Clear specific pattern
redis-cli --scan --pattern "cache:*" | xargs redis-cli DEL
```

## GitHub Integration Issues

### GitHub Authentication Failed

**Symptoms:**
```
401 Unauthorized
Bad credentials
```

**Solutions:**

1. **Verify token is valid:**
```bash
# Test token
curl -H "Authorization: token ghp_your_token" \
  https://api.github.com/user
```

2. **Check token scopes:**
   - Required: `repo`, `read:org`, `workflow`
   - Go to GitHub → Settings → Developer settings → Personal access tokens
   - Regenerate token with correct scopes

3. **Update token in .env:**
```env
GITHUB_TOKEN=ghp_new_token_here
```

4. **Restart application:**
```bash
sudo systemctl restart codereviewer-api
```

### Webhook Not Triggering Analysis

**Symptoms:**
- PR created but no analysis
- No webhook events received

**Solutions:**

1. **Verify webhook configuration:**
   - Go to repository → Settings → Webhooks
   - Check Payload URL is correct
   - Verify Secret matches GITHUB_WEBHOOK_SECRET

2. **Check webhook deliveries:**
   - In GitHub webhook settings
   - View recent deliveries
   - Check response codes (should be 200)

3. **Test webhook endpoint:**
```bash
curl -X POST http://your-domain.com/api/webhooks/github \
  -H "Content-Type: application/json" \
  -H "X-Hub-Signature-256: sha256=test" \
  -d '{"action":"test"}'
```

4. **Check application logs:**
```bash
# Look for webhook events
tail -f data/logs/app.log | grep webhook
```

5. **Verify signature validation:**
```bash
# Check GITHUB_WEBHOOK_SECRET is set
echo $GITHUB_WEBHOOK_SECRET
```

### Rate Limit Exceeded

**Symptoms:**
```
403 Forbidden
API rate limit exceeded
```

**Solutions:**

1. **Check rate limit status:**
```bash
curl -H "Authorization: token ghp_your_token" \
  https://api.github.com/rate_limit
```

2. **Wait for reset:**
   - Personal tokens: 5,000 requests/hour
   - Reset time shown in rate limit response

3. **Use GitHub App instead of personal token:**
   - GitHub Apps have higher rate limits
   - 15,000 requests/hour per installed repository

4. **Implement caching:**
   - Already implemented for repository data
   - Cache TTL: 1 hour

### Cannot Clone Repository

**Symptoms:**
```
fatal: could not read Username
Permission denied (publickey)
```

**Solutions:**

1. **Verify repository URL:**
```bash
# Should use HTTPS, not SSH
# Correct: https://github.com/user/repo.git
# Incorrect: git@github.com:user/repo.git
```

2. **Check token has repo access:**
   - Token must have `repo` scope
   - For private repos, token must have access

3. **Test clone manually:**
```bash
git clone https://ghp_token@github.com/user/repo.git
```

4. **Check disk space:**
```bash
df -h
```

## Analysis Issues

### Analysis Fails or Hangs

**Symptoms:**
- Analysis never completes
- Task stuck in PENDING
- No progress updates

**Solutions:**

1. **Check Celery workers:**
```bash
celery -A celery_app inspect active
```

2. **Check file parsing:**
```bash
# Test parser directly
python -c "
from src.parsers.python_parser import PythonParser
parser = PythonParser()
result = parser.parse_file('path/to/file.py')
print(result)
"
```

3. **Check for large files:**
```bash
# Find files > 1MB
find data/repos -size +1M -type f
```

4. **Increase task timeout:**
```python
# In celery_app.py
app.conf.task_time_limit = 600  # 10 minutes
```

5. **Enable debug logging:**
```env
LOG_LEVEL=DEBUG
```

### No Issues Detected

**Symptoms:**
- Analysis completes but finds no issues
- Expected issues not reported

**Solutions:**

1. **Check analyzers are enabled:**
```bash
# View enabled analyzers
python -c "
from src.services.code_analyzer_service import CodeAnalyzerService
service = CodeAnalyzerService()
print(service.get_enabled_analyzers())
"
```

2. **Verify rules are active:**
   - Go to Settings → Analysis Configuration
   - Ensure analyzers are enabled
   - Check custom rules are active

3. **Test with known vulnerable code:**
```python
# test_vuln.py
import pickle
password = "hardcoded123"
def insecure(user_input):
    os.system(f"echo {user_input}")
```

4. **Check severity threshold:**
   - Lower threshold to "Info"
   - May be filtering out low-severity issues

### Parser Errors

**Symptoms:**
```
SyntaxError: invalid syntax
ParsingError: Failed to parse file
```

**Solutions:**

1. **Verify file is valid syntax:**
```bash
# Python
python -m py_compile file.py

# JavaScript
node --check file.js

# Java
javac file.java
```

2. **Check file encoding:**
```bash
file -i filename.py
# Should be: text/plain; charset=utf-8
```

3. **Check language detection:**
```bash
# View detected language
python -c "
from src.parsers.parser_registry import ParserRegistry
registry = ParserRegistry()
lang = registry.detect_language('file.py')
print(lang)
"
```

4. **Manually specify language:**
   - In analysis request, specify language explicitly
   - Don't rely on auto-detection

### Language Not Supported

**Symptoms:**
- "No parser available for language" error
- Analysis skips files

**Solutions:**

1. **Check supported languages:**
```bash
python -c "
from src.parsers.parser_registry import ParserRegistry
registry = ParserRegistry()
print(registry.get_supported_languages())
"
```

2. **Verify parser is registered:**
```bash
python -c "
from src.parsers.parser_registry import ParserRegistry
registry = ParserRegistry()
print(registry.get_parser('python'))
"
```

3. **Install language-specific dependencies:**
```bash
# For Java analysis
sudo apt-get install openjdk-11-jdk

# For Go analysis
sudo apt-get install golang
```

## Performance Issues

### Slow Analysis

**Symptoms:**
- Analysis takes very long
- High CPU/memory usage
- Timeouts

**Solutions:**

1. **Reduce file count:**
```bash
# Analyze specific directories only
# Use .gitignore patterns
```

2. **Exclude large files:**
```bash
# In settings, exclude patterns:
# *.min.js, dist/*, build/*, node_modules/
```

3. **Increase worker concurrency:**
```bash
celery -A celery_app worker --concurrency=8
```

4. **Use file caching:**
   - Already implemented
   - Analysis results cached for 24 hours

5. **Profile slow functions:**
```python
import cProfile
cProfile.run('analyze_function()')
```

### Slow Web Interface

**Symptoms:**
- Pages load slowly
- API requests timeout
- Unresponsive UI

**Solutions:**

1. **Enable caching:**
```env
REDIS_URL=redis://localhost:6379/0
```

2. **Check database indexes:**
```bash
# Verify indexes exist
python -c "from src.core.database import verify_indexes; verify_indexes()"
```

3. **Reduce data returned:**
   - Use pagination
   - Limit results to 50 items per page

4. **Optimize queries:**
```python
# Use eager loading
query = query.options(joinedload(Issue.code_file))
```

5. **Check network latency:**
```bash
# Test API response time
curl -w "@curl-format.txt" -o /dev/null -s http://localhost:8000/api/health
```

### High Memory Usage

**Symptoms:**
- Out of memory errors
- System swap usage
- Killed processes

**Solutions:**

1. **Limit worker memory:**
```bash
# Restart workers after N tasks
celery -A celery_app worker --max-tasks-per-child=100
```

2. **Reduce worker concurrency:**
```bash
celery -A celery_app worker --concurrency=2
```

3. **Implement memory limits (Docker):**
```yaml
deploy:
  resources:
    limits:
      memory: 2G
```

4. **Clear caches periodically:**
```bash
# Clear Redis cache
redis-cli FLUSHDB

# Clear file cache
rm -rf /tmp/code-review-cache/*
```

5. **Monitor memory usage:**
```bash
# Real-time monitoring
watch -n 1 free -h

# Docker
docker stats
```

## Docker Issues

### Docker Containers Won't Start

**Symptoms:**
```
Error: Cannot start service
Container exited with code 1
```

**Solutions:**

1. **Check Docker logs:**
```bash
docker-compose logs app
docker-compose logs worker
docker-compose logs redis
docker-compose logs postgres
```

2. **Verify port availability:**
```bash
# Check if ports are in use
lsof -i :8000  # App
lsof -i :5432  # PostgreSQL
lsof -i :6379  # Redis
```

3. **Check environment variables:**
```bash
docker-compose config
# Verify all variables are set correctly
```

4. **Rebuild containers:**
```bash
docker-compose down
docker-compose build --no-cache
docker-compose up -d
```

5. **Check disk space:**
```bash
df -h
docker system df
```

### Docker Volume Permission Issues

**Symptoms:**
```
Permission denied
Cannot write to /app/data
```

**Solutions:**

1. **Fix volume permissions:**
```bash
# Get container user UID
docker-compose exec app id

# Fix permissions on host
sudo chown -R 1000:1000 ./data
```

2. **Run container as current user:**
```yaml
# docker-compose.yml
services:
  app:
    user: "${UID}:${GID}"
```

3. **Use named volumes:**
```yaml
volumes:
  - app-data:/app/data
```

### Docker Network Issues

**Symptoms:**
- Cannot connect between containers
- DNS resolution fails

**Solutions:**

1. **Check network:**
```bash
docker network ls
docker network inspect code-review-network
```

2. **Recreate network:**
```bash
docker-compose down
docker network prune
docker-compose up -d
```

3. **Use service names:**
```env
# Use Docker service names
DATABASE_URL=postgresql://user:pass@postgres:5432/db
REDIS_URL=redis://redis:6379/0
```

### Docker Build Fails

**Symptoms:**
```
Error building image
Package installation failed
```

**Solutions:**

1. **Clear Docker cache:**
```bash
docker builder prune
docker system prune -a
```

2. **Build without cache:**
```bash
docker-compose build --no-cache
```

3. **Check Dockerfile syntax:**
```bash
docker build -t test -f Dockerfile .
```

4. **Increase build memory:**
```bash
docker build --memory=4g -t app .
```

## Authentication Issues

### Cannot Login

**Symptoms:**
- "Invalid credentials" error
- Session not created

**Solutions:**

1. **Verify user exists:**
```bash
python -c "
from src.core.database import SessionLocal
from src.core.database import User

db = SessionLocal()
user = db.query(User).filter_by(username='admin').first()
print(user)
db.close()
"
```

2. **Reset password:**
```bash
python -c "
from src.core.database import SessionLocal
from src.core.auth_manager import AuthManager

db = SessionLocal()
auth = AuthManager(db)
user = auth.reset_password('admin', 'new_password')
db.close()
"
```

3. **Check password hashing:**
```bash
# Verify bcrypt is installed
python -c "import bcrypt; print(bcrypt.__version__)"
```

4. **Clear sessions:**
```bash
python -c "
from src.core.database import SessionLocal, Session
db = SessionLocal()
db.query(Session).delete()
db.commit()
db.close()
"
```

### Session Expired

**Symptoms:**
- Logged out unexpectedly
- 401 Unauthorized

**Solutions:**

1. **Check session TTL:**
```env
SESSION_TTL_DAYS=30
```

2. **Extend session:**
   - Log in again
   - Session cookies should persist

3. **Check cookie settings:**
```env
COOKIE_SECURE=false  # For development
COOKIE_SECURE=true   # For production with HTTPS
```

### Permission Denied

**Symptoms:**
- Cannot access certain pages
- "Insufficient permissions" error

**Solutions:**

1. **Check user role:**
```bash
python -c "
from src.core.database import SessionLocal, User
db = SessionLocal()
user = db.query(User).filter_by(username='admin').first()
print(f'Role: {user.role}')
db.close()
"
```

2. **Update user role:**
```bash
python -c "
from src.core.database import SessionLocal, User
db = SessionLocal()
user = db.query(User).filter_by(username='admin').first()
user.role = 'ADMIN'
db.commit()
db.close()
"
```

3. **Check RBAC configuration:**
   - Admin: Full access
   - User: Standard access
   - Viewer: Read-only

## Network Issues

### Cannot Access Application

**Symptoms:**
- "Connection refused"
- "This site can't be reached"

**Solutions:**

1. **Check if server is running:**
```bash
# Check process
ps aux | grep uvicorn

# Check port
lsof -i :8000
```

2. **Verify HOST setting:**
```env
HOST=0.0.0.0  # Listen on all interfaces
# Not: HOST=127.0.0.1  # Only localhost
```

3. **Check firewall:**
```bash
# Ubuntu/Debian
sudo ufw status
sudo ufw allow 8000/tcp

# CentOS/RHEL
sudo firewall-cmd --add-port=8000/tcp --permanent
sudo firewall-cmd --reload
```

4. **Test locally:**
```bash
curl http://localhost:8000/api/health
```

### CORS Errors

**Symptoms:**
```
Access to fetch blocked by CORS policy
No 'Access-Control-Allow-Origin' header
```

**Solutions:**

1. **Update ALLOWED_ORIGINS:**
```env
ALLOWED_ORIGINS=http://localhost:8000,http://localhost:3000,https://your-domain.com
```

2. **Check request origin:**
```javascript
// In browser console
console.log(window.location.origin);
```

3. **Restart application:**
```bash
sudo systemctl restart codereviewer-api
```

### SSL Certificate Issues

**Symptoms:**
```
SSL certificate problem
Certificate verification failed
```

**Solutions:**

1. **Renew certificate:**
```bash
sudo certbot renew
sudo systemctl reload nginx
```

2. **Check certificate validity:**
```bash
sudo certbot certificates
```

3. **Test SSL configuration:**
```bash
curl -I https://your-domain.com
```

4. **Force HTTPS redirect:**
```nginx
# In nginx config
return 301 https://$server_name$request_uri;
```

## LLM Integration Issues

### Ollama Connection Failed

**Symptoms:**
```
Connection refused to Ollama API
Cannot connect to http://localhost:11434
```

**Solutions:**

1. **Check Ollama is running:**
```bash
# Check process
ps aux | grep ollama

# Test API
curl http://localhost:11434/api/tags
```

2. **Start Ollama:**
```bash
ollama serve
```

3. **Pull model:**
```bash
ollama pull llama3.2
ollama pull codellama
```

4. **Verify API URL:**
```env
OLLAMA_API_URL=http://localhost:11434
```

### Anthropic API Errors

**Symptoms:**
```
401 Unauthorized
Invalid API key
```

**Solutions:**

1. **Verify API key:**
```bash
curl https://api.anthropic.com/v1/models \
  -H "x-api-key: $ANTHROPIC_API_KEY"
```

2. **Update API key:**
```env
ANTHROPIC_API_KEY=sk-ant-your-key-here
```

3. **Check rate limits:**
   - View usage in Anthropic console
   - May need to upgrade plan

### OpenAI API Errors

**Symptoms:**
```
429 Too Many Requests
Rate limit exceeded
```

**Solutions:**

1. **Check rate limits:**
```bash
curl https://api.openai.com/v1/models \
  -H "Authorization: Bearer $OPENAI_API_KEY"
```

2. **Implement retry logic:**
   - Already implemented with exponential backoff

3. **Reduce request rate:**
   - Limit concurrent LLM calls
   - Cache LLM responses

---

## Getting More Help

If you're still experiencing issues:

1. **Check GitHub Issues**: [Report a bug](https://github.com/your-org/repo/issues)
2. **View Documentation**: [Full docs](.)
3. **Security Issues**: See [SECURITY.md](../SECURITY.md)
4. **Community Support**: [Discord/Slack]

### Providing Debug Information

When reporting issues, include:

```bash
# System information
uname -a
python --version
pip freeze

# Application logs
tail -n 100 data/logs/app.log

# Configuration (remove sensitive data!)
cat .env | grep -v "TOKEN\|KEY\|PASSWORD"

# Error messages
# Copy full stack trace
```

---

**Need immediate help? Check our [FAQ](FAQ.md) or open a GitHub issue.**
