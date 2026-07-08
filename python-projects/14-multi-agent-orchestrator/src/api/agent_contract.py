"""
Agent Contract Management API

REST API endpoints for managing contracts and SLAs between agents.
"""

from typing import Optional
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from src.core.database import get_db_session
from src.services.agent_contract import (
    AgentContract,
    ContractType,
    ContractStatus,
    ViolationType
)


router = APIRouter()


# Request/Response Models
class CreateContractRequest(BaseModel):
    contract_type: str = Field(..., description="Contract type")
    provider_agent_id: int = Field(..., description="Provider agent ID")
    consumer_agent_id: int = Field(..., description="Consumer agent ID")
    title: str = Field(..., description="Contract title")
    description: str = Field(..., description="Contract description")
    sla_terms: Optional[dict] = Field(None, description="SLA terms")
    obligations: Optional[dict] = Field(None, description="Obligations")
    duration_hours: Optional[int] = Field(None, description="Contract duration in hours")
    renewable: bool = Field(False, description="Whether renewable")
    penalty_terms: Optional[dict] = Field(None, description="Penalty terms")
    metadata: Optional[dict] = Field(None, description="Additional metadata")


class ActivateContractRequest(BaseModel):
    activating_agent_id: int = Field(..., description="Agent accepting contract")


class RecordPerformanceRequest(BaseModel):
    response_time: Optional[float] = Field(None, description="Response time in seconds")
    quality_score: Optional[float] = Field(None, description="Quality score (0-1)")
    throughput: Optional[int] = Field(None, description="Throughput value")
    success: bool = Field(True, description="Whether request succeeded")
    metadata: Optional[dict] = Field(None, description="Additional metrics")


class TerminateContractRequest(BaseModel):
    terminating_agent_id: int = Field(..., description="Agent terminating contract")
    reason: str = Field(..., description="Termination reason")
    immediate: bool = Field(False, description="Immediate termination")


class RenewContractRequest(BaseModel):
    duration_hours: Optional[int] = Field(None, description="New duration")
    updated_terms: Optional[dict] = Field(None, description="Updated SLA terms")


@router.post("/contracts")
def create_contract(
    request: CreateContractRequest,
    session: Session = Depends(get_db_session)
):
    """
    Create a contract between agents.

    Establishes a formal agreement with SLA terms, obligations, and penalties.
    Contract starts in PROPOSED status and must be activated by a party.
    """
    try:
        contract = AgentContract.create_contract(
            session=session,
            contract_type=request.contract_type,
            provider_agent_id=request.provider_agent_id,
            consumer_agent_id=request.consumer_agent_id,
            title=request.title,
            description=request.description,
            sla_terms=request.sla_terms,
            obligations=request.obligations,
            duration_hours=request.duration_hours,
            renewable=request.renewable,
            penalty_terms=request.penalty_terms,
            metadata=request.metadata
        )

        return {
            "success": True,
            "contract": contract,
            "message": f"Contract '{request.title}' created"
        }

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/contracts/{contract_id}/activate")
def activate_contract(
    contract_id: str,
    request: ActivateContractRequest,
    session: Session = Depends(get_db_session)
):
    """
    Activate a proposed contract.

    Changes contract status from PROPOSED to ACTIVE and starts the contract period.
    Only contract parties (provider or consumer) can activate.
    """
    try:
        contract = AgentContract.activate_contract(
            session=session,
            contract_id=contract_id,
            activating_agent_id=request.activating_agent_id
        )

        return {
            "success": True,
            "contract": contract,
            "message": "Contract activated"
        }

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/contracts/{contract_id}/performance")
def record_performance(
    contract_id: str,
    request: RecordPerformanceRequest,
    session: Session = Depends(get_db_session)
):
    """
    Record contract performance metrics.

    Tracks response time, quality, throughput, and success rate.
    Automatically detects SLA violations and updates contract status.
    """
    try:
        metrics = AgentContract.record_performance(
            session=session,
            contract_id=contract_id,
            response_time=request.response_time,
            quality_score=request.quality_score,
            throughput=request.throughput,
            success=request.success,
            metadata=request.metadata
        )

        return {
            "success": True,
            "metrics": metrics,
            "message": "Performance recorded"
        }

    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/contracts/{contract_id}/compliance")
def check_compliance(
    contract_id: str,
    session: Session = Depends(get_db_session)
):
    """
    Check contract compliance with SLA terms.

    Validates current performance against SLA requirements.
    Returns violations and compliance score.
    """
    try:
        compliance = AgentContract.check_compliance(
            session=session,
            contract_id=contract_id
        )

        return {
            "success": True,
            **compliance
        }

    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/contracts/{contract_id}/terminate")
