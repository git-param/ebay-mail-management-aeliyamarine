from datetime import UTC, date, datetime, time, timedelta
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import and_, or_
from sqlalchemy.orm import Session, joinedload

from app.api.dependencies import normalized_role_name
from app.models.user import User
from app.services.audit_service import AuditService
from .models import BreakSession
from .schemas import BreakStartRequest


ROLE_SECTIONS = [
    ('ADMIN', 'Admins', {'ADMIN'}),
    ('OPS_MANAGER', 'Ops Managers', {'OPS_MANAGER', 'OPERATIONS_MANAGER'}),
    ('AGENT', 'Agent Users', {'AGENT', 'SUPPORT_AGENT'}),
]


def utc_day_bounds(value: date | None = None) -> tuple[datetime, datetime]:
    selected = value or datetime.now(UTC).date()
    start = datetime.combine(selected, time.min, tzinfo=UTC)
    return start, start + timedelta(days=1)


def display_role(user) -> str:
    role = normalized_role_name(user)
    if role == 'OPERATIONS_MANAGER':
        return 'OPS_MANAGER'
    if role == 'SUPPORT_AGENT':
        return 'AGENT'
    return role or 'AGENT'


def minutes_between(start: datetime, end: datetime | None = None) -> int:
    finish = end or datetime.now(UTC)
    if start.tzinfo is None:
        start = start.replace(tzinfo=UTC)
    if finish.tzinfo is None:
        finish = finish.replace(tzinfo=UTC)
    return max(0, int((finish - start).total_seconds() // 60))


def minutes_within_window(start: datetime, end: datetime | None, window_start: datetime, window_end: datetime) -> int:
    finish = end or datetime.now(UTC)
    if start.tzinfo is None:
        start = start.replace(tzinfo=UTC)
    if finish.tzinfo is None:
        finish = finish.replace(tzinfo=UTC)
    bounded_start = max(start, window_start)
    bounded_end = min(finish, window_end)
    return max(0, int((bounded_end - bounded_start).total_seconds() // 60))


class BreakManagementService:
    def __init__(self, db: Session):
        self.db = db

    def serialize(self, session: BreakSession) -> dict:
        user = session.user
        return {
            'id': session.id,
            'user_id': session.user_id,
            'user_name': user.full_name if user else 'Unknown User',
            'user_role': display_role(user) if user else 'AGENT',
            'reason': session.reason,
            'start_time': session.start_time,
            'end_time': session.end_time,
            'duration_minutes': session.duration_minutes if session.duration_minutes is not None else minutes_between(session.start_time, session.end_time),
        }

    def get_active_break(self, user_id: UUID) -> BreakSession | None:
        return (
            self.db.query(BreakSession)
            .options(joinedload(BreakSession.user))
            .filter(BreakSession.user_id == user_id, BreakSession.end_time.is_(None))
            .order_by(BreakSession.start_time.desc())
            .first()
        )

    def status(self, current_user) -> dict:
        active = self.get_active_break(current_user.id)
        return {
            'is_on_break': active is not None,
            'active_break': self.serialize(active) if active else None,
        }

    def start_break(self, current_user, payload: BreakStartRequest) -> dict:
        reason = payload.reason.strip()
        if not reason:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='Reason for break is required.')

        existing = self.get_active_break(current_user.id)
        if existing:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail='You are already on a break.')

        session = BreakSession(user_id=current_user.id, reason=reason, start_time=datetime.now(UTC))
        self.db.add(session)
        self.db.flush()

        AuditService(self.db).log(
            action='BREAK_START',
            user_id=current_user.id,
            entity_type='BREAK_SESSION',
            entity_id=session.id,
            category='BREAK_MANAGEMENT',
            metadata={
                'timestamp': session.start_time.isoformat(),
                'user_name': current_user.full_name,
                'user_role': display_role(current_user),
                'reason': reason,
            },
        )
        self.db.commit()
        self.db.refresh(session)
        session.user = current_user
        return self.serialize(session)

    def end_break(self, current_user) -> dict:
        session = self.get_active_break(current_user.id)
        if not session:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='No active break was found.')

        session.end_time = datetime.now(UTC)
        session.duration_minutes = minutes_between(session.start_time, session.end_time)

        AuditService(self.db).log(
            action='BREAK_END',
            user_id=current_user.id,
            entity_type='BREAK_SESSION',
            entity_id=session.id,
            category='BREAK_MANAGEMENT',
            metadata={
                'timestamp': session.end_time.isoformat(),
                'user_name': current_user.full_name,
                'user_role': display_role(current_user),
                'reason': session.reason,
                'duration_minutes': session.duration_minutes,
            },
        )
        self.db.commit()
        self.db.refresh(session)
        return self.serialize(session)

    def history(self, current_user, user_id: UUID | None, date_from: date | None, date_to: date | None) -> dict:
        role = display_role(current_user)
        target_user_id = user_id or current_user.id
        if target_user_id != current_user.id and role not in {'ADMIN', 'OPS_MANAGER'}:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail='You can only view your own break history.')

        query = (
            self.db.query(BreakSession)
            .options(joinedload(BreakSession.user))
            .filter(BreakSession.user_id == target_user_id)
        )
        if date_from:
            start, _ = utc_day_bounds(date_from)
            query = query.filter(BreakSession.start_time >= start)
        if date_to:
            _, end = utc_day_bounds(date_to)
            query = query.filter(BreakSession.start_time < end)

        items = query.order_by(BreakSession.start_time.desc()).all()
        return {'items': [self.serialize(item) for item in items], 'total': len(items)}

    def overview(self, selected_date: date | None = None) -> dict:
        day = selected_date or datetime.now(UTC).date()
        start, end = utc_day_bounds(day)
        users = (
            self.db.query(User)
            .options(joinedload(User.role))
            .filter(User.is_active.is_(True), User.deleted_at.is_(None))
            .order_by(User.full_name.asc())
            .all()
        )
        sessions = (
            self.db.query(BreakSession)
            .options(joinedload(BreakSession.user))
            .filter(
                or_(
                    and_(BreakSession.start_time >= start, BreakSession.start_time < end),
                    and_(BreakSession.end_time.is_not(None), BreakSession.end_time > start, BreakSession.start_time < end),
                    and_(BreakSession.end_time.is_(None), BreakSession.start_time < end),
                )
            )
            .order_by(BreakSession.start_time.asc())
            .all()
        )
        sessions_by_user: dict[UUID, list[BreakSession]] = {}
        for session in sessions:
            sessions_by_user.setdefault(session.user_id, []).append(session)

        sections = []
        for role_key, title, accepted in ROLE_SECTIONS:
            role_users = [user for user in users if display_role(user) in accepted or normalized_role_name(user) in accepted]
            if not role_users:
                continue

            section_users = []
            for user in role_users:
                user_sessions = sessions_by_user.get(user.id, [])
                active = next((item for item in user_sessions if item.end_time is None), None)
                total = sum(minutes_within_window(item.start_time, item.end_time, start, end) for item in user_sessions)
                section_users.append({
                    'user_id': user.id,
                    'user_name': user.full_name,
                    'user_role': display_role(user),
                    'is_on_break': active is not None,
                    'active_reason': active.reason if active else None,
                    'active_start_time': active.start_time if active else None,
                    'total_break_minutes_today': total,
                    'today_breaks': [self.serialize(item) for item in user_sessions],
                })

            sections.append({'role_key': role_key, 'title': title, 'users': section_users})

        return {'date': day, 'sections': sections}

    def export_data(self, user_ids: list[UUID] | None, date_from: date, date_to: date) -> tuple[list[User], list[BreakSession]]:
        if date_from > date_to:
            raise HTTPException(status_code=422, detail='Start date must be on or before end date.')
        if (date_to - date_from).days > 366:
            raise HTTPException(status_code=422, detail='Export range cannot exceed 366 days.')

        users_query = self.db.query(User).options(joinedload(User.role)).filter(User.deleted_at.is_(None))
        if user_ids is not None:
            users_query = users_query.filter(User.id.in_(user_ids))
        users = users_query.order_by(User.full_name.asc()).all()
        if user_ids is not None and len(users) != len(set(user_ids)):
            raise HTTPException(status_code=422, detail='One or more selected employees are unavailable.')

        start, _ = utc_day_bounds(date_from)
        _, end = utc_day_bounds(date_to)
        sessions = (
            self.db.query(BreakSession)
            .filter(BreakSession.user_id.in_([user.id for user in users]))
            .filter(BreakSession.start_time >= start, BreakSession.start_time < end)
            .order_by(BreakSession.start_time.asc())
            .all()
        ) if users else []
        return users, sessions
