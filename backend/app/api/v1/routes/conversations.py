from html.parser import HTMLParser
from multiprocessing import context
from datetime import UTC, datetime, timedelta
from uuid import UUID

import requests
from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.dependencies import can_manage_operations, get_current_user, is_admin, is_operations_manager, is_support_agent
from app.db.session import get_db
from app.models.category import Category, CategoryUserAssignment
from app.models.conversation import Conversation, ConversationAssignment, ConversationNote, ConversationStatus, Message, MessageAttachment
from app.models.ebay_account import EbayAccount
from app.models.offer import Offer
from app.models.user import User
from app.schemas.conversation import (
    AssignConversationRequest,
    BulkConversationUpdateRequest,
    BulkConversationUpdateResponse,
    CategoryBriefResponse,
    ConversationAssignmentResponse,
    ConversationDetailResponse,
    ConversationNoteCreateRequest,
    ConversationNoteResponse,
    ConversationPageResponse,
    ConversationProductContextResponse,
    ConversationSummaryResponse,
    EbayAccountBriefResponse,
    MessageResponse,
    MessageAttachmentResponse,
    ReplyConversationRequest,
    ReplyValidationResponse,
    TranslationRequest,
    TranslationResponse,
    SelectConversationOrderRequest,
    UpdateConversationCategoryRequest,
    UpdateConversationStatusRequest,
    UserBriefResponse,
)
from app.services.assignment_service import AssignmentService
from app.services.audit_service import AuditService
from app.services.category_assignment_service import CategoryAssignmentService
from app.services.conversation_note_service import ConversationNoteService
from app.services.conversation_product_context_service import ConversationProductContextService
from app.services.conversation_service import ConversationService
from app.services.message_service import MessageService
from app.services.message_type_detection_service import MessageTypeDetectionService
from app.services.ebay_reply_service import EbayReplyService
from app.services.notification_service import NotificationService
from app.services.offer_consistency_service import OfferConsistencyService
from app.services.order_context_service import OrderContextService
from app.services.reply_attachment_service import ReplyAttachmentService
from app.services.translation_service import TranslationService
from app import db


router = APIRouter()
BUYER_BEST_OFFER_EXPIRY_DURATION = timedelta(days=1)
SELLER_COUNTEROFFER_EXPIRY_DURATION = timedelta(days=4)
ACCEPTED_COUNTEROFFER_SEQUENCE_OFFSET = timedelta(minutes=70)


@router.post('/translate', response_model=TranslationResponse)
def translate_message(payload: TranslationRequest, current_user: User = Depends(get_current_user)) -> TranslationResponse:
    """Translate message text without persisting or logging its contents."""
    try:
        return TranslationResponse(**TranslationService().translate(payload.text, payload.target_language))
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except requests.RequestException as exc:
        raise HTTPException(status_code=502, detail='Translation provider is unavailable.') from exc


class BodyTextExtractor(HTMLParser):
    """Extract readable text from provider HTML emails for compact previews."""

    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []
        self.skip_depth = 0

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag.lower() in {'script', 'style', 'head'}:
            self.skip_depth += 1
        elif tag.lower() in {'br', 'p', 'div', 'tr', 'h1', 'h2', 'h3', 'li'}:
            self.parts.append(' ')

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() in {'script', 'style', 'head'} and self.skip_depth:
            self.skip_depth -= 1
        elif tag.lower() in {'p', 'div', 'tr', 'h1', 'h2', 'h3', 'li'}:
            self.parts.append(' ')

    def handle_data(self, data: str) -> None:
        if not self.skip_depth and data.strip():
            self.parts.append(data)

    def text(self) -> str:
        return ' '.join(' '.join(self.parts).split())


def plain_text_from_body(body: str) -> str:
    if '<' not in body or '>' not in body:
        return ' '.join(body.split())
    parser = BodyTextExtractor()
    parser.feed(body)
    return parser.text()


def is_ebay_system_conversation(conversation: Conversation) -> bool:
    return (conversation.provider_conversation_type or '').upper() == 'FROM_EBAY'


def require_conversation_access(current_user=Depends(get_current_user)):
    return current_user


def visible_category_ids_for_user(db: Session, current_user) -> set[UUID] | None:
    """Return category IDs assigned to an agent, or None for unrestricted roles."""
    if not is_support_agent(current_user):
        return None
    return {
        category_id
        for category_id in db.scalars(
            select(CategoryUserAssignment.category_id).where(CategoryUserAssignment.user_id == current_user.id)
        )
    }


def visibility_user_id_for_user(current_user) -> UUID | None:
    """Return the agent ID used to include explicit assignments in visibility filters."""
    return current_user.id if is_support_agent(current_user) else None


def ensure_reply_assignment(db: Session, conversation_id: UUID, current_user) -> None:
    """
    Prevent a user from replying to a conversation owned by someone else.

    Args:
        db: Request-scoped database session.
        conversation_id: Conversation being replied to.
        current_user: Authenticated user attempting the reply.

    Returns:
        None when unassigned or assigned to the caller.

    Side Effects:
        None.

    Business Rules:
        Assignment ownership applies to agents, administrators, and operations
        managers alike so privileged roles cannot reply from another queue.
    """
    assignment = AssignmentService(db).repository.get_current_assignment(conversation_id)
    if assignment and assignment.assigned_to != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail='This conversation is assigned to another user and cannot be replied to',
        )


def can_assign_conversations(current_user) -> bool:
    return is_admin(current_user) or is_operations_manager(current_user) or is_support_agent(current_user)


def ensure_can_assign_conversation(current_user) -> None:
    if not can_assign_conversations(current_user):
        from fastapi import HTTPException, status

        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail='Only support users can assign conversations')


