"""
Analytics Dashboard and Reporting System

Provides customizable dashboards, widgets, reports, data visualization,
and comprehensive analytics across all system metrics and KPIs.
"""

from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from collections import defaultdict
from enum import Enum
import random
import hashlib


class DashboardVisibility(str, Enum):
    """Dashboard visibility options"""
    PRIVATE = "private"
    TEAM = "team"
    PUBLIC = "public"


class WidgetType(str, Enum):
    """Widget types for dashboards"""
    LINE_CHART = "line_chart"
    BAR_CHART = "bar_chart"
    PIE_CHART = "pie_chart"
    TABLE = "table"
    METRIC = "metric"
    GAUGE = "gauge"
    HEATMAP = "heatmap"
    TIMELINE = "timeline"


class ReportFormat(str, Enum):
    """Report export formats"""
    PDF = "pdf"
    CSV = "csv"
    EXCEL = "excel"
    JSON = "json"


class ReportFrequency(str, Enum):
    """Report schedule frequency"""
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"
    QUARTERLY = "quarterly"


class TimeRange(str, Enum):
    """Time range options"""
    LAST_HOUR = "last_hour"
    LAST_24_HOURS = "last_24_hours"
    LAST_7_DAYS = "last_7_days"
    LAST_30_DAYS = "last_30_days"
    LAST_90_DAYS = "last_90_days"
    CUSTOM = "custom"


