"""
Admin Dashboard and System Management API Endpoints
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field
from typing import Dict, List, Optional, Any
from datetime import datetime

from src.core.database import get_db_session
from src.services.admin_dashboard import (
    AdminDashboardService,
    UserRole,
    UserStatus,
    SystemStatus
)


router = APIRouter()


# Request Models
class CreateUserRequest(BaseModel):
    """Request to create a user"""
    user_id: str
    username: str
    email: str
    role: UserRole = UserRole.USER
    metadata: Optional[Dict] = None


class UpdateUserRoleRequest(BaseModel):
    """Request to update user role"""
    user_id: str
    new_role: UserRole
    updated_by: str


class SuspendUserRequest(BaseModel):
    """Request to suspend user"""
    user_id: str
    reason: str
    suspended_by: str


class ReactivateUserRequest(BaseModel):
    """Request to reactivate user"""
    user_id: str
    reactivated_by: str


class UpdateConfigRequest(BaseModel):
    """Request to update system config"""
    config_key: str
    config_value: Any
    updated_by: str


class ScheduleMaintenanceRequest(BaseModel):
    """Request to schedule maintenance"""
    maintenance_id: str
    start_time: str
    end_time: str
    reason: str
    scheduled_by: str


class ToggleFeatureRequest(BaseModel):
    """Request to toggle feature flag"""
    feature_name: str
    enabled: bool
    toggled_by: str


class BulkUpdateUsersRequest(BaseModel):
    """Request to bulk update users"""
    user_ids: List[str]
    updates: Dict
    updated_by: str


# Response Models
class UserResponse(BaseModel):
    """User response"""
    user_id: str
    username: str
    email: str
    role: str
    status: str
    metadata: Dict
    created_at: str
    updated_at: str
    last_login_at: Optional[str]
    login_count: int
    permissions: List[str]


# Endpoints
@router.post("/admin/users", response_model=UserResponse)
async def create_user(
    request: CreateUserRequest,
    session: Session = Depends(get_db_session)
):
    """
    Create a new user.

    Requires admin permissions. Assigns default permissions based on role.
    """
    try:
        result = AdminDashboardService.create_user(
            session=session,
            user_id=request.user_id,
            username=request.username,
            email=request.email,
            role=request.role,
            metadata=request.metadata
        )
        return UserResponse(**result)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/admin/users")
async def list_users(
    role: Optional[UserRole] = None,
    status: Optional[UserStatus] = None,
    limit: int = 50,
    session: Session = Depends(get_db_session)
):
    """
    List users with optional filters.

    Filter by role, status, and limit results.
    """
    try:
        users = AdminDashboardService.list_users(
            session=session,
            role=role,
            status=status,
            limit=limit
        )
        return {"users": users, "total": len(users)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/admin/users/role")
async def update_user_role(
    request: UpdateUserRoleRequest,
    session: Session = Depends(get_db_session)
):
    """
    Update a user's role.

    Automatically updates permissions based on new role.
    Requires admin permissions.
    """
    try:
        result = AdminDashboardService.update_user_role(
            session=session,
            user_id=request.user_id,
            new_role=request.new_role,
            updated_by=request.updated_by
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/admin/users/suspend")
async def suspend_user(
    request: SuspendUserRequest,
    session: Session = Depends(get_db_session)
):
    """
    Suspend a user account.

    Prevents user from accessing the system. Requires admin permissions.
    """
    try:
        result = AdminDashboardService.suspend_user(
            session=session,
            user_id=request.user_id,
            reason=request.reason,
            suspended_by=request.suspended_by
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/admin/users/reactivate")
async def reactivate_user(
    request: ReactivateUserRequest,
    session: Session = Depends(get_db_session)
):
    """
    Reactivate a suspended user account.

    Restores user access. Requires admin permissions.
    """
    try:
        result = AdminDashboardService.reactivate_user(
            session=session,
            user_id=request.user_id,
            reactivated_by=request.reactivated_by
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/admin/users/bulk-update")
async def bulk_update_users(
    request: BulkUpdateUsersRequest,
    session: Session = Depends(get_db_session)
):
    """
    Bulk update multiple users.

    Apply same updates to multiple users at once. Requires admin permissions.
    """
    try:
        result = AdminDashboardService.bulk_update_users(
            session=session,
            user_ids=request.user_ids,
            updates=request.updates,
            updated_by=request.updated_by
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/admin/config")
async def update_system_config(
    request: UpdateConfigRequest,
    session: Session = Depends(get_db_session)
):
    """
    Update system configuration.

    Modify platform settings. Requires admin permissions.
    """
    try:
        result = AdminDashboardService.update_system_config(
            session=session,
            config_key=request.config_key,
            config_value=request.config_value,
            updated_by=request.updated_by
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/admin/config")
async def get_system_config(
    session: Session = Depends(get_db_session)
):
    """
    Get all system configuration.

    Returns complete platform configuration.
    """
    try:
        result = AdminDashboardService.get_system_config(session=session)
        return {"config": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/admin/audit-logs")
async def get_audit_logs(
    user_id: Optional[str] = None,
    action: Optional[str] = None,
    start_time: Optional[str] = None,
    end_time: Optional[str] = None,
    limit: int = 100,
    session: Session = Depends(get_db_session)
):
    """
    Get audit logs with filters.

    Track all administrative actions for compliance and security.
    """
    try:
        logs = AdminDashboardService.get_audit_logs(
            session=session,
            user_id=user_id,
            action=action,
            start_time=start_time,
            end_time=end_time,
            limit=limit
        )
        return {"logs": logs, "total": len(logs)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/admin/audit-logs/export")
async def export_audit_logs(
    start_time: Optional[str] = None,
    end_time: Optional[str] = None,
    session: Session = Depends(get_db_session)
):
    """
    Export audit logs for compliance.

    Download complete audit trail for specified time range.
    """
    try:
        result = AdminDashboardService.export_audit_logs(
            session=session,
            start_time=start_time,
            end_time=end_time
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/admin/health")
async def get_system_health(
    session: Session = Depends(get_db_session)
):
    """
    Get system health status.

    Returns health of all system components and metrics.
    """
    try:
        result = AdminDashboardService.get_system_health(session=session)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/admin/maintenance")
async def schedule_maintenance(
    request: ScheduleMaintenanceRequest,
    session: Session = Depends(get_db_session)
):
    """
    Schedule a maintenance window.

    Plan system downtime for upgrades and maintenance.
    """
    try:
        result = AdminDashboardService.schedule_maintenance(
            session=session,
            maintenance_id=request.maintenance_id,
            start_time=request.start_time,
            end_time=request.end_time,
            reason=request.reason,
            scheduled_by=request.scheduled_by
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/admin/features/toggle")
async def toggle_feature(
    request: ToggleFeatureRequest,
    session: Session = Depends(get_db_session)
):
    """
    Toggle a feature flag.

    Enable or disable platform features without deployment.
    """
    try:
        result = AdminDashboardService.toggle_feature(
            session=session,
            feature_name=request.feature_name,
            enabled=request.enabled,
            toggled_by=request.toggled_by
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/admin/features")
async def get_feature_flags(
    session: Session = Depends(get_db_session)
):
    """
    Get all feature flags.

    Returns current state of all feature toggles.
    """
    try:
        result = AdminDashboardService.get_feature_flags(session=session)
        return {"features": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/admin/statistics")
async def get_platform_statistics(
    session: Session = Depends(get_db_session)
):
    """
    Get comprehensive platform statistics.

    Returns:
    - User statistics (total, active, by role)
    - System configuration stats
    - Audit log metrics
    - Maintenance windows
    """
    try:
        result = AdminDashboardService.get_platform_statistics(session=session)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