def create_assignment_notification(db: Session, *, conversation: Conversation, assignment, assigned_to: UUID, assigned_by_user) -> None:
    assigner_name = assigned_by_user.full_name or assigned_by_user.email or 'another user'
    NotificationService(db).create(
        user_id=assigned_to,
        title='Conversation assigned',
        body=f'Conversation {conversation.subject or conversation.provider_conversation_id} was assigned to you by {assigner_name}.',
        event_type='MESSAGE_ASSIGNMENT',
        event_key=f'conversation-assigned:{assignment.id}',
        resource_type='CONVERSATION',
        resource_id=conversation.id,
    )


def ensure_can_manage_conversation(current_user) -> None:
    if not can_manage_operations(current_user):
        from fastapi import HTTPException, status

        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail='Only admins and operations managers can manage assignments and categories')


def serialize_conversation(
    conversation: Conversation,
    current_assignee_id: UUID | None = None,
    seller_account: EbayAccount | None = None,
    product_context: dict | None = None,
    order_context: dict | None = None,
    suggested_message_type_id: UUID | None = None,
    offers: list[Offer] | None = None,
) -> ConversationDetailResponse:
    """
    Serialize a full conversation with messages, notes, assignment, and audit-derived indicators.

    Purpose:
    Builds the detail response used by the inbox thread and side panels.

    Parameters:
    conversation: Conversation ORM object with related data loaded.
    current_assignee_id: Optional UUID of the current assignee.
    seller_account: Optional eBay account associated with the conversation.
    order_context: Optional resolved order context for the conversation.

    Returns:
    ConversationDetailResponse ready for API serialization.

    Business Logic:
    Includes calculated visibility fields such as last message direction,
    Not Read status, and Replied status without persisting duplicate columns.
    """
    assignments = [serialize_assignment(assignment) for assignment in conversation.assignments]
    return ConversationDetailResponse(
        id=conversation.id,
        provider=conversation.provider,
        provider_conversation_id=conversation.provider_conversation_id,
        provider_account_id=conversation.provider_account_id,
        subject=conversation.subject,
        buyer_identifier=conversation.buyer_identifier,
        provider_conversation_status=conversation.provider_conversation_status,
        provider_conversation_type=conversation.provider_conversation_type,
        reference_id=conversation.reference_id,
        reference_type=conversation.reference_type,
        unread_count=conversation.unread_count,
        message_count=len(conversation.messages),
        last_message_preview=latest_message_preview(conversation),
        last_message_direction=last_message_direction(conversation),
        calculated_status=calculated_conversation_status(conversation),
        is_not_read=is_not_read_conversation(conversation),
        is_replied=is_replied_conversation(conversation),
        response_due_at=response_due_at(conversation),
        status=conversation.status,
        category_id=conversation.category_id,
        category_manually_selected=conversation.category_manually_selected,
        has_offers=conversation.has_offers,
        category=serialize_category_brief(conversation.category) if conversation.category else None,
        last_message_at=conversation.last_message_at,
        external_created_at=conversation.external_created_at,
        created_at=conversation.created_at,
        updated_at=conversation.updated_at,
        current_assignment=next((assignment for assignment in assignments if assignment.unassigned_at is None), None),
        seller_account=serialize_ebay_account_brief(seller_account) if seller_account else None,
        current_assignee_id=current_assignee_id,
        messages=[serialize_message(message) for message in conversation.messages],
        offers=offers or [],
        assignments=assignments,
        notes=[serialize_note(note) for note in conversation.notes],
        product_context=product_context,
        order_context=serialize_order_context(order_context) if order_context else None,
        suggested_message_type_id=suggested_message_type_id,
    )


def serialize_conversation_summary(
    conversation: Conversation,
    seller_account: EbayAccount | None = None,
) -> ConversationSummaryResponse:
    """
    Serialize a conversation row for the listing screen.

    Purpose:
    Provides compact data needed to render the inbox table.

    Parameters:
    conversation: Conversation ORM object with category, messages, and
    assignment history loaded.
    seller_account: Optional seller account metadata.

    Returns:
    ConversationSummaryResponse for one list row.

    Business Logic:
    Conversation status indicators are calculated from message history so the
    UI reflects the latest buyer/agent/system activity automatically.
    """
    return ConversationSummaryResponse(
        id=conversation.id,
        provider=conversation.provider,
        provider_conversation_id=conversation.provider_conversation_id,
        provider_account_id=conversation.provider_account_id,
        subject=conversation.subject,
        buyer_identifier=conversation.buyer_identifier,
        provider_conversation_status=conversation.provider_conversation_status,
        provider_conversation_type=conversation.provider_conversation_type,
        reference_id=conversation.reference_id,
        reference_type=conversation.reference_type,
        unread_count=conversation.unread_count,
        message_count=len(conversation.messages),
        last_message_preview=latest_message_preview(conversation),
        last_message_direction=last_message_direction(conversation),
        calculated_status=calculated_conversation_status(conversation),
        is_not_read=is_not_read_conversation(conversation),
        is_replied=is_replied_conversation(conversation),
        response_due_at=response_due_at(conversation),
        status=conversation.status,
        category_id=conversation.category_id,
        category_manually_selected=conversation.category_manually_selected,
        has_offers=conversation.has_offers,
        category=serialize_category_brief(conversation.category) if conversation.category else None,
        last_message_at=conversation.last_message_at,
        external_created_at=conversation.external_created_at,
        created_at=conversation.created_at,
        updated_at=conversation.updated_at,
        current_assignment=serialize_assignment(current_assignment) if (current_assignment := current_assignment_for(conversation)) else None,
        seller_account=serialize_ebay_account_brief(seller_account) if seller_account else None,
    )


def serialize_message(message: Message) -> MessageResponse:
    """Serialize a message with attachments and delivery warnings."""
    raw_payload = message.raw_payload if isinstance(message.raw_payload, dict) else {}
    offer_data = message.offer_data if isinstance(message.offer_data, dict) else {}
    return MessageResponse(
        id=message.id,
        conversation_id=message.conversation_id,
        provider=message.provider,
        provider_message_id=message.provider_message_id,
        sender_type=message.sender_type,
        sender_identifier=message.sender_identifier,
        recipient_identifier=message.recipient_identifier,
        body=message.body,
        read_status=message.read_status,
        is_inbound=message.is_inbound,
        sent_at=message.sent_at,
        created_at=message.created_at,
        attachments=[serialize_attachment(attachment) for attachment in message.attachments],
        attachment_delivery_warning=raw_payload.get('attachment_delivery_warning'),
        is_offer_notification=offer_data.get('notification_type') == 'OFFER',
    )


