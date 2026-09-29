from datetime import UTC, datetime, timedelta, timezone
from decimal import Decimal
from time import perf_counter
from types import SimpleNamespace
from unittest.mock import Mock
from uuid import uuid4
from urllib.parse import parse_qs, urlsplit

import pytest
from sqlalchemy import Column, JSON, MetaData, Table, UniqueConstraint, create_engine, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.conversation import Conversation, Message, MessageSenderType, SyncLog, SyncLogStatus
from app.models.app_config import AppConfigSetting
from app.modules.integrations.ebay.providers import EBAY_PROVIDER_NAME
from app.models.ebay_account import EbayAccount
from app.models.offer import Offer
from app.repositories.conversation_repository import ConversationRepository
from app.modules.integrations.ebay.client.ebay_auth_client import EbayAuthClient, EbayRawApiResponse
from app.modules.integrations.ebay.services.ebay_best_offer_sync_service import EbayBestOfferSyncService
from app.modules.integrations.ebay.services.ebay_conversation_offer_resolver import EbayConversationOfferResolver
from app.modules.integrations.ebay.services.ebay_message_service import EbayMessageService
from app.modules.integrations.ebay.services.ebay_sync_service import EbaySyncService


@pytest.fixture
def db():
    # Exercise ORM queries/transactions without a live application database.
    # SQLite does not support JSONB; retain columns and unique keys, omit FKs.
    metadata = MetaData()
    for model in (Conversation, Message, Offer, EbayAccount, SyncLog, AppConfigSetting):
        source = model.__table__
        Table(source.name, metadata, *[
            Column(column.name, JSON() if isinstance(column.type, JSONB) else column.type,
                   primary_key=column.primary_key)
            for column in source.columns
        ], *[
            UniqueConstraint(*(column.name for column in constraint.columns))
            for constraint in source.constraints if isinstance(constraint, UniqueConstraint)
        ])
    engine = create_engine('sqlite://')
    metadata.create_all(engine)
    with Session(engine) as session:
        yield session
    engine.dispose()


def thread(db, account_id, buyer='buyer-2', external_id='thread-2'):
    conversation = Conversation(
        provider='EBAY', provider_conversation_id=external_id,
        provider_account_id=account_id, buyer_identifier=buyer,
        reference_id='123456789012', reference_type='LISTING',
        provider_conversation_type='FROM_MEMBERS', raw_payload={},
    )
    db.add(conversation)
    db.flush()
    return conversation


def message(db, conversation):
    record = Message(
        provider='EBAY', provider_message_id='message-1',
        conversation_id=conversation.id, body='Buyer sent an offer USD 20.00',
        sender_identifier=conversation.buyer_identifier,
        sender_type=MessageSenderType.CUSTOMER, is_inbound=True,
        sent_at=datetime.now(UTC), raw_payload={},
    )
    db.add(record)
    db.flush()
    return record


@pytest.mark.parametrize('buyer', ['buyer-1', '', None])
def test_offer_never_falls_back_to_another_buyer_for_same_item(db, buyer):
    account_id = uuid4()
    thread(db, account_id)
    service = EbayBestOfferSyncService.__new__(EbayBestOfferSyncService)
    service.db = db
    assert service._match_conversation(account_id, '123456789012', buyer) is None


def test_offer_matches_account_item_and_normalized_buyer(db):
    account_id = uuid4()
    expected = thread(db, account_id, buyer=' Buyer-2 ')
    thread(db, uuid4(), buyer='buyer-2', external_id='other-account')
    service = EbayBestOfferSyncService.__new__(EbayBestOfferSyncService)
    service.db = db
    assert service._match_conversation(account_id, '123456789012', 'BUYER-2') is expected
    assert service._match_conversation(account_id, '999999999999', 'BUYER-2') is None


