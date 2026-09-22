from uuid import UUID

import logging

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.orm import Session

from app.models.conversation import Message, MessageAttachment


logger = logging.getLogger(__name__)


class MessageRepository:
    def __init__(self, db: Session):
        self.db = db

    def list_by_conversation(self, conversation_id: UUID) -> list[Message]:
        statement = select(Message).where(Message.conversation_id == conversation_id).order_by(Message.sent_at.asc())
        return list(self.db.scalars(statement))

    def get_by_provider_id(self, provider: str, provider_message_id: str) -> Message | None:
        statement = (
            select(Message)
            .where(Message.provider == provider)
            .where(Message.provider_message_id == provider_message_id)
        )
        with self.db.no_autoflush:
            return self.db.scalar(statement)

    def add(self, message: Message) -> Message:
        self.db.add(message)
        return message

    def replace_attachments(self, message: Message, attachments: list[MessageAttachment]) -> None:
        """
        Replace a message's synced attachment set without violating provider uniqueness.

        eBay can expose the same media object through more than one attachment
        field in a message payload. Reuse existing rows and skip duplicate
        provider attachment IDs before assigning the final relationship list.
        """
        existing_by_provider_id = {
            attachment.provider_attachment_id: attachment
            for attachment in message.attachments
            if attachment.provider_attachment_id
        }
        if message.id:
            existing_by_provider_id.update(
                {
                    attachment.provider_attachment_id: attachment
                    for attachment in self.db.scalars(
                        select(MessageAttachment).where(
                            MessageAttachment.message_id == message.id,
                            MessageAttachment.provider_attachment_id.is_not(None),
                        )
                    )
                    if attachment.provider_attachment_id
                }
            )

        seen_provider_ids: set[str] = set()
        replacement_attachments: list[MessageAttachment] = []

        for attachment in attachments:
            provider_attachment_id = attachment.provider_attachment_id
            if provider_attachment_id and provider_attachment_id in seen_provider_ids:
                logger.warning(
                    'Skipping duplicate eBay attachment in sync batch: message_id=%s provider_attachment_id=%s file_name=%s',
                    message.id,
                    provider_attachment_id,
                    attachment.file_name,
                )
                continue
            if provider_attachment_id:
                seen_provider_ids.add(provider_attachment_id)

            existing_attachment = existing_by_provider_id.get(provider_attachment_id) if provider_attachment_id else None
            if existing_attachment:
                logger.warning(
                    'Reusing existing eBay attachment during sync: message_id=%s provider_attachment_id=%s file_name=%s',
                    message.id,
                    provider_attachment_id,
                    attachment.file_name,
                )
                self._copy_attachment_fields(existing_attachment, attachment)
                replacement_attachments.append(existing_attachment)
            else:
                replacement_attachments.append(attachment)

        message.attachments = replacement_attachments

    def _copy_attachment_fields(self, target: MessageAttachment, source: MessageAttachment) -> None:
        target.account_id = source.account_id
        target.provider = source.provider
        target.file_name = source.file_name
        target.media_name = source.media_name
        target.media_url = source.media_url
        target.media_type = source.media_type
        target.mime_type = source.mime_type
        target.file_size = source.file_size
        target.download_url = source.download_url
        target.raw_payload = source.raw_payload

    def upsert_by_provider_id(self, provider: str, provider_message_id: str, values: dict) -> tuple[Message, bool]:
        """
        Upsert a message by provider and provider_message_id.
        Returns (message, created).
        """
        # Normalize provider to uppercase
        provider = provider.upper()
        
        # Remove provider from values to avoid duplication
        values = values.copy()  # Don't modify the original dict
        if 'provider' in values:
            values.pop('provider')
        
        existing = self._get_by_provider_id_no_autoflush(provider, provider_message_id)
        
        if existing:
            self._update_message(existing, values)
            return existing, False

        if self.db.bind is not None and self.db.bind.dialect.name == 'postgresql':
            return self._upsert_postgresql(provider, provider_message_id, values)

        # Create new message
        message = Message(
            provider=provider,
            provider_message_id=provider_message_id,
            **values
        )
        self.db.add(message)
        self.db.flush()
        return message, True

    def _get_by_provider_id_no_autoflush(self, provider: str, provider_message_id: str) -> Message | None:
        with self.db.no_autoflush:
            return self.db.scalar(
                select(Message).where(
                    Message.provider == provider,
                    Message.provider_message_id == provider_message_id
                )
            )

    def _update_message(self, message: Message, values: dict) -> None:
        for key, value in values.items():
            if hasattr(message, key) and key not in ('id', 'provider', 'provider_message_id', 'created_at'):
                setattr(message, key, value)

    def _upsert_postgresql(self, provider: str, provider_message_id: str, values: dict) -> tuple[Message, bool]:
        insert_values = {
            'provider': provider,
            'provider_message_id': provider_message_id,
            **values,
        }
        insert_statement = (
            postgresql_insert(Message)
            .values(**insert_values)
            .on_conflict_do_nothing(
                index_elements=['provider', 'provider_message_id'],
            )
            .returning(Message.id)
        )

        inserted_id = self.db.scalar(insert_statement)
        if inserted_id is not None:
            message = self.db.get(Message, inserted_id)
            if message is None:
                raise RuntimeError('Inserted message could not be loaded')
            return message, True

        existing = self._get_by_provider_id_no_autoflush(provider, provider_message_id)
        if existing is None:
            raise RuntimeError('Message upsert conflict could not be reconciled')

        self._update_message(existing, values)
        return existing, False
