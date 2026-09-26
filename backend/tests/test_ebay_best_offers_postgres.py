"""Opt-in integration tests. Clone empty table structures into a disposable schema.

Run with ACES_RUN_POSTGRES_TESTS=1. Provider requests are always mocked. No live
application rows are read or modified; only public table definitions are used.
"""
import json
import os
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, select, text, func
from sqlalchemy.orm import Session

from app.db.session import engine as application_engine
from app.models.app_config import AppConfigSetting
from app.models.ebay_account import EbayAccount
from app.models.ebay_api_call_attempt import EbayApiCallAttempt
from app.models.ebay_best_offer_action import EbayBestOfferAction
from app.models.offer import Offer
from app.models.role import Role
from app.models.user import User
from app.models.permission import Permission, RolePermission
from app.models.conversation import SyncLog, SyncLogStatus
from app.services.ebay_api_usage_service import EbayApiUsageService
from app.services.ebay_best_offer_job_service import EbayBestOfferJobService, PREFIX
from app.services.ebay_best_offer_lock import account_operation_lock
from app.services.ebay_best_offer_worker import claim
from app.modules.integrations.ebay.services.ebay_best_offer_action_service import EbayBestOfferActionService
from app.modules.integrations.ebay.services.ebay_best_offer_query_service import EbayBestOfferQueryService
from app.modules.integrations.ebay.services.ebay_best_offer_sync_service import EbayBestOfferSyncService
from app.modules.integrations.ebay.schemas.best_offer_schemas import BestOfferActionRequest
from app.modules.integrations.ebay.client.ebay_auth_client import EbayAuthClient

pytestmark = pytest.mark.skipif(os.environ.get('ACES_RUN_POSTGRES_TESTS') != '1', reason='Explicit PostgreSQL test opt-in required')


@pytest.fixture
def isolated():
    schema = 'aces_offer_test_' + uuid4().hex
    assert re.fullmatch(r'aces_offer_test_[a-f0-9]{32}', schema)
    with application_engine.begin() as connection:
        connection.execute(text(f'CREATE SCHEMA "{schema}"'))
        tables = connection.scalars(text("SELECT tablename FROM pg_tables WHERE schemaname='public' AND tablename <> 'alembic_version'")).all()
        for table in tables:
            quoted = table.replace('"', '""')
            connection.execute(text(f'CREATE TABLE "{schema}"."{quoted}" (LIKE public."{quoted}" INCLUDING DEFAULTS INCLUDING CONSTRAINTS INCLUDING INDEXES)'))
    test_engine = create_engine(application_engine.url, connect_args={'options':f'-csearch_path={schema}'}, pool_size=12, max_overflow=8)
    try:
        with Session(test_engine) as db:
            role = Role(name='Admin')
            permission = Permission(code='offer.respond')
            db.add_all([role, permission]); db.flush()
            user = User(email='test@example.invalid', full_name='Test', password_hash='test', role_id=role.id)
            db.add(user); db.flush()
            db.add(RolePermission(role_id=role.id, permission_id=permission.id))
            account = EbayAccount(account_name='Test account', ebay_username='seller', environment='PRODUCTION',
                connection_status='CONNECTED', created_by=user.id, access_token='test-only',
                access_token_expires_at=datetime.now(UTC)+timedelta(days=1))
            db.add(account); db.flush()
            for key,value in [(PREFIX+'enabled','false'),(PREFIX+'interval_minutes','5'),
                    (PREFIX+'account_ids',json.dumps([str(account.id)])),('api.ebay_bestseller_daily_limit','2500000')]:
                db.add(AppConfigSetting(config_key=key,section='offer',label=key,value=value,value_type='text'))
            db.commit()
            yield db, test_engine, account, user
    finally:
        test_engine.dispose()
        # The validated literal name can only target this test's own schema.
        with application_engine.begin() as connection:
            connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))


def raw(offer_id='123', **changes):
    return {**dict(offerId=offer_id, listingId='456', buyerUsername='buyer', amount='30.00', currency='USD',
        quantity=2, status='Active', role='Seller', offerType='BuyerBestOffer',
        expirationTime=(datetime.now(UTC)+timedelta(hours=2)).isoformat(), listing={'title':'Test product','sku':'SKU-1','price':'50','currency':'USD'}), **changes}