def test_conversation_insert_conflict_reuses_thread_and_preserves_pending_message(db):
    conversation = thread(db, uuid4())
    record = message(db, conversation)
    repository = ConversationRepository(db)
    with db.begin_nested():
        recovered, created = repository._upsert_postgresql('EBAY', 'thread-2', {
            'provider_account_id': conversation.provider_account_id,
            'subject': 'Updated after concurrent import',
            'raw_payload': {},
        })
    db.commit()
    assert recovered.id == conversation.id
    assert created is False
    assert recovered.subject == 'Updated after concurrent import'
    assert db.get(Message, record.id) is record
    assert len(list(db.scalars(select(Conversation)))) == 1


def test_atomic_conversation_insert_initializes_defaults(db):
    repository = ConversationRepository(db)
    conversation, created = repository._upsert_postgresql('EBAY', 'new-thread', {'raw_payload': {}})
    db.commit()
    assert created is True
    assert conversation.provider_conversation_id == 'new-thread'
    assert conversation.category_manually_selected is False
    assert conversation.status.value == 'OPEN'


def test_system_sender_and_seller_case_do_not_become_buyer():
    service = EbayMessageService.__new__(EbayMessageService)
    account = SimpleNamespace(ebay_username='Seller')
    assert service._other_party_username(account, {}, [
        {'senderUsername': 'ebay', 'recipientUsername': 'SELLER'},
        {'senderUsername': 'seller', 'recipientUsername': 'buyer-2'},
    ]) == 'buyer-2'
    assert service._other_party_username(account, {}, [
        {'senderUsername': 'ebay', 'recipientUsername': 'SELLER'},
    ]) is None


def page(messages, total, **values):
    return dict(messages=[{'messageId': str(i)} for i in messages], total=total, **values)


def response(payload, ok=True):
    return EbayRawApiResponse(200 if ok else 503, payload, ok, 'https://example.invalid', {})


def test_message_pagination_fetches_all_pages_without_mutating_first_response():
    service = EbaySyncService.__new__(EbaySyncService)
    first = response(page(range(50), 125, next='next'))
    service._get_conversation_detail_with_retry = Mock(side_effect=[
        response(page(range(50, 100), 125, next='next')),
        response(page(range(100, 125), 125)),
    ])
    result = service._complete_conversation_detail(SimpleNamespace(), 'thread', 'FROM_MEMBERS', first.payload)
    assert [item['messageId'] for item in result['messages']] == [str(i) for i in range(125)]
    assert len(first.payload['messages']) == 50
    assert [call.kwargs['offset'] for call in service._get_conversation_detail_with_retry.call_args_list] == [50, 100]


@pytest.mark.parametrize('next_page', [response({}, False), response(page([], 51))])
def test_failed_later_message_page_does_not_return_partial_import(next_page):
    service = EbaySyncService.__new__(EbaySyncService)
    service._get_conversation_detail_with_retry = Mock(return_value=next_page)
    with pytest.raises((RuntimeError, ValueError)):
        service._complete_conversation_detail(SimpleNamespace(), 'thread', 'FROM_MEMBERS', page(range(50), 51))


def test_malformed_short_message_page_fails_import():
    service = EbaySyncService.__new__(EbaySyncService)
    with pytest.raises(ValueError, match='fewer messages'):
        service._complete_conversation_detail(SimpleNamespace(), 'thread', 'FROM_MEMBERS', page(range(2), 3))


