"""
Data Privacy and Compliance Service

Provides GDPR/CCPA compliance, data subject rights management, consent tracking,
data anonymization, and privacy audit trails.
"""

from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from collections import defaultdict
from enum import Enum
import hashlib
import random
import string


class ConsentStatus(str, Enum):
    """Consent status"""
    GRANTED = "granted"
    DENIED = "denied"
    WITHDRAWN = "withdrawn"
    EXPIRED = "expired"


class ConsentPurpose(str, Enum):
    """Consent purpose types"""
    NECESSARY = "necessary"
    FUNCTIONAL = "functional"
    ANALYTICS = "analytics"
    MARKETING = "marketing"
    PERSONALIZATION = "personalization"
    THIRD_PARTY = "third_party"


class DataSubjectRight(str, Enum):
    """GDPR data subject rights"""
    ACCESS = "access"  # Right to access
    RECTIFICATION = "rectification"  # Right to rectification
    ERASURE = "erasure"  # Right to erasure (right to be forgotten)
    PORTABILITY = "portability"  # Right to data portability
    RESTRICTION = "restriction"  # Right to restriction of processing
    OBJECTION = "objection"  # Right to object
    AUTOMATED_DECISION = "automated_decision"  # Rights related to automated decision making


class RequestStatus(str, Enum):
    """Data subject request status"""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    REJECTED = "rejected"
    EXPIRED = "expired"


class DataCategory(str, Enum):
    """Data category types"""
    PERSONAL = "personal"
    SENSITIVE = "sensitive"
    FINANCIAL = "financial"
    HEALTH = "health"
    BEHAVIORAL = "behavioral"
    TECHNICAL = "technical"


class AnonymizationMethod(str, Enum):
    """Anonymization methods"""
    HASH = "hash"
    MASK = "mask"
    GENERALIZE = "generalize"
    SUPPRESS = "suppress"
    PSEUDONYMIZE = "pseudonymize"


