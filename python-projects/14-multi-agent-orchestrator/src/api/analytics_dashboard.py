"""
Analytics Dashboard and Reporting API Endpoints
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field
from typing import Dict, List, Optional, Any
from datetime import datetime

from src.core.database import get_db_session
from src.services.analytics_dashboard import (
    AnalyticsDashboardService,
    DashboardVisibility,
    WidgetType,
    ReportFormat,
    ReportFrequency,
    TimeRange
)


router = APIRouter()


# Request Models
class CreateDashboardRequest(BaseModel):
    """Request to create a dashboard"""
    dashboard_id: str
    name: str
    description: Optional[str] = None
    owner_id: str
    visibility: DashboardVisibility = DashboardVisibility.PRIVATE
    layout: Optional[Dict] = None
    metadata: Optional[Dict] = None


class AddWidgetRequest(BaseModel):
    """Request to add a widget"""
    dashboard_id: str
    widget_id: str
    widget_type: WidgetType
    title: str
    data_source: str
    config: Optional[Dict] = None
    position: Optional[Dict] = None


class CreateReportRequest(BaseModel):
    """Request to create a report"""
    report_id: str
    name: str
    description: Optional[str] = None
    dashboard_id: Optional[str] = None
    widget_ids: Optional[List[str]] = None
    format: ReportFormat = ReportFormat.PDF
    metadata: Optional[Dict] = None


class ScheduleReportRequest(BaseModel):
    """Request to schedule a report"""
    schedule_id: str
    report_id: str
    frequency: ReportFrequency
    recipients: List[str]
    next_run_at: Optional[str] = None
    metadata: Optional[Dict] = None


class CloneDashboardRequest(BaseModel):
    """Request to clone a dashboard"""
    source_dashboard_id: str
    new_dashboard_id: str
    new_name: str
    owner_id: str


class TrackViewRequest(BaseModel):
    """Request to track dashboard view"""
    dashboard_id: str
    user_id: str


# Response Models
class DashboardResponse(BaseModel):
    """Dashboard response"""
    dashboard_id: str
    name: str
    description: Optional[str]
    owner_id: str
    visibility: str
    layout: Dict
    widgets: List[str]
    metadata: Dict
    created_at: str
    updated_at: str
    last_viewed_at: Optional[str]
    view_count: int
    is_favorite: bool


class WidgetResponse(BaseModel):
    """Widget response"""
    widget_id: str
    dashboard_id: str
    widget_type: str
    title: str
    data_source: str
    config: Dict
    position: Dict
    created_at: str
    updated_at: str
    refresh_interval: int
    is_visible: bool


class ReportResponse(BaseModel):
    """Report response"""
    report_id: str
    name: str
    description: Optional[str]
    dashboard_id: Optional[str]
    widget_ids: List[str]
    format: str
    metadata: Dict
    created_at: str
    generated_at: Optional[str]
    status: str
    file_url: Optional[str]
    file_size: Optional[int]


# Endpoints
@router.post("/dashboards/dashboards", response_model=DashboardResponse)
async def create_dashboard(
    request: CreateDashboardRequest,
    session: Session = Depends(get_db_session)
):
    """
    Create a new analytics dashboard.

    Dashboards can contain multiple widgets and be shared with teams or made public.
    """
    try:
        result = AnalyticsDashboardService.create_dashboard(
            session=session,
            dashboard_id=request.dashboard_id,
            name=request.name,
            description=request.description,
            owner_id=request.owner_id,
            visibility=request.visibility,
            layout=request.layout,
            metadata=request.metadata
        )
        return DashboardResponse(**result)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/dashboards/dashboards/{dashboard_id}", response_model=DashboardResponse)
async def get_dashboard(
    dashboard_id: str,
    session: Session = Depends(get_db_session)
):
    """Get dashboard details."""
    try:
        dashboard = AnalyticsDashboardService._dashboards.get(dashboard_id)
        if not dashboard:
            raise HTTPException(status_code=404, detail="Dashboard not found")
        return DashboardResponse(**dashboard)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/dashboards/dashboards/{dashboard_id}/data")
async def get_dashboard_with_data(
    dashboard_id: str,
    time_range: TimeRange = TimeRange.LAST_24_HOURS,
    session: Session = Depends(get_db_session)
):
    """
    Get dashboard with all widget data.

    Returns the dashboard configuration along with current data for all widgets.
    """
    try:
        result = AnalyticsDashboardService.get_dashboard_with_data(
            session=session,
            dashboard_id=dashboard_id,
            time_range=time_range
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/dashboards/dashboards")
async def list_dashboards(
    session: Session = Depends(get_db_session)
):
    """List all dashboards."""
    try:
        dashboards = list(AnalyticsDashboardService._dashboards.values())
        return {"dashboards": dashboards, "total": len(dashboards)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/dashboards/widgets", response_model=WidgetResponse)
async def add_widget(
    request: AddWidgetRequest,
    session: Session = Depends(get_db_session)
):
    """
    Add a widget to a dashboard.

    Widgets display data visualizations like charts, tables, and metrics.
    """
    try:
        result = AnalyticsDashboardService.add_widget(
            session=session,
            dashboard_id=request.dashboard_id,
            widget_id=request.widget_id,
            widget_type=request.widget_type,
            title=request.title,
            data_source=request.data_source,
            config=request.config,
            position=request.position
        )
        return WidgetResponse(**result)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/dashboards/widgets/{widget_id}")
async def get_widget_data(
    widget_id: str,
    time_range: TimeRange = TimeRange.LAST_24_HOURS,
    start_time: Optional[str] = None,
    end_time: Optional[str] = None,
    session: Session = Depends(get_db_session)
):
    """
    Get data for a specific widget.

    Supports custom time ranges and real-time data updates.
    """
    try:
        result = AnalyticsDashboardService.get_widget_data(
            session=session,
            widget_id=widget_id,
            time_range=time_range,
            start_time=start_time,
            end_time=end_time
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/dashboards/reports", response_model=ReportResponse)
async def create_report(
    request: CreateReportRequest,
    session: Session = Depends(get_db_session)
):
    """
    Create a custom report.

    Reports can be generated from dashboards or specific widgets in multiple formats.
    """
    try:
        result = AnalyticsDashboardService.create_report(
            session=session,
            report_id=request.report_id,
            name=request.name,
            description=request.description,
            dashboard_id=request.dashboard_id,
            widget_ids=request.widget_ids,
            format=request.format,
            metadata=request.metadata
        )
        return ReportResponse(**result)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/dashboards/reports/{report_id}", response_model=ReportResponse)
async def get_report(
    report_id: str,
    session: Session = Depends(get_db_session)
):
    """Get report details."""
    try:
        report = AnalyticsDashboardService._reports.get(report_id)
        if not report:
            raise HTTPException(status_code=404, detail="Report not found")
        return ReportResponse(**report)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/dashboards/schedules")
async def schedule_report(
    request: ScheduleReportRequest,
    session: Session = Depends(get_db_session)
):
    """
    Schedule a report for automatic generation.

    Reports can be scheduled daily, weekly, monthly, or quarterly.
    """
    try:
        result = AnalyticsDashboardService.schedule_report(
            session=session,
            schedule_id=request.schedule_id,
            report_id=request.report_id,
            frequency=request.frequency,
            recipients=request.recipients,
            next_run_at=request.next_run_at,
            metadata=request.metadata
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/dashboards/schedules")
async def list_schedules(
    session: Session = Depends(get_db_session)
):
    """List all report schedules."""
    try:
        schedules = list(AnalyticsDashboardService._report_schedules.values())
        return {"schedules": schedules, "total": len(schedules)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/dashboards/track-view")
async def track_dashboard_view(
    request: TrackViewRequest,
    session: Session = Depends(get_db_session)
):
    """
    Track dashboard view for analytics.

    Increments view count and updates last viewed timestamp.
    """
    try:
        result = AnalyticsDashboardService.track_dashboard_view(
            session=session,
            dashboard_id=request.dashboard_id,
            user_id=request.user_id
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/dashboards/popular")
async def get_popular_dashboards(
    limit: int = 10,
    session: Session = Depends(get_db_session)
):
    """
    Get most viewed dashboards.

    Returns dashboards sorted by view count.
    """
    try:
        result = AnalyticsDashboardService.get_popular_dashboards(
            session=session,
            limit=limit
        )
        return {"dashboards": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/dashboards/clone")
async def clone_dashboard(
    request: CloneDashboardRequest,
    session: Session = Depends(get_db_session)
):
    """
    Clone an existing dashboard.

    Creates a copy of a dashboard with all its widgets for a new owner.
    """
    try:
        result = AnalyticsDashboardService.clone_dashboard(
            session=session,
            source_dashboard_id=request.source_dashboard_id,
            new_dashboard_id=request.new_dashboard_id,
            new_name=request.new_name,
            owner_id=request.owner_id
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/dashboards/{dashboard_id}/export")
async def export_dashboard_config(
    dashboard_id: str,
    session: Session = Depends(get_db_session)
):
    """
    Export dashboard configuration.

    Returns dashboard and widget configurations in a portable format.
    """
    try:
        result = AnalyticsDashboardService.export_dashboard_config(
            session=session,
            dashboard_id=dashboard_id
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/dashboards/statistics")
async def get_statistics(
    session: Session = Depends(get_db_session)
):
    """
    Get comprehensive analytics dashboard statistics.

    Returns:
    - Total dashboards and breakdown by visibility
    - Total widgets and breakdown by type
    - Report and schedule counts
    - View analytics
    """
    try:
        result = AnalyticsDashboardService.get_statistics(session=session)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