def test_incremental_sync_uses_previous_success_minus_one_minute():
    service = EbaySyncService.__new__(EbaySyncService)
    last_sync = datetime(2026, 9, 29, 11, 50, tzinfo=UTC)
    cutoff = service._sync_window_start(last_sync)
    assert cutoff == datetime(2026, 9, 29, 11, 49, tzinfo=UTC)
    service.db = Mock()
    def summary(external_id, activity):
        return dict(conversationId=external_id, latestMessage={'createdDate': activity.isoformat()})
    pages = {
        ('FROM_MEMBERS', 0): {'total': 51, 'conversations': [summary('boundary', cutoff), summary('old-missing', cutoff - timedelta(seconds=1))]},
        ('FROM_MEMBERS', 50): {'total': 51, 'conversations': [summary('new-message-in-old-thread', cutoff + timedelta(minutes=5))]},
        ('FROM_EBAY', 0): {'total': 0, 'conversations': []},
    }
    service._get_conversations_with_retry = Mock(side_effect=lambda account, **kw: response(pages[(kw['conversation_type'], kw['offset'])]))
    results = list(service._iter_conversation_summaries(SimpleNamespace(id=uuid4()), updated_since=cutoff))
    assert [summary['conversationId'] for summary, _ in results] == ['boundary', 'new-message-in-old-thread']
    assert all(call.kwargs['start_time'] is None for call in service._get_conversations_with_retry.call_args_list)
    service.db.execute.assert_not_called()


@pytest.mark.parametrize('previous_sync', [None, datetime(2026, 9, 29, 11, 50), datetime(2026, 9, 29, 17, 20, tzinfo=timezone(timedelta(hours=5, minutes=30)))])
def test_sync_window_normalizes_timezone_and_initial_import(previous_sync):
    service = EbaySyncService.__new__(EbaySyncService)
    assert service._sync_window_start(previous_sync) == (None if previous_sync is None else datetime(2026, 9, 29, 11, 49, tzinfo=UTC))


@pytest.mark.parametrize('conversation_type,cutoff,expected_start', [
    ('FROM_MEMBERS', datetime(2026, 9, 29, 11, 49, tzinfo=UTC), '2026-09-29T11:49:00.000Z'),
    ('FROM_MEMBERS', None, None),
    ('FROM_EBAY', datetime(2026, 9, 29, 11, 49, tzinfo=UTC), None),
])
def test_client_sends_time_filter_only_where_ebay_supports_it(conversation_type, cutoff, expected_start):
    client = EbayAuthClient(client_id='test', client_secret='test', redirect_uri='test', runame='test', environment='PRODUCTION')
    client._request_message_api_raw = Mock(side_effect=lambda token, **values: values['request_url'])
    url = client.get_conversations_raw('token', conversation_type=conversation_type, start_time=cutoff, limit=50, offset=50)
    query = parse_qs(urlsplit(url).query)
    assert query.get('start_time') == ([expected_start] if expected_start else None)
    assert query['offset'] == ['50']
    assert query['conversation_type'] == [conversation_type]


def test_token_refresh_preserves_incremental_window():
    service = EbaySyncService.__new__(EbaySyncService)
    service.api_usage_service = Mock()
    service.token_service = SimpleNamespace(client=Mock())
    service.token_service.client.get_conversations_raw.side_effect = [EbayRawApiResponse(401, {}, False, '', {}), response({})]
    account = SimpleNamespace(access_token='expired')
    service._refresh_account_after_unauthorized = Mock(return_value=SimpleNamespace(access_token='refreshed'))
    cutoff = datetime(2026, 9, 29, 11, 49, tzinfo=UTC)
    result = service._get_conversations_with_retry(account, conversation_type='FROM_MEMBERS', limit=50, offset=0, start_time=cutoff)
    assert result.ok
    assert [call.kwargs['start_time'] for call in service.token_service.client.get_conversations_raw.call_args_list] == [cutoff, cutoff]


def test_creation_time_is_not_used_to_skip_changed_conversation():
    service = EbaySyncService.__new__(EbaySyncService)
    assert service._conversation_activity_at({'createdDate': '2025-01-01T00:00:00Z'}) is None