class BreachSeverity(str, Enum):
    """Data breach severity"""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class DataPrivacy:
    """Data Privacy and Compliance management"""

    # In-memory storage
    _consents: Dict[str, Dict] = {}
    _data_subject_requests: Dict[str, Dict] = {}
    _retention_policies: Dict[str, Dict] = {}
    _anonymization_rules: Dict[str, Dict] = {}
    _privacy_audits: List[Dict] = []
    _data_breaches: Dict[str, Dict] = {}
    _cookie_consents: Dict[str, Dict] = {}
    _privacy_notices: Dict[str, Dict] = {}

    @staticmethod
    def record_consent(
        session,
        consent_id: str,
        user_id: str,
        purpose: ConsentPurpose,
        status: ConsentStatus = ConsentStatus.GRANTED,
        expires_at: Optional[str] = None,
        metadata: Optional[Dict] = None
    ) -> dict:
        """Record user consent for data processing."""
        consent = {
            "consent_id": consent_id,
            "user_id": user_id,
            "purpose": purpose,
            "status": status,
            "granted_at": datetime.utcnow().isoformat() if status == ConsentStatus.GRANTED else None,
            "denied_at": datetime.utcnow().isoformat() if status == ConsentStatus.DENIED else None,
            "withdrawn_at": None,
            "expires_at": expires_at,
            "metadata": metadata or {},
            "created_at": datetime.utcnow().isoformat(),
            "updated_at": datetime.utcnow().isoformat(),
            "ip_address": metadata.get("ip_address") if metadata else None,
            "user_agent": metadata.get("user_agent") if metadata else None,
            "version": 1
        }

        DataPrivacy._consents[consent_id] = consent

        # Log audit
        DataPrivacy._log_privacy_audit(
            action="consent_recorded",
            user_id=user_id,
            details={
                "consent_id": consent_id,
                "purpose": purpose,
                "status": status
            }
        )

        return consent

    @staticmethod
    def withdraw_consent(session, consent_id: str, user_id: str) -> dict:
        """Withdraw previously granted consent."""
        consent = DataPrivacy._consents.get(consent_id)
        if not consent:
            raise ValueError(f"Consent not found: {consent_id}")

        if consent["user_id"] != user_id:
            raise ValueError("User ID mismatch")

        consent["status"] = ConsentStatus.WITHDRAWN
        consent["withdrawn_at"] = datetime.utcnow().isoformat()
        consent["updated_at"] = datetime.utcnow().isoformat()

        # Log audit
        DataPrivacy._log_privacy_audit(
            action="consent_withdrawn",
            user_id=user_id,
            details={"consent_id": consent_id}
        )

        return consent

    @staticmethod
    def check_consent(session, user_id: str, purpose: ConsentPurpose) -> dict:
        """Check if user has granted consent for a specific purpose."""
        # Find active consents for user and purpose
        user_consents = [
            c for c in DataPrivacy._consents.values()
            if c["user_id"] == user_id and c["purpose"] == purpose
        ]

        # Check if any active consent exists
        has_consent = False
        active_consent = None

        for consent in user_consents:
            if consent["status"] == ConsentStatus.GRANTED:
                # Check expiration
                if consent["expires_at"]:
                    if datetime.utcnow().isoformat() < consent["expires_at"]:
                        has_consent = True
                        active_consent = consent
                        break
                else:
                    has_consent = True
                    active_consent = consent
                    break

        return {
            "user_id": user_id,
            "purpose": purpose,
            "has_consent": has_consent,
            "consent": active_consent,
            "checked_at": datetime.utcnow().isoformat()
        }

    @staticmethod
    def create_data_subject_request(
        session,
        request_id: str,
        user_id: str,
        right_type: DataSubjectRight,
        description: Optional[str] = None,
        metadata: Optional[Dict] = None
    ) -> dict:
        """Create a data subject rights request (GDPR)."""
        request = {
            "request_id": request_id,
            "user_id": user_id,
            "right_type": right_type,
            "description": description or "",
            "status": RequestStatus.PENDING,
            "metadata": metadata or {},
            "created_at": datetime.utcnow().isoformat(),
            "updated_at": datetime.utcnow().isoformat(),
            "due_date": (datetime.utcnow() + timedelta(days=30)).isoformat(),  # GDPR: 30 days
            "completed_at": None,
            "response_data": None,
            "rejection_reason": None
        }

        DataPrivacy._data_subject_requests[request_id] = request

        # Log audit
        DataPrivacy._log_privacy_audit(
            action="dsr_created",
            user_id=user_id,
            details={
                "request_id": request_id,
                "right_type": right_type
            }
        )

        return request

    @staticmethod
    def process_data_subject_request(
        session,
        request_id: str,
        response_data: Optional[Dict] = None
    ) -> dict:
        """Process and complete a data subject request."""
        request = DataPrivacy._data_subject_requests.get(request_id)
        if not request:
            raise ValueError(f"Request not found: {request_id}")

        request["status"] = RequestStatus.IN_PROGRESS
        request["updated_at"] = datetime.utcnow().isoformat()

        # Simulate processing based on right type
        if request["right_type"] == DataSubjectRight.ACCESS:
            # Compile user data
            request["response_data"] = {
                "personal_data": "User data compiled",
                "processing_purposes": ["service_provision", "analytics"],
                "data_categories": ["personal", "behavioral"],
                "recipients": ["internal_systems"],
                "retention_period": "2 years"
            }
        elif request["right_type"] == DataSubjectRight.ERASURE:
            # Mark for deletion
            request["response_data"] = {
                "deleted_records": 42,
                "deleted_at": datetime.utcnow().isoformat()
            }
        elif request["right_type"] == DataSubjectRight.PORTABILITY:
            # Prepare data export
            request["response_data"] = {
                "export_url": f"/exports/{request['user_id']}.json",
                "format": "JSON",
                "size_bytes": 1024000
            }

        request["status"] = RequestStatus.COMPLETED
        request["completed_at"] = datetime.utcnow().isoformat()
        request["updated_at"] = datetime.utcnow().isoformat()

        # Log audit
        DataPrivacy._log_privacy_audit(
            action="dsr_completed",
            user_id=request["user_id"],
            details={"request_id": request_id}
        )

        return request

    @staticmethod
    def create_retention_policy(
        session,
        policy_id: str,
        name: str,
        data_category: DataCategory,
        retention_days: int,
        description: Optional[str] = None,
        auto_delete: bool = True
    ) -> dict:
        """Create a data retention policy."""
        if policy_id in DataPrivacy._retention_policies:
            raise ValueError(f"Policy already exists: {policy_id}")

        policy = {
            "policy_id": policy_id,
            "name": name,
            "data_category": data_category,
            "retention_days": retention_days,
            "description": description or "",
            "auto_delete": auto_delete,
            "created_at": datetime.utcnow().isoformat(),
            "updated_at": datetime.utcnow().isoformat(),
            "is_active": True,
            "records_processed": 0,
            "records_deleted": 0
        }

        DataPrivacy._retention_policies[policy_id] = policy

        return policy

    @staticmethod
    def anonymize_data(
        session,
        data: Dict,
        fields: List[str],
        method: AnonymizationMethod = AnonymizationMethod.HASH
    ) -> dict:
        """Anonymize sensitive data fields."""
        anonymized = data.copy()

        for field in fields:
            if field in anonymized:
                original_value = str(anonymized[field])

                if method == AnonymizationMethod.HASH:
                    anonymized[field] = hashlib.sha256(original_value.encode()).hexdigest()[:16]
                elif method == AnonymizationMethod.MASK:
                    anonymized[field] = "*" * len(original_value)
                elif method == AnonymizationMethod.GENERALIZE:
                    # Generalize (e.g., age 25 -> 20-30)
                    if original_value.isdigit():
                        age = int(original_value)
                        anonymized[field] = f"{(age // 10) * 10}-{((age // 10) + 1) * 10}"
                    else:
                        anonymized[field] = "GENERALIZED"
                elif method == AnonymizationMethod.SUPPRESS:
                    anonymized[field] = "[SUPPRESSED]"
                elif method == AnonymizationMethod.PSEUDONYMIZE:
                    # Generate random pseudonym
                    anonymized[field] = ''.join(random.choices(string.ascii_letters + string.digits, k=12))

        # Log audit
        DataPrivacy._log_privacy_audit(
            action="data_anonymized",
            user_id=None,
            details={
                "fields": fields,
                "method": method
            }
        )

        return {
            "original_data": data,
            "anonymized_data": anonymized,
            "fields_anonymized": fields,
            "method": method,
            "anonymized_at": datetime.utcnow().isoformat()
        }

    @staticmethod
    def report_data_breach(
        session,
        breach_id: str,
        description: str,
        severity: BreachSeverity,
        affected_records: int,
        data_categories: List[DataCategory],
        discovered_at: Optional[str] = None,
        metadata: Optional[Dict] = None
    ) -> dict:
        """Report a data breach incident."""
        if breach_id in DataPrivacy._data_breaches:
            raise ValueError(f"Breach already reported: {breach_id}")

        breach = {
            "breach_id": breach_id,
            "description": description,
            "severity": severity,
            "affected_records": affected_records,
            "data_categories": data_categories,
            "discovered_at": discovered_at or datetime.utcnow().isoformat(),
            "reported_at": datetime.utcnow().isoformat(),
            "metadata": metadata or {},
            "status": "reported",
            "notification_required": severity in [BreachSeverity.HIGH, BreachSeverity.CRITICAL],
            "authority_notified": False,
            "users_notified": False,
            "containment_actions": [],
            "remediation_status": "pending"
        }

        DataPrivacy._data_breaches[breach_id] = breach

        # Log audit
        DataPrivacy._log_privacy_audit(
            action="breach_reported",
            user_id=None,
            details={
                "breach_id": breach_id,
                "severity": severity,
                "affected_records": affected_records
            }
        )

        return breach

    @staticmethod
    def update_breach_status(
        session,
        breach_id: str,
        containment_actions: Optional[List[str]] = None,
        authority_notified: Optional[bool] = None,
        users_notified: Optional[bool] = None,
        remediation_status: Optional[str] = None
    ) -> dict:
        """Update data breach status and actions."""
        breach = DataPrivacy._data_breaches.get(breach_id)
        if not breach:
            raise ValueError(f"Breach not found: {breach_id}")

        if containment_actions:
            breach["containment_actions"].extend(containment_actions)
        if authority_notified is not None:
            breach["authority_notified"] = authority_notified
        if users_notified is not None:
            breach["users_notified"] = users_notified
        if remediation_status:
            breach["remediation_status"] = remediation_status

        return breach

    @staticmethod
    def _log_privacy_audit(action: str, user_id: Optional[str], details: Dict):
        """Log privacy-related action to audit trail."""
        audit_entry = {
            "audit_id": f"audit_{len(DataPrivacy._privacy_audits)}_{datetime.utcnow().timestamp()}",
            "action": action,
            "user_id": user_id,
            "details": details,
            "timestamp": datetime.utcnow().isoformat(),
            "ip_address": details.get("ip_address"),
            "user_agent": details.get("user_agent")
        }

        DataPrivacy._privacy_audits.append(audit_entry)

        # Keep only last 100000 audit entries
        DataPrivacy._privacy_audits = DataPrivacy._privacy_audits[-100000:]

    @staticmethod
    def get_user_privacy_dashboard(session, user_id: str) -> dict:
        """Get comprehensive privacy dashboard for a user."""
        # Get user consents
        user_consents = [
            c for c in DataPrivacy._consents.values()
            if c["user_id"] == user_id
        ]

        active_consents = [
            c for c in user_consents
            if c["status"] == ConsentStatus.GRANTED
        ]

        # Get user requests
        user_requests = [
            r for r in DataPrivacy._data_subject_requests.values()
            if r["user_id"] == user_id
        ]

        # Get audit trail for user
        user_audits = [
            a for a in DataPrivacy._privacy_audits
            if a["user_id"] == user_id
        ][-50:]  # Last 50 entries

        return {
            "user_id": user_id,
            "consents": {
                "total": len(user_consents),
                "active": len(active_consents),
                "by_purpose": {
                    purpose: len([c for c in active_consents if c["purpose"] == purpose])
                    for purpose in ConsentPurpose
                }
            },
            "data_subject_requests": {
                "total": len(user_requests),
                "pending": len([r for r in user_requests if r["status"] == RequestStatus.PENDING]),
                "completed": len([r for r in user_requests if r["status"] == RequestStatus.COMPLETED])
            },
            "audit_trail": user_audits,
            "data_categories": ["personal", "behavioral", "technical"],
            "retention_info": {
                "retention_period": "2 years",
                "auto_delete": True
            },
            "generated_at": datetime.utcnow().isoformat()
        }

    @staticmethod
    def get_consent_statistics(session) -> dict:
        """Get consent management statistics."""
        total_consents = len(DataPrivacy._consents)
        granted = sum(1 for c in DataPrivacy._consents.values() if c["status"] == ConsentStatus.GRANTED)
        withdrawn = sum(1 for c in DataPrivacy._consents.values() if c["status"] == ConsentStatus.WITHDRAWN)

        # By purpose
        by_purpose = defaultdict(int)
        for consent in DataPrivacy._consents.values():
            by_purpose[consent["purpose"]] += 1

        return {
            "total_consents": total_consents,
            "granted": granted,
            "denied": total_consents - granted - withdrawn,
            "withdrawn": withdrawn,
            "grant_rate": (granted / total_consents * 100) if total_consents > 0 else 0,
            "by_purpose": dict(by_purpose)
        }

    @staticmethod
    def get_dsr_statistics(session) -> dict:
        """Get data subject request statistics."""
        total_requests = len(DataPrivacy._data_subject_requests)

        by_status = defaultdict(int)
        by_right = defaultdict(int)

        for request in DataPrivacy._data_subject_requests.values():
            by_status[request["status"]] += 1
            by_right[request["right_type"]] += 1

        # Calculate average processing time
        completed = [
            r for r in DataPrivacy._data_subject_requests.values()
            if r["status"] == RequestStatus.COMPLETED and r["completed_at"]
        ]

        avg_processing_days = 0
        if completed:
            processing_times = []
            for req in completed:
                created = datetime.fromisoformat(req["created_at"])
                completed_time = datetime.fromisoformat(req["completed_at"])
                days = (completed_time - created).days
                processing_times.append(days)
            avg_processing_days = sum(processing_times) / len(processing_times)

        return {
            "total_requests": total_requests,
            "by_status": dict(by_status),
            "by_right_type": dict(by_right),
            "average_processing_days": avg_processing_days,
            "overdue": sum(
                1 for r in DataPrivacy._data_subject_requests.values()
                if r["status"] == RequestStatus.PENDING
                and r["due_date"] < datetime.utcnow().isoformat()
            )
        }

    @staticmethod
    def get_statistics(session) -> dict:
        """Get comprehensive privacy and compliance statistics."""
        consent_stats = DataPrivacy.get_consent_statistics(session)
        dsr_stats = DataPrivacy.get_dsr_statistics(session)

        return {
            "consents": consent_stats,
            "data_subject_requests": dsr_stats,
            "retention_policies": {
                "total": len(DataPrivacy._retention_policies),
                "active": sum(1 for p in DataPrivacy._retention_policies.values() if p["is_active"])
            },
            "data_breaches": {
                "total": len(DataPrivacy._data_breaches),
                "by_severity": {
                    severity: sum(1 for b in DataPrivacy._data_breaches.values() if b["severity"] == severity)
                    for severity in BreachSeverity
                },
                "pending_notification": sum(
                    1 for b in DataPrivacy._data_breaches.values()
                    if b["notification_required"] and not b["users_notified"]
                )
            },
            "audit_trail": {
                "total_entries": len(DataPrivacy._privacy_audits),
                "recent_24h": sum(
                    1 for a in DataPrivacy._privacy_audits
                    if a["timestamp"] >= (datetime.utcnow() - timedelta(hours=24)).isoformat()
                )
            }
        }