def stored_conversation_offers(db: Session, conversation: Conversation) -> list[Offer]:
    offers = list(
        db.scalars(
            select(Offer)
            .where(Offer.conversation_id == conversation.id)
            .order_by(func.coalesce(Offer.created_at_provider, Offer.created_at).asc(), Offer.created_at.asc())
        )
    )
    if not offers:
        offers = link_unattached_conversation_offers(db, conversation)
    if not offers:
        OfferConsistencyService(db).sync_conversation(conversation.id)
        db.flush()
        return []
    for offer in offers:
        raw_timestamp = offer_timestamp_from_raw_payload(offer.raw_payload, offer)
        if raw_timestamp and (
            not offer.created_at_provider
            or offer_timestamp_is_sync_fallback(offer)
            or raw_timestamp < offer.created_at_provider
        ):
            offer.created_at_provider = raw_timestamp
    infer_missing_offer_timeline_timestamps(offers)
    if not conversation.has_offers:
        conversation.has_offers = True
        db.flush()
    return sorted(offers, key=lambda offer: (offer.created_at_provider or offer.created_at, offer.created_at))


def link_unattached_conversation_offers(db: Session, conversation: Conversation) -> list[Offer]:
    account_id = conversation.provider_account_id
    listing_id = str(conversation.reference_id or "").strip()
    buyer = str(conversation.buyer_identifier or "").strip().lower()
    if not account_id or not listing_id or not buyer:
        return []

    offers = list(
        db.scalars(
            select(Offer)
            .where(
                Offer.provider == "EBAY",
                Offer.account_id == account_id,
                Offer.conversation_id.is_(None),
                Offer.listing_id == listing_id,
                func.lower(func.coalesce(Offer.buyer_username, "")) == buyer,
            )
            .order_by(func.coalesce(Offer.created_at_provider, Offer.created_at).asc(), Offer.created_at.asc())
        )
    )
    for offer in offers:
        offer.conversation_id = conversation.id
    if offers:
        db.flush()
    return offers


def infer_missing_offer_timeline_timestamps(offers: list[Offer]) -> None:
    anchors: dict[tuple[str | None, str | None], datetime] = {}
    sequence_anchors: dict[tuple[str | None, str | None], datetime] = {}
    for offer in offers:
        if not offer.created_at_provider:
            continue
        provider_offer_id = str(offer.provider_offer_id or "")
        raw_payload = offer.raw_payload if isinstance(offer.raw_payload, dict) else {}
        source_id = raw_payload.get("derivedFromOfferId")
        if source_id:
            anchors[(str(source_id), "SELLER_COUNTEROFFER")] = offer.created_at_provider
        if provider_offer_id.endswith(":seller-counteroffer-submitted"):
            anchors[(provider_offer_id.removesuffix(":seller-counteroffer-submitted"), "SELLER_COUNTEROFFER")] = offer.created_at_provider
            sequence_anchors[offer_sequence_key(offer)] = offer.created_at_provider

    for offer in offers:
        if offer.created_at_provider:
            continue
        offer_type = str(offer.offer_type or "").upper()
        status = str(offer.status or "").upper()
        provider_offer_id = str(offer.provider_offer_id or "")

        if offer_type == "SELLER_COUNTEROFFER" and status == "ACCEPTED":
            anchor = anchors.get((provider_offer_id, "SELLER_COUNTEROFFER"))
            if anchor:
                offer.created_at_provider = anchor + timedelta(seconds=1)
                continue

        if offer_type == "BUYER_OFFER":
            matching_anchor = sequence_anchors.get(offer_sequence_key(offer))
            if matching_anchor:
                offer.created_at_provider = matching_anchor - timedelta(seconds=1)


def offer_sequence_key(offer: Offer) -> tuple[str | None, str | None]:
    return (
        str(offer.listing_id or "").strip() or None,
        str(offer.buyer_username or "").strip().lower() or None,
    )


def offer_timestamp_is_sync_fallback(offer: Offer) -> bool:
    if not offer.created_at_provider:
        return True
    if not offer.created_at:
        return False
    return abs((offer.created_at_provider - offer.created_at).total_seconds()) < 1


def offer_timestamp_from_raw_payload(payload, offer: Offer | None = None) -> datetime | None:
    if not isinstance(payload, dict):
        return None

    for key in ("createdTime", "createdDate", "sent_at", "sentAt", "timestamp"):
        parsed = parse_offer_payload_datetime(payload.get(key))
        if parsed:
            return parsed

    posted_time = payload.get("messagePostedTime")
    if isinstance(posted_time, dict):
        parsed = parse_offer_payload_datetime((posted_time.get("value") or {}).get("value") if isinstance(posted_time.get("value"), dict) else posted_time.get("value"))
        if parsed:
            return parsed

    expiration_time = parse_offer_payload_datetime(payload.get("expirationTime"))
    if expiration_time and offer:
        offer_type = str(offer.offer_type or "").upper()
        status = str(offer.status or "").upper()
        raw_offer_type = str(payload.get("offerType") or "").upper()
        if offer_type == "BUYER_OFFER" or raw_offer_type == "BUYERBESTOFFER":
            return expiration_time - BUYER_BEST_OFFER_EXPIRY_DURATION
        if offer_type == "SELLER_COUNTEROFFER" or raw_offer_type == "SELLERCOUNTEROFFER":
            timestamp = expiration_time - SELLER_COUNTEROFFER_EXPIRY_DURATION
            if status == "ACCEPTED":
                return timestamp + ACCEPTED_COUNTEROFFER_SEQUENCE_OFFSET
            return timestamp

    for nested_key in ("original_raw_payload", "card", "raw"):
        parsed = offer_timestamp_from_raw_payload(payload.get(nested_key), offer)
        if parsed:
            return parsed

    return None