@pytest.mark.parametrize('cutoff,expected_ids', [
    (None, ['old-member', 'old-notification', 'boundary-notification', 'unknown-date']),
    (datetime(2026, 9, 29, 11, 49, tzinfo=UTC), ['boundary-notification', 'unknown-date']),
])
def test_initial_import_and_notification_window_paginate_without_order_assumptions(cutoff, expected_ids):
    service = EbaySyncService.__new__(EbaySyncService)
    pages = {
        ('FROM_MEMBERS', 0): {'total': 1, 'conversations': [
            {'conversationId': 'old-member', 'latestMessage': {'createdDate': '2025-01-01T00:00:00Z'}},
        ]},
        ('FROM_EBAY', 0): {'total': 51, 'conversations': [
            {'conversationId': 'old-notification', 'createdDate': '2025-01-01T00:00:00Z'},
        ]},
        ('FROM_EBAY', 50): {'total': 51, 'conversations': [
            {'conversationId': 'boundary-notification', 'createdDate': '2026-09-29T11:49:00Z'},
            {'conversationId': 'unknown-date'},
        ]},
    }
    service._get_conversations_with_retry = Mock(side_effect=lambda account, **kw: response(pages[(kw['conversation_type'], kw['offset'])]))
    results = list(service._iter_conversation_summaries(SimpleNamespace(id=uuid4()), updated_since=cutoff))
    assert [summary['conversationId'] for summary, _ in results] == expected_ids
    assert all(call.kwargs['start_time'] is None for call in service._get_conversations_with_retry.call_args_list)


def notification_log(db, account_id, timestamp, *, completed=True, status=SyncLogStatus.SUCCESS):
    log = SyncLog(provider=EBAY_PROVIDER_NAME, provider_account_id=account_id,
                  sync_type='EBAY_MESSAGE_SYNC', status=status, started_at=timestamp,
                  sync_metadata={'notification_sync': {'completed': completed, 'synced_through': timestamp.isoformat()}})
    db.add(log)
    db.flush()
    return log


@pytest.mark.parametrize('minutes_after,expected_due', [(3, False), (59, False), (60, True), (120, True)])
def test_notification_cadence_uses_own_successful_cursor(db, minutes_after, expected_due):
    service = EbaySyncService.__new__(EbaySyncService)
    service.db = db
    previous = datetime(2026, 9, 29, 11, 50, tzinfo=UTC)
    account = SimpleNamespace(id=uuid4(), last_sync_at=previous + timedelta(minutes=minutes_after - 1))
    notification_log(db, account.id, previous)
    # Recent member-only / failed / other-account runs must not reset cadence.
    notification_log(db, account.id, previous + timedelta(minutes=1), completed=False)
    notification_log(db, account.id, previous + timedelta(minutes=2), status=SyncLogStatus.FAILED)
    notification_log(db, uuid4(), previous + timedelta(minutes=2))
    plan = service._notification_sync_plan(account, previous + timedelta(minutes=minutes_after))
    assert plan['due'] is expected_due
    assert plan['updated_since'] == previous - timedelta(minutes=1)


@pytest.mark.parametrize('last_sync', [None, datetime(2026, 9, 29, 11, 50, tzinfo=UTC)])
def test_first_notification_plan_is_due_and_configurable(db, last_sync):
    service = EbaySyncService.__new__(EbaySyncService)
    service.db = db
    db.add(AppConfigSetting(section='api', config_key='api.ebay_notification_sync_interval_minutes',
                            label='Notification interval', value='15', value_type='integer'))
    db.flush()
    plan = service._notification_sync_plan(SimpleNamespace(id=uuid4(), last_sync_at=last_sync), datetime(2026, 9, 29, 12, tzinfo=UTC))
    assert plan['due'] is True
    assert plan['interval_minutes'] == 15
    assert plan['updated_since'] == (last_sync - timedelta(minutes=1) if last_sync else None)


