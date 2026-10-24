from datetime import UTC, date, datetime, time, timedelta, timezone
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session, joinedload

from app.api.dependencies import can_manage_operations, is_support_agent
from app.models.user import User
from app.modules.daily_reports.models import DailyWorkReport
from app.modules.daily_reports.schemas import ReportTask, ReviewedTask
from app.modules.task_management.activity import active_main_tasks, count_main_task


INDIA_TIME = timezone(timedelta(hours=5, minutes=30), name='Asia/Kolkata')


def report_day() -> date:
    return datetime.now(INDIA_TIME).date()


def format_report(day: date, automatic_tasks: list[dict], additional_tasks: list[dict]) -> str:
    lines = [f'Work Report: {day:%d-%m-%Y}', '']
    lines.extend(
        f"{task['name']} - {task['quantity']}"
        for task in automatic_tasks if task['quantity'] > 0
    )
    lines.extend(
        f"{task['name']} - {task['quantity']}"
        + (f" ({task['remarks']})" if task.get('remarks') else '')
        for task in additional_tasks if task['quantity'] > 0
    )
    return '\n'.join(lines).rstrip()


class DailyReportService:
    def __init__(self, db: Session):
        self.db = db

    @staticmethod
    def require_access(current_user) -> None:
        if not (can_manage_operations(current_user) or is_support_agent(current_user)):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail='Daily reports are unavailable for this role')

    def automatic_tasks(self, user_id: UUID, day: date) -> list[dict]:
        tasks = []
        for task in active_main_tasks(self.db):
            if task.source_type in {'MANUAL', 'OTHER'}:
                continue
            quantity = count_main_task(self.db, task, user_id, day)
            if quantity:
                tasks.append({'task_id': str(task.id), 'name': task.name, 'quantity': quantity})
        return tasks

    def _existing(self, user_id: UUID, day: date):
        return self.db.scalar(
            select(DailyWorkReport)
            .options(joinedload(DailyWorkReport.user))
            .where(DailyWorkReport.user_id == user_id, DailyWorkReport.report_date == day)
        )

    @staticmethod
    def serialize(report: DailyWorkReport, today: date) -> dict:
        return {
            'id': report.id,
            'user_id': report.user_id,
            'user_name': report.user.full_name,
            'report_date': report.report_date,
            'automatic_tasks': report.automatic_tasks,
            'additional_tasks': report.additional_tasks,
            'report_text': report.report_text,
            'copied_at': report.copied_at,
            'editable': report.report_date == today,
        }

    def today(self, current_user) -> dict:
        self.require_access(current_user)
        day = report_day()
        existing = self._existing(current_user.id, day)
        automatic = existing.automatic_tasks if existing and existing.copied_at else self.automatic_tasks(current_user.id, day)
        additional = existing.additional_tasks if existing else []
        return {
            'id': existing.id if existing else None,
            'user_id': current_user.id,
            'user_name': current_user.full_name,
            'report_date': day,
            'automatic_tasks': automatic,
            'additional_tasks': additional,
            'report_text': format_report(day, automatic, additional),
            'copied_at': existing.copied_at if existing else None,
            'editable': True,
        }

    def save_today(self, current_user, expected_day: date, tasks: list[ReportTask] | None = None,
                   *, copied: bool = False, reviewed: list[ReviewedTask] | None = None) -> dict:
        self.require_access(current_user)
        day = report_day()
        if expected_day != day:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail='This report date has ended. Reload to view the current day.')
        existing = self._existing(current_user.id, day)
        if copied:
            if reviewed is None:
                raise HTTPException(status_code=422, detail='Review every task quantity before copying')
            automatic, additional = self._reviewed_tasks(reviewed)
        else:
            automatic = self.automatic_tasks(current_user.id, day)
            additional = ([task.model_dump(mode='json') for task in tasks]
                          if tasks is not None else existing.additional_tasks if existing else [])
            if tasks is not None:
                self._validate_additional(additional, existing)
        now = datetime.now(UTC)
        values = {
            'user_id': current_user.id,
            'report_date': day,
            'automatic_tasks': automatic,
            'additional_tasks': additional,
            'report_text': format_report(day, automatic, additional),
            'copied_at': now if copied else existing.copied_at if existing else None,
            'created_at': now,
            'updated_at': now,
        }
        if report_day() != day:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail='The report date has ended. Reload to start the new day.')
        statement = pg_insert(DailyWorkReport).values(**values)
        update_values = {key: values[key] for key in ('automatic_tasks', 'additional_tasks', 'report_text', 'updated_at')}
        if copied:
            update_values['copied_at'] = now
        self.db.execute(statement.on_conflict_do_update(
            constraint='uq_daily_work_reports_user_date', set_=update_values,
        ))
        self.db.commit()
        return self.serialize(self._existing(current_user.id, day), day)

    def _reviewed_tasks(self, reviewed: list[ReviewedTask]) -> tuple[list[dict], list[dict]]:
        catalog = {task.id: task for task in active_main_tasks(self.db)}
        by_id = {item.task_id: item for item in reviewed}
        if len(by_id) != len(reviewed) or set(by_id) != set(catalog):
            raise HTTPException(status_code=422, detail='Review every available task exactly once')
        automatic, additional = [], []
        for task in catalog.values():
            item = by_id[task.id]
            if item.quantity == 0:
                continue
            remarks = (item.remarks or '').strip()
            if task.source_type == 'OTHER' and not remarks:
                raise HTTPException(status_code=422, detail='Other task remarks are required')
            entry = {'task_id': str(task.id), 'name': task.name, 'quantity': item.quantity,
                     'weight': float(task.weight), 'source_type': task.source_type}
            if task.source_type in {'MANUAL', 'OTHER'}:
                entry['remarks'] = remarks if task.source_type == 'OTHER' else None
                additional.append(entry)
            else:
                automatic.append(entry)
        return automatic, additional

    def _validate_additional(self, additional: list[dict], existing: DailyWorkReport | None) -> None:
        catalog = {str(task.id): task for task in active_main_tasks(self.db)}
        seen = set()
        for item in additional:
            if not item.get('task_id') and any(
                old.get('name') == item['name'] and old.get('quantity') == item['quantity']
                for old in (existing.additional_tasks if existing else [])
            ):
                continue
            task = catalog.get(item['task_id']) if item.get('task_id') else None
            if not task or task.source_type not in {'MANUAL', 'OTHER'} or task.id in seen:
                raise HTTPException(status_code=422, detail='Select each active manual task once')
            if task.source_type == 'OTHER' and not (item.get('remarks') or '').strip():
                raise HTTPException(status_code=422, detail='Other task remarks are required')
            item['name'] = task.name
            item['remarks'] = (item.get('remarks') or '').strip() or None
            seen.add(task.id)

    def list_reports(self, current_user, *, date_from: date | None, date_to: date | None,
                     user_id: UUID | None, limit: int, offset: int) -> dict:
        self.require_access(current_user)
        if date_from and date_to and date_from > date_to:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail='From date must be on or before To date')
        if not can_manage_operations(current_user):
            if user_id and user_id != current_user.id:
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail='You can only view your own reports')
            user_id = current_user.id
        query = select(DailyWorkReport)
        if user_id:
            query = query.where(DailyWorkReport.user_id == user_id)
        if date_from:
            query = query.where(DailyWorkReport.report_date >= date_from)
        if date_to:
            query = query.where(DailyWorkReport.report_date <= date_to)
        total = self.db.scalar(select(func.count()).select_from(query.subquery())) or 0
        items = self.db.scalars(
            query.options(joinedload(DailyWorkReport.user))
            .order_by(DailyWorkReport.report_date.desc(), DailyWorkReport.user_id)
            .offset(offset).limit(limit)
        ).all()
        today = report_day()
        return {'items': [self.serialize(item, today) for item in items], 'total': total}

    def report_users(self, current_user) -> list[dict]:
        if not can_manage_operations(current_user):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail='Only managers can list report users')
        rows = self.db.execute(
            select(User.id, User.full_name)
            .join(DailyWorkReport, DailyWorkReport.user_id == User.id)
            .distinct().order_by(User.full_name)
        )
        return [{'id': user_id, 'full_name': name} for user_id, name in rows]
