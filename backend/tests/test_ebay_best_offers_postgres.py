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
from app.models.conversation import Conversation, SyncLog, SyncLogStatus
from app.models.ebay_best_offer_listing_sync_state import EbayBestOfferListingSyncState
from app.services.ebay_api_usage_service import EbayApiUsageService
from app.services.ebay_best_offer_job_service import EbayBestOfferJobService, PREFIX
from app.services.ebay_best_offer_lock import account_operation_lock
from app.services.ebay_best_offer_worker import claim
from app.modules.integrations.ebay.services.ebay_best_offer_action_service import EbayBestOfferActionService
from app.modules.integrations.ebay.services.ebay_best_offer_query_service import EbayBestOfferQueryService
from app.modules.integrations.ebay.services.ebay_best_offer_snapshot import current_snapshot_ids, replace_current_snapshot, SNAPSHOT
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
    db.flush()
    ids, _ = current_snapshot_ids(db, account.id)
    replace_current_snapshot(db, account.id, ids | {offer.id})
    db.commit()
    return offer


def test_due_current_offer_decline_overrides_stale_account_scan(isolated, monkeypatch):
    db, _, account, _ = isolated
    offer = seed_offer(db, account, status='Pending')
    calls = []
    def provider(self, token, **kwargs):
        calls.append(kwargs.get('item_id'))
        rows = [raw(status='Declined' if kwargs.get('item_id') else 'Pending')]
        return SimpleNamespace(ok=True, status_code=200,
            payload={'ack': 'Success', 'offers': rows, 'totalPages': 1, 'errors': []})
    monkeypatch.setattr(EbayAuthClient, 'get_best_offers_raw', provider)
    result = EbayBestOfferSyncService(db).sync_current(account.id)
    db.refresh(offer)
    assert offer.provider_status == 'Declined'
    assert result['reconciliation']['reconciled'] == 1
    assert calls == [None, '456']
    assert EbayBestOfferQueryService(db).list(view='current')['total'] == 0
    assert EbayBestOfferQueryService(db).list(view='history')['items'][0]['status_group'] == 'CLOSED'


def test_closed_latest_step_hides_older_snapshot_for_both_accounts(isolated):
    db, _, seller, user = isolated
    buyer_account = EbayAccount(account_name='Buyer account', ebay_username='buyer', environment='PRODUCTION',
        connection_status='CONNECTED', created_by=user.id)
    db.add(buyer_account); db.commit()
    old = seed_offer(db, seller, offer_id='100', status='Countered')
    seed_offer(db, buyer_account, offer_id='100', status='Countered', role='Buyer')
    closed = seed_offer(db, seller, offer_id='101', status='Declined', offerType='SellerCounterOffer')
    # Snapshot membership can lag behind the authoritative terminal row.
    replace_current_snapshot(db, seller.id, {old.id}); db.commit()
    service = EbayBestOfferQueryService(db)
    assert service.list(view='current')['total'] == 0
    assert service.list(view='current', account_id=buyer_account.id)['total'] == 0
    history = service.list(view='history')['items']
    assert len(history) == 1 and history[0]['id'] == closed.id
    assert history[0]['offer_from'] == 'seller' and history[0]['offer_to'] == 'buyer'


def test_all_offers_last_checked_filter_and_mark_done(isolated):
    from app.modules.integrations.ebay.routes.ebay_best_offer_routes import mark_done

    db, _, account, user = isolated
    older_at = datetime(2026, 9, 1, 10, tzinfo=UTC)
    newer_at = datetime(2026, 9, 2, 10, tzinfo=UTC)
    older = seed_offer(db, account, offer_id='100', status='Active', buyerUsername='older-buyer', createdTime=newer_at.isoformat())
    newer = seed_offer(db, account, offer_id='101', status='Declined', buyerUsername='newer-buyer', createdTime=older_at.isoformat())
    older.last_synced_at = older_at
    newer.last_synced_at = newer_at
    db.commit()
    service = EbayBestOfferQueryService(db)
    assert {item['id'] for item in service.list(view='all')['items']} == {older.id, newer.id}
    filtered = service.list(view='all', checked_after=datetime(2026, 9, 2, tzinfo=UTC))
    assert [item['id'] for item in filtered['items']] == [newer.id]
    mark_done(newer.id, db=db, user=user)
    assert [item['id'] for item in service.list(view='all')['items']] == [older.id]
    saved = service.list(view='done')['items']
    assert [item['id'] for item in saved] == [newer.id]
    assert saved[0]['display_status'] == 'Declined' and saved[0]['done_at']


