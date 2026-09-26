"""Persisted configuration and single-flight reservations on existing SyncLog."""
from datetime import UTC, datetime, timedelta
import json
from uuid import uuid4
from fastapi import HTTPException
from sqlalchemy import select, text
from app.models.app_config import AppConfigSetting
from app.models.ebay_account import EbayAccount
from app.models.conversation import SyncLog, SyncLogStatus
from app.models.ebay_best_offer_action import EbayBestOfferAction
from app.services.audit_service import AuditService
from app.services.ebay_best_offer_lock import lock_key

BATCH = 'EBAY_BEST_OFFER_BATCH'
ACCOUNT = 'EBAY_BEST_OFFER_SYNC'
PREFIX = 'offer.best_offer_'


def read_config(db):
    values = dict(db.execute(select(AppConfigSetting.config_key, AppConfigSetting.value)
        .where(AppConfigSetting.config_key.like(PREFIX + '%'))).all())
    return {'enabled': values.get(PREFIX+'enabled', 'false') == 'true',
            'interval_minutes': int(values.get(PREFIX+'interval_minutes', '5')),
            'account_ids': json.loads(values.get(PREFIX+'account_ids', '[]'))}


def eligible_accounts(db):
    return list(db.scalars(select(EbayAccount).where(EbayAccount.is_active.is_(True),
        EbayAccount.connection_status == 'CONNECTED').order_by(EbayAccount.account_name)))


def job_response(job):
    return {'id': job.id, 'account_id': job.provider_account_id, 'status': job.status.value,
            'started_at': job.started_at, 'completed_at': job.completed_at,
            'records_processed': job.records_processed, 'error': job.error_message,
            'result': job.sync_metadata or {}}


