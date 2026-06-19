from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from app.api.dependencies import require_operations_manager_or_admin
from app.db.session import get_db
from app.models.category import Category
from app.models.conversation import Conversation, ConversationAssignment, ConversationStatus
from app.models.user import User
from app.schemas.analytics import AnalyticsDashboardResponse, MetricResponse


router = APIRouter()


def metric(label: str, value) -> MetricResponse:
    return MetricResponse(label=label, value=value)


@router.get('/dashboard', response_model=AnalyticsDashboardResponse)
def get_dashboard_analytics(
    db: Session = Depends(get_db),
    current_user=Depends(require_operations_manager_or_admin),
) -> AnalyticsDashboardResponse:
    now = datetime.now(UTC)
    total = int(db.scalar(select(func.count(Conversation.id))) or 0)
    open_count = int(db.scalar(select(func.count(Conversation.id)).where(Conversation.status == ConversationStatus.OPEN)) or 0)
    pending_count = int(db.scalar(select(func.count(Conversation.id)).where(Conversation.status == ConversationStatus.PENDING)) or 0)
    resolved_count = int(db.scalar(select(func.count(Conversation.id)).where(Conversation.status == ConversationStatus.RESOLVED)) or 0)

    by_category = [
        metric(label or 'Uncategorized', count)
        for label, count in db.execute(
            select(Category.name, func.count(Conversation.id))
            .select_from(Conversation)
            .outerjoin(Category, Category.id == Conversation.category_id)
            .group_by(Category.name)
            .order_by(func.count(Conversation.id).desc())
        )
    ]
    by_status = [
        metric(status.value if hasattr(status, 'value') else str(status), count)
        for status, count in db.execute(select(Conversation.status, func.count(Conversation.id)).group_by(Conversation.status))
    ]
    current_assignment = (
        select(ConversationAssignment.conversation_id, ConversationAssignment.assigned_to)
        .where(ConversationAssignment.unassigned_at.is_(None))
        .subquery()
    )
    by_assigned_user = [
        metric(name or 'Unassigned', count)
        for name, count in db.execute(
            select(User.full_name, func.count(Conversation.id))
            .select_from(Conversation)
            .outerjoin(current_assignment, current_assignment.c.conversation_id == Conversation.id)
            .outerjoin(User, User.id == current_assignment.c.assigned_to)
            .group_by(User.full_name)
            .order_by(func.count(Conversation.id).desc())
        )
    ]
    daily_trends = [
        metric(str(day), count)
        for day, count in db.execute(
            select(func.date(Conversation.created_at), func.count(Conversation.id))
            .where(Conversation.created_at >= now - timedelta(days=30))
            .group_by(func.date(Conversation.created_at))
            .order_by(func.date(Conversation.created_at))
        )
    ]
    active_conversations = list(
        db.scalars(
            select(Conversation)
            .options(joinedload(Conversation.category))
            .where(Conversation.status.in_([ConversationStatus.OPEN, ConversationStatus.PENDING]))
        )
    )
    sla_breaches = sum(
        1
        for conversation in active_conversations
        if conversation.last_message_at
        and conversation.last_message_at + timedelta(hours=conversation.category.sla_hours if conversation.category else 24) < now
    )
    return AnalyticsDashboardResponse(
        role_scope='ADMIN' if current_user.role.name == 'Admin' else 'OPERATIONS',
        totals=[
            metric('Total messages', total),
            metric('Open messages', open_count),
            metric('Pending messages', pending_count),
            metric('Resolved messages', resolved_count),
        ],
        by_category=by_category,
        by_status=by_status,
        by_assigned_user=by_assigned_user,
        daily_trends=daily_trends,
        sla_metrics=[metric('SLA breaches', sla_breaches)],
    )