def test_frequent_sync_makes_no_notification_list_calls():
    service = EbaySyncService.__new__(EbaySyncService)
    cutoff = datetime(2026, 9, 29, 11, 49, tzinfo=UTC)
    service._get_conversations_with_retry = Mock(return_value=response({'total': 0, 'conversations': []}))
    assert list(service._iter_conversation_summaries(SimpleNamespace(id=uuid4()), updated_since=cutoff,
                                                   notification_plan={'due': False, 'updated_since': cutoff})) == []
    assert service._get_conversations_with_retry.call_count == 1
    assert service._get_conversations_with_retry.call_args.kwargs['conversation_type'] == 'FROM_MEMBERS'
    assert service._get_conversations_with_retry.call_args.kwargs['start_time'] is None


def test_routine_sync_stops_after_old_member_page_with_large_history():
    service = EbaySyncService.__new__(EbaySyncService)
    cutoff = datetime(2026, 9, 29, 11, 49, tzinfo=UTC)
    service._get_conversations_with_retry = Mock(return_value=response({
        'total': 7309, 'conversations': [
            {'conversationId': str(i), 'latestMessage': {'createdDate': '2026-09-28T11:00:00Z'}}
            for i in range(50)
        ],
    }))
    results = list(service._iter_conversation_summaries(SimpleNamespace(id=uuid4()), updated_since=cutoff,
                   notification_plan={'due': False, 'updated_since': cutoff}))
    assert results == []
    assert service._get_conversations_with_retry.call_count == 1


def test_reconciliation_recovers_later_page_reply_before_recent_member_cutoff():
    service = EbaySyncService.__new__(EbaySyncService)
    recent_cutoff = datetime(2026, 9, 29, 12, 49, tzinfo=UTC)
    saved_cutoff = datetime(2026, 9, 29, 11, 49, tzinfo=UTC)
    pages = {
        ('FROM_MEMBERS', 0): {'total': 51, 'conversations': [
            {'conversationId': 'old', 'latestMessage': {'createdDate': '2025-01-01T00:00:00Z'}}]},
        ('FROM_MEMBERS', 50): {'total': 51, 'conversations': [
            {'conversationId': 'late-page-reply', 'createdDate': '2025-01-01T00:00:00Z',
             'latestMessage': {'createdDate': '2026-09-29T12:10:00Z'}}]},
        ('FROM_EBAY', 0): {'total': 0, 'conversations': []},
    }
    service._get_conversations_with_retry = Mock(side_effect=lambda account, **kw: response(pages[(kw['conversation_type'], kw['offset'])]))
    results = list(service._iter_conversation_summaries(SimpleNamespace(id=uuid4()), updated_since=recent_cutoff,
                   notification_plan={'due': True, 'updated_since': saved_cutoff}))
    assert [summary['conversationId'] for summary, _ in results] == ['late-page-reply']
    assert service._get_conversations_with_retry.call_count == 3


def test_routine_sync_continues_past_page_with_unknown_activity_or_boundary():
    service = EbaySyncService.__new__(EbaySyncService)
    cutoff = datetime(2026, 9, 29, 11, 49, tzinfo=UTC)
    service._get_conversations_with_retry = Mock(side_effect=[
        response({'total': 51, 'conversations': [{'conversationId': 'unknown'},
                  {'conversationId': 'boundary', 'latestMessage': {'createdDate': cutoff.isoformat()}}]}),
        response({'total': 51, 'conversations': [{'conversationId': 'old', 'latestMessage': {'createdDate': '2025-01-01T00:00:00Z'}}]}),
    ])
    results = list(service._iter_conversation_summaries(SimpleNamespace(id=uuid4()), updated_since=cutoff,
                   notification_plan={'due': False, 'updated_since': cutoff}))
    assert [summary['conversationId'] for summary, _ in results] == ['unknown', 'boundary']
    assert service._get_conversations_with_retry.call_count == 2


