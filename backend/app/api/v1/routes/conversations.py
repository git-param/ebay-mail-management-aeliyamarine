from datetime import timedelta
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.dependencies import can_manage_operations, get_current_user, is_support_agent
from app.db.session import get_db
from app.models.category import Category
from app.models.conversation import Conversation, ConversationAssignment, ConversationNote, ConversationStatus, Message
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


router = APIRouter()


def require_conversation_access(current_user=Depends(get_current_user)):
    return current_user


def visible_category_ids_for_user(db: Session, current_user) -> set[UUID] | None:
    if is_support_agent(current_user):
        return CategoryAssignmentService(db).assigned_category_ids(current_user.id)
    return None


def ensure_can_manage_conversation(current_user) -> None:
    if not can_manage_operations(current_user):
        from fastapi import HTTPException, status

        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail='Only admins and operations managers can manage assignments and categories')


def serialize_conversation(
    conversation: Conversation,
    current_assignee_id: UUID | None = None,
    seller_account: EbayAccount | None = None,
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
        provider=attachment.provider,
        provider_attachment_id=attachment.provider_attachment_id,
        file_name=attachment.file_name,
        mime_type=attachment.mime_type,
        file_size=attachment.file_size,
        download_url=attachment.download_url,
        created_at=attachment.created_at,
    )


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
        ),
        limit=limit,
        offset=offset,
    )


@router.get('/{conversation_id}', response_model=ConversationDetailResponse)
def get_conversation(
    conversation_id: UUID,
    db: Session = Depends(get_db),
    current_user=Depends(require_conversation_access),
) -> ConversationDetailResponse:
    service = ConversationService(db)
    conversation = service.get_conversation(conversation_id, visible_category_ids=visible_category_ids_for_user(db, current_user))
    seller_account = db.get(EbayAccount, conversation.provider_account_id) if conversation.provider_account_id else None
    return serialize_conversation(conversation, service.get_current_assignee_id(conversation.id), seller_account)


@router.get('/{conversation_id}/messages', response_model=list[MessageResponse])
def list_conversation_messages(
    conversation_id: UUID,
    db: Session = Depends(get_db),
    current_user=Depends(require_conversation_access),
) -> list[MessageResponse]:
    ConversationService(db).get_conversation(conversation_id, visible_category_ids=visible_category_ids_for_user(db, current_user))
    return [serialize_message(message) for message in MessageService(db).list_messages(conversation_id)]


@router.post('/{conversation_id}/reply/validate', response_model=ReplyValidationResponse)
def validate_reply(
    conversation_id: UUID,
    payload: ReplyConversationRequest,
    db: Session = Depends(get_db),
    current_user=Depends(require_conversation_access),
) -> ReplyValidationResponse:
    ConversationService(db).get_conversation(conversation_id, visible_category_ids=visible_category_ids_for_user(db, current_user))
    violations = EbayReplyService(db).validate_reply(payload.body)
    return ReplyValidationResponse(valid=not violations, violations=violations)


@router.post('/{conversation_id}/reply', response_model=MessageResponse)
def reply_to_conversation(
    conversation_id: UUID,
    payload: ReplyConversationRequest,
    db: Session = Depends(get_db),
    current_user=Depends(require_conversation_access),
) -> MessageResponse:
    ConversationService(db).get_conversation(conversation_id, visible_category_ids=visible_category_ids_for_user(db, current_user))
    message = EbayReplyService(db).send_reply(
        conversation_id=conversation_id,
        body=payload.body.strip(),
        actor_id=current_user.id,
    )
    return serialize_message(message)


@router.post('/{conversation_id}/assign', response_model=ConversationAssignmentResponse)
def assign_conversation(
    conversation_id: UUID,
    payload: AssignConversationRequest,
    db: Session = Depends(get_db),
    current_user=Depends(require_conversation_access),
) -> ConversationAssignmentResponse:
    ensure_can_manage_conversation(current_user)
    conversation = ConversationService(db).get_conversation(conversation_id)
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
    ConversationService(db).get_conversation(conversation_id, visible_category_ids=visible_category_ids_for_user(db, current_user))
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
    ConversationService(db).get_conversation(conversation_id, visible_category_ids=visible_category_ids_for_user(db, current_user))
    return [serialize_note(note) for note in ConversationNoteService(db).list_notes(conversation_id)]


@router.patch('/{conversation_id}/status', response_model=ConversationDetailResponse)
def update_conversation_status(
    conversation_id: UUID,
    payload: UpdateConversationStatusRequest,
    db: Session = Depends(get_db),
    current_user=Depends(require_conversation_access),
) -> ConversationDetailResponse:
    service = ConversationService(db)
    service.get_conversation(conversation_id, visible_category_ids=visible_category_ids_for_user(db, current_user))
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
    return serialize_conversation(conversation, service.get_current_assignee_id(conversation.id))


@router.patch('/{conversation_id}/category', response_model=ConversationDetailResponse)
def update_conversation_category(
    conversation_id: UUID,
    payload: UpdateConversationCategoryRequest,
    db: Session = Depends(get_db),
    current_user=Depends(require_conversation_access),
) -> ConversationDetailResponse:
    service = ConversationService(db)
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
    return serialize_conversation(conversation, service.get_current_assignee_id(conversation.id))


@router.post('/bulk-update', response_model=BulkConversationUpdateResponse)
def bulk_update_conversations(
    payload: BulkConversationUpdateRequest,
    db: Session = Depends(get_db),
    current_user=Depends(require_conversation_access),
) -> BulkConversationUpdateResponse:
    ensure_can_manage_conversation(current_user)
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
            conversation = service.get_conversation(conversation_id)
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