def test_negotiation_card_shows_latest_price_per_side_and_full_closed_history(isolated):
    from app.modules.integrations.ebay.routes.ebay_best_offer_routes import mark_done

    db, _, account, user = isolated
    start = datetime(2026, 9, 1, 10, tzinfo=UTC)
    first = seed_offer(db, account, offer_id='500', amount='500', status='Countered',
        offerType='BuyerBestOffer', createdTime=start.isoformat())
    seller = seed_offer(db, account, offer_id='600', amount='600', status='Countered',
        offerType='SellerCounterOffer', createdTime=(start + timedelta(hours=1)).isoformat())
    buyer = seed_offer(db, account, offer_id='550', amount='550', status='Active',
        offerType='BuyerCounterOffer', createdTime=(start + timedelta(hours=2)).isoformat())
    service = EbayBestOfferQueryService(db)
    result = service.list(view='all')
    assert result['total'] == 1
    card = result['items'][0]
    assert card['id'] == buyer.id and card['latest_side'] == 'buyer'
    assert [(step['side'], str(step['amount'])) for step in card['negotiation']] == [
        ('buyer', '500'), ('seller', '600'), ('buyer', '550')]
    assert [step['at'] for step in card['negotiation']] == [
        start, start + timedelta(hours=1), start + timedelta(hours=2)]

    buyer.provider_status = 'Declined'
    db.commit()
    closed = service.list(view='all')['items'][0]
    assert closed['status_group'] == 'CLOSED'
    assert len(closed['negotiation']) == 3
    mark_done(buyer.id, db=db, user=user)
    assert service.list(view='all')['total'] == 0
    saved = service.list(view='done')['items']
    assert len(saved) == 1 and saved[0]['id'] == buyer.id
    db.refresh(first)
    db.refresh(seller)
    assert first.done_at and seller.done_at


def test_declined_offer_cannot_reopen_from_delayed_provider_response(isolated, monkeypatch):
    db, _, account, _ = isolated
    offer = seed_offer(db, account, status='Declined')
    original = dict(offer.provider_snapshot)
    mock_two_pass(monkeypatch, lambda item_id: [raw(status='Countered')])
    service = EbayBestOfferSyncService(db)
    updated, created = service._upsert(account, raw(status='Pending'), None)
    db.commit()
    assert not created and updated.provider_status == 'Declined'
    service.reconcile_listing(account, '456')
    db.refresh(offer)
    assert offer.provider_status == 'Declined' and offer.provider_snapshot == original
    assert EbayBestOfferQueryService(db).list(view='current')['total'] == 0


def test_same_offer_terminal_on_other_account_hides_stale_mirror(isolated):
    db, _, account, user = isolated
    other = EbayAccount(account_name='Buyer account', ebay_username='buyer', environment='PRODUCTION',
        connection_status='CONNECTED', created_by=user.id)
    db.add(other); db.commit()
    seed_offer(db, account, status='Declined')
    seed_offer(db, other, status='Countered', role='Buyer')
    assert EbayBestOfferQueryService(db).list(view='current', account_id=other.id)['total'] == 0


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
    first_page = [raw(), raw('buyer-role', role='Buyer'), raw('unknown-role', role=None), raw('bad', listingId=None)]
    second_page = [raw('124')]
    def response(_self, _token, **parameters):
        calls.append(parameters)
        if parameters['item_id']:
            assert parameters['best_offer_status'] == 'All' and parameters['item_id'] == '456'
            return SimpleNamespace(ok=True,status_code=200,payload={'ack':'Success','offers':[first_page[0], first_page[1], second_page[0]],'totalPages':1})
        assert parameters['best_offer_status'] == 'Active' and parameters['item_id'] is None
        offers = first_page if parameters['page']==1 else second_page
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


@pytest.mark.parametrize('provider_status', ['SellerAccept','PendingBuyerPayment','PendingBuyerConfirmation','AdminEnded','Accepted','Declined','Expired'])
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
    assert not offer.reconciliation_required
    state = db.scalar(select(EbayBestOfferListingSyncState))
    delay = state.next_reconcile_at - state.last_reconciled_at
    assert delay == (timedelta(minutes=15) if provider_status == 'PendingBuyerPayment' else timedelta(minutes=5)
        if provider_status in {'SellerAccept', 'PendingBuyerConfirmation'} else timedelta(days=7))


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
    seed_offer(db,account,offer_id='124',amount='40.00',buyerUsername='other-buyer')
    monkeypatch.setattr(EbayAuthClient,'get_best_offers_raw',lambda *_a,**_k:pytest.fail('View called eBay'))
    view=EbayBestOfferQueryService(db).list(search='SKU-1',sort='amount',page_size=1,can_respond=True)
    assert view['total']==2 and len(view['items'])==1 and view['items'][0]['provider_offer_id']=='124'
    assert view['items'][0]['can_respond']