def parse_offer_payload_datetime(value) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed.astimezone(UTC)


def serialize_attachment(attachment) -> MessageAttachmentResponse:
    """Serialize attachment metadata for chat rendering and downloads."""
    return MessageAttachmentResponse(
        id=attachment.id,
        message_id=attachment.message_id,
        account_id=attachment.account_id,
        provider=attachment.provider,
        provider_attachment_id=attachment.provider_attachment_id,
        file_name=attachment.file_name,
        media_name=attachment.media_name,
        media_url=attachment.media_url,
        media_type=attachment.media_type,
        mime_type=attachment.mime_type,
        file_size=attachment.file_size,
        download_url=attachment.download_url,
        created_at=attachment.created_at,
    )


def serialize_order_context(context: OrderContextResponse | None):
    if not context:
        return None

    return {
        "selected_order": serialize_order_context_order(context.selected_order),
        "candidate_orders": [
            serialize_order_context_order(order)
            for order in context.candidate_orders
        ],
        "linking": {
            "strategy": context.linking.strategy,
            "requires_manual_selection": context.linking.requires_manual_selection,
        },
        "deep_links": context.deep_links or {},
    }


def serialize_order_context_order(order):
    """
    Serialize one linked order candidate.

    Purpose:
    Provides compact order, return, cancellation, and line-item context for
    support agents.

    Parameters:
    order: EbayOrder ORM object or None.

    Returns:
    Dictionary representation of the order, or None.

    Business Logic:
    Generates eBay deep links from provider order identifiers for quick review.
    """
    if not order:
        return None
    return {
        'id': order.id,
        'order_id': order.order_id,
        'buyer_username': order.buyer_username,
        'payment_status': order.payment_status,
        'fulfillment_status': order.fulfillment_status,
        'cancel_status': order.cancel_status,
        'refund_status': order.refund_status,
        'pricing_summary': order.pricing_summary,
        'refunds': order.refunds,
        'line_items': [
            {
                'id': line_item.id,
                'item_id': line_item.item_id,
                'listing_id': line_item.listing_id,
                'sku': line_item.sku,
                'title': line_item.title,
                'image_url': line_item.image_url,
                'quantity': line_item.quantity,
                'price_value': float(line_item.price_value) if line_item.price_value is not None else None,
                'price_currency': line_item.price_currency,
            }
            for line_item in order.line_items
        ],
        'returns': [
            {
                'id': item.id,
                'return_id': item.return_id,
                'return_status': item.return_status,
                'return_reason': item.return_reason,
                'return_state': item.return_state,
                'created_date': item.created_date,
                'ebay_url': f'https://www.ebay.com/sh/ord/returns?returnId={item.return_id}',
            }
            for item in order.returns
        ],
        'cancellations': [
            {
                'id': item.id,
                'cancel_id': item.cancel_id,
                'cancel_state': item.cancel_state,
                'cancel_reason': item.cancel_reason,
                'requester': item.requester,
                'created_date': item.created_date,
                'ebay_url': f'https://www.ebay.com/sh/ord/cancellations?cancelId={item.cancel_id}',
            }
            for item in order.cancellations
        ],
        'ebay_url': f'https://www.ebay.com/sh/ord/details?orderId={order.order_id}',
    }


def serialize_assignment(assignment: ConversationAssignment) -> ConversationAssignmentResponse:
    """
    Serialize an assignment history row.

    Purpose:
    Exposes assigned by, assigned to, and assignment timestamps for audit
    visibility.

    Parameters:
    assignment: ConversationAssignment ORM object.

    Returns:
    ConversationAssignmentResponse.

    Business Logic:
    Includes nested assigner and assignee summaries when relationships are
    loaded.
    """
    return ConversationAssignmentResponse(
        id=assignment.id,
        conversation_id=assignment.conversation_id,
        assigned_to=assignment.assigned_to,
        assigned_by=assignment.assigned_by,
        assigned_at=assignment.assigned_at,
        unassigned_at=assignment.unassigned_at,
        assignee=serialize_user_brief(assignment.assignee) if assignment.assignee else None,
        assigner=serialize_user_brief(assignment.assigner) if assignment.assigner else None,
    )


def serialize_note(note: ConversationNote) -> ConversationNoteResponse:
    """
    Serialize an internal conversation note.

    Purpose:
    Returns note content and author metadata to the detail panel.

    Parameters:
    note: ConversationNote ORM object.

    Returns:
    ConversationNoteResponse.

    Business Logic:
    Author metadata is optional to preserve notes even if a user record is
    unavailable.
    """
    return ConversationNoteResponse(
        id=note.id,
        conversation_id=note.conversation_id,
        author_id=note.author_id,
        body=note.body,
        created_at=note.created_at,
        updated_at=note.updated_at,
        author=serialize_user_brief(note.author) if note.author else None,
    )


def serialize_user_brief(user: User) -> UserBriefResponse:
    """
    Serialize compact user identity information.

    Purpose:
    Avoids exposing full user records in assignment and note responses.

    Parameters:
    user: User ORM object.

    Returns:
    UserBriefResponse containing ID, name, email, and role.

    Business Logic:
    Role is returned as an empty string if the relationship is unavailable.
    """
    return UserBriefResponse(
        id=user.id,
        full_name=user.full_name,
        email=user.email,
        role=user.role.name if user.role else '',
    )


def serialize_category_brief(category: Category) -> CategoryBriefResponse:
    """
    Serialize compact category metadata.

    Purpose:
    Supplies label and color data for inbox badges and filters.

    Parameters:
    category: Category ORM object.

    Returns:
    CategoryBriefResponse.

    Business Logic:
    Only presentation-safe category fields are exposed.
    """
    return CategoryBriefResponse(id=category.id, name=category.name, color=category.color)


