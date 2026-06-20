from datetime import UTC, datetime
from uuid import UUID, uuid4

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models.conversation import Message, MessageSenderType
from app.models.ebay_account import EbayAccount
from app.modules.integrations.ebay.oauth.token_service import EbayTokenService
from app.modules.integrations.ebay.providers import EBAY_PROVIDER_NAME
from app.services.audit_service import AuditService
from app.services.conversation_service import ConversationService
from app.services.reply_policy_service import ReplyPolicyService


class EbayReplyService:
    def __init__(self, db: Session):
        self.db = db
        self.token_service = EbayTokenService(db)
        self.reply_policy = ReplyPolicyService()

    def validate_reply(self, body: str) -> list[str]:
        return self.reply_policy.validate(body)

    def send_reply(self, *, conversation_id: UUID, body: str, actor_id: UUID) -> Message:
        violations = self.validate_reply(body)
        if violations:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=' '.join(violations))

        conversation = ConversationService(self.db).get_conversation(conversation_id)
        if conversation.provider != EBAY_PROVIDER_NAME:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='Only eBay conversations can be replied to from this action')
        if not conversation.provider_account_id:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='Conversation is missing an eBay account')

        account = self._get_account(conversation.provider_account_id)
        account = self._ensure_access_token(account)
        response = self.token_service.client.send_conversation_message(
            account.access_token,
            conversation_id=conversation.provider_conversation_id,
            message_body=body,
            conversation_type=conversation.provider_conversation_type or 'FROM_MEMBERS',
        )
        if not response.ok:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=self._reply_error_detail(response.payload),
            )

        provider_message_id = self._provider_message_id(response.payload) or f'local-reply-{uuid4()}'
        message = Message(
            conversation_id=conversation.id,
            provider=EBAY_PROVIDER_NAME,
            provider_message_id=provider_message_id,
            sender_type=MessageSenderType.AGENT,
            sender_identifier=account.ebay_username,
            recipient_identifier=conversation.buyer_identifier,
            body=body,
            read_status=True,
            is_inbound=False,
            sent_at=datetime.now(UTC),
            raw_payload=response.payload if isinstance(response.payload, dict) else {'response': response.payload},
        )
        self.db.add(message)
        conversation.last_message_at = message.sent_at
        AuditService(self.db).log(
            action='MESSAGE_REPLY_SENT',
            user_id=actor_id,
            entity_type='CONVERSATION',
            entity_id=conversation.id,
            category='MESSAGE_MANAGEMENT',
        )
        self.db.commit()
        self.db.refresh(message)
        return message

    def _get_account(self, account_id: UUID) -> EbayAccount:
        account = self.db.get(EbayAccount, account_id)
        if not account:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='eBay account not found')
        if not account.access_token and not account.refresh_token:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='eBay account is not connected')
        return account

    def _ensure_access_token(self, account: EbayAccount) -> EbayAccount:
        if not account.access_token or (
            account.access_token_expires_at and account.access_token_expires_at <= datetime.now(UTC)
        ):
            return self.token_service.refresh_access_token(account.id)
        return account

    def _provider_message_id(self, payload: object) -> str | None:
        if not isinstance(payload, dict):
            return None
        value = payload.get('messageId') or payload.get('id')
        return value.strip() if isinstance(value, str) and value.strip() else None

    def _reply_error_detail(self, payload: object) -> str:
        if not isinstance(payload, dict):
            return 'eBay reply request failed'

        errors = payload.get('errors')
        if isinstance(errors, list) and errors:
            first_error = errors[0]
            if isinstance(first_error, dict):
                message = first_error.get('longMessage') or first_error.get('message')
                if isinstance(message, str) and message.strip():
                    return f'eBay reply request failed: {message.strip()}'

        return 'eBay reply request failed'