def test_status_filter_includes_legacy_capitalization(isolated):
    db, _, account, _ = isolated
    seed_offer(db, account, offer_id='accepted-provider', status='Accepted', buyerUsername='first-buyer')
    historical = seed_offer(db, account, offer_id='accepted-history', status='Accepted', buyerUsername='second-buyer')
    historical.provider_status = None
    historical.status = 'ACCEPTED'
    seed_offer(db, account, offer_id='pending-provider', status='Pending')
    db.commit()
    for status in ('Accepted', 'ACCEPTED', ' accepted '):
        view = EbayBestOfferQueryService(db).list(status=status, view='history')
        assert view['total'] == 2
        assert {item['provider_offer_id'] for item in view['items']} == {'accepted-provider', 'accepted-history'}


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
    seed_offer(db,account,offer_id='buyer-expired',role='Buyer',status='Expired',buyerUsername='other-buyer')
    history=Offer(provider='EBAY',account_id=account.id,provider_offer_id='old-history',listing_id='457',
        direction='INCOMING',status='EXPIRED',record_source='MESSAGE_PARSE',offer_amount=10,currency='USD')
    synthetic=Offer(provider='EBAY',account_id=account.id,provider_offer_id='123:seller-counteroffer-submitted',
        direction='OUTGOING',status='PENDING',record_source='DERIVED')
    db.add_all([history,synthetic]);db.commit()
    service=EbayBestOfferQueryService(db)
    result=service.list(can_respond=True, view='history')
    assert result['total']==2
    records={item['provider_offer_id']:item for item in result['items']}
    assert service.list(can_respond=True)['items'][0]['can_respond']
    assert records['buyer-expired']['display_status']=='Expired'
    assert not records['buyer-expired']['can_respond']
    assert not records['old-history']['can_respond'] and not records['old-history']['status_verified']
    assert service.list(role='Buyer', view='history')['total']==1
    assert service.list(role='Unknown', view='history')['total']==1
    assert service.list(status='Expired', view='history')['total']==2  # Includes legacy EXPIRED history.


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
    history = seed_offer(db, account, offer_id='old', listingId='old-listing')
    history.record_source = 'LEGACY_UNKNOWN'
    db.commit()
    snapshot = raw(offer_id='new')
    calls = []
    def response(*_args, **kwargs):
        calls.append(kwargs)
        assert kwargs.get('item_id') in (None, '456'), 'Normal sync must not scan unrelated old history'
        return SimpleNamespace(ok=True, status_code=200, payload={'ack':'Success', 'offers':[snapshot], 'totalPages':1})
    monkeypatch.setattr(EbayAuthClient, 'get_best_offers_raw', response)
    service = EbayBestOfferSyncService(db)
    assert service.sync_current(account.id)['changes']['new'] == 1
    offer = db.scalar(select(Offer).where(Offer.provider_offer_id == 'new'))
    version = offer.version
    result = service.sync_current(account.id)
    assert result['offers_synced'] == 0 and result['changes']['unchanged'] == 2
    db.refresh(offer)
    assert offer.version == version and len(calls) == 3
    third = service.sync_current(account.id)
    assert third['reconciliation']['not_due'] == 1
    assert len(calls) == 4  # The scheduled listing check is not repeated immediately.


def test_unavailable_history_is_a_note_and_preserves_records(isolated, monkeypatch):
    db, _, account, _ = isolated
    offer = seed_offer(db, account, status='Expired')
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


def conversation_candidate(db, account, listing_id='456', days_ago=1):
    activity = datetime.now(UTC) - timedelta(days=days_ago)
    conversation = Conversation(provider='EBAY', provider_account_id=account.id,
        provider_conversation_id=uuid4().hex, provider_conversation_type='FROM_MEMBERS',
        reference_id=listing_id, buyer_identifier='buyer', last_message_at=activity, created_at=activity)
    db.add(conversation)
    db.commit()
    return conversation