def serialize_ebay_account_brief(account: EbayAccount) -> EbayAccountBriefResponse:
    """
    Serialize compact seller account metadata.

    Purpose:
    Lets the inbox list show which seller account owns a conversation.

    Parameters:
    account: EbayAccount ORM object.

    Returns:
    EbayAccountBriefResponse.

    Business Logic:
    Includes store name when available for clearer seller identification.
    """
    return EbayAccountBriefResponse(
        id=account.id,
        account_name=account.account_name,
        ebay_username=account.ebay_username,
        store_name=account.store_name,
    )


def get_seller_account_map(db: Session, conversations: list[Conversation]) -> dict[UUID, EbayAccount]:
    """
    Load seller accounts for a page of conversations.

    Purpose:
    Avoids per-row account queries while serializing conversation lists.

    Parameters:
    db: Active database session.
    conversations: Conversations being serialized.

    Returns:
    Mapping of account UUID to EbayAccount.

    Business Logic:
    Conversations without provider accounts are ignored.
    """
    account_ids = {conversation.provider_account_id for conversation in conversations if conversation.provider_account_id}
    if not account_ids:
        return {}

    return {
        account.id: account
        for account in db.scalars(select(EbayAccount).where(EbayAccount.id.in_(account_ids)))
    }


def current_assignment_for(conversation: Conversation) -> ConversationAssignment | None:
    """
    Return the current assignment for a conversation.

    Purpose:
    Supports list-row assignment display and filtering.

    Parameters:
    conversation: Conversation with assignment history loaded.

    Returns:
    Current ConversationAssignment, or None.

    Business Logic:
    The current assignment is the assignment whose unassigned_at value is null.
    """
    return next((assignment for assignment in conversation.assignments if assignment.unassigned_at is None), None)


def latest_message_preview(conversation: Conversation, limit: int = 180) -> str | None:
    """
    Build a compact preview from the latest message body.

    Purpose:
    Shows meaningful conversation context in the inbox list.

    Parameters:
    conversation: Conversation with messages loaded.
    limit: Maximum preview length.

    Returns:
    Preview text or None when no messages exist.

    Business Logic:
    Whitespace is normalized and long previews are truncated with ellipsis.
    """
    if not conversation.messages:
        return None

    latest_message = max(conversation.messages, key=lambda message: message.sent_at)
    preview = plain_text_from_body(latest_message.body)
    if len(preview) <= limit:
        return preview
    return f'{preview[: limit - 3]}...'


def response_due_at(conversation: Conversation):
    """
    Calculate the response deadline for a conversation.

    Purpose:
    Drives SLA labels in the inbox list and detail panel.

    Parameters:
    conversation: Conversation with category loaded.

    Returns:
    Datetime deadline or None when there is no message timestamp.

    Business Logic:
    Uses category SLA hours when configured and falls back to 24 hours.
    """
    if not conversation.last_message_at:
        return None

    sla_hours = conversation.category.sla_hours if conversation.category else 24
    return conversation.last_message_at + timedelta(hours=sla_hours)


def latest_message_for(conversation: Conversation) -> Message | None:
    """
    Return the latest message in a conversation.

    Purpose:
    Shares latest-message selection across preview, direction, and status
    calculations.

    Parameters:
    conversation: Conversation with messages loaded.

    Returns:
    Latest Message by sent_at, or None.

    Business Logic:
    Message sent_at is authoritative for provider conversation chronology.
    """
    if not conversation.messages:
        return None
    return max(conversation.messages, key=lambda message: message.sent_at)


def last_message_direction(conversation: Conversation) -> str | None:
    """
    Calculate the latest message direction label.

    Purpose:
    Feeds the Last Message Direction indicator on conversation rows.

    Parameters:
    conversation: Conversation with messages loaded.

    Returns:
    Buyer, Agent, System, or None.

    Business Logic:
    Inbound provider/customer messages are Buyer, outbound agent messages are
    Agent, and explicit system messages are System.
    """
    message = latest_message_for(conversation)
    if not message:
        return None
    if message.sender_type.value == 'SYSTEM':
        return 'System'
    if message.sender_type.value == 'AGENT' or not message.is_inbound:
        return 'Agent'
    return 'Buyer'


def is_replied_conversation(conversation: Conversation) -> bool:
    """
    Determine whether the latest conversation activity is a seller reply.

    Purpose:
    Calculates the Replied status without requiring a stored duplicate field.

    Parameters:
    conversation: Conversation with messages loaded.

    Returns:
    True when the latest message is outbound from the seller.

    Business Logic:
    The overview arrow is a last-message indicator, so older replies do not
    count once a buyer or provider message arrives after them.
    """
    message = latest_message_for(conversation)
    return bool(message and (message.sender_type.value == 'AGENT' or not message.is_inbound))


def is_not_read_conversation(conversation: Conversation) -> bool:
    """
    Determine whether a conversation should be highlighted as Not Read.

    Purpose:
    Controls the black-dot unread indicator on the conversation listing.

    Parameters:
    conversation: Conversation with latest message data loaded.

    Returns:
    True when the latest message is inbound and unread.

    Business Logic:
    Conversation unread_count and latest message read_status are both honored
    because provider syncs may populate either field.
    """
    message = latest_message_for(conversation)
    return bool(message and message.is_inbound and (message.read_status is False or conversation.unread_count > 0))


def calculated_conversation_status(conversation: Conversation) -> str:
    """
    Calculate the business-facing conversation status.

    Purpose:
    Adds Replied and Not Read statuses derived from conversation history.

    Parameters:
    conversation: Conversation with messages loaded.

    Returns:
    Not Read, Replied, or the stored workflow status.

    Business Logic:
    Not Read takes priority over Replied because unread buyer activity needs
    immediate visibility even if the thread has older agent replies.
    """
    if is_not_read_conversation(conversation):
        return 'Not Read'
    if is_replied_conversation(conversation):
        return 'Replied'
    return conversation.status.value

