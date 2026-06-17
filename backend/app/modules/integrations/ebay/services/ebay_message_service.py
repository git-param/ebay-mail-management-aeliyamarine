from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.models.conversation import Conversation, ConversationStatus, MessageSenderType
from app.models.ebay_account import EbayAccount
from app.modules.integrations.ebay.providers import EBAY_PROVIDER_NAME
from app.repositories.conversation_repository import ConversationRepository
from app.repositories.message_repository import MessageRepository


class EbayMessageService:
    def __init__(self, db: Session):
        self.db = db
        self.conversation_repository = ConversationRepository(db)
        self.message_repository = MessageRepository(db)

    def upsert_conversation(
        self,
        *,
        account: EbayAccount,
        conversation_summary: dict,
        conversation_detail: dict,
        conversation_type: str,
    ) -> tuple[Conversation, bool]:
        conversation_id = self._required_string(
            conversation_summary.get('conversationId') or conversation_detail.get('conversationId'),
            'conversationId',
        )
        messages = self._messages_from_detail(conversation_detail)
        latest_message_at = self._latest_message_at(conversation_summary, messages)
        values = {
            'provider_account_id': account.id,
            'subject': self._conversation_subject(conversation_summary, conversation_detail, messages),
            'buyer_identifier': self._other_party_username(account, conversation_summary, messages),
            'provider_conversation_status': self._string_or_none(
                conversation_detail.get('conversationStatus') or conversation_summary.get('conversationStatus')
            ),
            'provider_conversation_type': self._string_or_none(
                conversation_detail.get('conversationType')
                or conversation_summary.get('conversationType')
                or conversation_type
            ),
            'reference_id': self._string_or_none(
                conversation_detail.get('referenceId') or conversation_summary.get('referenceId')
            ),
            'reference_type': self._string_or_none(
                conversation_detail.get('referenceType') or conversation_summary.get('referenceType')
            ),
            'unread_count': int(conversation_summary.get('unreadCount') or conversation_detail.get('unreadCount') or 0),
            'last_message_at': latest_message_at,
            'external_created_at': self._parse_ebay_datetime(
                conversation_detail.get('createdDate') or conversation_summary.get('createdDate')
            ),
            'raw_payload': {
                'summary': conversation_summary,
                'detail': conversation_detail,
            },
        }

        conversation, created = self.conversation_repository.upsert_by_provider_id(
            EBAY_PROVIDER_NAME,
            conversation_id,
            values,
        )
        if created:
            conversation.status = ConversationStatus.OPEN
        return conversation, created

    def upsert_messages(
        self,
        *,
        account: EbayAccount,
        conversation: Conversation,
        conversation_detail: dict,
    ) -> tuple[int, int]:
        created_count = 0
        updated_count = 0
        for message_payload in self._messages_from_detail(conversation_detail):
            message_id = self._string_or_none(message_payload.get('messageId'))
            if not message_id:
                continue

            sent_at = self._parse_ebay_datetime(message_payload.get('createdDate')) or datetime.now(UTC)
            sender_username = self._string_or_none(message_payload.get('senderUsername'))
            recipient_username = self._string_or_none(message_payload.get('recipientUsername'))
            is_inbound = sender_username != account.ebay_username
            values = {
                'conversation_id': conversation.id,
                'sender_type': MessageSenderType.CUSTOMER if is_inbound else MessageSenderType.AGENT,
                'sender_identifier': sender_username,
                'recipient_identifier': recipient_username,
                'body': self._string_or_none(message_payload.get('messageBody')) or '',
                'read_status': message_payload.get('readStatus') if isinstance(message_payload.get('readStatus'), bool) else None,
                'is_inbound': is_inbound,
                'sent_at': sent_at,
                'raw_payload': message_payload,
            }
            _, created = self.message_repository.upsert_by_provider_id(EBAY_PROVIDER_NAME, message_id, values)
            if created:
                created_count += 1
            else:
                updated_count += 1

        return created_count, updated_count

    def _messages_from_detail(self, conversation_detail: dict) -> list[dict]:
        messages = conversation_detail.get('messages')
        if isinstance(messages, list):
            return [message for message in messages if isinstance(message, dict)]
        return []

    def _latest_message_at(self, conversation_summary: dict, messages: list[dict]) -> datetime | None:
        latest_message = conversation_summary.get('latestMessage')
        latest_date = None
        if isinstance(latest_message, dict):
            latest_date = self._parse_ebay_datetime(latest_message.get('createdDate'))
        for message in messages:
            message_date = self._parse_ebay_datetime(message.get('createdDate'))
            if message_date and (not latest_date or message_date > latest_date):
                latest_date = message_date
        return latest_date

    def _other_party_username(self, account: EbayAccount, conversation_summary: dict, messages: list[dict]) -> str | None:
        for message in messages:
            sender_username = self._string_or_none(message.get('senderUsername'))
            recipient_username = self._string_or_none(message.get('recipientUsername'))
            if sender_username and sender_username != account.ebay_username:
                return sender_username
            if recipient_username and recipient_username != account.ebay_username:
                return recipient_username

        latest_message = conversation_summary.get('latestMessage')
        if isinstance(latest_message, dict):
            sender_username = self._string_or_none(latest_message.get('senderUsername'))
            recipient_username = self._string_or_none(latest_message.get('recipientUsername'))
            if sender_username and sender_username != account.ebay_username:
                return sender_username
            if recipient_username and recipient_username != account.ebay_username:
                return recipient_username
        return None

    def _required_string(self, value: object, field_name: str) -> str:
        normalized_value = self._string_or_none(value)
        if not normalized_value:
            raise ValueError(f'eBay conversation payload missing {field_name}')
        return normalized_value

    def _string_or_none(self, value: object) -> str | None:
        if isinstance(value, str) and value.strip():
            return value.strip()
        return None

    def _short_string_or_none(self, value: object, max_length: int = 500) -> str | None:
        normalized_value = self._string_or_none(value)
        if not normalized_value:
            return None
        return normalized_value[:max_length]

    def _conversation_subject(
        self,
        conversation_summary: dict,
        conversation_detail: dict,
        messages: list[dict],
        max_length: int = 500,
    ) -> str | None:
        title = self._string_or_none(
            conversation_detail.get('conversationTitle') or conversation_summary.get('conversationTitle')
        )
        if not title or len(title) > max_length:
            return None

        normalized_title = self._normalize_for_comparison(title)
        for message in messages:
            message_body = self._string_or_none(message.get('messageBody'))
            if message_body and normalized_title == self._normalize_for_comparison(message_body):
                return None

        return title

    def _parse_ebay_datetime(self, value: object) -> datetime | None:
        if not isinstance(value, str) or not value.strip():
            return None
        normalized_value = value.strip()
        if normalized_value.endswith('Z'):
            normalized_value = f'{normalized_value[:-1]}+00:00'
        try:
            parsed_value = datetime.fromisoformat(normalized_value)
        except ValueError:
            return None
        if parsed_value.tzinfo is None:
            return parsed_value.replace(tzinfo=UTC)
        return parsed_value

    def _normalize_for_comparison(self, value: str) -> str:
        return ' '.join(value.split())