def mock_two_pass(monkeypatch, listing_offers):
    calls = []
    def response(_self, _token, **params):
        calls.append(params)
        item_id = params.get('item_id')
        assert params['best_offer_status'] == ('All' if item_id else 'Active')
        return SimpleNamespace(ok=True, status_code=200, payload={'ack': 'Success',
            'offers': listing_offers(item_id) if item_id else [], 'totalPages': 1})
    monkeypatch.setattr(EbayAuthClient, 'get_best_offers_raw', response)
    return calls


def test_disappeared_current_offer_is_archived_without_messages(isolated, monkeypatch):
    db, _, account, _ = isolated
    conversation = conversation_candidate(db, account)
    seed_offer(db, account)
    calls = mock_two_pass(monkeypatch, lambda item_id: [raw(status='Accepted')])
    service = EbayBestOfferSyncService(db)
    result = service.sync_current(account.id, include_history=True)
    assert result['discovery']['returned'] == 0
    assert result['reconciliation']['reconciled'] == 1
    assert result['changes']['status_changes'] == 1 and result['api_calls'] == 2
    offer = db.scalar(select(Offer))
    assert offer.provider_status == 'Accepted' and offer.conversation_id == conversation.id
    db.refresh(conversation)
    assert conversation.has_offers
    view = EbayBestOfferQueryService(db).list(lifecycle='COMPLETED', view='history')
    assert view['total'] == 1 and view['items'][0]['status_group'] == 'COMPLETED'
    assert view['status_groups']['COMPLETED'] == 1
    assert EbayBestOfferQueryService(db).list(lifecycle='AGREED', view='history')['total'] == 0
    second = service.sync_current(account.id, include_history=True)
    assert second['reconciliation']['candidates'] == 0
    assert len(calls) == 3  # The second run only does account-wide discovery.


def test_history_never_scans_old_conversations(isolated, monkeypatch):
    db, _, account, _ = isolated
    conversation_candidate(db, account, days_ago=180)
    calls = mock_two_pass(monkeypatch, lambda item_id: [raw(status='Expired')])
    service = EbayBestOfferSyncService(db)
    assert service.sync_current(account.id)['reconciliation']['candidates'] == 0
    assert service.sync_current(account.id, include_history=True)['changes']['new'] == 0
    assert [call['item_id'] for call in calls] == [None, None]
    assert db.scalar(select(Offer)) is None


def test_orphan_listing_state_never_triggers_history_requests(isolated, monkeypatch):
    db, _, account, _ = isolated
    db.add(EbayBestOfferListingSyncState(account_id=account.id, listing_id='456',
        last_checked_at=datetime.now(UTC)-timedelta(hours=1), next_reconcile_at=datetime.now(UTC)-timedelta(minutes=1)))
    db.commit()
    mock_two_pass(monkeypatch, lambda item_id: [raw(status='Declined')])
    result = EbayBestOfferSyncService(db).sync_current(account.id, include_history=True)
    assert result['changes']['new'] == 0
    assert db.scalar(select(Offer)) is None


def test_verified_agreement_is_due_without_uncertain_flag_and_keeps_exact_state(isolated, monkeypatch):
    db, _, account, _ = isolated
    offer = seed_offer(db, account, status='SellerAccept')
    assert not offer.reconciliation_required
    mock_two_pass(monkeypatch, lambda item_id: [raw(status='PendingBuyerPayment')])
    result = EbayBestOfferSyncService(db).sync_current(account.id)
    assert result['changes']['status_changes'] == 1
    db.refresh(offer)
    assert offer.provider_status == 'PendingBuyerPayment' and offer.status != 'ACCEPTED'
    assert not offer.reconciliation_required
    view = EbayBestOfferQueryService(db).list(lifecycle='AGREED', can_respond=True, view='current')
    assert view['status_groups']['AGREED'] == 1 and view['status_groups']['COMPLETED'] == 0
    assert view['items'][0]['display_status'] == 'Awaiting buyer payment'
    assert not view['items'][0]['can_respond']
    second = EbayBestOfferSyncService(db).sync_current(account.id)
    assert second['reconciliation']['not_due'] == 1
    assert EbayBestOfferQueryService(db).list(lifecycle='AGREED')['total'] == 1