@router.get('', response_model=ConversationPageResponse)
def list_conversations(
    limit: int = Query(default=25, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    search: str | None = Query(default=None, min_length=1),
    status: ConversationStatus | None = Query(default=None),
    provider: str | None = Query(default=None, min_length=1),
    conversation_type: str | None = Query(default=None, min_length=1),
    ebay_account_id: UUID | None = Query(default=None),
    assigned_user_id: UUID | None = Query(default=None),
    category_id: UUID | None = Query(default=None),
    db: Session = Depends(get_db),
    current_user=Depends(require_conversation_access),
) -> ConversationPageResponse:
    """Return the caller's role-scoped inbox with optional operational filters."""
    if is_support_agent(current_user) and assigned_user_id and assigned_user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail='Agents can only filter assignments by themselves')
    service = ConversationService(db)
    visible_category_ids = visible_category_ids_for_user(db, current_user)
    visibility_user_id = visibility_user_id_for_user(current_user)
    conversations = service.list_conversations(
        limit=limit,
        offset=offset,
        search=search,
        status=status,
        provider=provider,
        conversation_type=conversation_type,
        provider_account_id=ebay_account_id,
        assigned_user_id=assigned_user_id,
        category_id=category_id,
        visible_category_ids=visible_category_ids,
        visibility_user_id=visibility_user_id,
    )
    seller_accounts = get_seller_account_map(db, conversations)
    return ConversationPageResponse(
        items=[
            serialize_conversation_summary(conversation, seller_accounts.get(conversation.provider_account_id))
            for conversation in conversations
        ],
        total=service.count_conversations(
            search=search,
            status=status,
            provider=provider,
            conversation_type=conversation_type,
            provider_account_id=ebay_account_id,
            assigned_user_id=assigned_user_id,
            category_id=category_id,
            visible_category_ids=visible_category_ids,
            visibility_user_id=visibility_user_id,
        ),
        limit=limit,
        offset=offset,
    )


@router.get('/attachments/{stored_name}')
def download_reply_attachment(
    stored_name: str,
    db: Session = Depends(get_db),
    current_user=Depends(require_conversation_access),
) -> FileResponse:
    """Download a locally stored reply attachment."""
    path = ReplyAttachmentService().resolve_download_path(stored_name)
    attachment = db.scalar(
        select(MessageAttachment)
        .join(Message, Message.id == MessageAttachment.message_id)
        .where(MessageAttachment.storage_path == str(path))
    )
    if not attachment:
        from fastapi import HTTPException, status

        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Attachment not found')
    ConversationService(db).get_conversation(
        attachment.message.conversation_id,
        visible_category_ids=visible_category_ids_for_user(db, current_user),
        visibility_user_id=visibility_user_id_for_user(current_user),
    )
    return FileResponse(path, media_type=attachment.mime_type, filename=attachment.file_name)


@router.get('/public/attachments/{attachment_id}/download')
def download_public_reply_attachment(
    attachment_id: UUID,
    db: Session = Depends(get_db),
) -> FileResponse:
    """Serve a stored reply attachment through a public unguessable URL."""
    attachment = db.get(MessageAttachment, attachment_id)
    if not attachment or not attachment.storage_path:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Attachment not found')
    path = ReplyAttachmentService().resolve_storage_path(attachment.storage_path)
    return FileResponse(path, media_type=attachment.mime_type, filename=attachment.file_name)


@router.get('/{conversation_id}', response_model=ConversationDetailResponse)
def get_conversation(
    conversation_id: UUID,
    db: Session = Depends(get_db),
    current_user=Depends(require_conversation_access),
) -> ConversationDetailResponse:
    service = ConversationService(db)
    conversation = service.get_conversation(
        conversation_id,
        visible_category_ids=visible_category_ids_for_user(db, current_user),
        visibility_user_id=visibility_user_id_for_user(current_user),
    )
    if is_not_read_conversation(conversation):
        conversation = service.mark_read(conversation)
    seller_account = db.get(EbayAccount, conversation.provider_account_id) if conversation.provider_account_id else None
    product_service = ConversationProductContextService(db)
    product_context = product_service.serialize(product_service.context_for_conversation(conversation))
    context = OrderContextService(db).build_context(conversation)
    order_context = OrderContextService(db).serialize_context(context)
    offers = stored_conversation_offers(db, conversation)
    db.commit()
    return serialize_conversation(
        conversation,
        service.get_current_assignee_id(conversation.id),
        seller_account,
        product_context,
        order_context,
        MessageTypeDetectionService(db).suggest(conversation),
        offers,
    )


@router.patch('/{conversation_id}/order', response_model=ConversationDetailResponse)
def select_conversation_order(
    conversation_id: UUID,
    payload: SelectConversationOrderRequest,
    db: Session = Depends(get_db),
    current_user=Depends(require_conversation_access),
) -> ConversationDetailResponse:
    service = ConversationService(db)
    conversation = service.get_conversation(
        conversation_id,
        visible_category_ids=visible_category_ids_for_user(db, current_user),
        visibility_user_id=visibility_user_id_for_user(current_user),
    )
    conversation = OrderContextService(db).select_order(conversation, payload.order_record_id)
    seller_account = db.get(EbayAccount, conversation.provider_account_id) if conversation.provider_account_id else None
    product_service = ConversationProductContextService(db)
    product_context = product_service.serialize(product_service.context_for_conversation(conversation))
    context = OrderContextService(db).build_context(conversation)
    order_context = OrderContextService(db).serialize_context(context)
    offers = stored_conversation_offers(db, conversation)
    db.commit()
    return serialize_conversation(conversation, service.get_current_assignee_id(conversation.id), seller_account, product_context, order_context, offers=offers)


@router.get('/{conversation_id}/context', response_model=ConversationProductContextResponse | None)
def get_conversation_context(
    conversation_id: UUID,
    db: Session = Depends(get_db),
    current_user=Depends(require_conversation_access),
) -> ConversationProductContextResponse | None:
    conversation = ConversationService(db).get_conversation(
        conversation_id,
        visible_category_ids=visible_category_ids_for_user(db, current_user),
        visibility_user_id=visibility_user_id_for_user(current_user),
    )
    product_service = ConversationProductContextService(db)
    context = product_service.serialize(product_service.context_for_conversation(conversation))
    db.commit()
    return context


