# Cloud Deployment Guide

Complete guide for deploying Multi-Agent Task Orchestrator to major cloud platforms.

## 📋 Table of Contents

- [Prerequisites](#prerequisites)
- [AWS Deployment](#aws-deployment)
- [Google Cloud Platform](#google-cloud-platform)
- [Azure Deployment](#azure-deployment)
- [Heroku Deployment](#heroku-deployment)
- [Render Deployment](#render-deployment)
- [Railway Deployment](#railway-deployment)
- [Docker Deployment](#docker-deployment)
- [Environment Configuration](#environment-configuration)
- [Database Migration](#database-migration)
- [Monitoring & Scaling](#monitoring--scaling)

---

## Prerequisites

Before deploying to any cloud platform:

✅ **Required**:
- Python 3.9+
- Git repository
- OpenAI or Anthropic API key
- PostgreSQL database (for production)
- Redis instance (for production)

✅ **Optional** (but recommended):
- Domain name
- SSL certificate
- CDN for static assets

---

## AWS Deployment

### Option 1: AWS Elastic Beanstalk (Easiest)

#### 1. Install EB CLI

```bash
pip install awsebcli
```

#### 2. Initialize Elastic Beanstalk

```bash
cd 14-multi-agent-orchestrator
eb init -p python-3.9 multi-agent-orchestrator --region us-east-1
```

#### 3. Create Environment

```bash
eb create multi-agent-orchestrator-prod
```

#### 4. Set Environment Variables

```bash
eb setenv \
  DATABASE_URL="postgresql://user:password@rds-endpoint.region.rds.amazonaws.com:5432/dbname" \
  REDIS_URL="redis://elasticache-endpoint:6379/0" \
  OPENAI_API_KEY="your-key-here" \
  SECRET_KEY="your-secret-key-here"
```

#### 5. Deploy

```bash
eb deploy
```

### Option 2: AWS ECS (Container-based)

#### 1. Build Docker Image

```bash
docker build -t multi-agent-orchestrator .
```

#### 2. Push to ECR

```bash
aws ecr get-login-password --region us-east-1 | docker login --username AWS --password-stdin <account-id>.dkr.ecr.us-east-1.amazonaws.com
docker tag multi-agent-orchestrator:latest <account-id>.dkr.ecr.us-east-1.amazonaws.com/multi-agent-orchestrator:latest
docker push <account-id>.dkr.ecr.us-east-1.amazonaws.com/multi-agent-orchestrator:latest
```

#### 3. Create ECS Task Definition

See `deploy/aws/task-definition.json` for template.

#### 4. Create ECS Service

```bash
aws ecs create-service \
  --cluster multi-agent-cluster \
  --service-name orchestrator-service \
  --task-definition multi-agent-orchestrator:1 \
  --desired-count 2 \
  --launch-type FARGATE
```

### AWS RDS Setup

```bash
# Create PostgreSQL database
aws rds create-db-instance \
  --db-instance-identifier multi-agent-db \
  --db-instance-class db.t3.micro \
  --engine postgres \
  --master-username postgres \
  --master-user-password your-password \
  --allocated-storage 20
```

### AWS ElastiCache Setup

```bash
# Create Redis cluster
aws elasticache create-cache-cluster \
  --cache-cluster-id multi-agent-cache \
  --cache-node-type cache.t3.micro \
  --engine redis \
  --num-cache-nodes 1
```

---

## Google Cloud Platform

### Option 1: Google Cloud Run (Serverless)

#### 1. Build and Push to GCR

```bash
gcloud builds submit --tag gcr.io/PROJECT_ID/multi-agent-orchestrator
```

#### 2. Deploy to Cloud Run

```bash
gcloud run deploy multi-agent-orchestrator \
  --image gcr.io/PROJECT_ID/multi-agent-orchestrator \
  --platform managed \
  --region us-central1 \
  --allow-unauthenticated \
  --set-env-vars="DATABASE_URL=postgresql://user:password@/dbname?host=/cloudsql/PROJECT_ID:REGION:INSTANCE" \
  --set-env-vars="REDIS_URL=redis://REDIS_IP:6379/0" \
  --set-env-vars="OPENAI_API_KEY=your-key-here"
```

#### 3. Connect Cloud SQL

```bash
gcloud run services update multi-agent-orchestrator \
  --add-cloudsql-instances PROJECT_ID:REGION:INSTANCE
```

### Option 2: Google Kubernetes Engine (GKE)

#### 1. Create GKE Cluster

```bash
gcloud container clusters create multi-agent-cluster \
  --num-nodes=3 \
  --machine-type=n1-standard-2 \
  --region=us-central1
```

#### 2. Deploy with Kubernetes

```bash
kubectl apply -f deploy/k8s/deployment.yaml
kubectl apply -f deploy/k8s/service.yaml
```

### GCP Cloud SQL Setup

```bash
gcloud sql instances create multi-agent-db \
  --database-version=POSTGRES_14 \
  --tier=db-f1-micro \
  --region=us-central1
```

### GCP Memorystore (Redis) Setup

```bash
gcloud redis instances create multi-agent-cache \
  --size=1 \
  --region=us-central1 \
  --redis-version=redis_6_x
```

---

## Azure Deployment

### Option 1: Azure App Service

#### 1. Create App Service Plan

```bash
az appservice plan create \
  --name multi-agent-plan \
  --resource-group multi-agent-rg \
  --sku B1 \
  --is-linux
```

#### 2. Create Web App

```bash
az webapp create \
  --resource-group multi-agent-rg \
  --plan multi-agent-plan \
  --name multi-agent-orchestrator \
  --runtime "PYTHON|3.9"
```

#### 3. Configure Environment Variables

```bash
az webapp config appsettings set \
  --resource-group multi-agent-rg \
  --name multi-agent-orchestrator \
  --settings \
    DATABASE_URL="postgresql://user@server:password@server.postgres.database.azure.com:5432/dbname?sslmode=require" \
    REDIS_URL="redis://cache.redis.cache.windows.net:6380?ssl=True" \
    OPENAI_API_KEY="your-key-here"
```

#### 4. Deploy

```bash
az webapp up \
  --resource-group multi-agent-rg \
  --name multi-agent-orchestrator \
  --runtime "PYTHON:3.9"
```

### Azure Database for PostgreSQL Setup

```bash
az postgres server create \
  --resource-group multi-agent-rg \
  --name multi-agent-db \
  --location eastus \
  --admin-user postgres \
  --admin-password your-password \
  --sku-name B_Gen5_1
```

### Azure Cache for Redis Setup

```bash
az redis create \
  --resource-group multi-agent-rg \
  --name multi-agent-cache \
  --location eastus \
  --sku Basic \
  --vm-size c0
```

---

## Heroku Deployment

### 1. Create Heroku App

```bash
heroku create multi-agent-orchestrator
```

### 2. Add Buildpack

```bash
heroku buildpacks:set heroku/python
```

### 3. Add PostgreSQL

```bash
heroku addons:create heroku-postgresql:hobby-dev
```

### 4. Add Redis

```bash
heroku addons:create heroku-redis:hobby-dev
```

### 5. Set Environment Variables

```bash
heroku config:set \
  OPENAI_API_KEY=your-key-here \
  SECRET_KEY=your-secret-key-here \
  DEBUG=false
```

### 6. Deploy

```bash
git push heroku main
```

### 7. Run Migrations

```bash
heroku run ./migrate.sh upgrade
```

### 8. Scale Dynos

```bash
heroku ps:scale web=2 worker=1
```

---

## Render Deployment

### 1. Create render.yaml

```yaml
services:
  - type: web
    name: multi-agent-orchestrator
    env: python
    buildCommand: "pip install -r requirements.txt"
    startCommand: "python server.py"
    envVars:
      - key: DATABASE_URL
        fromDatabase:
          name: multi-agent-db
          property: connectionString
      - key: REDIS_URL
        fromService:
          type: redis
          name: multi-agent-cache
          property: connectionString
      - key: OPENAI_API_KEY
        sync: false

databases:
  - name: multi-agent-db
    databaseName: multi_agent_orchestrator
    user: postgres

services:
  - type: redis
    name: multi-agent-cache
    maxmemoryPolicy: noeviction
```

### 2. Connect GitHub

1. Go to [render.com](https://render.com)
2. Connect GitHub repository
3. Render will auto-deploy using render.yaml

### 3. Set Environment Variables

Set in Render dashboard:
- `OPENAI_API_KEY`
- `SECRET_KEY`

---

## Railway Deployment

### 1. Install Railway CLI

```bash
npm i -g @railway/cli
```

### 2. Login and Initialize

```bash
railway login
railway init
```

### 3. Add PostgreSQL

```bash
railway add postgresql
```

### 4. Add Redis

```bash
railway add redis
```

### 5. Deploy

```bash
railway up
```

### 6. Set Environment Variables

```bash
railway variables set OPENAI_API_KEY=your-key-here
railway variables set SECRET_KEY=your-secret-key-here
```

---

## Docker Deployment

### 1. Build Image

```bash
docker build -t multi-agent-orchestrator:latest .
```

### 2. Docker Compose (Recommended)

```yaml
version: '3.8'

services:
  web:
    image: multi-agent-orchestrator:latest
    ports:
      - "8001:8001"
    environment:
      - DATABASE_URL=postgresql://postgres:postgres@db:5432/orchestrator
      - REDIS_URL=redis://redis:6379/0
      - OPENAI_API_KEY=${OPENAI_API_KEY}
    depends_on:
      - db
      - redis

  db:
    image: postgres:14
    environment:
      - POSTGRES_DB=orchestrator
      - POSTGRES_PASSWORD=postgres
    volumes:
      - postgres_data:/var/lib/postgresql/data

  redis:
    image: redis:7-alpine
    volumes:
      - redis_data:/data

volumes:
  postgres_data:
  redis_data:
```

### 3. Start Services

```bash
docker-compose up -d
```

---

## Environment Configuration

### Environment Variables by Priority

| Variable | Required | Default | Cloud Auto-Set |
|----------|----------|---------|---------------|
| `DATABASE_URL` | Yes | sqlite:///./data/orchestrator.db | ✅ Heroku, Render, Railway |
| `REDIS_URL` | Recommended | redis://localhost:6379/0 | ✅ Heroku, Render, Railway |
| `OPENAI_API_KEY` | Yes* | - | ❌ Manual |
| `ANTHROPIC_API_KEY` | Yes* | - | ❌ Manual |
| `SECRET_KEY` | Yes | - | ❌ Manual |
| `PORT` | No | 8001 | ✅ Most platforms |

*At least one LLM API key required

### Generate SECRET_KEY

```bash
python3 -c "import secrets; print(secrets.token_urlsafe(32))"
```

---

## Database Migration

### On First Deployment

```bash
# Heroku
heroku run ./migrate.sh upgrade

# Render (auto-runs if configured)
# See render.yaml

# Railway
railway run ./migrate.sh upgrade

# AWS EB
eb ssh
./migrate.sh upgrade

# GCP Cloud Run
gcloud run jobs execute migrate-job

# Manual (after SSH)
source venv/bin/activate
./migrate.sh upgrade
```

---

## Monitoring & Scaling

### Health Checks

Configure health check endpoint:
- **Path**: `/api/health`
- **Expected Response**: `{"status":"healthy"}`
- **Interval**: 30 seconds
- **Timeout**: 5 seconds

### Scaling Recommendations

| Platform | Instances | Memory | CPU |
|----------|-----------|--------|-----|
| **Development** | 1 | 512MB | 0.5 vCPU |
| **Production** | 2-4 | 1-2GB | 1-2 vCPU |
| **High Load** | 5-10 | 2-4GB | 2-4 vCPU |

### Auto-Scaling Configuration

**AWS ECS**:
```json
{
  "targetValue": 75.0,
  "scaleOutCooldown": 60,
  "scaleInCooldown": 60
}
```

**GCP Cloud Run**:
```bash
gcloud run services update multi-agent-orchestrator \
  --min-instances=1 \
  --max-instances=10 \
  --concurrency=80
```

**Azure App Service**:
```bash
az monitor autoscale create \
  --resource-group multi-agent-rg \
  --resource multi-agent-orchestrator \
  --min-count 1 \
  --max-count 10 \
  --count 2
```

---

## Cost Optimization

### Estimated Monthly Costs

| Platform | Tier | App | Database | Redis | Total |
|----------|------|-----|----------|-------|-------|
| **Heroku** | Hobby | $7 | $9 | $3 | **$19** |
| **Render** | Starter | $7 | $7 | $10 | **$24** |
| **Railway** | Pro | ~$10 | ~$8 | ~$5 | **~$23** |
| **AWS** | t3.micro | $8 | $15 | $15 | **~$38** |
| **GCP** | Cloud Run | $5-15 | $10 | $12 | **$27-37** |
| **Azure** | B1 | $13 | $15 | $14 | **~$42** |

*Costs are estimates and may vary

### Cost-Saving Tips

1. ✅ Use SQLite for development (free)
2. ✅ Start with smallest database tier
3. ✅ Use Redis only in production
4. ✅ Enable auto-scaling with low minimums
5. ✅ Use serverless options (Cloud Run, Lambda)
6. ✅ Implement caching to reduce database queries
7. ✅ Monitor LLM API costs with `COST_ALERT_THRESHOLD`

---

## Security Checklist

- [ ] Set strong `SECRET_KEY`
- [ ] Use environment variables for secrets
- [ ] Enable SSL/TLS (HTTPS)
- [ ] Restrict database access (firewall rules)
- [ ] Use managed databases with automated backups
- [ ] Enable rate limiting
- [ ] Configure CORS properly
- [ ] Use VPC/private networks for internal services
- [ ] Rotate API keys regularly
- [ ] Enable audit logging
- [ ] Use least-privilege IAM roles
- [ ] Keep dependencies updated

---

## Troubleshooting

### Common Issues

**Issue**: Database connection fails
**Solution**: Check `DATABASE_URL` format, firewall rules, and SSL settings

**Issue**: Redis connection timeout
**Solution**: Verify `REDIS_URL`, check network connectivity

**Issue**: LLM API errors
**Solution**: Verify API keys, check quotas, monitor costs

**Issue**: Migration fails
**Solution**: Check database permissions, run migrations manually

**Issue**: High memory usage
**Solution**: Increase instance size or reduce concurrent workers

---

## Support

For deployment issues:
1. Check platform-specific docs
2. Review application logs
3. Verify environment variables
4. Test database/Redis connectivity
5. Open GitHub issue with deployment details

---

**Ready to deploy?** Choose your platform and follow the guide above! 🚀