def test_item_reconciliation_never_creates_unknown_role_offers(isolated, monkeypatch):
    db, _, account, _ = isolated
    seed_offer(db, account)
    mock_two_pass(monkeypatch, lambda item_id: [raw(offer_id='unknown-new', status='Accepted', role=None)])
    result = EbayBestOfferSyncService(db).sync_current(account.id, include_history=True)
    assert result['reconciliation']['unknown_role_skipped'] == 1
    assert db.scalar(select(func.count()).select_from(Offer)) == 1


def test_unknown_provider_state_does_not_release_an_ambiguous_action(isolated, monkeypatch):
    db, _, account, user = isolated
    offer = seed_offer(db, account)
    action = EbayBestOfferAction(offer_id=offer.id, account_id=account.id, actor_id=user.id,
        idempotency_key=uuid4(), request_hash='a'*64, expected_version=1,
        action='Accept', parameters={}, state='RECONCILIATION_REQUIRED')
    db.add(action)
    offer.reconciliation_required = True
    db.commit()
    mock_two_pass(monkeypatch, lambda item_id: [raw(status='FutureProviderState')])
    EbayBestOfferSyncService(db).sync_current(account.id)
    db.refresh(offer)
    db.refresh(action)
    assert offer.provider_status == 'FutureProviderState' and offer.reconciliation_required
    assert action.state == 'RECONCILIATION_REQUIRED'
    view = EbayBestOfferQueryService(db).list(lifecycle='UNKNOWN', view='history')
    assert view['items'][0]['display_status'] == 'FutureProviderState'


def test_latest_buyer_item_replaces_older_offer_before_filters_and_counts(isolated):
    db, _, account, _ = isolated
    old = seed_offer(db, account, offer_id='158152461', buyerUsername=' sales-plc ', status='Countered',
        createdTime='2026-09-17T10:00:00Z')
    newest = seed_offer(db, account, offer_id='158152464', buyerUsername='SALES-PLC', status='Accepted',
        createdTime='2026-09-17T10:00:00Z')
    old.last_synced_at = datetime.now(UTC) + timedelta(hours=1)
    db.commit()
    service = EbayBestOfferQueryService(db)
    for mode in ('current', 'history'):
        view = service.list(view=mode, page_size=1)
        assert view['total'] == (1 if mode == 'history' else 0)
        if mode == 'history':
            assert view['items'][0]['id'] == newest.id
            assert view['status_groups']['COMPLETED'] == 1 and view['status_groups']['OPEN'] == 0
        assert service.list(view=mode, status='Countered')['total'] == 0
        assert service.list(view=mode, search='158152461')['total'] == 0


def test_latest_offer_uses_provider_time_instead_of_amount_or_sync_order(isolated):
    db, _, account, _ = isolated
    latest = seed_offer(db, account, offer_id='100', amount='20', createdTime='2026-09-18T10:00:00Z')
    seed_offer(db, account, offer_id='200', amount='100', createdTime='2026-09-17T10:00:00Z')
    view = EbayBestOfferQueryService(db).list(sort='amount')
    assert view['total'] == 1 and view['items'][0]['id'] == latest.id


def test_empty_sync_replaces_current_cache_but_keeps_action_and_history(isolated, monkeypatch):
    db, _, account, user = isolated
    offer = seed_offer(db, account)
    action = EbayBestOfferAction(offer_id=offer.id, account_id=account.id, actor_id=user.id,
        idempotency_key=uuid4(), request_hash='a'*64, expected_version=1, action='Accept',
        parameters={}, state='SUCCEEDED')
    db.add(action)
    db.commit()
    calls = []
    def response(*_args, **params):
        calls.append(params)
        return SimpleNamespace(ok=False, status_code=200, payload={'ack':'Failure', 'offers': [],
            'errors':[{'code':'20140', 'severity':'Error', 'message':'No best offers found for your criteria.'}]})
    monkeypatch.setattr(EbayAuthClient, 'get_best_offers_raw', response)
    result = EbayBestOfferSyncService(db).sync_current(account.id)
    assert result['outcome'] == 'SUCCESS' and not result['errors']
    service = EbayBestOfferQueryService(db)
    assert service.list(account_id=account.id)['total'] == 0
    assert service.list(account_id=account.id, view='history')['total'] == 0
    assert db.get(Offer, offer.id) is not None
    assert db.get(EbayBestOfferAction, action.id).offer_id == offer.id
    assert all(call['best_offer_status'] in {'Active', 'All'} for call in calls)
    with pytest.raises(HTTPException) as exc:
        EbayBestOfferActionService(db).respond(offer.id,
            BestOfferActionRequest(action='Accept', expected_version=offer.version, idempotency_key=uuid4()), user)
    assert exc.value.status_code == 409


