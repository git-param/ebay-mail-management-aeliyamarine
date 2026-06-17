from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user
from app.db.session import get_db
from app.models.conversation import Conversation, ConversationAssignment, Message
from app.schemas.conversation import (
    AssignConversationRequest,
    ConversationAssignmentResponse,
    ConversationDetailResponse,
    ConversationPageResponse,
    ConversationSummaryResponse,
    MessageResponse,
    UpdateConversationCategoryRequest,
    UpdateConversationStatusRequest,
)
from app.services.assignment_service import AssignmentService
from app.services.conversation_service import ConversationService
from app.services.message_service import MessageService


router = APIRouter()


def require_conversation_access(current_user=Depends(get_current_user)):
    return current_user


def serialize_conversation(
    conversation: Conversation,
    current_assignee_id: UUID | None = None,
) -> ConversationDetailResponse:
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
        status=conversation.status,
        category_id=conversation.category_id,
        last_message_at=conversation.last_message_at,
        external_created_at=conversation.external_created_at,
        created_at=conversation.created_at,
        updated_at=conversation.updated_at,
        current_assignee_id=current_assignee_id,
        messages=[serialize_message(message) for message in conversation.messages],
    )


def serialize_conversation_summary(conversation: Conversation) -> ConversationSummaryResponse:
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
        status=conversation.status,
        category_id=conversation.category_id,
        last_message_at=conversation.last_message_at,
        external_created_at=conversation.external_created_at,
        created_at=conversation.created_at,
        updated_at=conversation.updated_at,
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
    )


@router.get('', response_model=ConversationPageResponse)
def list_conversations(
    limit: int = Query(default=25, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    current_user=Depends(require_conversation_access),
) -> ConversationPageResponse:
    service = ConversationService(db)
    conversations = service.list_conversations(limit=limit, offset=offset)
    return ConversationPageResponse(
        items=[serialize_conversation_summary(conversation) for conversation in conversations],
        total=service.count_conversations(),
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
    return serialize_conversation(conversation, service.get_current_assignee_id(conversation.id))


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
