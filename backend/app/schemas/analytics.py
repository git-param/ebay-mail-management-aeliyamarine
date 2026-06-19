from pydantic import BaseModel


class MetricResponse(BaseModel):
    label: str
    value: int | float | str | None


class AnalyticsDashboardResponse(BaseModel):
    role_scope: str
    totals: list[MetricResponse]
    by_category: list[MetricResponse]
    by_status: list[MetricResponse]
    by_assigned_user: list[MetricResponse]
    daily_trends: list[MetricResponse]
    sla_metrics: list[MetricResponse]
