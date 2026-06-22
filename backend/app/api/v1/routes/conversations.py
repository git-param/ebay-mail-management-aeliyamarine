from datetime import timedelta
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.dependencies import can_manage_operations, get_current_user, is_admin, is_operations_manager, is_support_agent
from app.db.session import get_db
from app.models.category import Category, CategoryUserAssignment
from app.models.conversation import Conversation, ConversationAssignment, ConversationNote, ConversationStatus, Message, MessageAttachment
from app.models.ebay_account import EbayAccount
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
    ConversationSummaryResponse,
    EbayAccountBriefResponse,
    MessageResponse,
    MessageAttachmentResponse,
    ReplyConversationRequest,
    ReplyValidationResponse,
    SelectConversationOrderRequest,
    UpdateConversationCategoryRequest,
    UpdateConversationStatusRequest,
    UserBriefResponse,
)
from app.services.assignment_service import AssignmentService
from app.services.audit_service import AuditService
from app.services.category_assignment_service import CategoryAssignmentService
from app.services.conversation_note_service import ConversationNoteService
from app.services.conversation_service import ConversationService
from app.services.message_service import MessageService
from app.services.ebay_reply_service import EbayReplyService
from app.services.notification_service import NotificationService
from app.services.order_context_service import OrderContextService
from app.services.reply_attachment_service import ReplyAttachmentService


router = APIRouter()


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


def can_assign_conversations(current_user) -> bool:
    return is_admin(current_user) or is_operations_manager(current_user) or is_support_agent(current_user)


def ensure_can_assign_conversation(current_user) -> None:
    if not can_assign_conversations(current_user):
        from fastapi import HTTPException, status

        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail='Only support users can assign conversations')


def ensure_can_manage_conversation(current_user) -> None:
    if not can_manage_operations(current_user):
        from fastapi import HTTPException, status

        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail='Only admins and operations managers can manage assignments and categories')


def serialize_conversation(
    conversation: Conversation,
    current_assignee_id: UUID | None = None,
    seller_account: EbayAccount | None = None,
    order_context: dict | None = None,
) -> ConversationDetailResponse:
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
        response_due_at=response_due_at(conversation),
        status=conversation.status,
        category_id=conversation.category_id,
        category=serialize_category_brief(conversation.category) if conversation.category else None,
        last_message_at=conversation.last_message_at,
        external_created_at=conversation.external_created_at,
        created_at=conversation.created_at,
        updated_at=conversation.updated_at,
        current_assignment=next((assignment for assignment in assignments if assignment.unassigned_at is None), None),
        seller_account=serialize_ebay_account_brief(seller_account) if seller_account else None,
        current_assignee_id=current_assignee_id,
        messages=[serialize_message(message) for message in conversation.messages],
        assignments=assignments,
        notes=[serialize_note(note) for note in conversation.notes],
        order_context=serialize_order_context(order_context) if order_context else None,
    )


def serialize_conversation_summary(
    conversation: Conversation,
    seller_account: EbayAccount | None = None,
) -> ConversationSummaryResponse:
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
        response_due_at=response_due_at(conversation),
        status=conversation.status,
        category_id=conversation.category_id,
        category=serialize_category_brief(conversation.category) if conversation.category else None,
        last_message_at=conversation.last_message_at,
        external_created_at=conversation.external_created_at,
        created_at=conversation.created_at,
        updated_at=conversation.updated_at,
        current_assignment=serialize_assignment(current_assignment) if (current_assignment := current_assignment_for(conversation)) else None,
        seller_account=serialize_ebay_account_brief(seller_account) if seller_account else None,
    )


def serialize_message(message: Message) -> MessageResponse:
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
    )


def serialize_attachment(attachment) -> MessageAttachmentResponse:
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


def serialize_order_context(context: dict):
    return {
        'selected_order': serialize_order_context_order(context.get('selected_order')),
        'candidate_orders': [serialize_order_context_order(order) for order in context.get('candidate_orders', [])],
        'linking': context.get('linking') or {'strategy': 'NO_MATCH', 'requires_manual_selection': False},
        'deep_links': context.get('deep_links') or {},
    }


def serialize_order_context_order(order):
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
                'title': line_item.title,
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
    return UserBriefResponse(
        id=user.id,
        full_name=user.full_name,
        email=user.email,
        role=user.role.name if user.role else '',
    )


def serialize_category_brief(category: Category) -> CategoryBriefResponse:
    return CategoryBriefResponse(id=category.id, name=category.name, color=category.color)


def serialize_ebay_account_brief(account: EbayAccount) -> EbayAccountBriefResponse:
    return EbayAccountBriefResponse(
        id=account.id,
        account_name=account.account_name,
        ebay_username=account.ebay_username,
        store_name=account.store_name,
    )


def get_seller_account_map(db: Session, conversations: list[Conversation]) -> dict[UUID, EbayAccount]:
    account_ids = {conversation.provider_account_id for conversation in conversations if conversation.provider_account_id}
    if not account_ids:
        return {}

    return {
        account.id: account
        for account in db.scalars(select(EbayAccount).where(EbayAccount.id.in_(account_ids)))
    }


