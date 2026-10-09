"""Authenticated endpoints for composing the first message to an eBay buyer."""

from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, UploadFile
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user
from app.api.v1.routes.conversations import serialize_message
from app.constants.api import ConversationsRoutes
from app.db.session import get_db
from app.models.user import User
from app.schemas.conversation import MessageResponse, ReplyConversationRequest, ReplyValidationResponse
from app.services.new_buyer_conversation_service import NewBuyerConversationService
from app.services.reply_policy_service import ReplyPolicyService


router = APIRouter()


@router.post(ConversationsRoutes.START_VALIDATE, response_model=ReplyValidationResponse)
def validate_first_message(
    payload: ReplyConversationRequest,
    current_user: User = Depends(get_current_user),
) -> ReplyValidationResponse:
    violations = ReplyPolicyService().validate(payload.body)
    return ReplyValidationResponse(valid=not violations, violations=violations)


@router.post(ConversationsRoutes.START, response_model=MessageResponse)
async def start_buyer_conversation(
    account_id: UUID = Form(...),
    buyer_username: str = Form(..., min_length=1, max_length=255),
    body: str = Form(..., min_length=1, max_length=2000),
    message_type_id: UUID = Form(...),
    send_copy_to_email: bool = Form(default=True),
    attachments: list[UploadFile] | None = File(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> MessageResponse:
    message = await NewBuyerConversationService(db).send_first_message(
        account_id=account_id,
        buyer_username=buyer_username,
        body=body,
        actor_id=current_user.id,
        message_type_id=message_type_id,
        send_copy_to_email=send_copy_to_email,
        attachments=attachments,
    )
    return serialize_message(message)
