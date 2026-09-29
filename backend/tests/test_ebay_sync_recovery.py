from datetime import UTC, datetime, timedelta
from decimal import Decimal
from time import perf_counter
from types import SimpleNamespace
from unittest.mock import Mock
from uuid import uuid4

import pytest
from sqlalchemy import Column, JSON, MetaData, Table, UniqueConstraint, create_engine, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.conversation import Conversation, Message, MessageSenderType
from app.models.ebay_account import EbayAccount
from app.models.offer import Offer
from app.modules.integrations.ebay.client.ebay_auth_client import EbayRawApiResponse
from app.modules.integrations.ebay.services.ebay_best_offer_sync_service import EbayBestOfferSyncService
from app.modules.integrations.ebay.services.ebay_conversation_offer_resolver import EbayConversationOfferResolver
from app.modules.integrations.ebay.services.ebay_message_service import EbayMessageService
from app.modules.integrations.ebay.services.ebay_sync_service import EbaySyncService, MESSAGE_SYNC_VERSION


@pytest.fixture
def db():
    # Exercise ORM queries/transactions without a live application database.
    # SQLite does not support JSONB; retain columns and unique keys, omit FKs.
    metadata = MetaData()
    for model in (Conversation, Message, Offer, EbayAccount):
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


def test_incremental_scan_recovers_old_missing_and_legacy_threads_on_later_pages():
    service = EbaySyncService.__new__(EbaySyncService)
    cutoff = datetime(2026, 9, 29, tzinfo=UTC)
    old = cutoff - timedelta(days=7)
    service.db = Mock()
    service.db.execute.return_value = [
        ('imported', old),
    ]
    def summary(external_id, **values):
        return dict(conversationId=external_id, latestMessage={'createdDate': old.isoformat()}, **values)
    pages = {
        ('FROM_MEMBERS', 0): {'total': 51, 'conversations': [summary('imported')]},
        ('FROM_MEMBERS', 50): {'total': 51, 'conversations': [summary('missing'), summary('legacy')]},
        ('FROM_EBAY', 0): {'total': 0, 'conversations': []},
    }
    service._get_conversations_with_retry = lambda account, **kw: response(pages[(kw['conversation_type'], kw['offset'])])
    results = list(service._iter_conversation_summaries(SimpleNamespace(id=uuid4()), updated_since=cutoff))
    assert [summary['conversationId'] for summary, _ in results] == ['missing', 'legacy']


def test_creation_time_is_not_used_to_skip_changed_conversation():
    service = EbaySyncService.__new__(EbaySyncService)
    assert service._conversation_activity_at({'createdDate': '2025-01-01T00:00:00Z'}) is None


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
    assert conversation.raw_payload['message_sync_version'] is None
    assert counters['conversations_processed'] == 1


@pytest.mark.parametrize('failed,capped', [(1, None), (0, 10), (0, None)])
def test_watermark_preserved_on_failed_or_capped_sync(failed, capped):
    service = EbaySyncService.__new__(EbaySyncService)
    service.db = Mock()
    service.sync_log_service = Mock()
    service._set_sync_error_messages = Mock()
    service._set_sync_metadata = Mock()
    service._build_result = Mock()
    account = SimpleNamespace(id=uuid4(), last_sync_at=datetime(2026, 9, 1, tzinfo=UTC))
    old = account.last_sync_at
    context = service._initialize_sync_context(account, old, capped)
    counters = service._initialize_counters()
    counters['conversations_failed'] = failed
    service._finalize_sync(account, SimpleNamespace(id=uuid4()), counters, context, None, None)
    assert account.last_sync_at == (old if failed or capped else context['sync_started_at_utc'])
