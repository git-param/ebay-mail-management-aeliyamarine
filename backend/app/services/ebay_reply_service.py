import logging
from datetime import UTC, datetime
from uuid import UUID, uuid4

from fastapi import HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from app.models.conversation import Message, MessageSenderType
from app.models.ebay_account import EbayAccount
from app.modules.integrations.ebay.oauth.token_service import EbayTokenService
from app.modules.integrations.ebay.providers import EBAY_PROVIDER_NAME
from app.services.audit_service import AuditService
from app.services.conversation_service import ConversationService
from app.services.reply_policy_service import ReplyPolicyService
from app.services.reply_attachment_service import ReplyAttachmentService


logger = logging.getLogger(__name__)


class EbayReplyService:
    """Coordinate eBay reply delivery and local reply persistence."""

    def __init__(self, db: Session):
        self.db = db
        self.token_service = EbayTokenService(db)
        self.reply_policy = ReplyPolicyService()
        self.attachment_service = ReplyAttachmentService()

    def validate_reply(self, body: str) -> list[str]:
        """Return eBay messaging policy violations for a reply body."""
        return self.reply_policy.validate(body)

    async def send_reply(
        self,
        *,
        conversation_id: UUID,
        body: str,
        actor_id: UUID,
        attachments: list[UploadFile] | None = None,
    ) -> Message:
        """Send an eBay reply and preserve local attachment metadata."""
        violations = self.validate_reply(body)
        if violations:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=' '.join(violations))
        clean_attachments = attachments or []
        self.attachment_service.validate_uploads(clean_attachments)

        conversation = ConversationService(self.db).get_conversation(conversation_id)
        if conversation.provider != EBAY_PROVIDER_NAME:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='Only eBay conversations can be replied to from this action')
        if not conversation.provider_account_id:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='Conversation is missing an eBay account')

        account = self._get_account(conversation.provider_account_id)
        account = self._ensure_access_token(account)
        message = Message(
            conversation_id=conversation.id,
            provider=EBAY_PROVIDER_NAME,
            provider_message_id=f'pending-reply-{uuid4()}',
            sender_type=MessageSenderType.AGENT,
            sender_identifier=account.ebay_username,
            recipient_identifier=conversation.buyer_identifier,
            body=body,
            read_status=True,
            is_inbound=False,
            sent_at=datetime.now(UTC),
            raw_payload={},
        )
        self.db.add(message)
        self.db.flush()

        saved_attachments = []
        if clean_attachments:
            logger.info('Saving %s outbound reply attachments conversation_id=%s', len(clean_attachments), conversation.id)
            saved_attachments = await self.attachment_service.save_uploads(
                uploads=clean_attachments,
                message_id=message.id,
                account_id=account.id,
            )
            for attachment in saved_attachments:
                message.attachments.append(attachment)
            self.db.flush()

        message_media = self.attachment_service.build_ebay_message_media(saved_attachments)
        if saved_attachments and message_media:
            logger.info('Sending eBay reply with messageMedia conversation_id=%s media_count=%s', conversation.id, len(message_media))
        elif saved_attachments:
            logger.warning('Skipping eBay messageMedia because no HTTPS public backend URL is configured')

        response = self.token_service.client.send_conversation_message(
            account.access_token,
            conversation_id=conversation.provider_conversation_id,
            message_body=body,
            conversation_type=conversation.provider_conversation_type or 'FROM_MEMBERS',
            message_media=message_media or None,
        )
        attachment_warning = None
        if saved_attachments and message_media and response.ok:
            logger.info('eBay messageMedia reply succeeded conversation_id=%s response=%s', conversation.id, response.payload)
            self.attachment_service.mark_delivery_result(attachments=saved_attachments, delivery='ebay_sent')
        if saved_attachments and message_media and not response.ok:
            logger.warning(
                'eBay messageMedia reply failed conversation_id=%s payload=%s response=%s',
                conversation.id,
                message_media,
                response.payload,
            )
            self.attachment_service.mark_delivery_result(
                attachments=saved_attachments,
                delivery='ebay_failed_text_retry_pending',
                ebay_error=response.payload,
            )
            response = self.token_service.client.send_conversation_message(
                account.access_token,
                conversation_id=conversation.provider_conversation_id,
                message_body=body,
                conversation_type=conversation.provider_conversation_type or 'FROM_MEMBERS',
            )
            attachment_warning = 'Reply sent, but eBay rejected attachment delivery. Attachments were saved locally.'
        if not response.ok:
            self.db.rollback()
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=self._reply_error_detail(response.payload),
            )

        provider_message_id = self._provider_message_id(response.payload) or f'local-reply-{uuid4()}'
        message.provider_message_id = provider_message_id
        message.raw_payload = self._message_raw_payload(response.payload, attachment_warning)
        if saved_attachments and not message_media:
            attachment_warning = 'Reply sent, but attachments were saved locally because no public HTTPS attachment URL is configured.'
            self.attachment_service.mark_delivery_result(attachments=saved_attachments, delivery='local_only_no_public_url')
            message.raw_payload = self._message_raw_payload(response.payload, attachment_warning)
        elif saved_attachments and attachment_warning:
            self.attachment_service.mark_delivery_result(
                attachments=saved_attachments,
                delivery='ebay_failed_text_sent',
                ebay_error=saved_attachments[0].raw_payload.get('ebay_error') if saved_attachments[0].raw_payload else None,
            )
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
        """Return a connected eBay account or raise an API-safe error."""
        account = self.db.get(EbayAccount, account_id)
        if not account:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='eBay account not found')
        if not account.access_token and not account.refresh_token:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='eBay account is not connected')
        return account

    def _ensure_access_token(self, account: EbayAccount) -> EbayAccount:
        """Refresh the account token when it is missing or expired."""
        if not account.access_token or (
            account.access_token_expires_at and account.access_token_expires_at <= datetime.now(UTC)
        ):
            return self.token_service.refresh_access_token(account.id)
        return account

    def _provider_message_id(self, payload: object) -> str | None:
        """Extract the eBay message ID from the send response payload."""
        if not isinstance(payload, dict):
            return None
        value = payload.get('messageId') or payload.get('id')
        return value.strip() if isinstance(value, str) and value.strip() else None

    def _reply_error_detail(self, payload: object) -> str:
        """Build a concise user-facing eBay reply failure message."""
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

    def _message_raw_payload(self, payload: object, attachment_warning: str | None) -> dict:
        """Store the eBay response with optional attachment delivery warning."""
        raw_payload = payload if isinstance(payload, dict) else {'response': payload}
        if attachment_warning:
            raw_payload = {**raw_payload, 'attachment_delivery_warning': attachment_warning}
        return raw_payload