def terminate_contract(
    contract_id: str,
    request: TerminateContractRequest,
    session: Session = Depends(get_db_session)
):
    """
    Terminate a contract.

    Ends the contract before expiration. Penalties may apply for early termination
    unless immediate termination is specified. Only contract parties can terminate.
    """
    try:
        result = AgentContract.terminate_contract(
            session=session,
            contract_id=contract_id,
            terminating_agent_id=request.terminating_agent_id,
            reason=request.reason,
            immediate=request.immediate
        )

        return {
            "success": True,
            **result,
            "message": "Contract terminated"
        }

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/contracts/{contract_id}/renew")
def renew_contract(
    contract_id: str,
    request: RenewContractRequest,
    session: Session = Depends(get_db_session)
):
    """
    Renew an expiring contract.

    Creates a new contract with the same parties and terms (or updated terms).
    Only works if contract is marked as renewable. Old contract is fulfilled.
    """
    try:
        renewed = AgentContract.renew_contract(
            session=session,
            contract_id=contract_id,
            duration_hours=request.duration_hours,
            updated_terms=request.updated_terms
        )

        return {
            "success": True,
            "renewed_contract": renewed,
            "message": "Contract renewed"
        }

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/contracts/{contract_id}")
def get_contract(
    contract_id: str,
    session: Session = Depends(get_db_session)
):
    """
    Get contract details.

    Returns complete contract information including SLA terms,
    performance metrics, violations, and current status.
    """
    try:
        contract = AgentContract.get_contract(
            session=session,
            contract_id=contract_id
        )

        return {
            "success": True,
            "contract": contract
        }

    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/agents/{agent_id}/contracts")
def list_agent_contracts(
    agent_id: int,
    status: Optional[str] = None,
    contract_type: Optional[str] = None,
    session: Session = Depends(get_db_session)
):
    """
    List contracts for an agent.

    Returns contracts where agent is provider or consumer,
    with optional filtering by status or type.
    """
    try:
        result = AgentContract.list_agent_contracts(
            session=session,
            agent_id=agent_id,
            status=status,
            contract_type=contract_type
        )

        return {
            "success": True,
            **result
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/contracts/{contract_id}/violations")
def get_violations(
    contract_id: str,
    severity: Optional[str] = None,
    session: Session = Depends(get_db_session)
):
    """
    Get contract violations.

    Returns all SLA violations for the contract with optional
    filtering by severity (low, medium, high, critical).
    """
    try:
        result = AgentContract.get_contract_violations(
            session=session,
            contract_id=contract_id,
            severity=severity
        )

        return {
            "success": True,
            **result
        }

    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/statistics")
def get_statistics(
    session: Session = Depends(get_db_session)
):
    """
    Get contract system statistics.

    Returns aggregate data including contract counts by status and type,
    violation statistics, and average performance scores.
    """
    try:
        stats = AgentContract.get_contract_statistics(session=session)

        return {
            "success": True,
            "statistics": stats
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/contract-types")
def list_contract_types():
    """
    List all contract types.

    Returns all available contract types for agent agreements.
    """
    return {
        "success": True,
        "contract_types": [
            {"type": ContractType.SERVICE_LEVEL_AGREEMENT, "description": "Service level agreement with SLA terms"},
            {"type": ContractType.COLLABORATION_AGREEMENT, "description": "Collaboration agreement between agents"},
            {"type": ContractType.RESOURCE_SHARING, "description": "Resource sharing agreement"},
            {"type": ContractType.DATA_EXCHANGE, "description": "Data exchange agreement"},
            {"type": ContractType.TASK_DELEGATION, "description": "Task delegation agreement"},
            {"type": ContractType.COALITION_AGREEMENT, "description": "Coalition membership agreement"}
        ]
    }


@router.get("/contract-statuses")
def list_contract_statuses():
    """
    List all contract statuses.

    Returns all possible contract lifecycle statuses.
    """
    return {
        "success": True,
        "statuses": [
            {"status": ContractStatus.DRAFT, "description": "Draft contract, not proposed yet"},
            {"status": ContractStatus.PROPOSED, "description": "Proposed, awaiting activation"},
            {"status": ContractStatus.ACTIVE, "description": "Active and being monitored"},
            {"status": ContractStatus.FULFILLED, "description": "Successfully completed"},
            {"status": ContractStatus.BREACHED, "description": "SLA violations exceeded threshold"},
            {"status": ContractStatus.TERMINATED, "description": "Terminated before completion"},
            {"status": ContractStatus.EXPIRED, "description": "Expired without renewal"}
        ]
    }


@router.get("/violation-types")
def list_violation_types():
    """
    List all SLA violation types.

    Returns all types of SLA violations that can be detected.
    """
    return {
        "success": True,
        "violation_types": [
            {"type": ViolationType.RESPONSE_TIME, "description": "Response time exceeds SLA"},
            {"type": ViolationType.THROUGHPUT, "description": "Throughput below SLA"},
            {"type": ViolationType.QUALITY, "description": "Quality score below SLA"},
            {"type": ViolationType.AVAILABILITY, "description": "Availability below SLA"},
            {"type": ViolationType.RESOURCE_LIMIT, "description": "Resource limits exceeded"},
            {"type": ViolationType.DEADLINE, "description": "Deadline missed"}
        ]
    }