def test_due_notifications_include_messages_between_member_syncs():
    service = EbaySyncService.__new__(EbaySyncService)
    member_cutoff = datetime(2026, 9, 29, 12, 49, tzinfo=UTC)
    notification_cutoff = datetime(2026, 9, 29, 11, 49, tzinfo=UTC)
    service._get_conversations_with_retry = Mock(side_effect=lambda account, **kw: response({
        'total': 1, 'conversations': [{'conversationId': 'between-runs', 'createdDate': '2026-09-29T12:10:00Z'}]
    }) if kw['conversation_type'] == 'FROM_EBAY' else response({'total': 0, 'conversations': []}))
    results = list(service._iter_conversation_summaries(SimpleNamespace(id=uuid4()), updated_since=member_cutoff,
                                                      notification_plan={'due': True, 'updated_since': notification_cutoff}))
    assert [summary['conversationId'] for summary, _ in results] == ['between-runs']


@pytest.mark.parametrize('failed,capped,enrichment_failed,due,completed', [
    (0, None, False, True, True), (1, None, False, True, False),
    (0, 10, False, True, False), (0, None, True, True, False), (0, None, False, False, False),
])
def test_notification_cursor_only_commits_complete_success(failed, capped, enrichment_failed, due, completed):
    service = EbaySyncService.__new__(EbaySyncService)
    context = service._initialize_sync_context(SimpleNamespace(id=uuid4()), None, capped)
    context['notification_sync_plan']['due'] = due
    if enrichment_failed:
        context['enrichment_failed_conversation_ids'] = ['failed-thread']
    counters = service._initialize_counters()
    counters['conversations_failed'] = failed
    metadata = service._notification_sync_metadata(counters, context)
    assert metadata['completed'] is completed
    assert metadata['synced_through'] == (context['sync_started_at_utc'].isoformat() if completed else None)


@pytest.mark.parametrize('invalid_message', [{}, None])
def test_invalid_message_cannot_silently_mark_conversation_imported(invalid_message):
    service = EbaySyncService.__new__(EbaySyncService)
    with pytest.raises(ValueError, match='without messageId'):
        service._complete_conversation_detail(SimpleNamespace(), 'thread', 'FROM_MEMBERS',
                                              {'messages': [invalid_message], 'total': 1})


def test_resolver_detaches_other_buyers_offer_and_keeps_matching_offer(db):
    account = EbayAccount(account_name='Test', ebay_username='seller', created_by=uuid4())
    db.add(account)
    db.flush()
    conversation = thread(db, account.id)
    wrong_offer = Offer(provider='EBAY', account_id=account.id, provider_offer_id='buyer-1-offer',
                        conversation_id=conversation.id, buyer_username='buyer-1',
                        listing_id=conversation.reference_id, status='PENDING', direction='INCOMING')
    matching_offer = Offer(provider='EBAY', account_id=account.id, provider_offer_id='buyer-2-offer',
                           buyer_username='BUYER-2', listing_id=conversation.reference_id,
                           status='PENDING', direction='INCOMING')
    db.add_all([wrong_offer, matching_offer])
    db.flush()
    offers = EbayConversationOfferResolver(db).resolve_for_conversation(conversation)
    assert offers == [matching_offer]
    assert wrong_offer.conversation_id is None
    assert wrong_offer.message_id is None
    assert matching_offer.conversation_id == conversation.id
    assert conversation.has_offers


def test_resolver_offer_integrity_failure_does_not_rollback_conversation(db, monkeypatch):
    account = EbayAccount(account_name='Test', ebay_username='seller', created_by=uuid4())
    db.add(account)
    db.flush()
    conversation = thread(db, account.id)
    record = message(db, conversation)
    service = EbayConversationOfferResolver(db)
    def fail(**kwargs):
        raise IntegrityError('insert offer', {}, RuntimeError('constraint rejected offer'))
    monkeypatch.setattr(service, '_upsert_offer_from_message', fail)
    assert service.resolve_for_conversation(conversation) == []
    assert conversation.raw_payload['offer_resolution_failed'] is True
    db.commit()
    assert db.get(Message, record.id) is record
    assert db.get(Conversation, conversation.id) is conversation


