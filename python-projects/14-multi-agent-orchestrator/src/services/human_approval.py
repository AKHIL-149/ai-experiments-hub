"""
Human Approval Gate Service

Manages human-in-the-loop approval gates for critical operations in agent workflows.
Allows workflows to pause and wait for human approval before proceeding.
"""

from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta
from collections import defaultdict


class ApprovalType:
    """Types of approval requests"""
    EXECUTE_TASK = "execute_task"
    DEPLOY_CODE = "deploy_code"
    SPEND_BUDGET = "spend_budget"
    DATA_ACCESS = "data_access"
    EXTERNAL_API = "external_api"
    DELETE_DATA = "delete_data"
    MODIFY_CONFIG = "modify_config"
    ESCALATE_ISSUE = "escalate_issue"
    GENERAL = "general"


class ApprovalStatus:
    """Approval request statuses"""
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXPIRED = "expired"
    CANCELLED = "cancelled"


class ApprovalPriority:
    """Approval priority levels"""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class HumanApproval:
    """
    Human Approval Gate Service

    Manages approval gates that pause agent workflows until a human
    reviews and approves or rejects the requested action.
    """

    # In-memory storage
    _approval_requests = {}
    _request_counter = 0
    _approval_history = []
    _user_approvals = defaultdict(list)
    _workflow_approvals = defaultdict(list)

    @staticmethod
    def _generate_request_id() -> str:
        """Generate unique approval request ID"""
        HumanApproval._request_counter += 1
        return f"approval_{HumanApproval._request_counter}"

    @staticmethod
    def create_approval_request(
        session,
        workflow_id: str,
        agent_id: int,
        approval_type: str,
        title: str,
        description: str,
        context: dict,
        priority: str = ApprovalPriority.MEDIUM,
        required_approvers: Optional[List[str]] = None,
        timeout_minutes: int = 60,
        auto_approve_conditions: Optional[dict] = None,
        metadata: Optional[dict] = None
    ) -> dict:
        """
        Create human approval request.

        Pauses workflow execution until human reviews and approves or rejects.
        """
        request_id = HumanApproval._generate_request_id()

        approval_request = {
            "id": request_id,
            "workflow_id": workflow_id,
            "agent_id": agent_id,
            "approval_type": approval_type,
            "title": title,
            "description": description,
            "context": context,
            "priority": priority,
            "required_approvers": required_approvers or [],
            "timeout_minutes": timeout_minutes,
            "auto_approve_conditions": auto_approve_conditions or {},
            "metadata": metadata or {},
            "status": ApprovalStatus.PENDING,
            "approvals": [],
            "rejections": [],
            "created_at": datetime.utcnow().isoformat(),
            "expires_at": (datetime.utcnow() + timedelta(minutes=timeout_minutes)).isoformat(),
            "approved_at": None,
            "approved_by": None,
            "rejection_reason": None
        }

        # Check auto-approve conditions
        if HumanApproval._check_auto_approve(approval_request):
            approval_request["status"] = ApprovalStatus.APPROVED
            approval_request["approved_at"] = datetime.utcnow().isoformat()
            approval_request["approved_by"] = "auto_approved"
            approval_request["auto_approved"] = True

        HumanApproval._approval_requests[request_id] = approval_request
        HumanApproval._workflow_approvals[workflow_id].append(request_id)

        return approval_request

    @staticmethod
    def _check_auto_approve(approval_request: dict) -> bool:
        """
        Check if approval request meets auto-approve conditions.
        """
        conditions = approval_request.get("auto_approve_conditions", {})
        if not conditions:
            return False

        context = approval_request["context"]

        # Check budget threshold
        if "max_budget" in conditions:
            budget = context.get("budget", 0)
            if budget <= conditions["max_budget"]:
                return True

        # Check risk level
        if "max_risk_level" in conditions:
            risk = context.get("risk_level", "high")
            allowed_risks = ["low", "medium", "high"]
            max_risk_idx = allowed_risks.index(conditions["max_risk_level"])
            current_risk_idx = allowed_risks.index(risk) if risk in allowed_risks else 2

            if current_risk_idx <= max_risk_idx:
                return True

        # Check data size
        if "max_data_size_mb" in conditions:
            data_size = context.get("data_size_mb", 0)
            if data_size <= conditions["max_data_size_mb"]:
                return True

        return False

    @staticmethod
    def approve_request(
        session,
        request_id: str,
        approver_user_id: str,
        approver_name: str,
        comments: Optional[str] = None,
        metadata: Optional[dict] = None
    ) -> dict:
        """
        Approve an approval request.

        Marks the request as approved and allows workflow to continue.
        """
        if request_id not in HumanApproval._approval_requests:
            raise ValueError(f"Approval request {request_id} not found")

        approval_request = HumanApproval._approval_requests[request_id]

        if approval_request["status"] != ApprovalStatus.PENDING:
            raise ValueError(f"Cannot approve request with status {approval_request['status']}")

        # Check if expired
        expires_at = datetime.fromisoformat(approval_request["expires_at"])
        if datetime.utcnow() > expires_at:
            approval_request["status"] = ApprovalStatus.EXPIRED
            raise ValueError("Approval request has expired")

        # Record approval
        approval = {
            "approver_user_id": approver_user_id,
            "approver_name": approver_name,
            "comments": comments,
            "metadata": metadata or {},
            "approved_at": datetime.utcnow().isoformat()
        }

        approval_request["approvals"].append(approval)

        # Check if all required approvers have approved
        required_approvers = approval_request["required_approvers"]
        if required_approvers:
            approved_by = [a["approver_user_id"] for a in approval_request["approvals"]]
            all_approved = all(req in approved_by for req in required_approvers)

            if not all_approved:
                # Still waiting for other approvers
                return approval_request

        # Mark as approved
        approval_request["status"] = ApprovalStatus.APPROVED
        approval_request["approved_at"] = datetime.utcnow().isoformat()
        approval_request["approved_by"] = approver_user_id

        # Record in history
        HumanApproval._approval_history.append({
            "request_id": request_id,
            "workflow_id": approval_request["workflow_id"],
            "agent_id": approval_request["agent_id"],
            "approval_type": approval_request["approval_type"],
            "status": ApprovalStatus.APPROVED,
            "approver": approver_user_id,
            "approved_at": approval_request["approved_at"]
        })

        HumanApproval._user_approvals[approver_user_id].append(request_id)

        return approval_request

    @staticmethod
    def reject_request(
        session,
        request_id: str,
        rejector_user_id: str,
        rejector_name: str,
        reason: str,
        metadata: Optional[dict] = None
    ) -> dict:
        """
        Reject an approval request.

        Marks the request as rejected and prevents workflow from continuing.
        """
        if request_id not in HumanApproval._approval_requests:
            raise ValueError(f"Approval request {request_id} not found")

        approval_request = HumanApproval._approval_requests[request_id]

        if approval_request["status"] != ApprovalStatus.PENDING:
            raise ValueError(f"Cannot reject request with status {approval_request['status']}")

        # Check if expired
        expires_at = datetime.fromisoformat(approval_request["expires_at"])
        if datetime.utcnow() > expires_at:
            approval_request["status"] = ApprovalStatus.EXPIRED
            raise ValueError("Approval request has expired")

        # Record rejection
        rejection = {
            "rejector_user_id": rejector_user_id,
            "rejector_name": rejector_name,
            "reason": reason,
            "metadata": metadata or {},
            "rejected_at": datetime.utcnow().isoformat()
        }

        approval_request["rejections"].append(rejection)
        approval_request["status"] = ApprovalStatus.REJECTED
        approval_request["rejection_reason"] = reason

        # Record in history
        HumanApproval._approval_history.append({
            "request_id": request_id,
            "workflow_id": approval_request["workflow_id"],
            "agent_id": approval_request["agent_id"],
            "approval_type": approval_request["approval_type"],
            "status": ApprovalStatus.REJECTED,
            "rejector": rejector_user_id,
            "rejected_at": rejection["rejected_at"],
            "reason": reason
        })

        HumanApproval._user_approvals[rejector_user_id].append(request_id)

        return approval_request

    @staticmethod
    def cancel_request(
        session,
        request_id: str,
        cancelled_by: str,
        reason: str
    ) -> dict:
        """
        Cancel an approval request.

        Allows workflow or system to cancel a pending approval request.
        """
        if request_id not in HumanApproval._approval_requests:
            raise ValueError(f"Approval request {request_id} not found")

        approval_request = HumanApproval._approval_requests[request_id]

        if approval_request["status"] != ApprovalStatus.PENDING:
            raise ValueError(f"Cannot cancel request with status {approval_request['status']}")

        approval_request["status"] = ApprovalStatus.CANCELLED
        approval_request["cancelled_by"] = cancelled_by
        approval_request["cancellation_reason"] = reason
        approval_request["cancelled_at"] = datetime.utcnow().isoformat()

        return approval_request

    @staticmethod
    def check_expired_requests(session) -> List[dict]:
        """
        Check for expired approval requests.

        Automatically marks expired requests and returns them.
        """
        now = datetime.utcnow()
        expired_requests = []

        for request_id, request in HumanApproval._approval_requests.items():
            if request["status"] == ApprovalStatus.PENDING:
                expires_at = datetime.fromisoformat(request["expires_at"])

                if now > expires_at:
                    request["status"] = ApprovalStatus.EXPIRED
                    expired_requests.append(request)

        return expired_requests

    @staticmethod
    def get_approval_request(
        session,
        request_id: str
    ) -> dict:
        """Get approval request details."""
        if request_id not in HumanApproval._approval_requests:
            raise ValueError(f"Approval request {request_id} not found")

        request = HumanApproval._approval_requests[request_id]

        # Check if expired
        if request["status"] == ApprovalStatus.PENDING:
            expires_at = datetime.fromisoformat(request["expires_at"])
            if datetime.utcnow() > expires_at:
                request["status"] = ApprovalStatus.EXPIRED

        return request

    @staticmethod
    def list_approval_requests(
        session,
        status: Optional[str] = None,
        approval_type: Optional[str] = None,
        priority: Optional[str] = None,
        workflow_id: Optional[str] = None,
        agent_id: Optional[int] = None
    ) -> dict:
        """
        List approval requests with filtering.

        Returns requests matching the filter criteria.
        """
        # Check for expired requests first
        HumanApproval.check_expired_requests(session)

        requests = list(HumanApproval._approval_requests.values())

        # Apply filters
        if status:
            requests = [r for r in requests if r["status"] == status]

        if approval_type:
            requests = [r for r in requests if r["approval_type"] == approval_type]

        if priority:
            requests = [r for r in requests if r["priority"] == priority]

        if workflow_id:
            requests = [r for r in requests if r["workflow_id"] == workflow_id]

        if agent_id:
            requests = [r for r in requests if r["agent_id"] == agent_id]

        # Sort by priority and creation time
        priority_order = {
            ApprovalPriority.CRITICAL: 0,
            ApprovalPriority.HIGH: 1,
            ApprovalPriority.MEDIUM: 2,
            ApprovalPriority.LOW: 3
        }

        requests.sort(
            key=lambda r: (
                priority_order.get(r["priority"], 4),
                r["created_at"]
            )
        )

        return {
            "requests": requests,
            "total": len(requests)
        }

    @staticmethod
    def get_pending_approvals(
        session,
        approver_user_id: Optional[str] = None
    ) -> dict:
        """
        Get pending approval requests.

        Returns all pending requests, optionally filtered by approver.
        """
        HumanApproval.check_expired_requests(session)

        pending = [
            r for r in HumanApproval._approval_requests.values()
            if r["status"] == ApprovalStatus.PENDING
        ]

        # Filter by approver if specified
        if approver_user_id:
            pending = [
                r for r in pending
                if not r["required_approvers"] or approver_user_id in r["required_approvers"]
            ]

        # Sort by priority
        priority_order = {
            ApprovalPriority.CRITICAL: 0,
            ApprovalPriority.HIGH: 1,
            ApprovalPriority.MEDIUM: 2,
            ApprovalPriority.LOW: 3
        }

        pending.sort(
            key=lambda r: (
                priority_order.get(r["priority"], 4),
                r["created_at"]
            )
        )

        return {
            "pending_requests": pending,
            "total": len(pending),
            "by_priority": {
                ApprovalPriority.CRITICAL: sum(1 for r in pending if r["priority"] == ApprovalPriority.CRITICAL),
                ApprovalPriority.HIGH: sum(1 for r in pending if r["priority"] == ApprovalPriority.HIGH),
                ApprovalPriority.MEDIUM: sum(1 for r in pending if r["priority"] == ApprovalPriority.MEDIUM),
                ApprovalPriority.LOW: sum(1 for r in pending if r["priority"] == ApprovalPriority.LOW)
            }
        }

    @staticmethod
    def get_user_approval_history(
        session,
        user_id: str,
        limit: int = 20
    ) -> dict:
        """
        Get user's approval history.

        Returns all approvals and rejections by a specific user.
        """
        request_ids = HumanApproval._user_approvals.get(user_id, [])

        requests = []
        for request_id in request_ids[-limit:]:
            if request_id in HumanApproval._approval_requests:
                requests.append(HumanApproval._approval_requests[request_id])

        # Calculate statistics
        total_actions = len(request_ids)
        approved = sum(1 for r in requests if r["status"] == ApprovalStatus.APPROVED)
        rejected = sum(1 for r in requests if r["status"] == ApprovalStatus.REJECTED)

        return {
            "user_id": user_id,
            "total_actions": total_actions,
            "approved_count": approved,
            "rejected_count": rejected,
            "approval_rate": approved / total_actions if total_actions > 0 else 0,
            "recent_requests": requests
        }

    @staticmethod
    def get_workflow_approvals(
        session,
        workflow_id: str
    ) -> dict:
        """
        Get all approval requests for a workflow.

        Returns complete approval history for a specific workflow.
        """
        request_ids = HumanApproval._workflow_approvals.get(workflow_id, [])

        requests = []
        for request_id in request_ids:
            if request_id in HumanApproval._approval_requests:
                requests.append(HumanApproval._approval_requests[request_id])

        # Calculate statistics
        total = len(requests)
        pending = sum(1 for r in requests if r["status"] == ApprovalStatus.PENDING)
        approved = sum(1 for r in requests if r["status"] == ApprovalStatus.APPROVED)
        rejected = sum(1 for r in requests if r["status"] == ApprovalStatus.REJECTED)
        expired = sum(1 for r in requests if r["status"] == ApprovalStatus.EXPIRED)

        return {
            "workflow_id": workflow_id,
            "total_requests": total,
            "pending": pending,
            "approved": approved,
            "rejected": rejected,
            "expired": expired,
            "requests": requests
        }

    @staticmethod
    def get_approval_statistics(session) -> dict:
        """
        Get approval system statistics.

        Returns aggregate metrics about all approval requests.
        """
        all_requests = list(HumanApproval._approval_requests.values())

        # Status distribution
        status_dist = defaultdict(int)
        for r in all_requests:
            status_dist[r["status"]] += 1

        # Type distribution
        type_dist = defaultdict(int)
        for r in all_requests:
            type_dist[r["approval_type"]] += 1

        # Priority distribution
        priority_dist = defaultdict(int)
        for r in all_requests:
            priority_dist[r["priority"]] += 1

        # Calculate metrics
        total = len(all_requests)
        approved = status_dist[ApprovalStatus.APPROVED]
        rejected = status_dist[ApprovalStatus.REJECTED]
        pending = status_dist[ApprovalStatus.PENDING]

        # Average response time for approved/rejected requests
        response_times = []
        for r in all_requests:
            if r["status"] in [ApprovalStatus.APPROVED, ApprovalStatus.REJECTED]:
                created = datetime.fromisoformat(r["created_at"])
                responded = datetime.fromisoformat(
                    r.get("approved_at") or r["rejections"][0]["rejected_at"]
                )
                response_time = (responded - created).total_seconds()
                response_times.append(response_time)

        avg_response_time = sum(response_times) / len(response_times) if response_times else 0

        return {
            "total_requests": total,
            "status_distribution": dict(status_dist),
            "type_distribution": dict(type_dist),
            "priority_distribution": dict(priority_dist),
            "approval_rate": approved / total if total > 0 else 0,
            "rejection_rate": rejected / total if total > 0 else 0,
            "pending_count": pending,
            "average_response_time_seconds": avg_response_time,
            "total_unique_approvers": len(HumanApproval._user_approvals),
            "total_workflows_with_approvals": len(HumanApproval._workflow_approvals)
        }
