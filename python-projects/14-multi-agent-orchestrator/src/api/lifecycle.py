"""
Agent Lifecycle Management API endpoints
"""

from typing import List, Dict, Any, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from src.core.database import get_db_session
from src.services.agent_lifecycle import AgentLifecycle
from src.core.logging import logger


router = APIRouter()


# Pydantic Models

class AgentRegisterRequest(BaseModel):
    """Request model for agent registration"""
    name: str
    role: str
    capabilities: Optional[List[str]] = None
    config: Optional[Dict[str, Any]] = None
    metadata: Optional[Dict[str, Any]] = None


class AgentHeartbeatRequest(BaseModel):
    """Request model for agent heartbeat"""
    status: Optional[str] = None
    metrics: Optional[Dict[str, Any]] = None


# Endpoints

@router.post("/register")
async def register_agent(
    request: AgentRegisterRequest,
    db: Session = Depends(get_db_session)
) -> Dict[str, Any]:
    """Register a new agent"""
    try:
        agent = AgentLifecycle.register_agent(
            session=db,
            name=request.name,
            role=request.role,
            capabilities=request.capabilities,
            config=request.config,
            metadata=request.metadata
        )

        db.commit()

        return {
            "id": agent.id,
            "name": agent.name,
            "role": agent.role.value,
            "status": agent.status.value,
            "capabilities": agent.capabilities,
            "created_at": agent.created_at.isoformat() if agent.created_at else None
        }

    except ValueError as e:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to register agent: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.delete("/deregister/{agent_id}")
async def deregister_agent(
    agent_id: int,
    reason: Optional[str] = Query(None),
    db: Session = Depends(get_db_session)
) -> Dict[str, bool]:
    """Deregister an agent"""
    try:
        deleted = AgentLifecycle.deregister_agent(
            session=db,
            agent_id=agent_id,
            reason=reason
        )

        db.commit()

        if not deleted:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found")

        return {"deregistered": True}

    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to deregister agent: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.post("/start/{agent_id}")
async def start_agent(
    agent_id: int,
    db: Session = Depends(get_db_session)
) -> Dict[str, Any]:
    """Start an agent"""
    try:
        agent = AgentLifecycle.start_agent(
            session=db,
            agent_id=agent_id
        )

        db.commit()

        return {
            "id": agent.id,
            "name": agent.name,
            "status": agent.status.value,
            "last_active": agent.last_active.isoformat() if agent.last_active else None
        }

    except ValueError as e:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to start agent: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.post("/stop/{agent_id}")
async def stop_agent(
    agent_id: int,
    reason: Optional[str] = Query(None),
    db: Session = Depends(get_db_session)
) -> Dict[str, Any]:
    """Stop an agent"""
    try:
        agent = AgentLifecycle.stop_agent(
            session=db,
            agent_id=agent_id,
            reason=reason
        )

        db.commit()

        return {
            "id": agent.id,
            "name": agent.name,
            "status": agent.status.value
        }

    except ValueError as e:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to stop agent: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.post("/pause/{agent_id}")
async def pause_agent(
    agent_id: int,
    reason: Optional[str] = Query(None),
    db: Session = Depends(get_db_session)
) -> Dict[str, Any]:
    """Pause an agent"""
    try:
        agent = AgentLifecycle.pause_agent(
            session=db,
            agent_id=agent_id,
            reason=reason
        )

        db.commit()

        return {
            "id": agent.id,
            "name": agent.name,
            "status": agent.status.value
        }

    except ValueError as e:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to pause agent: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.post("/resume/{agent_id}")
async def resume_agent(
    agent_id: int,
    db: Session = Depends(get_db_session)
) -> Dict[str, Any]:
    """Resume a paused agent"""
    try:
        agent = AgentLifecycle.resume_agent(
            session=db,
            agent_id=agent_id
        )

        db.commit()

        return {
            "id": agent.id,
            "name": agent.name,
            "status": agent.status.value,
            "last_active": agent.last_active.isoformat() if agent.last_active else None
        }

    except ValueError as e:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to resume agent: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.post("/heartbeat/{agent_id}")
async def agent_heartbeat(
    agent_id: int,
    request: AgentHeartbeatRequest,
    db: Session = Depends(get_db_session)
) -> Dict[str, Any]:
    """Update agent heartbeat"""
    try:
        agent = AgentLifecycle.heartbeat(
            session=db,
            agent_id=agent_id,
            status=request.status,
            metrics=request.metrics
        )

        db.commit()

        return {
            "id": agent.id,
            "name": agent.name,
            "status": agent.status.value,
            "last_active": agent.last_active.isoformat() if agent.last_active else None
        }

    except ValueError as e:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to update heartbeat: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.get("/health/{agent_id}")
async def health_check_agent(
    agent_id: int,
    db: Session = Depends(get_db_session)
) -> Dict[str, Any]:
    """Perform health check on an agent"""
    try:
        health = AgentLifecycle.health_check(
            session=db,
            agent_id=agent_id
        )

        db.commit()

        return health

    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.get("/health")
async def health_check_all_agents(
    db: Session = Depends(get_db_session)
) -> Dict[str, Any]:
    """Check health of all agents"""
    try:
        health_summary = AgentLifecycle.check_all_agents_health(
            session=db
        )

        db.commit()

        return health_summary

    except Exception as e:
        logger.error(f"Health check all failed: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.get("/inactive")
async def get_inactive_agents(
    inactive_threshold_minutes: int = Query(5, ge=1, le=1440),
    db: Session = Depends(get_db_session)
) -> Dict[str, Any]:
    """Get inactive agents"""
    try:
        agents = AgentLifecycle.get_inactive_agents(
            session=db,
            inactive_threshold_minutes=inactive_threshold_minutes
        )

        return {
            "inactive_threshold_minutes": inactive_threshold_minutes,
            "count": len(agents),
            "agents": [
                {
                    "id": agent.id,
                    "name": agent.name,
                    "status": agent.status.value,
                    "last_active": agent.last_active.isoformat() if agent.last_active else None
                }
                for agent in agents
            ]
        }

    except Exception as e:
        logger.error(f"Failed to get inactive agents: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.post("/recover/{agent_id}")
async def recover_agent(
    agent_id: int,
    db: Session = Depends(get_db_session)
) -> Dict[str, Any]:
    """Recover an unhealthy agent"""
    try:
        agent = AgentLifecycle.recover_agent(
            session=db,
            agent_id=agent_id
        )

        db.commit()

        return {
            "id": agent.id,
            "name": agent.name,
            "status": agent.status.value,
            "last_active": agent.last_active.isoformat() if agent.last_active else None,
            "recovered": True
        }

    except ValueError as e:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to recover agent: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.get("/events/{agent_id}")
async def get_lifecycle_events(
    agent_id: int,
    limit: int = Query(50, ge=1, le=1000),
    db: Session = Depends(get_db_session)
) -> Dict[str, Any]:
    """Get lifecycle events for an agent"""
    try:
        events = AgentLifecycle.get_lifecycle_events(
            session=db,
            agent_id=agent_id,
            limit=limit
        )

        return {
            "agent_id": agent_id,
            "count": len(events),
            "events": events
        }

    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to get lifecycle events: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))