class AnalyticsDashboardService:
    """Analytics Dashboard and Reporting System"""

    # In-memory storage
    _dashboards: Dict[str, Dict] = {}
    _widgets: Dict[str, Dict] = {}
    _reports: Dict[str, Dict] = {}
    _report_schedules: Dict[str, Dict] = {}
    _metrics_data: Dict[str, List[Dict]] = defaultdict(list)
    _dashboard_views: Dict[str, int] = defaultdict(int)

    @staticmethod
    def create_dashboard(
        session,
        dashboard_id: str,
        name: str,
        description: Optional[str] = None,
        owner_id: str = None,
        visibility: DashboardVisibility = DashboardVisibility.PRIVATE,
        layout: Optional[Dict] = None,
        metadata: Optional[Dict] = None
    ) -> dict:
        """Create a new dashboard."""
        if dashboard_id in AnalyticsDashboardService._dashboards:
            raise ValueError(f"Dashboard already exists: {dashboard_id}")

        dashboard = {
            "dashboard_id": dashboard_id,
            "name": name,
            "description": description,
            "owner_id": owner_id,
            "visibility": visibility,
            "layout": layout or {"columns": 12, "rows": []},
            "widgets": [],
            "metadata": metadata or {},
            "created_at": datetime.utcnow().isoformat(),
            "updated_at": datetime.utcnow().isoformat(),
            "last_viewed_at": None,
            "view_count": 0,
            "is_favorite": False
        }

        AnalyticsDashboardService._dashboards[dashboard_id] = dashboard

        return dashboard

    @staticmethod
    def add_widget(
        session,
        dashboard_id: str,
        widget_id: str,
        widget_type: WidgetType,
        title: str,
        data_source: str,
        config: Optional[Dict] = None,
        position: Optional[Dict] = None
    ) -> dict:
        """Add a widget to a dashboard."""
        dashboard = AnalyticsDashboardService._dashboards.get(dashboard_id)
        if not dashboard:
            raise ValueError(f"Dashboard not found: {dashboard_id}")

        widget = {
            "widget_id": widget_id,
            "dashboard_id": dashboard_id,
            "widget_type": widget_type,
            "title": title,
            "data_source": data_source,
            "config": config or {},
            "position": position or {"x": 0, "y": 0, "w": 6, "h": 4},
            "created_at": datetime.utcnow().isoformat(),
            "updated_at": datetime.utcnow().isoformat(),
            "refresh_interval": config.get("refresh_interval", 60) if config else 60,
            "is_visible": True
        }

        # Store widget
        AnalyticsDashboardService._widgets[widget_id] = widget

        # Add to dashboard
        dashboard["widgets"].append(widget_id)
        dashboard["updated_at"] = datetime.utcnow().isoformat()

        return widget

    @staticmethod
    def get_widget_data(
        session,
        widget_id: str,
        time_range: TimeRange = TimeRange.LAST_24_HOURS,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None
    ) -> dict:
        """Get data for a widget."""
        widget = AnalyticsDashboardService._widgets.get(widget_id)
        if not widget:
            raise ValueError(f"Widget not found: {widget_id}")

        # Generate sample data based on widget type
        data = AnalyticsDashboardService._generate_widget_data(
            widget["widget_type"],
            widget["data_source"],
            time_range,
            start_time,
            end_time
        )

        return {
            "widget_id": widget_id,
            "widget_type": widget["widget_type"],
            "title": widget["title"],
            "data": data,
            "time_range": time_range,
            "generated_at": datetime.utcnow().isoformat()
        }

    @staticmethod
    def _generate_widget_data(
        widget_type: WidgetType,
        data_source: str,
        time_range: TimeRange,
        start_time: Optional[str],
        end_time: Optional[str]
    ) -> Dict:
        """Generate sample widget data."""
        if widget_type == WidgetType.LINE_CHART:
            return AnalyticsDashboardService._generate_line_chart_data(time_range)
        elif widget_type == WidgetType.BAR_CHART:
            return AnalyticsDashboardService._generate_bar_chart_data()
        elif widget_type == WidgetType.PIE_CHART:
            return AnalyticsDashboardService._generate_pie_chart_data()
        elif widget_type == WidgetType.TABLE:
            return AnalyticsDashboardService._generate_table_data()
        elif widget_type == WidgetType.METRIC:
            return AnalyticsDashboardService._generate_metric_data()
        elif widget_type == WidgetType.GAUGE:
            return AnalyticsDashboardService._generate_gauge_data()
        else:
            return {"data": []}

    @staticmethod
    def _generate_line_chart_data(time_range: TimeRange) -> Dict:
        """Generate line chart data."""
        points = 24 if time_range == TimeRange.LAST_24_HOURS else 30

        data_points = []
        base_time = datetime.utcnow() - timedelta(hours=points)

        for i in range(points):
            data_points.append({
                "timestamp": (base_time + timedelta(hours=i)).isoformat(),
                "value": random.randint(10, 100)
            })

        return {
            "series": [
                {
                    "name": "Series 1",
                    "data": data_points
                }
            ]
        }

    @staticmethod
    def _generate_bar_chart_data() -> Dict:
        """Generate bar chart data."""
        return {
            "categories": ["Category A", "Category B", "Category C", "Category D"],
            "series": [
                {
                    "name": "Series 1",
                    "data": [random.randint(10, 100) for _ in range(4)]
                }
            ]
        }

    @staticmethod
    def _generate_pie_chart_data() -> Dict:
        """Generate pie chart data."""
        return {
            "data": [
                {"label": "Slice A", "value": random.randint(10, 100)},
                {"label": "Slice B", "value": random.randint(10, 100)},
                {"label": "Slice C", "value": random.randint(10, 100)},
                {"label": "Slice D", "value": random.randint(10, 100)}
            ]
        }

    @staticmethod
    def _generate_table_data() -> Dict:
        """Generate table data."""
        return {
            "columns": ["Name", "Value", "Status", "Date"],
            "rows": [
                ["Item 1", "100", "Active", datetime.utcnow().isoformat()],
                ["Item 2", "200", "Pending", datetime.utcnow().isoformat()],
                ["Item 3", "150", "Active", datetime.utcnow().isoformat()]
            ]
        }

    @staticmethod
    def _generate_metric_data() -> Dict:
        """Generate metric data."""
        current = random.randint(100, 1000)
        previous = random.randint(100, 1000)
        change = ((current - previous) / previous * 100) if previous > 0 else 0

        return {
            "current_value": current,
            "previous_value": previous,
            "change_percent": round(change, 2),
            "trend": "up" if change > 0 else "down"
        }

    @staticmethod
    def _generate_gauge_data() -> Dict:
        """Generate gauge data."""
        return {
            "value": random.randint(0, 100),
            "min": 0,
            "max": 100,
            "thresholds": [
                {"value": 30, "color": "red"},
                {"value": 70, "color": "yellow"},
                {"value": 100, "color": "green"}
            ]
        }

    @staticmethod
    def create_report(
        session,
        report_id: str,
        name: str,
        description: Optional[str] = None,
        dashboard_id: Optional[str] = None,
        widget_ids: Optional[List[str]] = None,
        format: ReportFormat = ReportFormat.PDF,
        metadata: Optional[Dict] = None
    ) -> dict:
        """Create a custom report."""
        report = {
            "report_id": report_id,
            "name": name,
            "description": description,
            "dashboard_id": dashboard_id,
            "widget_ids": widget_ids or [],
            "format": format,
            "metadata": metadata or {},
            "created_at": datetime.utcnow().isoformat(),
            "generated_at": None,
            "status": "pending",
            "file_url": None,
            "file_size": None
        }

        # Simulate report generation
        report["status"] = "completed"
        report["generated_at"] = datetime.utcnow().isoformat()
        report["file_url"] = f"/reports/{report_id}.{format.value}"
        report["file_size"] = random.randint(1000, 10000)

        AnalyticsDashboardService._reports[report_id] = report

        return report

    @staticmethod
    def schedule_report(
        session,
        schedule_id: str,
        report_id: str,
        frequency: ReportFrequency,
        recipients: List[str],
        next_run_at: Optional[str] = None,
        metadata: Optional[Dict] = None
    ) -> dict:
        """Schedule a report for automatic generation."""
        if report_id not in AnalyticsDashboardService._reports:
            raise ValueError(f"Report not found: {report_id}")

        schedule = {
            "schedule_id": schedule_id,
            "report_id": report_id,
            "frequency": frequency,
            "recipients": recipients,
            "next_run_at": next_run_at or AnalyticsDashboardService._calculate_next_run(frequency),
            "last_run_at": None,
            "is_active": True,
            "metadata": metadata or {},
            "created_at": datetime.utcnow().isoformat(),
            "run_count": 0
        }

        AnalyticsDashboardService._report_schedules[schedule_id] = schedule

        return schedule

    @staticmethod
    def _calculate_next_run(frequency: ReportFrequency) -> str:
        """Calculate next run time based on frequency."""
        now = datetime.utcnow()

        if frequency == ReportFrequency.DAILY:
            next_run = now + timedelta(days=1)
        elif frequency == ReportFrequency.WEEKLY:
            next_run = now + timedelta(weeks=1)
        elif frequency == ReportFrequency.MONTHLY:
            next_run = now + timedelta(days=30)
        elif frequency == ReportFrequency.QUARTERLY:
            next_run = now + timedelta(days=90)
        else:
            next_run = now + timedelta(days=1)

        return next_run.isoformat()

    @staticmethod
    def track_dashboard_view(session, dashboard_id: str, user_id: str) -> dict:
        """Track dashboard view for analytics."""
        dashboard = AnalyticsDashboardService._dashboards.get(dashboard_id)
        if not dashboard:
            raise ValueError(f"Dashboard not found: {dashboard_id}")

        dashboard["view_count"] += 1
        dashboard["last_viewed_at"] = datetime.utcnow().isoformat()

        AnalyticsDashboardService._dashboard_views[dashboard_id] += 1

        return {
            "dashboard_id": dashboard_id,
            "view_count": dashboard["view_count"],
            "last_viewed_at": dashboard["last_viewed_at"]
        }

    @staticmethod
    def get_dashboard_with_data(
        session,
        dashboard_id: str,
        time_range: TimeRange = TimeRange.LAST_24_HOURS
    ) -> dict:
        """Get dashboard with all widget data."""
        dashboard = AnalyticsDashboardService._dashboards.get(dashboard_id)
        if not dashboard:
            raise ValueError(f"Dashboard not found: {dashboard_id}")

        # Get data for all widgets
        widgets_with_data = []
        for widget_id in dashboard["widgets"]:
            widget = AnalyticsDashboardService._widgets.get(widget_id)
            if widget and widget["is_visible"]:
                widget_data = AnalyticsDashboardService.get_widget_data(
                    session=session,
                    widget_id=widget_id,
                    time_range=time_range
                )
                widgets_with_data.append({
                    **widget,
                    "data": widget_data["data"]
                })

        return {
            **dashboard,
            "widgets_data": widgets_with_data
        }

    @staticmethod
    def get_popular_dashboards(session, limit: int = 10) -> List[dict]:
        """Get most viewed dashboards."""
        dashboards = list(AnalyticsDashboardService._dashboards.values())
        dashboards.sort(key=lambda x: x["view_count"], reverse=True)

        return dashboards[:limit]

    @staticmethod
    def clone_dashboard(
        session,
        source_dashboard_id: str,
        new_dashboard_id: str,
        new_name: str,
        owner_id: str
    ) -> dict:
        """Clone an existing dashboard."""
        source = AnalyticsDashboardService._dashboards.get(source_dashboard_id)
        if not source:
            raise ValueError(f"Source dashboard not found: {source_dashboard_id}")

        # Create new dashboard
        cloned_dashboard = {
            "dashboard_id": new_dashboard_id,
            "name": new_name,
            "description": f"Cloned from: {source['name']}",
            "owner_id": owner_id,
            "visibility": DashboardVisibility.PRIVATE,
            "layout": source["layout"].copy(),
            "widgets": [],
            "metadata": source["metadata"].copy(),
            "created_at": datetime.utcnow().isoformat(),
            "updated_at": datetime.utcnow().isoformat(),
            "last_viewed_at": None,
            "view_count": 0,
            "is_favorite": False
        }

        # Clone widgets
        for widget_id in source["widgets"]:
            original_widget = AnalyticsDashboardService._widgets.get(widget_id)
            if original_widget:
                new_widget_id = f"{new_dashboard_id}_{widget_id}"
                cloned_widget = {
                    **original_widget,
                    "widget_id": new_widget_id,
                    "dashboard_id": new_dashboard_id,
                    "created_at": datetime.utcnow().isoformat(),
                    "updated_at": datetime.utcnow().isoformat()
                }
                AnalyticsDashboardService._widgets[new_widget_id] = cloned_widget
                cloned_dashboard["widgets"].append(new_widget_id)

        AnalyticsDashboardService._dashboards[new_dashboard_id] = cloned_dashboard

        return cloned_dashboard

    @staticmethod
    def export_dashboard_config(session, dashboard_id: str) -> dict:
        """Export dashboard configuration."""
        dashboard = AnalyticsDashboardService._dashboards.get(dashboard_id)
        if not dashboard:
            raise ValueError(f"Dashboard not found: {dashboard_id}")

        widgets_config = []
        for widget_id in dashboard["widgets"]:
            widget = AnalyticsDashboardService._widgets.get(widget_id)
            if widget:
                widgets_config.append({
                    "widget_type": widget["widget_type"],
                    "title": widget["title"],
                    "data_source": widget["data_source"],
                    "config": widget["config"],
                    "position": widget["position"]
                })

        return {
            "dashboard_id": dashboard_id,
            "name": dashboard["name"],
            "description": dashboard["description"],
            "layout": dashboard["layout"],
            "widgets": widgets_config,
            "exported_at": datetime.utcnow().isoformat()
        }

    @staticmethod
    def get_statistics(session) -> dict:
        """Get comprehensive analytics dashboard statistics."""
        total_dashboards = len(AnalyticsDashboardService._dashboards)
        total_widgets = len(AnalyticsDashboardService._widgets)
        total_reports = len(AnalyticsDashboardService._reports)
        total_schedules = len(AnalyticsDashboardService._report_schedules)

        # By visibility
        by_visibility = defaultdict(int)
        for dashboard in AnalyticsDashboardService._dashboards.values():
            by_visibility[dashboard["visibility"]] += 1

        # By widget type
        by_widget_type = defaultdict(int)
        for widget in AnalyticsDashboardService._widgets.values():
            by_widget_type[widget["widget_type"]] += 1

        # Total views
        total_views = sum(
            d["view_count"] for d in AnalyticsDashboardService._dashboards.values()
        )

        return {
            "dashboards": {
                "total": total_dashboards,
                "by_visibility": dict(by_visibility),
                "total_views": total_views
            },
            "widgets": {
                "total": total_widgets,
                "by_type": dict(by_widget_type)
            },
            "reports": {
                "total": total_reports,
                "scheduled": total_schedules,
                "active_schedules": sum(
                    1 for s in AnalyticsDashboardService._report_schedules.values()
                    if s["is_active"]
                )
            }
        }
