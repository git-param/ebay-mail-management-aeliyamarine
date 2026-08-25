"""
ebay_reply_service.py
---------------------
Coordinates eBay reply delivery and local reply persistence.

Attachment flow (revised):
  1.  Validate and store all attachments locally for helpdesk history.
  2.  Upload each attachment directly to eBay's media API to obtain
      eBay-hosted URLs (``mediaUrl`` returned by eBay).
  3.  Embed eBay-hosted URLs in the outbound MessageMedia payload.
  4.  Send the reply message to eBay.
  5.  On any failure (upload or send), roll back the database transaction
      and return a clear error — no text-only fallback is attempted.

The PUBLIC_BACKEND_URL / ngrok-based public-URL approach has been removed.
"""

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
from app.models.message_type import MessageType
from app.repositories.message_type_repository import MessageClassificationRepository
from app.services.conversation_service import ConversationService
from app.services.reply_policy_service import ReplyPolicyService
from app.services.reply_attachment_service import ReplyAttachmentService
from app.services.sla_service import SLAService


logger = logging.getLogger(__name__)


class EbayReplyService:
    """
    Coordinate eBay reply delivery and local message/attachment persistence.

    This service is the single entry-point for sending agent replies to eBay
    conversations.  It handles:

    - Reply body policy validation.
    - Attachment validation, local storage, and eBay upload.
    - eBay message-send API calls.
    - Audit logging.
    - Database transaction management (commit on success, rollback on error).
    """

    def __init__(self, db: Session) -> None:
        self.db = db
        self.token_service = EbayTokenService(db)
        self.reply_policy = ReplyPolicyService()
        self.attachment_service = ReplyAttachmentService()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def validate_reply(self, body: str) -> list[str]:
        """
        Return a list of eBay messaging policy violations for a reply body.

        An empty list means the body is valid.

        Args:
            body: The proposed reply text.

        Returns:
            A list of human-readable violation strings.
        """
        return self.reply_policy.validate(body)

    async def send_reply(
        self,
        *,
        conversation_id: UUID,
        body: str,
        actor_id: UUID,
        message_type_id: UUID,
        send_copy_to_email: bool = True,
        attachments: list[UploadFile] | None = None,
    ) -> Message:
        """
        Send an eBay reply, optionally with image attachments.

        Transaction behaviour:
          - No attachments → send message; commit on success.
          - Attachments present, all eBay uploads succeed → send message; commit.
          - Attachments present, any eBay upload fails → rollback; raise 502.
          - Message send fails → rollback; raise 502.

        No text-only fallback is used when attachment upload fails.

        Args:
            conversation_id: UUID of the helpdesk Conversation to reply to.
            body:            Reply text (validated against eBay policy).
            actor_id:        UUID of the user sending the reply (for audit log).
            attachments:     Optional list of UploadFile objects from the request.

        Returns:
            The persisted Message ORM instance with updated provider_message_id.

        Raises:
            HTTPException 400: Policy violation, unsupported attachment type,
                               missing eBay account, or wrong provider.
            HTTPException 404: Conversation or eBay account not found.
            HTTPException 502: eBay upload or message-send failure.
        """
        # --- 1. Validate reply body policy ---
        selected_type = self.db.get(MessageType, message_type_id)
        if not selected_type or selected_type.is_deleted or not selected_type.is_active:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail='Select an active message type')
        if any(child.is_active and not child.is_deleted for child in selected_type.children):
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail='Select a message subtype')
        violations = self.validate_reply(body)
        if violations:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=' '.join(violations),
            )

        clean_attachments = [upload for upload in (attachments or []) if upload.filename]
        send_copy_to_email = bool(send_copy_to_email)

        # --- 2. Validate attachment types/count before any I/O ---
        if clean_attachments:
            self.attachment_service.validate_uploads(clean_attachments)

        # --- 3. Load and validate the conversation ---
        conversation = ConversationService(self.db).get_conversation(conversation_id)

        if conversation.status.value == 'CLOSED':
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail='Closed conversations are read-only')

        if conversation.provider != EBAY_PROVIDER_NAME:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail='Only eBay conversations can be replied to from this action',
            )
        if (conversation.provider_conversation_type or '').upper() == 'FROM_EBAY':
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail='eBay system conversations cannot be replied to.',
            )
        if not conversation.provider_account_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail='Conversation is missing an eBay account',
            )

        # --- 4. Ensure the eBay account has a valid access token ---
        account = self._get_account(conversation.provider_account_id)
        account = self._ensure_access_token(account)

        # --- 5. Create a pending Message row ---
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
            raw_payload={'actor_id': str(actor_id), 'email_copy_requested': send_copy_to_email},
        )
        self.db.add(message)
        self.db.flush()

        # --- 6. Store attachments locally and upload to eBay ---
        saved_attachments: list = []
        message_media: list[dict] = []

        if clean_attachments:
            logger.warning(
                'Saving %s outbound reply attachments locally: conversation_id=%s',
                len(clean_attachments),
                conversation.id,
            )
            saved_attachments = await self.attachment_service.save_uploads(
                uploads=clean_attachments,
                message_id=message.id,
                account_id=account.id,
            )
            for attachment in saved_attachments:
                message.attachments.append(attachment)
            self.db.flush()

            # Upload each file to eBay — any failure aborts the entire reply.
            logger.warning(
                'Uploading %s attachments to eBay: conversation_id=%s',
                len(saved_attachments),
                conversation.id,
            )
            try:
                message_media = await self.attachment_service.upload_to_ebay(
                    attachments=saved_attachments,
                    access_token=account.access_token,
                    ebay_client=self.token_service.client,
                )
            except HTTPException:
                # Roll back the pending message and locally saved metadata.
                self.db.rollback()
                raise

            logger.warning(
                'All eBay uploads successful: conversation_id=%s media_count=%s',
                conversation.id,
                len(message_media),
            )

        # --- 7. Send the reply message to eBay ---
        logger.warning(
            'Sending eBay reply: conversation_id=%s account_id=%s has_media=%s email_copy_requested=%s',
            conversation.id,
            account.id,
            bool(message_media),
            send_copy_to_email,
        )

        send_context = self._send_context(conversation)
        if send_context['transport'] == 'trading':
            response = self.token_service.client.send_trading_member_message(
                account.access_token,
                call_name=send_context['call_name'],
                item_id=send_context['item_id'],
                recipient_id=send_context['recipient_id'],
                body=body,
                subject=send_context.get('subject'),
                parent_message_id=send_context.get('parent_message_id'),
                email_copy_to_sender=send_copy_to_email,
                correlation_id=str(message.id),
                message_media=message_media or None,
            )
        else:
            response = self.token_service.client.send_conversation_message(
                account.access_token,
                conversation_id=send_context['conversation_id'],
                conversation_type=send_context['conversation_type'],
                message_body=body,
                message_media=message_media or None,
                email_copy_to_sender=send_copy_to_email,
            )

        logger.warning(
            'eBay reply send response: conversation_id=%s account_id=%s call_name=%s ok=%s email_copy_requested=%s payload=%s',
            conversation.id,
            account.id,
            send_context['call_name'],
            response.ok,
            send_copy_to_email,
            response.payload,
        )

        if not response.ok:
            self.db.rollback()
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=self._reply_error_detail(response.payload),
            )

        # --- 8. Record final delivery outcome on attachment rows ---
        if saved_attachments:
            self.attachment_service.mark_delivery_result(
                attachments=saved_attachments,
                delivery='ebay_sent',
            )
            self.attachment_service.delete_local_files(
                attachments=saved_attachments,
            )

        # --- 9. Finalise the message row with the real eBay message ID ---
        provider_message_id = self._provider_message_id(response.payload) or f'local-reply-{uuid4()}'
        message.provider_message_id = provider_message_id
        message.raw_payload = {
            **(response.payload if isinstance(response.payload, dict) else {'response': response.payload}),
            'actor_id': str(actor_id),
            'email_copy_requested': send_copy_to_email,
            'ebay_call_name': send_context['call_name'],
        }

        conversation.last_message_at = message.sent_at
        SLAService(self.db).complete_after_reply(conversation, actor_id, message.sent_at)

        MessageClassificationRepository(self.db).create(
            conversation_id=conversation.id,
            conversation_message_id=message.id,
            seller_account_id=conversation.provider_account_id,
            user_id=actor_id,
            message_type_id=selected_type.id,
        )

        # --- 10. Audit log and commit ---
        AuditService(self.db).log(
            action='MESSAGE_REPLY_SENT',
            user_id=actor_id,
            entity_type='CONVERSATION',
            entity_id=conversation.id,
            category='MESSAGE_MANAGEMENT',
            metadata={
                'message_id': str(message.id),
                'ebay_account_id': str(account.id),
                'ebay_call_name': send_context['call_name'],
                'email_copy_requested': send_copy_to_email,
            },
        )
        AuditService(self.db).log(
            action='REPLY_CATEGORIZED', user_id=actor_id, entity_type='MESSAGE', entity_id=message.id,
            category='MESSAGE_MANAGEMENT', metadata={'message_type_id': str(selected_type.id)},
        )
        self.db.commit()
        self.db.refresh(message)
        return message

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _get_account(self, account_id: UUID) -> EbayAccount:
        """
        Return a connected eBay account or raise an API-safe 404/400 error.

        Args:
            account_id: UUID of the EbayAccount to look up.

        Raises:
            HTTPException 404: Account not found in the database.
            HTTPException 400: Account exists but has no stored tokens.
        """
        account = self.db.get(EbayAccount, account_id)
        if not account:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail='eBay account not found',
            )
        if not account.access_token and not account.refresh_token:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail='eBay account is not connected',
            )
        return account

    def _ensure_access_token(self, account: EbayAccount) -> EbayAccount:
        """
        Refresh the account access token when it is missing or has expired.

        Args:
            account: The EbayAccount to check and potentially refresh.

        Returns:
            The same or a refreshed EbayAccount instance.
        """
        if not account.access_token or (
            account.access_token_expires_at
            and account.access_token_expires_at <= datetime.now(UTC)
        ):
            return self.token_service.refresh_access_token(account.id)
        return account

    def _provider_message_id(self, payload: object) -> str | None:
        """
        Extract the eBay message ID from a successful send-message response.

        Args:
            payload: The deserialized eBay API response body.

        Returns:
            A non-empty message ID string, or ``None`` when not found.
        """
        if not isinstance(payload, dict):
            return None
        value = payload.get('messageId') or payload.get('id')
        return value.strip() if isinstance(value, str) and value.strip() else None

    def _send_context(self, conversation) -> dict:
        recipient_id = (conversation.buyer_identifier or '').strip()
        if not recipient_id:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='Cannot send reply because the buyer username is unavailable.')

        order_mapping = getattr(conversation, 'order_mapping', None)
        if order_mapping and (order_mapping.ebay_item_id or order_mapping.listing_id or conversation.reference_id):
            return {
                'transport': 'trading',
                'call_name': 'AddMemberMessageAAQToPartner',
                'item_id': order_mapping.ebay_item_id or order_mapping.listing_id or conversation.reference_id,
                'recipient_id': recipient_id,
                'subject': conversation.subject or 'Message from seller',
            }
        linked_order = getattr(conversation, 'linked_order', None)
        linked_line_item = next(iter(getattr(linked_order, 'line_items', []) or []), None) if linked_order else None
        linked_item_id = getattr(linked_line_item, 'item_id', None) or getattr(linked_line_item, 'listing_id', None)
        if linked_item_id:
            return {
                'transport': 'trading',
                'call_name': 'AddMemberMessageAAQToPartner',
                'item_id': linked_item_id,
                'recipient_id': recipient_id,
                'subject': conversation.subject or 'Message from seller',
            }

        item_id = conversation.reference_id if (conversation.reference_type or '').upper() == 'LISTING' else None
        parent_message = next((message for message in sorted(conversation.messages, key=lambda row: row.sent_at, reverse=True) if message.is_inbound and message.provider_message_id), None)
        if item_id and parent_message:
            return {
                'transport': 'trading',
                'call_name': 'AddMemberMessageRTQ',
                'item_id': item_id,
                'recipient_id': recipient_id,
                'parent_message_id': parent_message.provider_message_id,
            }

        provider_conversation_id = (conversation.provider_conversation_id or '').strip()
        if provider_conversation_id:
            return {
                'transport': 'conversation',
                'call_name': 'send_conversation_message',
                'conversation_id': provider_conversation_id,
                'conversation_type': conversation.provider_conversation_type or 'FROM_MEMBERS',
            }

        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='Cannot send reply because the eBay conversation id is unavailable.')

    def _reply_error_detail(self, payload: object) -> str:
        """
        Build a concise user-facing message for an eBay reply-send failure.

        Args:
            payload: The deserialized eBay error response body.

        Returns:
            A plain-English error string for the HTTP 502 detail field.
        """
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