def seed_offer(db, account, **changes):
    service = EbayBestOfferSyncService(db)
    offer, _ = service._upsert(account, raw(**changes), None)
    db.commit()
    return offer


def test_quota_first_use_concurrent_atomic_and_caller_rollback(isolated):
    db, engine, account, _ = isolated
    account_id = account.id
    def reserve(_):
        with Session(engine) as other:
            return EbayApiUsageService(other).reserve_attempt(account_id=account_id, operation='GetBestOffers')
    with ThreadPoolExecutor(max_workers=8) as pool:
        ids = list(pool.map(reserve, range(16)))
    assert len(set(ids)) == 16
    assert EbayApiUsageService(db).get_today_usage('bestseller').call_count == 16
    assert db.scalar(select(func.count()).select_from(EbayApiCallAttempt)) == 16
    offer = seed_offer(db, account)
    offer.buyer_username = 'uncommitted'
    EbayApiUsageService(db).reserve_attempt(account_id=account.id, operation='GetBestOffers')
    db.rollback()
    assert db.get(Offer, offer.id).buyer_username == 'buyer'
    assert EbayApiUsageService(db).get_today_usage('bestseller').call_count == 17


def test_reservation_reentry_claim_cas_and_account_protection(isolated):
    db, engine, account, _ = isolated
    first = EbayBestOfferJobService(db).reserve([account.id])
    assert first['newly_reserved']
    with Session(engine) as other:
        second = EbayBestOfferJobService(other).reserve([account.id])
        assert not second['newly_reserved']
        assert second['batch_id'] == first['batch_id']
        assert not claim(other, first['batch_id'], 'wrong-token')
        assert claim(other, first['batch_id'], first['reservation_token'])
        assert not claim(other, first['batch_id'], first['reservation_token'])
    with account_operation_lock(engine, account.id):
        with pytest.raises(HTTPException) as exc:
            with account_operation_lock(engine, account.id):
                pass
        assert exc.value.status_code == 409


def test_discovery_pagination_roles_idempotency_and_row_savepoints(isolated, monkeypatch):
    db, _, account, _ = isolated
    calls = []
    def response(_self, _token, **parameters):
        calls.append(parameters)
        assert parameters['best_offer_status'] == 'Active' and parameters['item_id'] is None
        offers = [raw(),raw('buyer-role',role='Buyer'),raw('unknown-role',role=None),raw('bad',listingId=None)] if parameters['page']==1 else [raw('124')]
        return SimpleNamespace(ok=True,status_code=200,payload={'ack':'Success','offers':offers,'totalPages':2})
    monkeypatch.setattr(EbayAuthClient,'get_best_offers_raw',response)
    service = EbayBestOfferSyncService(db)
    result = service.sync_current(account.id)
    assert result['outcome'] == 'PARTIAL' and result['offers_synced'] == 3
    assert result['discovery'] == {'pages':2,'returned':5,'seller':3,'buyer':1,'buyer_skipped':0,'unknown_role_skipped':1}
    assert db.scalar(select(func.count()).select_from(Offer)) == 3
    service.sync_current(account.id)
    assert db.scalar(select(func.count()).select_from(Offer)) == 3
    assert len(calls) == 4
    assert EbayApiUsageService(db).get_today_usage('bestseller').call_count == 4


@pytest.mark.parametrize('provider_status', ['SellerAccept','PendingBuyerPayment','Accepted','Declined','Expired'])
def test_absence_reconciliation_preserves_exact_state_without_guessing(isolated, monkeypatch, provider_status):
    db, _, account, _ = isolated
    offer = seed_offer(db, account)
    def response(_self,_token,**params):
        offers = [] if params['item_id'] is None else [raw(status=provider_status, role=None)]
        return SimpleNamespace(ok=True,status_code=200,payload={'ack':'Success','offers':offers,'totalPages':1})
    monkeypatch.setattr(EbayAuthClient,'get_best_offers_raw',response)
    result = EbayBestOfferSyncService(db).sync_current(account.id)
    assert result['outcome']=='SUCCESS'
    db.refresh(offer)
    assert offer.provider_status == provider_status and offer.provider_role == 'Seller'
    assert offer.reconciliation_required == (provider_status in ['SellerAccept','PendingBuyerPayment'])