def current_assignment_for(conversation: Conversation) -> ConversationAssignment | None:
    return next((assignment for assignment in conversation.assignments if assignment.unassigned_at is None), None)


def latest_message_preview(conversation: Conversation, limit: int = 180) -> str | None:
    if not conversation.messages:
        return None

    latest_message = max(conversation.messages, key=lambda message: message.sent_at)
    preview = ' '.join(latest_message.body.split())
    if len(preview) <= limit:
        return preview
    return f'{preview[: limit - 3]}...'


def response_due_at(conversation: Conversation):
    if not conversation.last_message_at:
        return None

    sla_hours = conversation.category.sla_hours if conversation.category else 24
    return conversation.last_message_at + timedelta(hours=sla_hours)


@router.get('', response_model=ConversationPageResponse)
def list_conversations(
    limit: int = Query(default=25, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    search: str | None = Query(default=None, min_length=1),
    status: ConversationStatus | None = Query(default=None),
    provider: str | None = Query(default=None, min_length=1),
    ebay_account_id: UUID | None = Query(default=None),
    assigned_user_id: UUID | None = Query(default=None),
    category_id: UUID | None = Query(default=None),
    db: Session = Depends(get_db),
    current_user=Depends(require_conversation_access),
) -> ConversationPageResponse:
    service = ConversationService(db)
    visible_category_ids = visible_category_ids_for_user(db, current_user)
    visibility_user_id = visibility_user_id_for_user(current_user)
    conversations = service.list_conversations(
        limit=limit,
        offset=offset,
        search=search,
        status=status,
        provider=provider,
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
    return FileResponse(path)


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
    seller_account = db.get(EbayAccount, conversation.provider_account_id) if conversation.provider_account_id else None
    order_context = OrderContextService(db).context_for_conversation(conversation)
    return serialize_conversation(conversation, service.get_current_assignee_id(conversation.id), seller_account, order_context)


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
    order_context = OrderContextService(db).context_for_conversation(conversation)
    return serialize_conversation(conversation, service.get_current_assignee_id(conversation.id), seller_account, order_context)


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
    ConversationService(db).get_conversation(
        conversation_id,
        visible_category_ids=visible_category_ids_for_user(db, current_user),
        visibility_user_id=visibility_user_id_for_user(current_user),
    )
    violations = EbayReplyService(db).validate_reply(payload.body)
    return ReplyValidationResponse(valid=not violations, violations=violations)


@router.post('/{conversation_id}/reply', response_model=MessageResponse)
async def reply_to_conversation(
    conversation_id: UUID,
    request: Request,
    body: str | None = Form(default=None),
    attachments: list[UploadFile] | None = File(default=None),
    db: Session = Depends(get_db),
    current_user=Depends(require_conversation_access),
) -> MessageResponse:
    """Send a reply, accepting JSON for text-only replies or multipart with attachments."""
    reply_body = body
    if not reply_body and request.headers.get('content-type', '').startswith('application/json'):
        payload = await request.json()
        reply_body = str(payload.get('body') or '')
    reply_body = (reply_body or '').strip()
    if not reply_body or len(reply_body) > 2000:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail='Reply body must be between 1 and 2000 characters')
    ConversationService(db).get_conversation(
        conversation_id,
        visible_category_ids=visible_category_ids_for_user(db, current_user),
        visibility_user_id=visibility_user_id_for_user(current_user),
    )
    message = await EbayReplyService(db).send_reply(
        conversation_id=conversation_id,
        body=reply_body,
        actor_id=current_user.id,
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
    assignment = AssignmentService(db).assign_conversation(
        conversation_id=conversation_id,
        assigned_to=payload.assigned_to,
        assigned_by=current_user.id,
    )
    NotificationService(db).create(
        user_id=payload.assigned_to,
        title='Conversation assigned',
        body=f'Conversation {conversation.subject or conversation.provider_conversation_id} was assigned to you.',
        event_type='MESSAGE_ASSIGNMENT',
        event_key=f'conversation-assigned:{assignment.id}',
        resource_type='CONVERSATION',
        resource_id=conversation_id,
    )
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
    ConversationService(db).get_conversation(
        conversation_id,
        visible_category_ids=visible_category_ids_for_user(db, current_user),
        visibility_user_id=visibility_user_id_for_user(current_user),
    )
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
    service.get_conversation(
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
    order_context = OrderContextService(db).context_for_conversation(conversation)
    return serialize_conversation(conversation, service.get_current_assignee_id(conversation.id), seller_account, order_context)


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
    order_context = OrderContextService(db).context_for_conversation(conversation)
    return serialize_conversation(conversation, service.get_current_assignee_id(conversation.id), seller_account, order_context)


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
                assignment_service.assign_conversation(
                    conversation_id=conversation_id,
                    assigned_to=payload.assigned_to,
                    assigned_by=current_user.id,
                )
                assignment_count += 1
            for owner_id in owner_ids:
                assignment_service.assign_conversation(
                    conversation_id=conversation_id,
                    assigned_to=owner_id,
                    assigned_by=current_user.id,
                )
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
