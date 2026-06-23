from datetime import date
from pathlib import Path
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user
from app.db.session import get_db
from app.models.conversation import ConversationStatus
from app.schemas.analytics import AnalyticsDashboardResponse, MetricResponse
from app.services.analytics_service import AnalyticsFilters, AnalyticsService


router = APIRouter()


def metric(label: str, value) -> MetricResponse:
    """
    Build a dashboard metric response object.

    Purpose:
    Keeps legacy metric construction available for callers that expect the
    MetricResponse shape.

    Parameters:
    label: Human-readable metric label.
    value: Metric value.

    Returns:
    MetricResponse with the supplied label and value.

    Business Logic:
    This helper performs no calculation; analytics calculations live in
    AnalyticsService to avoid duplicated business logic.
    """
    return MetricResponse(label=label, value=value)


@router.get('/dashboard', response_model=AnalyticsDashboardResponse)
def get_dashboard_analytics(
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
    agent_id: UUID | None = Query(default=None),
    category_id: UUID | None = Query(default=None),
    status: ConversationStatus | None = Query(default=None),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
) -> AnalyticsDashboardResponse:
    """
    Return filtered analytics for admin, operations, or agent dashboards.

    Purpose:
    Serves operational metrics, chart data, and summary tables for the
    analytics screen.

    Parameters:
    start_date: Optional beginning of the reporting period.
    end_date: Optional end of the reporting period.
    agent_id: Optional current-assignee filter for admin/operations users.
    category_id: Optional category filter.
    status: Optional stored conversation status filter.
    db: Request-scoped database session.
    current_user: Authenticated user.

    Returns:
    AnalyticsDashboardResponse containing totals, distributions, SLA metrics,
    trend data, and summary tables.

    Business Logic:
    Support agents are automatically scoped to their own conversations by
    AnalyticsService. Admin and operations users can apply the full filter set.
    """
    return AnalyticsService(db).dashboard(
        AnalyticsFilters(
            start_date=start_date,
            end_date=end_date,
            agent_id=agent_id,
            category_id=category_id,
            status=status,
        ),
        current_user,
    )


@router.get('/dashboard/export')
def export_dashboard_analytics(
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
    agent_id: UUID | None = Query(default=None),
    category_id: UUID | None = Query(default=None),
    status: ConversationStatus | None = Query(default=None),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
) -> FileResponse:
    """
    Export filtered analytics to an Excel workbook.

    Purpose:
    Generates a multi-sheet XLSX report containing raw data, agent summary,
    category summary, SLA summary, and embedded charts.

    Parameters:
    start_date: Optional beginning of the reporting period.
    end_date: Optional end of the reporting period.
    agent_id: Optional current-assignee filter for admin/operations users.
    category_id: Optional category filter.
    status: Optional stored conversation status filter.
    db: Request-scoped database session.
    current_user: Authenticated user.

    Returns:
    FileResponse streaming the generated Excel workbook.

    Business Logic:
    Uses the same AnalyticsService calculations as the dashboard endpoint so
    exported totals match the UI exactly.
    """
    path = AnalyticsService(db).export_workbook(
        AnalyticsFilters(
            start_date=start_date,
            end_date=end_date,
            agent_id=agent_id,
            category_id=category_id,
            status=status,
        ),
        current_user,
    )
    filename = f'conversation_analytics_{date.today().isoformat()}.xlsx'
    return FileResponse(
        Path(path),
        filename=filename,
        media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    )