@pytest.mark.parametrize('confirmed,ambiguous,expected', [(True,False,'SUCCEEDED'),(False,False,'FAILED'),(False,True,'RECONCILIATION_REQUIRED')])
def test_durable_action_single_dispatch_idempotency_and_ambiguity(isolated,monkeypatch,confirmed,ambiguous,expected):
    db, engine, account, user = isolated
    offer = seed_offer(db,account)
    dispatched=[]
    def response(_self,_token,**params):
        dispatched.append(params)
        with Session(engine) as observer:
            ledger=observer.scalar(select(EbayBestOfferAction))
            assert ledger.state=='DISPATCHING' and ledger.dispatched_at
            assert observer.scalar(select(func.count()).select_from(EbayApiCallAttempt))==1
        return SimpleNamespace(ok=confirmed,payload={'confirmed':confirmed,'ambiguous':ambiguous})
    monkeypatch.setattr(EbayAuthClient,'respond_to_best_offer_raw',response)
    payload=BestOfferActionRequest(action='Accept',expected_version=offer.version,idempotency_key=uuid4())
    service=EbayBestOfferActionService(db)
    first=service.respond(offer.id,payload,user)
    second=service.respond(offer.id,payload,user)
    assert first['state']==expected and second['id']==first['id'] and len(dispatched)==1
    db.refresh(offer)
    assert offer.provider_status=='Active'  # Accept is never invented as paid.
    if ambiguous:
        retry=BestOfferActionRequest(action='Accept',expected_version=offer.version,idempotency_key=uuid4())
        with pytest.raises(HTTPException) as exc:
            service.respond(offer.id,retry,user)
        assert exc.value.status_code==409 and len(dispatched)==1


def test_unknown_action_active_result_remains_scheduled(isolated,monkeypatch):
    db, _, account, user=isolated
    offer=seed_offer(db,account)
    db.add(EbayBestOfferAction(offer_id=offer.id,account_id=account.id,actor_id=user.id,
        idempotency_key=uuid4(),request_hash='a'*64,expected_version=1,action='Accept',parameters={},state='RECONCILIATION_REQUIRED'))
    offer.reconciliation_required=True;db.commit()
    monkeypatch.setattr(EbayAuthClient,'get_best_offers_raw',lambda *_args,**_kwargs:SimpleNamespace(ok=True,status_code=200,
        payload={'ack':'Success','offers':[raw(role=None)],'totalPages':1}))
    EbayBestOfferSyncService(db).reconcile_listing(account,'456')
    db.refresh(offer)
    assert offer.reconciliation_required
    assert db.scalar(select(EbayBestOfferAction)).state=='RECONCILIATION_REQUIRED'


def test_local_queries_filter_sort_paginate_without_provider(isolated,monkeypatch):
    db, _, account, _=isolated
    seed_offer(db,account)
    seed_offer(db,account,offer_id='124',amount='40.00')
    monkeypatch.setattr(EbayAuthClient,'get_best_offers_raw',lambda *_a,**_k:pytest.fail('View called eBay'))
    view=EbayBestOfferQueryService(db).list(search='SKU-1',sort='amount',page_size=1,can_respond=True)
    assert view['total']==2 and len(view['items'])==1 and view['items'][0]['provider_offer_id']=='124'
    assert view['items'][0]['can_respond']


