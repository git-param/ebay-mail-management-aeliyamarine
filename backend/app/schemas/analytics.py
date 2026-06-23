from pydantic import BaseModel


class MetricResponse(BaseModel):
    """Single labeled analytics value used by dashboard widgets and charts."""

    label: str
    value: int | float | str | None


class AnalyticsDashboardResponse(BaseModel):
    """Role-aware analytics payload for dashboard and reporting screens."""

    role_scope: str
    totals: list[MetricResponse]
    by_category: list[MetricResponse]
    by_status: list[MetricResponse]
    by_assigned_user: list[MetricResponse]
    daily_trends: list[MetricResponse]
    sla_metrics: list[MetricResponse]
    agent_productivity: list[MetricResponse] = []
    category_distribution: list[MetricResponse] = []
    agent_summary: list[dict] = []
    category_summary: list[dict] = []
    filters: dict = {}