@router.get('/{conversation_id}/messages', response_model=list[MessageResponse])
def list_conversation_messages(
    conversation_id: UUID,
    db: Session = Depends(get_db),
    current_user=Depends(require_conversation_access),
) -> list[MessageResponse]:
    ConversationService(db).get_conversation(
        conversation_id,
        visible_category_ids=visible_category_ids_for_user(db, current_user),
        visibility_user_id=visibility_user_id_for_user(current_user),
    )
    return [serialize_message(message) for message in MessageService(db).list_messages(conversation_id)]


@router.post('/{conversation_id}/reply/validate', response_model=ReplyValidationResponse)
def validate_reply(
    conversation_id: UUID,
    payload: ReplyConversationRequest,
    db: Session = Depends(get_db),
    current_user=Depends(require_conversation_access),
) -> ReplyValidationResponse:
    """Validate reply content only after confirming the caller owns the queue item."""
    conversation = ConversationService(db).get_conversation(
        conversation_id,
        visible_category_ids=visible_category_ids_for_user(db, current_user),
        visibility_user_id=visibility_user_id_for_user(current_user),
    )
    if is_ebay_system_conversation(conversation):
        return ReplyValidationResponse(valid=False, violations=['eBay system conversations cannot be replied to.'])
    ensure_reply_assignment(db, conversation_id, current_user)
    violations = EbayReplyService(db).validate_reply(payload.body)
    return ReplyValidationResponse(valid=not violations, violations=violations)


@router.post('/{conversation_id}/reply', response_model=MessageResponse)
async def reply_to_conversation(
    conversation_id: UUID,
    request: Request,
    body: str | None = Form(default=None),
    message_type_id: UUID | None = Form(default=None),
    attachments: list[UploadFile] | None = File(default=None),
    db: Session = Depends(get_db),
    current_user=Depends(require_conversation_access),
) -> MessageResponse:
    """
    Deliver a reply after enforcing visibility and active-assignment ownership.

    The assignment check occurs before contacting eBay. Unassigned threads can
    be handled by eligible category agents, while assigned threads can only be
    answered by their current owner regardless of the caller's role.
    """
    reply_body = body
    if not reply_body and request.headers.get('content-type', '').startswith('application/json'):
        payload = await request.json()
        reply_body = str(payload.get('body') or '')
        try:
            message_type_id = UUID(str(payload.get('message_type_id') or ''))
        except ValueError:
            message_type_id = None
    reply_body = (reply_body or '').strip()
    if not reply_body or len(reply_body) > 2000:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail='Reply body must be between 1 and 2000 characters')
    if not message_type_id:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail='Message type is required')
    ConversationService(db).get_conversation(
        conversation_id,
        visible_category_ids=visible_category_ids_for_user(db, current_user),
        visibility_user_id=visibility_user_id_for_user(current_user),
    )
    message = await EbayReplyService(db).send_reply(
        conversation_id=conversation_id,
        body=reply_body,
        actor_id=current_user.id,
        message_type_id=message_type_id,
        attachments=attachments or [],
    )
    return serialize_message(message)


@router.post('/{conversation_id}/assign', response_model=ConversationAssignmentResponse)
def assign_conversation(
    conversation_id: UUID,
    payload: AssignConversationRequest,
    db: Session = Depends(get_db),
    current_user=Depends(require_conversation_access),
) -> ConversationAssignmentResponse:
    ensure_can_assign_conversation(current_user)
    conversation = ConversationService(db).get_conversation(
        conversation_id,
        visible_category_ids=visible_category_ids_for_user(db, current_user),
        visibility_user_id=visibility_user_id_for_user(current_user),
    )
    ensure_reply_assignment(db, conversation_id, current_user)
    if conversation.status == ConversationStatus.CLOSED:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail='Closed conversations cannot be reassigned')
    assignment = AssignmentService(db).assign_conversation(
        conversation_id=conversation_id,
        assigned_to=payload.assigned_to,
        assigned_by=current_user.id,
    )
    create_assignment_notification(db, conversation=conversation, assignment=assignment, assigned_to=payload.assigned_to, assigned_by_user=current_user)
    AuditService(db).log(
        action='CONVERSATION_ASSIGNED',
        user_id=current_user.id,
        entity_type='CONVERSATION',
        entity_id=conversation_id,
        category='ASSIGNMENT',
        metadata={'assigned_to': str(payload.assigned_to)},
    )
    db.commit()
    db.refresh(assignment)
    return serialize_assignment(assignment)


@router.post('/{conversation_id}/notes', response_model=ConversationNoteResponse)
def create_conversation_note(
    conversation_id: UUID,
    payload: ConversationNoteCreateRequest,
    db: Session = Depends(get_db),
    current_user=Depends(require_conversation_access),
) -> ConversationNoteResponse:
    conversation = ConversationService(db).get_conversation(
        conversation_id,
        visible_category_ids=visible_category_ids_for_user(db, current_user),
        visibility_user_id=visibility_user_id_for_user(current_user),
    )
    if conversation.status == ConversationStatus.CLOSED:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail='Closed conversations cannot receive notes')
    note = ConversationNoteService(db).add_note(
        conversation_id=conversation_id,
        author_id=current_user.id,
        body=payload.body,
    )
    return serialize_note(note)


@router.get('/{conversation_id}/notes', response_model=list[ConversationNoteResponse])
def list_conversation_notes(
    conversation_id: UUID,
    db: Session = Depends(get_db),
    current_user=Depends(require_conversation_access),
) -> list[ConversationNoteResponse]:
    ConversationService(db).get_conversation(
        conversation_id,
        visible_category_ids=visible_category_ids_for_user(db, current_user),
        visibility_user_id=visibility_user_id_for_user(current_user),
    )
    return [serialize_note(note) for note in ConversationNoteService(db).list_notes(conversation_id)]


