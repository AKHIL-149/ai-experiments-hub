"""
FastAPI server for Multi-Agent Task Orchestrator
"""

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

from src.core.config import settings
from src.core.logging import setup_logging, logger
from src.core.middleware import RequestLoggingMiddleware, ErrorTrackingMiddleware
from src.core.rate_limit_middleware import RateLimitMiddleware
from src.core.cache_middleware import ResponseCachingMiddleware
from src.api import tasks, agents, health, metrics, auth, workflows, websockets, errors, rate_limits, cache, messages, memory, orchestration, executions, analytics, lifecycle, scheduler, capabilities, priorities, dependencies, resources, collaboration, load_balancer, health_monitor, events, workflow_engine, shared_memory, communication_protocol, task_decomposition, conflict_resolution, agent_consensus, coalition_formation, agent_negotiation, agent_reputation, agent_incentive, agent_learning, agent_knowledge, agent_performance, agent_role, workflow_template, agent_discovery, agent_contract, agent_auction, agent_trust, agent_coordination, human_approval, cost_tracking, performance_monitoring, alert_management, audit_logging, backup_recovery, config_management


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Lifespan event handler for startup and shutdown
    """
    # Startup
    logger.info(f"🚀 Starting {settings.APP_NAME}")
    logger.info(f"📊 Database: {settings.DATABASE_URL.split('@')[1] if '@' in settings.DATABASE_URL else 'configured'}")
    logger.info(f"🔴 Redis: {settings.REDIS_URL}")
    logger.info(f"🤖 Default LLM: {settings.DEFAULT_LLM_PROVIDER}/{settings.DEFAULT_MODEL}")
    logger.info(f"📝 Log Level: {settings.LOG_LEVEL}")

    yield

    # Shutdown
    logger.info(f"🛑 Shutting down {settings.APP_NAME}")


# Initialize FastAPI application
app = FastAPI(
    title=settings.APP_NAME,
    description="AI-powered multi-agent task orchestration system using LangGraph",
    version="0.1.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

# Add custom middleware
app.add_middleware(RequestLoggingMiddleware)
app.add_middleware(ErrorTrackingMiddleware)
app.add_middleware(RateLimitMiddleware)
app.add_middleware(ResponseCachingMiddleware)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(health.router, prefix="/api", tags=["Health"])
app.include_router(auth.router, prefix="/api/auth", tags=["Authentication"])
app.include_router(workflows.router, prefix="/api/workflows", tags=["Workflows"])
app.include_router(tasks.router, prefix="/api/tasks", tags=["Tasks"])
app.include_router(agents.router, prefix="/api/agents", tags=["Agents"])
app.include_router(messages.router, prefix="/api/messages", tags=["Agent Messages"])
app.include_router(memory.router, prefix="/api/memory", tags=["Shared Memory"])
app.include_router(orchestration.router, prefix="/api/orchestration", tags=["Orchestration"])
app.include_router(executions.router, prefix="/api/executions", tags=["Executions"])
app.include_router(analytics.router, prefix="/api/analytics", tags=["Analytics"])
app.include_router(lifecycle.router, prefix="/api/lifecycle", tags=["Lifecycle"])
app.include_router(scheduler.router, prefix="/api/scheduler", tags=["Scheduler"])
app.include_router(capabilities.router, prefix="/api/capabilities", tags=["Capabilities"])
app.include_router(priorities.router, prefix="/api/priorities", tags=["Priorities"])
app.include_router(dependencies.router, prefix="/api/dependencies", tags=["Dependencies"])
app.include_router(resources.router, prefix="/api/resources", tags=["Resources"])
app.include_router(collaboration.router, prefix="/api/collaboration", tags=["Collaboration"])
app.include_router(load_balancer.router, prefix="/api/load-balancer", tags=["Load Balancer"])
app.include_router(health_monitor.router, prefix="/api/health-monitor", tags=["Health Monitor"])
app.include_router(events.router, prefix="/api/events", tags=["Events"])
app.include_router(workflow_engine.router, prefix="/api/workflow-engine", tags=["Workflow Engine"])
app.include_router(shared_memory.router, prefix="/api/shared-memory", tags=["Shared Memory"])
app.include_router(communication_protocol.router, prefix="/api/communication", tags=["Communication"])
app.include_router(task_decomposition.router, prefix="/api/task-decomposition", tags=["Task Decomposition"])
app.include_router(conflict_resolution.router, prefix="/api/conflict-resolution", tags=["Conflict Resolution"])
app.include_router(agent_consensus.router, prefix="/api/consensus", tags=["Agent Consensus"])
app.include_router(coalition_formation.router, prefix="/api/coalitions", tags=["Coalition Formation"])
app.include_router(agent_negotiation.router, prefix="/api/negotiations", tags=["Agent Negotiation"])
app.include_router(agent_reputation.router, prefix="/api/reputation", tags=["Agent Reputation"])
app.include_router(agent_incentive.router, prefix="/api/incentives", tags=["Agent Incentives"])
app.include_router(agent_learning.router, prefix="/api/learning", tags=["Agent Learning"])
app.include_router(agent_knowledge.router, prefix="/api/knowledge", tags=["Agent Knowledge"])
app.include_router(agent_performance.router, prefix="/api/performance", tags=["Agent Performance"])
app.include_router(agent_role.router, prefix="/api/roles", tags=["Agent Roles"])
app.include_router(workflow_template.router, prefix="/api/workflow-templates", tags=["Workflow Templates"])
app.include_router(agent_discovery.router, prefix="/api/discovery", tags=["Agent Discovery"])
app.include_router(agent_contract.router, prefix="/api/contracts", tags=["Agent Contracts"])
app.include_router(agent_auction.router, prefix="/api/auctions", tags=["Agent Auctions"])
app.include_router(agent_trust.router, prefix="/api/trust", tags=["Agent Trust"])
app.include_router(agent_coordination.router, prefix="/api/coordination", tags=["Agent Coordination"])
app.include_router(human_approval.router, prefix="/api/approvals", tags=["Human Approval"])
app.include_router(cost_tracking.router, prefix="/api/costs", tags=["Cost Tracking"])
app.include_router(performance_monitoring.router, prefix="/api/performance-monitoring", tags=["Performance Monitoring"])
app.include_router(alert_management.router, prefix="/api/alerts", tags=["Alert Management"])
app.include_router(audit_logging.router, prefix="/api/audit", tags=["Audit Logging"])
app.include_router(backup_recovery.router, prefix="/api/backup", tags=["Backup & Recovery"])
app.include_router(config_management.router, prefix="/api/config", tags=["Configuration Management"])
app.include_router(metrics.router, prefix="/api", tags=["Metrics"])
app.include_router(websockets.router, prefix="/api", tags=["WebSockets"])
app.include_router(errors.router, prefix="/api/errors", tags=["Error Tracking"])
app.include_router(rate_limits.router, prefix="/api", tags=["Rate Limits"])
app.include_router(cache.router, prefix="/api", tags=["Cache"])


@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "name": settings.APP_NAME,
        "version": "0.1.0",
        "status": "running",
        "docs": "/docs",
    }


if __name__ == "__main__":
    uvicorn.run(
        "server:app",
        host=settings.API_HOST,
        port=settings.API_PORT,
        reload=settings.DEBUG,
        log_level=settings.LOG_LEVEL.lower(),
    )