def test_failed_later_discovery_page_never_publishes_partial_cache(isolated, monkeypatch):
    db, _, account, _ = isolated
    previous = seed_offer(db, account, offer_id='old')
    def response(*_args, **params):
        if params['page'] == 1:
            return SimpleNamespace(ok=True, status_code=200, payload={'ack':'Success',
                'offers':[raw(offer_id='new')], 'totalPages':2})
        return SimpleNamespace(ok=False, status_code=200, payload={'ack':'Failure',
            'errors':[{'code':'37', 'severity':'Error', 'message':'Provider unavailable'}]})
    monkeypatch.setattr(EbayAuthClient, 'get_best_offers_raw', response)
    with pytest.raises(RuntimeError):
        EbayBestOfferSyncService(db).sync_current(account.id)
    ids, _ = current_snapshot_ids(db, account.id)
    assert ids == {previous.id}
    assert EbayBestOfferQueryService(db).list()['items'][0]['id'] == previous.id


def test_empty_account_cache_does_not_clear_another_account_or_merge_buyers(isolated, monkeypatch):
    db, _, account, user = isolated
    seed_offer(db, account)
    other = EbayAccount(account_name='Other', ebay_username='other', environment='PRODUCTION',
        connection_status='CONNECTED', created_by=user.id)
    db.add(other)
    db.commit()
    first = seed_offer(db, other)
    second = seed_offer(db, other, offer_id='124', buyerUsername='another-buyer')
    calls = mock_two_pass(monkeypatch, lambda item_id: [])
    service = EbayBestOfferSyncService(db)
    service.sync_current(account.id)
    service.sync_current(account.id)
    assert len(calls) == 3  # No repeated listing checks after confirmed absence.
    view = EbayBestOfferQueryService(db).list()
    assert view['total'] == 2 and {item['id'] for item in view['items']} == {first.id, second.id}
    assert db.scalar(select(func.count()).select_from(SyncLog).where(SyncLog.sync_type == SNAPSHOT)) == 2


def test_archived_conversations_do_not_trigger_history_requests_in_normal_sync(isolated, monkeypatch):
    db, _, account, _ = isolated
    conversation_candidate(db, account)
    calls = mock_two_pass(monkeypatch, lambda item_id: pytest.fail('Routine sync scanned archived history'))
    result = EbayBestOfferSyncService(db).sync_current(account.id)
    assert result['outcome'] == 'SUCCESS' and result['api_calls'] == 1
    assert len(calls) == 1 and EbayBestOfferQueryService(db).list()['total'] == 0


def test_superseded_current_offer_cannot_receive_an_action(isolated, monkeypatch):
    db, _, account, user = isolated
    old = seed_offer(db, account, offer_id='123', createdTime='2026-09-17T10:00:00Z')
    seed_offer(db, account, offer_id='124', createdTime='2026-09-18T10:00:00Z')
    monkeypatch.setattr(EbayAuthClient, 'respond_to_best_offer_raw', lambda *_a, **_k: pytest.fail('Superseded action sent'))
    with pytest.raises(HTTPException) as exc:
        EbayBestOfferActionService(db).respond(old.id,
            BestOfferActionRequest(action='Accept', expected_version=old.version, idempotency_key=uuid4()), user)
    assert exc.value.status_code == 409


def test_legacy_import_microseconds_do_not_override_newer_provider_offer_id(isolated):
    db, _, account, _ = isolated
    older = seed_offer(db, account, offer_id='158152461', status='Countered')
    latest = seed_offer(db, account, offer_id='158152464', status='Accepted')
    stamp = datetime(2026, 9, 17, 10, 0, 0, tzinfo=UTC)
    older.first_seen_at = stamp + timedelta(microseconds=900)
    latest.first_seen_at = stamp + timedelta(microseconds=100)
    db.commit()
    view = EbayBestOfferQueryService(db).list(view='history')
    assert view['total'] == 1 and view['items'][0]['id'] == latest.id


def test_stopped_scan_preserves_previous_complete_snapshot(isolated, monkeypatch):
    db, _, account, _ = isolated
    previous = seed_offer(db, account, offer_id='old')
    calls = []
    def response(*_args, **params):
        calls.append(params)
        return SimpleNamespace(ok=True, status_code=200, payload={'ack':'Success',
            'offers':[raw(offer_id='new')], 'totalPages':2})
    monkeypatch.setattr(EbayAuthClient, 'get_best_offers_raw', response)
    result = EbayBestOfferSyncService(db).sync_current(account.id, should_stop=lambda: bool(calls))
    assert result['outcome'] == 'STOPPED'
    assert current_snapshot_ids(db, account.id)[0] == {previous.id}


