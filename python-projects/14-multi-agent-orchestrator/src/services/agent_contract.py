"""
Agent Contract Management Service

Manages formal agreements and SLAs between agents including obligations,
performance guarantees, and contract enforcement.
"""

from typing import Dict, List, Optional
from datetime import datetime, timedelta
from collections import defaultdict
import uuid


class ContractType:
    """Contract types"""
    SERVICE_LEVEL_AGREEMENT = "sla"
    COLLABORATION_AGREEMENT = "collaboration"
    RESOURCE_SHARING = "resource_sharing"
    DATA_EXCHANGE = "data_exchange"
    TASK_DELEGATION = "task_delegation"
    COALITION_AGREEMENT = "coalition"


class ContractStatus:
    """Contract statuses"""
    DRAFT = "draft"
    PROPOSED = "proposed"
    ACTIVE = "active"
    FULFILLED = "fulfilled"
    BREACHED = "breached"
    TERMINATED = "terminated"
    EXPIRED = "expired"


class ViolationType:
    """SLA violation types"""
    RESPONSE_TIME = "response_time"
    THROUGHPUT = "throughput"
    QUALITY = "quality"
    AVAILABILITY = "availability"
    RESOURCE_LIMIT = "resource_limit"
    DEADLINE = "deadline"


class AgentContract:
    """
    Agent Contract Management System

    Manages formal agreements between agents with SLAs, obligations,
    monitoring, and enforcement.
    """

    # In-memory storage
    _contracts = {}
    _contract_counter = 0

    _agent_contracts = defaultdict(list)  # agent_id -> [contract_ids]
    _violations = defaultdict(list)  # contract_id -> [violations]
    _metrics = defaultdict(dict)  # contract_id -> metrics

    _templates = {}  # template_id -> contract_template

    @staticmethod
    def create_contract(
        session,
        contract_type: str,
        provider_agent_id: int,
        consumer_agent_id: int,
        title: str,
        description: str,
        sla_terms: Optional[dict] = None,
        obligations: Optional[dict] = None,
        duration_hours: Optional[int] = None,
        renewable: bool = False,
        penalty_terms: Optional[dict] = None,
        metadata: Optional[dict] = None
    ) -> dict:
        """
        Create a contract between agents.

        Args:
            session: Database session
            contract_type: Type of contract
            provider_agent_id: Provider agent ID
            consumer_agent_id: Consumer agent ID
            title: Contract title
            description: Contract description
            sla_terms: SLA terms and metrics
            obligations: Obligations for each party
            duration_hours: Contract duration
            renewable: Whether contract is renewable
            penalty_terms: Penalties for violations
            metadata: Additional metadata

        Returns:
            Contract record
        """
        AgentContract._contract_counter += 1
        contract_id = f"contract_{AgentContract._contract_counter}"

        start_time = datetime.utcnow()
        end_time = None
        if duration_hours:
            end_time = start_time + timedelta(hours=duration_hours)

        contract = {
            "id": contract_id,
            "contract_type": contract_type,
            "provider_agent_id": provider_agent_id,
            "consumer_agent_id": consumer_agent_id,
            "title": title,
            "description": description,
            "sla_terms": sla_terms or {},
            "obligations": obligations or {
                "provider": [],
                "consumer": []
            },
            "status": ContractStatus.PROPOSED,
            "start_time": start_time.isoformat(),
            "end_time": end_time.isoformat() if end_time else None,
            "duration_hours": duration_hours,
            "renewable": renewable,
            "penalty_terms": penalty_terms or {},
            "metadata": metadata or {},
            "created_at": datetime.utcnow().isoformat(),
            "activated_at": None,
            "fulfilled_at": None,
            "violation_count": 0,
            "performance_score": 1.0
        }

        AgentContract._contracts[contract_id] = contract
        AgentContract._agent_contracts[provider_agent_id].append(contract_id)
        AgentContract._agent_contracts[consumer_agent_id].append(contract_id)

        # Initialize metrics
        AgentContract._metrics[contract_id] = {
            "total_requests": 0,
            "successful_requests": 0,
            "failed_requests": 0,
            "average_response_time": 0.0,
            "average_quality": 0.0,
            "uptime_percentage": 100.0,
            "last_updated": datetime.utcnow().isoformat()
        }

        return contract

    @staticmethod
    def activate_contract(
        session,
        contract_id: str,
        activating_agent_id: int
    ) -> dict:
        """
        Activate a proposed contract.

        Args:
            session: Database session
            contract_id: Contract ID
            activating_agent_id: Agent accepting contract

        Returns:
            Activated contract
        """
        if contract_id not in AgentContract._contracts:
            raise ValueError(f"Contract {contract_id} not found")

        contract = AgentContract._contracts[contract_id]

        if contract["status"] != ContractStatus.PROPOSED:
            raise ValueError(f"Contract must be in PROPOSED status, currently {contract['status']}")

        # Verify activating agent is a party
        if activating_agent_id not in [contract["provider_agent_id"], contract["consumer_agent_id"]]:
            raise ValueError("Only contract parties can activate")

        contract["status"] = ContractStatus.ACTIVE
        contract["activated_at"] = datetime.utcnow().isoformat()
        contract["start_time"] = datetime.utcnow().isoformat()

        # Recalculate end time if duration specified
        if contract["duration_hours"]:
            end_time = datetime.utcnow() + timedelta(hours=contract["duration_hours"])
            contract["end_time"] = end_time.isoformat()

        return contract

    @staticmethod
    def record_performance(
        session,
        contract_id: str,
        response_time: Optional[float] = None,
        quality_score: Optional[float] = None,
        throughput: Optional[int] = None,
        success: bool = True,
        metadata: Optional[dict] = None
    ) -> dict:
        """
        Record contract performance metrics.

        Args:
            session: Database session
            contract_id: Contract ID
            response_time: Response time in seconds
            quality_score: Quality score (0-1)
            throughput: Throughput value
            success: Whether request succeeded
            metadata: Additional metrics

        Returns:
            Updated metrics
        """
        if contract_id not in AgentContract._contracts:
            raise ValueError(f"Contract {contract_id} not found")

        contract = AgentContract._contracts[contract_id]
        metrics = AgentContract._metrics[contract_id]

        # Update counters
        metrics["total_requests"] += 1
        if success:
            metrics["successful_requests"] += 1
        else:
            metrics["failed_requests"] += 1

        # Update running averages
        if response_time is not None:
            current_avg = metrics["average_response_time"]
            total = metrics["total_requests"]
            metrics["average_response_time"] = (
                (current_avg * (total - 1) + response_time) / total
            )

        if quality_score is not None:
            current_avg = metrics["average_quality"]
            total = metrics["total_requests"]
            metrics["average_quality"] = (
                (current_avg * (total - 1) + quality_score) / total
            )

        metrics["last_updated"] = datetime.utcnow().isoformat()

        # Check for violations
        violations = AgentContract._check_sla_violations(contract, metrics)
        if violations:
            for violation in violations:
                AgentContract._record_violation(contract_id, violation)

        # Update performance score
        contract["performance_score"] = AgentContract._calculate_performance_score(
            contract, metrics
        )

        return metrics

    @staticmethod
    def check_compliance(
        session,
        contract_id: str
    ) -> dict:
        """
        Check contract compliance with SLA terms.

        Args:
            session: Database session
            contract_id: Contract ID

        Returns:
            Compliance report
        """
        if contract_id not in AgentContract._contracts:
            raise ValueError(f"Contract {contract_id} not found")

        contract = AgentContract._contracts[contract_id]
        metrics = AgentContract._metrics[contract_id]

        sla_terms = contract["sla_terms"]
        violations = []
        compliant_terms = []

        # Check response time SLA
        if "max_response_time" in sla_terms:
            max_allowed = sla_terms["max_response_time"]
            actual = metrics["average_response_time"]
            if actual > max_allowed:
                violations.append({
                    "term": "max_response_time",
                    "expected": max_allowed,
                    "actual": actual,
                    "severity": "high" if actual > max_allowed * 1.5 else "medium"
                })
            else:
                compliant_terms.append("max_response_time")

        # Check quality SLA
        if "min_quality" in sla_terms:
            min_required = sla_terms["min_quality"]
            actual = metrics["average_quality"]
            if actual < min_required:
                violations.append({
                    "term": "min_quality",
                    "expected": min_required,
                    "actual": actual,
                    "severity": "high"
                })
            else:
                compliant_terms.append("min_quality")

        # Check availability SLA
        if "min_availability" in sla_terms:
            min_required = sla_terms["min_availability"]
            actual = metrics["uptime_percentage"]
            if actual < min_required:
                violations.append({
                    "term": "min_availability",
                    "expected": min_required,
                    "actual": actual,
                    "severity": "critical"
                })
            else:
                compliant_terms.append("min_availability")

        is_compliant = len(violations) == 0

        return {
            "contract_id": contract_id,
            "is_compliant": is_compliant,
            "compliance_score": len(compliant_terms) / max(len(sla_terms), 1),
            "violations": violations,
            "compliant_terms": compliant_terms,
            "checked_at": datetime.utcnow().isoformat()
        }

    @staticmethod
    def terminate_contract(
        session,
        contract_id: str,
        terminating_agent_id: int,
        reason: str,
        immediate: bool = False
    ) -> dict:
        """
        Terminate a contract.

        Args:
            session: Database session
            contract_id: Contract ID
            terminating_agent_id: Agent terminating contract
            reason: Termination reason
            immediate: Whether to terminate immediately

        Returns:
            Termination result
        """
        if contract_id not in AgentContract._contracts:
            raise ValueError(f"Contract {contract_id} not found")

        contract = AgentContract._contracts[contract_id]

        # Verify terminating agent is a party
        if terminating_agent_id not in [contract["provider_agent_id"], contract["consumer_agent_id"]]:
            raise ValueError("Only contract parties can terminate")

        old_status = contract["status"]
        contract["status"] = ContractStatus.TERMINATED
        contract["metadata"]["termination"] = {
            "terminated_by": terminating_agent_id,
            "reason": reason,
            "immediate": immediate,
            "terminated_at": datetime.utcnow().isoformat(),
            "previous_status": old_status
        }

        # Apply penalties if applicable
        penalties = []
        if not immediate and contract["penalty_terms"]:
            penalties = AgentContract._apply_early_termination_penalty(
                contract, terminating_agent_id
            )

        return {
            "contract_id": contract_id,
            "terminated_at": datetime.utcnow().isoformat(),
            "terminated_by": terminating_agent_id,
            "reason": reason,
            "penalties_applied": penalties
        }

    @staticmethod
    def renew_contract(
        session,
        contract_id: str,
        duration_hours: Optional[int] = None,
        updated_terms: Optional[dict] = None
    ) -> dict:
        """
        Renew an expiring contract.

        Args:
            session: Database session
            contract_id: Contract ID
            duration_hours: New duration
            updated_terms: Updated SLA terms

        Returns:
            Renewed contract
        """
        if contract_id not in AgentContract._contracts:
            raise ValueError(f"Contract {contract_id} not found")

        contract = AgentContract._contracts[contract_id]

        if not contract["renewable"]:
            raise ValueError("Contract is not renewable")

        # Create new contract with same parties
        new_duration = duration_hours or contract["duration_hours"]

        renewed_contract = AgentContract.create_contract(
            session=session,
            contract_type=contract["contract_type"],
            provider_agent_id=contract["provider_agent_id"],
            consumer_agent_id=contract["consumer_agent_id"],
            title=f"{contract['title']} (Renewed)",
            description=contract["description"],
            sla_terms=updated_terms or contract["sla_terms"],
            obligations=contract["obligations"],
            duration_hours=new_duration,
            renewable=contract["renewable"],
            penalty_terms=contract["penalty_terms"],
            metadata={
                **contract["metadata"],
                "renewed_from": contract_id
            }
        )

        # Mark old contract as fulfilled
        contract["status"] = ContractStatus.FULFILLED
        contract["fulfilled_at"] = datetime.utcnow().isoformat()

        return renewed_contract

    @staticmethod
    def get_contract(
        session,
        contract_id: str
    ) -> dict:
        """
        Get contract details.

        Args:
            session: Database session
            contract_id: Contract ID

        Returns:
            Contract with metrics and violations
        """
        if contract_id not in AgentContract._contracts:
            raise ValueError(f"Contract {contract_id} not found")

        contract = AgentContract._contracts[contract_id]
        metrics = AgentContract._metrics.get(contract_id, {})
        violations = AgentContract._violations.get(contract_id, [])

        return {
            **contract,
            "metrics": metrics,
            "violations": violations,
            "violation_count": len(violations)
        }

    @staticmethod
    def list_agent_contracts(
        session,
        agent_id: int,
        status: Optional[str] = None,
        contract_type: Optional[str] = None
    ) -> dict:
        """
        List contracts for an agent.

        Args:
            session: Database session
            agent_id: Agent ID
            status: Filter by status
            contract_type: Filter by type

        Returns:
            Agent's contracts
        """
        contract_ids = AgentContract._agent_contracts.get(agent_id, [])
        contracts = [
            AgentContract._contracts[cid]
            for cid in contract_ids
            if cid in AgentContract._contracts
        ]

        if status:
            contracts = [c for c in contracts if c["status"] == status]

        if contract_type:
            contracts = [c for c in contracts if c["contract_type"] == contract_type]

        # Separate by role
        as_provider = [c for c in contracts if c["provider_agent_id"] == agent_id]
        as_consumer = [c for c in contracts if c["consumer_agent_id"] == agent_id]

        return {
            "agent_id": agent_id,
            "total_contracts": len(contracts),
            "as_provider": as_provider,
            "as_consumer": as_consumer
        }

    @staticmethod
    def get_contract_violations(
        session,
        contract_id: str,
        severity: Optional[str] = None
    ) -> dict:
        """
        Get violations for a contract.

        Args:
            session: Database session
            contract_id: Contract ID
            severity: Filter by severity

        Returns:
            Contract violations
        """
        if contract_id not in AgentContract._contracts:
            raise ValueError(f"Contract {contract_id} not found")

        violations = AgentContract._violations.get(contract_id, [])

        if severity:
            violations = [v for v in violations if v["severity"] == severity]

        # Group by type
        by_type = defaultdict(list)
        for violation in violations:
            by_type[violation["violation_type"]].append(violation)

        return {
            "contract_id": contract_id,
            "total_violations": len(violations),
            "violations": violations,
            "violations_by_type": dict(by_type)
        }

    @staticmethod
    def get_contract_statistics(session) -> dict:
        """
        Get contract system statistics.

        Args:
            session: Database session

        Returns:
            System statistics
        """
        total_contracts = len(AgentContract._contracts)

        # Count by status
        by_status = defaultdict(int)
        for contract in AgentContract._contracts.values():
            by_status[contract["status"]] += 1

        # Count by type
        by_type = defaultdict(int)
        for contract in AgentContract._contracts.values():
            by_type[contract["contract_type"]] += 1

        # Violation statistics
        total_violations = sum(len(v) for v in AgentContract._violations.values())
        contracts_with_violations = sum(1 for v in AgentContract._violations.values() if v)

        # Performance statistics
        avg_performance_score = (
            sum(c["performance_score"] for c in AgentContract._contracts.values()) / total_contracts
            if total_contracts > 0 else 0.0
        )

        return {
            "total_contracts": total_contracts,
            "contracts_by_status": dict(by_status),
            "contracts_by_type": dict(by_type),
            "total_violations": total_violations,
            "contracts_with_violations": contracts_with_violations,
            "average_performance_score": avg_performance_score
        }

    # Helper methods

    @staticmethod
    def _check_sla_violations(contract: dict, metrics: dict) -> List[dict]:
        """Check for SLA violations"""
        violations = []
        sla_terms = contract["sla_terms"]

        # Response time violation
        if "max_response_time" in sla_terms:
            if metrics["average_response_time"] > sla_terms["max_response_time"]:
                violations.append({
                    "violation_type": ViolationType.RESPONSE_TIME,
                    "expected": sla_terms["max_response_time"],
                    "actual": metrics["average_response_time"],
                    "severity": "high"
                })

        # Quality violation
        if "min_quality" in sla_terms:
            if metrics["average_quality"] < sla_terms["min_quality"]:
                violations.append({
                    "violation_type": ViolationType.QUALITY,
                    "expected": sla_terms["min_quality"],
                    "actual": metrics["average_quality"],
                    "severity": "high"
                })

        # Availability violation
        if "min_availability" in sla_terms:
            if metrics["uptime_percentage"] < sla_terms["min_availability"]:
                violations.append({
                    "violation_type": ViolationType.AVAILABILITY,
                    "expected": sla_terms["min_availability"],
                    "actual": metrics["uptime_percentage"],
                    "severity": "critical"
                })

        return violations

    @staticmethod
    def _record_violation(contract_id: str, violation: dict):
        """Record a contract violation"""
        violation_record = {
            **violation,
            "contract_id": contract_id,
            "detected_at": datetime.utcnow().isoformat(),
            "resolved": False
        }

        AgentContract._violations[contract_id].append(violation_record)
        AgentContract._contracts[contract_id]["violation_count"] += 1

        # Check if contract should be marked as breached
        violation_count = len(AgentContract._violations[contract_id])
        if violation_count >= 3:  # Threshold for breach
            AgentContract._contracts[contract_id]["status"] = ContractStatus.BREACHED

    @staticmethod
    def _calculate_performance_score(contract: dict, metrics: dict) -> float:
        """Calculate overall performance score"""
        scores = []

        sla_terms = contract["sla_terms"]

        # Response time score
        if "max_response_time" in sla_terms:
            max_allowed = sla_terms["max_response_time"]
            actual = metrics["average_response_time"]
            score = max(0, 1 - (actual / max_allowed - 1))
            scores.append(score)

        # Quality score
        if "min_quality" in sla_terms:
            scores.append(metrics["average_quality"])

        # Success rate score
        total = metrics["total_requests"]
        if total > 0:
            success_rate = metrics["successful_requests"] / total
            scores.append(success_rate)

        return sum(scores) / len(scores) if scores else 1.0

    @staticmethod
    def _apply_early_termination_penalty(contract: dict, terminating_agent_id: int) -> List[dict]:
        """Apply penalties for early termination"""
        penalties = []

        penalty_terms = contract.get("penalty_terms", {})
        if "early_termination_fee" in penalty_terms:
            penalties.append({
                "type": "early_termination_fee",
                "agent_id": terminating_agent_id,
                "amount": penalty_terms["early_termination_fee"],
                "applied_at": datetime.utcnow().isoformat()
            })

        return penalties