def test_rbac_endpoints_agent_config403_and_permission_required(isolated,monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from app.api.dependencies import get_current_user
    from app.db.session import get_db
    from app.modules.integrations.ebay.routes.ebay_best_offer_routes import router
    db, _, account, _=isolated
    offer=seed_offer(db,account)
    role=Role(name='AGENT');db.add(role);db.commit()
    user=SimpleNamespace(role=role,role_id=role.id,id=uuid4())
    app=FastAPI();app.include_router(router,prefix='/best-offers')
    app.dependency_overrides[get_current_user]=lambda:user
    app.dependency_overrides[get_db]=lambda:db
    with TestClient(app) as http:
        assert http.get('/best-offers/config').status_code==403
        assert http.patch('/best-offers/config',json={'enabled':True}).status_code==403
        assert http.post('/best-offers/sync',json={}).status_code==403
        assert http.get('/best-offers/jobs/'+str(uuid4())).status_code==403
        view=http.get('/best-offers/current')
        assert view.status_code==200 and not view.json()['items'][0]['can_respond']
        result=http.post(f'/best-offers/{offer.id}/respond',json={'action':'Accept','expected_version':1,'idempotency_key':str(uuid4())})
        assert result.status_code==403


def test_worker_continues_after_an_account_failure(isolated,monkeypatch):
    from sqlalchemy.orm import sessionmaker
    from app.services.ebay_best_offer_worker import run_batch
    db, engine, first_account, user=isolated
    other=EbayAccount(account_name='Other',ebay_username='other',environment='PRODUCTION',connection_status='CONNECTED',created_by=user.id)
    db.add(other);db.commit()
    reservation=EbayBestOfferJobService(db).reserve([first_account.id,other.id])
    monkeypatch.setattr('app.db.session.SessionLocal',sessionmaker(bind=engine))
    first_id=first_account.id
    def sync(_self,account_id,**_kwargs):
        if account_id==first_id:
            raise ValueError('Simulated account failure')
        return {'offers_synced':2,'outcome':'SUCCESS','errors':[]}
    monkeypatch.setattr(EbayBestOfferSyncService,'sync_current',sync)
    run_batch(reservation['batch_id'],reservation['reservation_token'],SimpleNamespace(is_set=lambda:False))
    db.expire_all()
    jobs=list(db.scalars(select(SyncLog).where(SyncLog.provider_account_id.is_not(None))))
    assert {j.status for j in jobs}=={SyncLogStatus.FAILED,SyncLogStatus.SUCCESS}
    assert all(j.completed_at for j in jobs)


def test_spawned_worker_owns_session_and_exits(isolated,monkeypatch):
    import multiprocessing
    from app.services.ebay_best_offer_worker import run_batch
    from app.services.ebay_best_offer_job_service import BATCH
    db, engine, _, _=isolated
    token=str(uuid4())
    batch=SyncLog(provider='EBAY',sync_type=BATCH,status=SyncLogStatus.PENDING,
        sync_metadata={'jobs':[],'trigger':'manual','reservation_token':token})
    db.add(batch);db.commit()
    schema=engine.connect_args if hasattr(engine,'connect_args') else None
    with engine.connect() as connection:
        schema=connection.scalar(text('SELECT current_schema()'))
    child_url=engine.url.update_query_dict({'options':f'-csearch_path={schema}'})
    monkeypatch.setenv('DATABASE_URL',child_url.render_as_string(hide_password=False))
    context=multiprocessing.get_context('spawn')
    process=context.Process(target=run_batch,args=(str(batch.id),token,context.Event()),daemon=False)
    process.start()
    try:
        process.join(timeout=30)
        assert not process.is_alive() and process.exitcode==0
        db.refresh(batch)
        assert batch.status==SyncLogStatus.SUCCESS
    finally:
        if process.is_alive():
            process.terminate();process.join(timeout=5)
        process.close()


def test_application_startup_shutdown_with_stopped_best_offer_schedule(isolated,monkeypatch):
    import asyncio
    from sqlalchemy.orm import sessionmaker
    from fastapi.testclient import TestClient
    import app.main as main
    import app.services.ebay_best_offer_auto_sync_service as schedule
    _,engine,_,_=isolated
    async def idle():
        await asyncio.Event().wait()
    monkeypatch.setattr(main,'ebay_auto_sync_loop',idle)
    monkeypatch.setattr(main,'notification_cleanup_loop',idle)
    monkeypatch.setattr(schedule,'SessionLocal',sessionmaker(bind=engine))
    monkeypatch.setattr(schedule,'dispatch',lambda reservation: reservation if not reservation['newly_reserved'] else pytest.fail('Stopped schedule spawned a worker'))
    with TestClient(main.create_app()) as http:
        assert http.get('/health').json()=={'status':'ok'}
        assert http.get('/api/v1/integrations/ebay/best-offers/current').status_code==401


def test_stale_dispatch_recovered_without_a_batch_and_never_retried(isolated):
    db, engine, account, user=isolated
    offer=seed_offer(db,account)
    ledger=EbayBestOfferAction(offer_id=offer.id,account_id=account.id,actor_id=user.id,
        idempotency_key=uuid4(),request_hash='a'*64,expected_version=1,action='Accept',parameters={},state='DISPATCHING',
        created_at=datetime.now(UTC)-timedelta(minutes=5),dispatched_at=datetime.now(UTC)-timedelta(minutes=5))
    db.add(ledger);db.commit()
    with account_operation_lock(engine,account.id):
        result=EbayBestOfferJobService(db).reserve(trigger='auto',due_only=True)
        assert not result['newly_reserved']
        db.refresh(ledger)
        assert ledger.state=='DISPATCHING'  # A live account operation cannot be reclaimed.
    EbayBestOfferJobService(db).reserve(trigger='auto',due_only=True)
    db.refresh(ledger);db.refresh(offer)
    assert ledger.state=='RECONCILIATION_REQUIRED' and offer.reconciliation_required


def test_all_offers_includes_buyer_expired_and_unverified_history_without_actions(isolated):
    db,_,account,_=isolated
    seed_offer(db,account)
    seed_offer(db,account,offer_id='buyer-expired',role='Buyer',status='Expired')
    history=Offer(provider='EBAY',account_id=account.id,provider_offer_id='old-history',listing_id='457',
        direction='INCOMING',status='EXPIRED',record_source='MESSAGE_PARSE',offer_amount=10,currency='USD')
    synthetic=Offer(provider='EBAY',account_id=account.id,provider_offer_id='123:seller-counteroffer-submitted',
        direction='OUTGOING',status='PENDING',record_source='DERIVED')
    db.add_all([history,synthetic]);db.commit()
    service=EbayBestOfferQueryService(db)
    result=service.list(can_respond=True)
    assert result['total']==3
    records={item['provider_offer_id']:item for item in result['items']}
    assert records['123']['can_respond']
    assert records['buyer-expired']['display_status']=='Expired'
    assert not records['buyer-expired']['can_respond']
    assert not records['old-history']['can_respond'] and not records['old-history']['status_verified']
    assert service.list(role='Buyer')['total']==1
    assert service.list(role='Unknown')['total']==1
    assert service.list(status='Expired')['total']==1


def test_buyer_historical_reconciliation_preserves_role(isolated,monkeypatch):
    db,_,account,_=isolated
    offer=seed_offer(db,account,role='Buyer')
    monkeypatch.setattr(EbayAuthClient,'get_best_offers_raw',lambda *_args,**_kwargs:SimpleNamespace(ok=True,status_code=200,
        payload={'ack':'Success','offers':[raw(role=None,status='Expired')],'totalPages':1}))
    EbayBestOfferSyncService(db).reconcile_listing(account,'456')
    db.refresh(offer)
    assert offer.provider_role=='Buyer' and offer.provider_status=='Expired'


def test_latest_sync_counts_changes_and_skips_old_history(isolated, monkeypatch):
    db, _, account, _ = isolated
    history = seed_offer(db, account, offer_id='old')
    history.record_source = 'LEGACY_UNKNOWN'
    db.commit()
    snapshot = raw(offer_id='new')
    calls = []
    def response(*_args, **kwargs):
        calls.append(kwargs)
        assert not kwargs.get('item_id'), 'Normal sync must not scan old history'
        return SimpleNamespace(ok=True, status_code=200, payload={'ack':'Success', 'offers':[snapshot], 'totalPages':1})
    monkeypatch.setattr(EbayAuthClient, 'get_best_offers_raw', response)
    service = EbayBestOfferSyncService(db)
    assert service.sync_current(account.id)['changes']['new'] == 1
    offer = db.scalar(select(Offer).where(Offer.provider_offer_id == 'new'))
    version = offer.version
    result = service.sync_current(account.id)
    assert result['offers_synced'] == 0 and result['changes']['unchanged'] == 1
    db.refresh(offer)
    assert offer.version == version and len(calls) == 2


def test_unavailable_history_is_a_note_and_preserves_records(isolated, monkeypatch):
    db, _, account, _ = isolated
    offer = seed_offer(db, account)
    offer.record_source = 'LEGACY_UNKNOWN'
    db.commit()
    def response(*_args, **kwargs):
        if kwargs.get('item_id'):
            return SimpleNamespace(ok=True, status_code=200, payload={'ack':'Failure', 'errors':[
                {'code':'21549', 'severity':'Error', 'message':'Item is no longer in our database'}]})
        return SimpleNamespace(ok=True, status_code=200, payload={'ack':'Success', 'offers':[], 'totalPages':1})
    monkeypatch.setattr(EbayAuthClient, 'get_best_offers_raw', response)
    result = EbayBestOfferSyncService(db).sync_current(account.id, include_history=True)
    assert result['outcome'] == 'SUCCESS' and not result['errors']
    assert result['warnings'][0]['provider_codes'] == ['21549']
    assert db.get(Offer, offer.id) is not None