def test_optional_history_refresh_is_bounded_and_rotates_due_listings(isolated, monkeypatch):
    db, _, account, _ = isolated
    service = EbayBestOfferSyncService(db)
    for index in range(30):
        service._upsert(account, raw(offer_id=str(1000+index), listingId=str(2000+index), status='Expired'), None)
    db.commit()
    calls = mock_two_pass(monkeypatch, lambda item_id: [raw(offer_id=str(int(item_id)-1000), listingId=item_id, status='Expired')])
    first = service.sync_current(account.id, include_history=True)
    assert first['reconciliation']['reconciled'] == 25 and first['api_calls'] == 26
    second = service.sync_current(account.id, include_history=True)
    assert second['reconciliation']['reconciled'] == 5 and second['api_calls'] == 6
    third = service.sync_current(account.id, include_history=True)
    assert third['api_calls'] == 1
    assert len({call['item_id'] for call in calls if call['item_id']}) == 30


def test_cancelled_batch_stops_before_provider_requests(isolated, monkeypatch):
    import threading
    import app.db.session as sessions
    from app.services.ebay_best_offer_worker import run_batch
    db, engine, account, user = isolated
    service = EbayBestOfferJobService(db)
    reservation = service.reserve([account.id])
    cancelled = service.cancel(reservation['batch_id'], user)
    assert cancelled['result']['cancel_requested']
    monkeypatch.setattr(sessions, 'SessionLocal', lambda: Session(engine))
    monkeypatch.setattr(EbayAuthClient, 'get_best_offers_raw', lambda *_args, **_kwargs: pytest.fail('Cancelled sync used eBay quota'))
    run_batch(reservation['batch_id'], reservation['reservation_token'], threading.Event())
    db.expire_all()
    batch = db.get(SyncLog, reservation['batch_id'])
    assert batch.status == SyncLogStatus.FAILED and batch.completed_at is not None
    job = db.get(SyncLog, batch.sync_metadata['jobs'][0])
    assert job.sync_metadata['outcome'] == 'STOPPED'
    assert job.sync_metadata['api_calls'] == 0


def test_pending_counteroffer_survives_empty_discovery_until_due_reconciliation(isolated, monkeypatch):
    db, _, account, _ = isolated
    offer = seed_offer(db, account, status='Pending', offerType='SellerCounterOffer')
    db.add(EbayBestOfferListingSyncState(account_id=account.id, listing_id='456',
        last_checked_at=datetime.now(UTC), next_reconcile_at=datetime.now(UTC)+timedelta(minutes=5)))
    db.commit()
    calls = mock_two_pass(monkeypatch, lambda item_id: [raw(status='Accepted', offerType='SellerCounterOffer')])
    first = EbayBestOfferSyncService(db).sync_current(account.id)
    assert first['api_calls'] == 1 and first['reconciliation']['not_due'] == 1
    current = EbayBestOfferQueryService(db).list()
    assert current['total'] == 1 and current['items'][0]['provider_status'] == 'Pending'
    state = db.scalar(select(EbayBestOfferListingSyncState))
    state.next_reconcile_at = datetime.now(UTC)-timedelta(seconds=1)
    db.commit()
    second = EbayBestOfferSyncService(db).sync_current(account.id)
    assert second['api_calls'] == 2
    assert EbayBestOfferQueryService(db).list()['total'] == 0
    history = EbayBestOfferQueryService(db).list(view='history')
    assert history['total'] == 1 and history['items'][0]['id'] == offer.id
    assert history['items'][0]['provider_status'] == 'Accepted'


def offer_event(account, event_id='event-1', item_id='456'):
    return {'metadata':{'topic':'OFFER_ACTIVITY'}, 'notification':{
        'notificationId':event_id, 'data':{'itemId':item_id, 'offerId':'123',
        'seller':{'username':account.ebay_username}, 'buyer':{'username':'buyer'}}}}