class EbayBestOfferJobService:
    def __init__(self, db):
        self.db = db

    def config(self):
        config = read_config(self.db)
        latest = self.db.scalar(select(SyncLog).where(SyncLog.sync_type == BATCH)
            .order_by(SyncLog.started_at.desc()).limit(1))
        accounts = eligible_accounts(self.db)
        config['accounts'] = [{'id': a.id, 'name': a.account_name, 'username': a.ebay_username} for a in accounts]
        config['latest_job'] = job_response(latest) if latest else None
        automatic = self.db.scalar(select(SyncLog).where(SyncLog.sync_type == BATCH, SyncLog.sync_metadata['trigger'].astext == 'auto').order_by(SyncLog.started_at.desc()).limit(1))
        config['next_run_at'] = (max(datetime.now(UTC), (automatic.completed_at or automatic.started_at) + timedelta(minutes=config['interval_minutes']))
            if automatic and config['enabled'] else datetime.now(UTC) if config['enabled'] else None)
        return config

    def update_config(self, payload, user):
        rows = {r.config_key: r for r in self.db.scalars(select(AppConfigSetting)
            .where(AppConfigSetting.config_key.like(PREFIX + '%')).with_for_update())}
        if payload.account_ids is not None:
            allowed = {a.id for a in eligible_accounts(self.db)}
            if set(payload.account_ids) - allowed:
                raise HTTPException(422, 'Select active connected eBay accounts only')
            rows[PREFIX+'account_ids'].value = json.dumps(sorted({str(i) for i in payload.account_ids}))
        if payload.hours is not None:
            rows[PREFIX+'interval_minutes'].value = str(payload.hours * 60 + payload.minutes)
        if payload.enabled is not None:
            rows[PREFIX+'enabled'].value = str(payload.enabled).lower()
        for row in rows.values():
            row.updated_by_user_id = user.id
        event = 'EBAY_BEST_OFFER_CONFIG_CHANGED'
        if payload.enabled is not None:
            event = 'EBAY_BEST_OFFER_AUTO_STARTED' if payload.enabled else 'EBAY_BEST_OFFER_AUTO_STOPPED'
        AuditService(self.db).log(action=event, user_id=user.id, category='OFFER_MANAGEMENT',
            metadata=payload.model_dump(mode='json', exclude_none=True))
        self.db.commit()
        return self.config()

    def recover_abandoned(self):
        batch = self.db.scalar(select(SyncLog).where(SyncLog.sync_type == BATCH,
            SyncLog.status.in_([SyncLogStatus.PENDING, SyncLogStatus.RUNNING])))
        if not batch or batch.started_at > datetime.now(UTC) - timedelta(minutes=2):
            return
        # Never reclaim a live worker, regardless of heartbeat age.
        available = self.db.scalar(text('SELECT pg_try_advisory_xact_lock(:key)'), {'key': lock_key('batch-execution')})
        if not available:
            return
        for job in self.db.scalars(select(SyncLog).where(SyncLog.id.in_(
                [batch.id] + [uuid for uuid in (batch.sync_metadata or {}).get('jobs', [])]))):
            if job.status in {SyncLogStatus.PENDING, SyncLogStatus.RUNNING}:
                job.status = SyncLogStatus.FAILED
                job.error_message = 'Worker abandoned; a new reservation is required'
                job.completed_at = datetime.now(UTC)
        self.db.flush()

    def recover_actions(self):
        from app.models.offer import Offer
        # An account lock distinguishes an interrupted dispatch from a live one.
        cutoff = datetime.now(UTC) - timedelta(minutes=2)
        stale = list(self.db.scalars(select(EbayBestOfferAction).where(
            EbayBestOfferAction.state.in_(['PREPARED', 'DISPATCHING']),
            EbayBestOfferAction.created_at < cutoff)))
        for action in stale:
            available = self.db.scalar(text('SELECT pg_try_advisory_xact_lock(:key)'),
                {'key': lock_key(action.account_id)})
            if not available:
                continue
            if action.state == 'PREPARED':
                action.state = 'FAILED'
                action.error = 'Interrupted before dispatch; no provider action sent'
            else:
                action.state = 'RECONCILIATION_REQUIRED'
                action.error = 'Interrupted dispatch; provider result requires reconciliation'
                offer = self.db.get(Offer, action.offer_id)
                if offer:
                    offer.reconciliation_required = True
            action.completed_at = datetime.now(UTC)
        self.db.flush()

    def reserve(self, account_ids=None, *, trigger='manual', user=None, due_only=False):
        # Serialize reservation across all API/scheduler processes.
        self.db.execute(text('SELECT pg_advisory_xact_lock(:key)'), {'key': lock_key('reservation')})
        self.recover_abandoned()
        self.recover_actions()
        running = self.db.scalar(select(SyncLog).where(SyncLog.sync_type == BATCH,
            SyncLog.status.in_([SyncLogStatus.PENDING, SyncLogStatus.RUNNING])))
        if running:
            self.db.commit()
            jobs = list(self.db.scalars(select(SyncLog).where(SyncLog.id.in_((running.sync_metadata or {}).get('jobs', [])))))
            return {'newly_reserved': False, 'batch_id': running.id, 'status': 'already_running',
                    'jobs': [job_response(j) for j in jobs]}
        config = read_config(self.db)
        if due_only:
            if not config['enabled']:
                self.db.commit()
                return {'newly_reserved': False, 'jobs': [], 'status': 'stopped'}
            latest = self.db.scalar(select(SyncLog).where(SyncLog.sync_type == BATCH,
                SyncLog.sync_metadata['trigger'].astext == 'auto').order_by(SyncLog.started_at.desc()).limit(1))
            if latest and (latest.completed_at or latest.started_at) + timedelta(minutes=config['interval_minutes']) > datetime.now(UTC):
                self.db.commit()
                return {'newly_reserved': False, 'jobs': [], 'status': 'not_due'}
        selected = set(str(i) for i in (account_ids if account_ids is not None else config['account_ids']))
        eligible = eligible_accounts(self.db)
        if selected - {str(a.id) for a in eligible}:
            if trigger == 'manual':
                raise HTTPException(422, 'One or more selected accounts are not active and connected')
        accounts = [a for a in eligible if str(a.id) in selected]
        if not accounts:
            self.db.commit()
            return {'newly_reserved': False, 'jobs': [], 'status': 'no_accounts'}
        token = str(uuid4())
        jobs = []
        for account in accounts:
            prior = self.db.scalar(select(SyncLog).where(SyncLog.sync_type == ACCOUNT,
                SyncLog.provider_account_id == account.id, SyncLog.status.in_([SyncLogStatus.PENDING, SyncLogStatus.RUNNING])))
            if prior:
                continue
            job = SyncLog(id=uuid4(), provider='EBAY', provider_account_id=account.id, sync_type=ACCOUNT,
                status=SyncLogStatus.PENDING, records_processed=0,
                sync_metadata={'trigger': trigger, 'reservation_token': token, 'account_name': account.account_name})
            self.db.add(job)
            jobs.append(job)
        if not jobs:
            self.db.commit()
            return {'newly_reserved': False, 'jobs': [], 'status': 'already_running'}
        batch = SyncLog(id=uuid4(), provider='EBAY', sync_type=BATCH, status=SyncLogStatus.PENDING,
            records_processed=0, sync_metadata={'trigger': trigger, 'reservation_token': token,
                'jobs': [str(j.id) for j in jobs], 'requested_by': str(user.id) if user else None})
        self.db.add(batch)
        if user:
            AuditService(self.db).log(action='EBAY_BEST_OFFER_MANUAL_SYNC_REQUESTED', user_id=user.id,
                category='OFFER_MANAGEMENT', metadata={'batch_id': str(batch.id), 'accounts': list(selected)})
        self.db.commit()
        return {'newly_reserved': True, 'batch_id': batch.id, 'reservation_token': token,
                'status': 'queued', 'jobs': [job_response(j) for j in jobs]}
