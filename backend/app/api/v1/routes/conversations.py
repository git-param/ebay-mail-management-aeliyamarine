from datetime import timedelta
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user
from app.db.session import get_db
from app.models.category import Category
from app.models.conversation import Conversation, ConversationAssignment, ConversationNote, ConversationStatus, Message
from app.models.ebay_account import EbayAccount
from app.models.user import User
from app.schemas.conversation import (
    AssignConversationRequest,
    CategoryBriefResponse,
    ConversationAssignmentResponse,
    ConversationDetailResponse,
    ConversationNoteCreateRequest,
    ConversationNoteResponse,
    ConversationPageResponse,
    ConversationSummaryResponse,
    EbayAccountBriefResponse,
    MessageResponse,
    UpdateConversationCategoryRequest,
    UpdateConversationStatusRequest,
    UserBriefResponse,
)
from app.services.assignment_service import AssignmentService
from app.services.conversation_note_service import ConversationNoteService
from app.services.conversation_service import ConversationService
from app.services.message_service import MessageService


router = APIRouter()


def require_conversation_access(current_user=Depends(get_current_user)):
    return current_user


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
    conversations = service.list_conversations(
        limit=limit,
        offset=offset,
        search=search,
        status=status,
        provider=provider,
        provider_account_id=ebay_account_id,
        assigned_user_id=assigned_user_id,
        category_id=category_id,
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
    conversation = service.get_conversation(conversation_id)
    seller_account = db.get(EbayAccount, conversation.provider_account_id) if conversation.provider_account_id else None
    return serialize_conversation(conversation, service.get_current_assignee_id(conversation.id), seller_account)


@router.get('/{conversation_id}/messages', response_model=list[MessageResponse])
def list_conversation_messages(
    conversation_id: UUID,
    db: Session = Depends(get_db),
    current_user=Depends(require_conversation_access),
) -> list[MessageResponse]:
    return [serialize_message(message) for message in MessageService(db).list_messages(conversation_id)]


@router.post('/{conversation_id}/assign', response_model=ConversationAssignmentResponse)
def assign_conversation(
    conversation_id: UUID,
    payload: AssignConversationRequest,
    db: Session = Depends(get_db),
    current_user=Depends(require_conversation_access),
) -> ConversationAssignmentResponse:
    assignment = AssignmentService(db).assign_conversation(
        conversation_id=conversation_id,
        assigned_to=payload.assigned_to,
        assigned_by=current_user.id,
    )
    return serialize_assignment(assignment)


@router.post('/{conversation_id}/notes', response_model=ConversationNoteResponse)
def create_conversation_note(
    conversation_id: UUID,
    payload: ConversationNoteCreateRequest,
    db: Session = Depends(get_db),
    current_user=Depends(require_conversation_access),
) -> ConversationNoteResponse:
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
    return [serialize_note(note) for note in ConversationNoteService(db).list_notes(conversation_id)]


@router.patch('/{conversation_id}/status', response_model=ConversationDetailResponse)
def update_conversation_status(
    conversation_id: UUID,
    payload: UpdateConversationStatusRequest,
    db: Session = Depends(get_db),
    current_user=Depends(require_conversation_access),
) -> ConversationDetailResponse:
    service = ConversationService(db)
    conversation = service.update_status(
        conversation_id=conversation_id,
        new_status=payload.status,
        changed_by=current_user.id,
        note=payload.note,
    )
    return serialize_conversation(conversation, service.get_current_assignee_id(conversation.id))


@router.patch('/{conversation_id}/category', response_model=ConversationDetailResponse)
def update_conversation_category(
    conversation_id: UUID,
    payload: UpdateConversationCategoryRequest,
    db: Session = Depends(get_db),
    current_user=Depends(require_conversation_access),
) -> ConversationDetailResponse:
    service = ConversationService(db)
    conversation = service.update_category(
        conversation_id=conversation_id,
        category_id=payload.category_id,
        changed_by=current_user.id,
        note=payload.note,
    )
    return serialize_conversation(conversation, service.get_current_assignee_id(conversation.id))