def test_verified_event_discovers_pending_offer_without_preloaded_item_or_messages(isolated, monkeypatch):
    from app.modules.integrations.ebay.services.ebay_offer_activity_service import EbayOfferActivityService, EVENT
    db, _, account, _ = isolated
    events = EbayOfferActivityService(db)
    assert events.enqueue(account.id, offer_event(account))['status'] == 'queued'
    assert events.enqueue(account.id, offer_event(account))['status'] == 'duplicate'
    assert db.scalar(select(func.count()).select_from(Offer)) == 0
    calls = mock_two_pass(monkeypatch, lambda item_id: [raw(status='Pending', role=None, offerType='SellerCounterOffer')])
    result = EbayBestOfferSyncService(db).sync_current(account.id)
    assert result['api_calls'] == 2 and result['changes']['new'] == 1
    assert [call['item_id'] for call in calls] == [None, '456']
    view = EbayBestOfferQueryService(db).list(can_respond=True)
    assert view['total'] == 1 and view['items'][0]['provider_status'] == 'Pending'
    assert not view['items'][0]['can_respond']
    event = db.scalar(select(SyncLog).where(SyncLog.sync_type == EVENT))
    assert event.status == SyncLogStatus.SUCCESS


def test_offer_event_rejects_cross_account_identity_and_wrong_topic(isolated):
    from app.modules.integrations.ebay.services.ebay_offer_activity_service import EbayOfferActivityService
    db, _, account, _ = isolated
    payload = offer_event(account)
    payload['notification']['data']['seller']['username'] = 'another-seller'
    with pytest.raises(HTTPException):
        EbayOfferActivityService(db).enqueue(account.id, payload)
    payload = offer_event(account)
    payload['metadata']['topic'] = 'NEW_MESSAGE'
    with pytest.raises(HTTPException):
        EbayOfferActivityService(db).enqueue(account.id, payload)


def test_offer_event_challenge_uses_persisted_endpoint_and_token(isolated, monkeypatch):
    import hashlib
    from app.modules.integrations.ebay.services.ebay_offer_activity_service import EbayOfferActivityService
    db, _, account, _ = isolated
    service = EbayOfferActivityService(db)
    row = service.settings(account.id, create=True)
    settings = json.loads(row.value)
    settings['endpoint'] = 'https://example.invalid/offer-activity'
    row.value = json.dumps(settings); db.commit()
    assert service.challenge(account.id, 'challenge')['challengeResponse'] == hashlib.sha256(
        ('challenge'+settings['verification_token']+settings['endpoint']).encode()).hexdigest()


def test_offer_activity_setup_reuses_persisted_destination_and_subscription(isolated, monkeypatch):
    from app.modules.integrations.ebay.services.ebay_offer_activity_service import EbayOfferActivityService
    db, _, account, _ = isolated
    service = EbayOfferActivityService(db)
    monkeypatch.setattr(service, 'endpoint', lambda _id: 'https://example.invalid/activity')
    monkeypatch.setattr(service, 'app_token', lambda: 'test-app-token')
    calls = []
    def request(method, path, token, payload=None):
        calls.append((method, path, payload))
        return {}, {'Location':'https://api.ebay.com/commerce/notification/v1'+path+'/test-id'}
    monkeypatch.setattr(service, 'request', request)
    assert service.setup(account.id)['status'] == 'ENABLED'
    assert service.setup(account.id)['status'] == 'ENABLED'
    assert [path for _, path, _ in calls] == ['/destination', '/subscription']
    assert calls[1][2]['topicId'] == 'OFFER_ACTIVITY'


def test_new_offer_event_wakes_due_listing_and_archives_terminal_status(isolated, monkeypatch):
    from app.modules.integrations.ebay.services.ebay_offer_activity_service import EbayOfferActivityService
    db, _, account, _ = isolated
    seed_offer(db, account, status='Pending', offerType='SellerCounterOffer')
    db.add(EbayBestOfferListingSyncState(account_id=account.id, listing_id='456',
        last_checked_at=datetime.now(UTC), next_reconcile_at=datetime.now(UTC)+timedelta(minutes=5)))
    db.commit()
    EbayOfferActivityService(db).enqueue(account.id, offer_event(account, event_id='accepted-event'))
    mock_two_pass(monkeypatch, lambda item_id: [raw(status='Accepted', role=None, offerType='SellerCounterOffer')])
    result = EbayBestOfferSyncService(db).sync_current(account.id)
    assert result['reconciliation']['reconciled'] == 1 and result['api_calls'] == 2
    assert EbayBestOfferQueryService(db).list()['total'] == 0
    assert EbayBestOfferQueryService(db).list(view='history')['items'][0]['provider_status'] == 'Accepted'