@router.patch('/{conversation_id}/status', response_model=ConversationDetailResponse)
def update_conversation_status(
    conversation_id: UUID,
    payload: UpdateConversationStatusRequest,
    db: Session = Depends(get_db),
    current_user=Depends(require_conversation_access),
) -> ConversationDetailResponse:
    service = ConversationService(db)
    conversation = service.get_conversation(
        conversation_id,
        visible_category_ids=visible_category_ids_for_user(db, current_user),
        visibility_user_id=visibility_user_id_for_user(current_user),
    )
    conversation = service.update_status(
        conversation_id=conversation_id,
        new_status=payload.status,
        changed_by=current_user.id,
        note=payload.note,
    )
    AuditService(db).log(
        action='MESSAGE_STATUS_CHANGED',
        user_id=current_user.id,
        entity_type='CONVERSATION',
        entity_id=conversation_id,
        category='MESSAGE_MANAGEMENT',
        metadata={'status': payload.status.value},
    )
    db.commit()
    seller_account = db.get(EbayAccount, conversation.provider_account_id) if conversation.provider_account_id else None
    product_service = ConversationProductContextService(db)
    product_context = product_service.serialize(product_service.context_for_conversation(conversation))
    offers = stored_conversation_offers(db, conversation)
    db.commit()
    return serialize_conversation(conversation, service.get_current_assignee_id(conversation.id), seller_account, product_context, offers=offers)


@router.patch('/{conversation_id}/category', response_model=ConversationDetailResponse)
def update_conversation_category(
    conversation_id: UUID,
    payload: UpdateConversationCategoryRequest,
    db: Session = Depends(get_db),
    current_user=Depends(require_conversation_access),
) -> ConversationDetailResponse:
    service = ConversationService(db)
    service.get_conversation(
        conversation_id,
        visible_category_ids=visible_category_ids_for_user(db, current_user),
        visibility_user_id=visibility_user_id_for_user(current_user),
    )
    ensure_can_manage_conversation(current_user)
    conversation = service.update_category(
        conversation_id=conversation_id,
        category_id=payload.category_id,
        changed_by=current_user.id,
        note=payload.note,
    )
    AuditService(db).log(
        action='MESSAGE_CATEGORY_CHANGED',
        user_id=current_user.id,
        entity_type='CONVERSATION',
        entity_id=conversation_id,
        category='MESSAGE_MANAGEMENT',
        metadata={'category_id': str(payload.category_id) if payload.category_id else None},
    )
    db.commit()
    seller_account = db.get(EbayAccount, conversation.provider_account_id) if conversation.provider_account_id else None
    product_service = ConversationProductContextService(db)
    product_context = product_service.serialize(product_service.context_for_conversation(conversation))
    offers = stored_conversation_offers(db, conversation)
    db.commit()
    return serialize_conversation(conversation, service.get_current_assignee_id(conversation.id), seller_account, product_context, offers=offers)


@router.post('/bulk-update', response_model=BulkConversationUpdateResponse)
def bulk_update_conversations(
    payload: BulkConversationUpdateRequest,
    db: Session = Depends(get_db),
    current_user=Depends(require_conversation_access),
) -> BulkConversationUpdateResponse:
    if payload.category_id is not None or payload.status is not None or payload.assign_to_category_owners:
        ensure_can_manage_conversation(current_user)
    if payload.assigned_to:
        ensure_can_assign_conversation(current_user)
    service = ConversationService(db)
    assignment_service = AssignmentService(db)
    updated_count = 0
    assignment_count = 0
    skipped_count = 0

    owner_ids: list[UUID] = []
    if payload.assign_to_category_owners and payload.category_id:
        owner_ids = [user.id for user in CategoryAssignmentService(db).users_for_category(payload.category_id)]

    for conversation_id in payload.conversation_ids:
        try:
            conversation = service.get_conversation(
                conversation_id,
                visible_category_ids=visible_category_ids_for_user(db, current_user),
                visibility_user_id=visibility_user_id_for_user(current_user),
            )
            if payload.category_id is not None:
                service.update_category(
                    conversation_id=conversation_id,
                    category_id=payload.category_id,
                    changed_by=current_user.id,
                    note='Bulk category update',
                )
            if payload.status is not None:
                service.update_status(
                    conversation_id=conversation_id,
                    new_status=payload.status,
                    changed_by=current_user.id,
                    note='Bulk status update',
                )
            if payload.assigned_to:
                assignment = assignment_service.assign_conversation(
                    conversation_id=conversation_id,
                    assigned_to=payload.assigned_to,
                    assigned_by=current_user.id,
                )
                create_assignment_notification(db, conversation=conversation, assignment=assignment, assigned_to=payload.assigned_to, assigned_by_user=current_user)
                assignment_count += 1
            for owner_id in owner_ids:
                assignment = assignment_service.assign_conversation(
                    conversation_id=conversation_id,
                    assigned_to=owner_id,
                    assigned_by=current_user.id,
                )
                create_assignment_notification(db, conversation=conversation, assignment=assignment, assigned_to=owner_id, assigned_by_user=current_user)
                assignment_count += 1
            updated_count += 1
        except Exception:
            skipped_count += 1

    AuditService(db).log(
        action='BULK_ASSIGNMENT_UPDATED',
        user_id=current_user.id,
        entity_type='CONVERSATION',
        category='ASSIGNMENT',
        metadata={
            'conversation_ids': [str(value) for value in payload.conversation_ids],
            'assigned_to': str(payload.assigned_to) if payload.assigned_to else None,
            'category_id': str(payload.category_id) if payload.category_id else None,
            'assign_to_category_owners': payload.assign_to_category_owners,
            'updated_count': updated_count,
            'skipped_count': skipped_count,
        },
    )
    db.commit()
    return BulkConversationUpdateResponse(
        updated_count=updated_count,
        assignment_count=assignment_count,
        skipped_count=skipped_count,
        message='Bulk update completed',
    )
