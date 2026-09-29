"""Record one restored-session login per user and India calendar day."""
from datetime import UTC, datetime, time, timedelta, timezone
from hashlib import sha256

from fastapi import HTTPException
from sqlalchemy import select, text

from app.models.audit_log import AuditLog
from app.services.audit_service import AuditService

INDIA_TIME = timezone(timedelta(hours=5, minutes=30), name='Asia/Kolkata')


def audit_date_bounds(date_from, date_to):
    if date_from > date_to:
        raise HTTPException(422, 'From date must be on or before To date')
    return (datetime.combine(date_from, time.min, tzinfo=INDIA_TIME).astimezone(UTC),
            datetime.combine(date_to + timedelta(days=1), time.min, tzinfo=INDIA_TIME).astimezone(UTC))


def record_daily_login(db, user, *, ip_address=None, user_agent=None, now=None):
    now = now or datetime.now(UTC)
    day = now.astimezone(INDIA_TIME).date()
    start, end = audit_date_bounds(day, day)
    # Serialize tabs/workers for this user/day in the same transaction as the insert.
    lock_key = int.from_bytes(sha256(f'daily-login:{user.id}:{day}'.encode()).digest()[:8], 'big', signed=True)
    db.execute(text('SELECT pg_advisory_xact_lock(:key)'), {'key': lock_key})
    existing = db.scalar(select(AuditLog.id).where(AuditLog.user_id == user.id,
        AuditLog.action == 'LOGIN_SUCCESS', AuditLog.created_at >= start, AuditLog.created_at < end).limit(1))
    if existing:
        return False
    AuditService(db).log(action='LOGIN_SUCCESS', user_id=user.id, category='AUTHENTICATION',
        metadata={'login_method': 'cookie', 'login_date': day.isoformat(), 'timezone': 'Asia/Kolkata'},
        ip_address=ip_address, user_agent=user_agent)
    return True