def test_offer_title_does_not_turn_normal_chat_into_offer(db):
    conversation = thread(db, uuid4())
    conversation.subject = 'Buyer sent an offer USD 20.00'
    record = message(db, conversation)
    record.body = 'Can you send a photo?'
    service = EbayConversationOfferResolver(db)
    assert service._extract_from_message(record, conversation, SimpleNamespace(ebay_username='seller')) is None


def test_duplicate_offer_race_preserves_pending_message_import(db, monkeypatch):
    account_id = uuid4()
    conversation = thread(db, account_id)
    record = message(db, conversation)
    existing = Offer(provider='EBAY', account_id=account_id, provider_offer_id='offer-1',
                     listing_id=conversation.reference_id, buyer_username=conversation.buyer_identifier,
                     offer_amount=Decimal('20'), currency='USD', status='PENDING', direction='INCOMING')
    db.add(existing)
    db.flush()
    service = EbayConversationOfferResolver(db)
    lookup = service._existing_offer
    calls = 0
    def race_lookup(*args):
        nonlocal calls
        calls += 1
        return None if calls == 1 else lookup(*args)
    monkeypatch.setattr(service, '_existing_offer', race_lookup)
    result = service._upsert_offer_from_message(
        account=SimpleNamespace(id=account_id), conversation=conversation, message=record,
        offer_data={'provider_offer_id': 'offer-1'}, offers_by_provider_id={},
    )
    db.commit()
    assert result.id == existing.id
    assert db.scalar(select(Message).where(Message.id == record.id)) is record
    assert db.get(Conversation, conversation.id) is conversation


def test_enrichment_failure_preserves_messages_and_leaves_thread_retryable(db):
    service = EbaySyncService.__new__(EbaySyncService)
    service.db = db
    account = SimpleNamespace(id=uuid4())
    conversation = thread(db, account.id)
    service.message_service = SimpleNamespace(
        upsert_conversation=lambda **kw: (conversation, True),
        upsert_messages=lambda **kw: (message(db, conversation) and 1, 0),
    )
    def fail(conversation):
        conversation.subject = 'Should be rolled back'
        raise RuntimeError('Browse unavailable')
    service.product_context_service = SimpleNamespace(enrich_conversation=fail)
    service.conversation_offer_resolver = SimpleNamespace(resolve_for_conversation=lambda conversation: [])
    counters = service._initialize_counters()
    context = service._initialize_sync_context(account, None, None)
    service._process_conversation_detail(account, {}, 'thread-2', 'FROM_MEMBERS', {}, perf_counter(), counters, context)
    db.commit()
    assert db.scalar(select(Message).where(Message.conversation_id == conversation.id)) is not None
    assert conversation.subject is None
    assert context['enrichment_failed_conversation_ids'] == ['thread-2']
    assert counters['conversations_processed'] == 1


@pytest.mark.parametrize('failed,capped,enrichment_failed', [(1, None, False), (0, 10, False), (0, None, True), (0, None, False)])
def test_watermark_preserved_on_failed_or_capped_sync(failed, capped, enrichment_failed):
    service = EbaySyncService.__new__(EbaySyncService)
    service.db = Mock()
    service.sync_log_service = Mock()
    service.sync_log_service.complete_sync.return_value = SimpleNamespace(id=uuid4(), error_message=None)
    service._set_sync_error_messages = Mock()
    service._set_sync_metadata = Mock()
    service._build_result = Mock()
    account = SimpleNamespace(id=uuid4(), last_sync_at=datetime(2026, 9, 1, tzinfo=UTC))
    old = account.last_sync_at
    context = service._initialize_sync_context(account, old, capped)
    if enrichment_failed:
        context['enrichment_failed_conversation_ids'] = ['thread-1']
    counters = service._initialize_counters()
    counters['conversations_failed'] = failed
    service._finalize_sync(account, SimpleNamespace(id=uuid4()), counters, context, None, None)
    assert account.last_sync_at == (old if failed or capped or enrichment_failed else context['sync_started_at_utc'])
