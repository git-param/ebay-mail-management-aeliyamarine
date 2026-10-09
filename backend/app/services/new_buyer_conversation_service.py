"""Start buyer conversations from a username and a connected seller account."""

from uuid import UUID, uuid4

from fastapi import HTTPException, UploadFile
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.conversation import Conversation, ConversationStatus, Message
from app.models.ebay_account import EbayAccount, EbayConnectionStatus
from app.services.ebay_reply_service import EbayReplyService


class NewBuyerConversationService:
    def __init__(self, db: Session):
        self.db = db

    async def send_first_message(
        self,
        *,
        account_id: UUID,
        buyer_username: str,
        body: str,
        actor_id: UUID,
        message_type_id: UUID,
        send_copy_to_email: bool = True,
        attachments: list[UploadFile] | None = None,
    ) -> Message:
        username = buyer_username.strip()
        body = body.strip()
        if not body or len(body) > 2000:
            raise HTTPException(status_code=422, detail='Enter a message between 1 and 2000 characters.')
        if not username or len(username) > 255 or any(character.isspace() for character in username):
            raise HTTPException(status_code=422, detail='Enter a valid eBay username without spaces.')
        account = self.db.get(EbayAccount, account_id)
        if not account:
            raise HTTPException(status_code=404, detail='eBay account not found.')
        if not account.is_active or account.connection_status != EbayConnectionStatus.CONNECTED:
            raise HTTPException(status_code=400, detail='Select an active, connected eBay account.')
        if username.casefold() == account.ebay_username.strip().casefold():
            raise HTTPException(status_code=422, detail='The buyer username must differ from the sending account.')

        # Reuse an open member thread for this account; a local buyer record is optional.
        conversation = self.db.scalar(
            select(Conversation)
            .where(
                Conversation.provider == 'EBAY',
                Conversation.provider_account_id == account.id,
                func.lower(Conversation.buyer_identifier) == username.lower(),
                Conversation.provider_conversation_type == 'FROM_MEMBERS',
                Conversation.status != ConversationStatus.CLOSED,
            )
            .order_by(Conversation.last_message_at.desc().nullslast())
            .limit(1)
        )
        reply_service = EbayReplyService(self.db)
        try:
            # Refresh tokens before creating the transient thread: token refresh may commit.
            account = reply_service.prepare_sending_account(account.id)
            if conversation is None:
                conversation = Conversation(
                    provider='EBAY',
                    provider_conversation_id=f'new-buyer-{uuid4()}',
                    provider_account_id=account.id,
                    buyer_identifier=username,
                    subject=f'Message to {username}',
                    provider_conversation_type='FROM_MEMBERS',
                    status=ConversationStatus.OPEN,
                    raw_payload={'locally_initiated': True},
                )
                self.db.add(conversation)
                self.db.flush()
            return await reply_service.send_reply(
                conversation_id=conversation.id,
                body=body,
                actor_id=actor_id,
                message_type_id=message_type_id,
                send_copy_to_email=send_copy_to_email,
                attachments=attachments,
            )
        except Exception:
            self.db.rollback()
            raise
