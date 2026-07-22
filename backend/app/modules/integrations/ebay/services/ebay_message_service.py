import re
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.models.conversation import Conversation, ConversationStatus, MessageAttachment, MessageSenderType
from app.models.ebay_account import EbayAccount
from app.modules.integrations.ebay.providers import EBAY_PROVIDER_NAME
from app.repositories.conversation_repository import ConversationRepository
from app.repositories.message_repository import MessageRepository
from app.services.categorization_service import CategorizationService
from app.services.category_assignment_service import CategoryAssignmentService
from app.services.notification_service import NotificationService
from app.services.sla_service import SLAService


class EbayMessageService:
    EBAY_IMAGE_URL_PATTERN = re.compile(
        r'^https://i\.ebayimg\.com/00/s/[^/]+/z/(?P<image_id>[^/]+)/\$_1\.[^/?#]+(?:[?#].*)?$',
        re.IGNORECASE,
    )

    def __init__(self, db: Session):
        self.db = db
        self.conversation_repository = ConversationRepository(db)
        self.message_repository = MessageRepository(db)
        # Ensure we always use uppercase provider
        self.provider = EBAY_PROVIDER_NAME.upper()  # 'EBAY'

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
            'provider': self.provider,  # 'EBAY'
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
            self.provider,  # 'EBAY'
            conversation_id,
            values,
        )
        if created:
            conversation.status = ConversationStatus.OPEN
        category_id = CategorizationService(self.db).classify_text(
            ' '.join(
                [
                    values.get('subject') or '',
                    values.get('buyer_identifier') or '',
                    values.get('reference_id') or '',
                    *(self._string_or_none(message.get('messageBody')) or '' for message in messages),
                ]
            )
        )
        if category_id and not conversation.category_manually_selected:
            conversation.category_id = category_id
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
        
        # Determine if this is a FROM_EBAY conversation
        is_from_ebay = self._is_from_ebay_conversation(conversation)

        for message_payload in self._messages_from_detail(conversation_detail):
            message_id = self._string_or_none(message_payload.get('messageId'))
            if not message_id:
                continue

            sent_at = self._parse_ebay_datetime(message_payload.get('createdDate')) or datetime.now(UTC)
            sender_username = self._string_or_none(message_payload.get('senderUsername'))
            recipient_username = self._string_or_none(message_payload.get('recipientUsername'))

            seller_username = (account.ebay_username or '').strip().lower()
            sender_normalized = (sender_username or '').strip().lower()

            is_provider_message = is_from_ebay or sender_normalized == 'ebay'
            is_inbound = bool(sender_username and sender_normalized != seller_username)

            if is_provider_message:
                sender_type = MessageSenderType.PROVIDER
                is_inbound = False
            elif is_inbound:
                sender_type = MessageSenderType.CUSTOMER
            else:
                sender_type = MessageSenderType.AGENT

            values = {
                'conversation_id': conversation.id,
                'provider': self.provider,
                'sender_type': sender_type,
                'sender_identifier': sender_username,
                'recipient_identifier': recipient_username,
                'body': self._string_or_none(message_payload.get('messageBody')) or '',
                'read_status': message_payload.get('readStatus') if isinstance(message_payload.get('readStatus'), bool) else None,
                'is_inbound': is_inbound,
                'sent_at': sent_at,
                'raw_payload': message_payload,

                # Important:
                # Do not extract or persist offer data during sync.
                # Offer cards must be generated by backend detail resolver later.
                'offer_data': None,
            }
            message, created = self.message_repository.upsert_by_provider_id(
                self.provider,  # 'EBAY'
                message_id, 
                values
            )
            self.message_repository.replace_attachments(
                message,
                self._attachments_from_message_payload(account, message_payload),
            )
            if created:
                created_count += 1
                if is_inbound:
                    SLAService(self.db).start_cycle(conversation, sent_at)
                if is_inbound and conversation.category_id:
                    self._notify_category_owners(conversation, message.id)
            else:
                updated_count += 1

        return created_count, updated_count

    def _is_from_ebay_conversation(self, conversation: Conversation) -> bool:
        return (conversation.provider_conversation_type or '').upper() == 'FROM_EBAY'

    def _messages_from_detail(self, conversation_detail: dict) -> list[dict]:
        messages = conversation_detail.get('messages')
        if isinstance(messages, list):
            return [message for message in messages if isinstance(message, dict)]
        return []

    def _attachments_from_message_payload(self, account: EbayAccount, message_payload: dict) -> list[MessageAttachment]:
        attachment_payloads = []
        for key in ('messageMedia', 'MessageMedia', 'attachments', 'messageAttachments', 'documents', 'files'):
            value = message_payload.get(key)
            if isinstance(value, list):
                attachment_payloads.extend(item for item in value if isinstance(item, dict))
            elif isinstance(value, dict):
                attachment_payloads.append(value)

        attachments = []
        for index, payload in enumerate(attachment_payloads, start=1):
            provider_attachment_id = self._string_or_none(
                payload.get('attachmentId')
                or payload.get('documentId')
                or payload.get('fileId')
                or payload.get('id')
                or payload.get('mediaName')
                or payload.get('MediaName')
            )
            file_name = self._string_or_none(
                payload.get('fileName')
                or payload.get('name')
                or payload.get('documentName')
                or payload.get('title')
                or payload.get('mediaName')
                or payload.get('MediaName')
            ) or f'Attachment {index}'
            media_url = self._string_or_none(
                payload.get('mediaUrl')
                or payload.get('MediaURL')
                or payload.get('downloadUrl')
                or payload.get('url')
                or payload.get('href')
            )
            display_media_url = self._clear_ebay_image_url(media_url) if media_url else None
            media_type = self._string_or_none(payload.get('mediaType') or payload.get('MediaType'))
            file_size = payload.get('fileSize') or payload.get('size') or payload.get('contentLength')
            try:
                normalized_file_size = int(file_size) if file_size is not None else None
            except (TypeError, ValueError):
                normalized_file_size = None
            attachments.append(
                MessageAttachment(
                    account_id=account.id,
                    provider=self.provider,  # 'EBAY'
                    provider_attachment_id=provider_attachment_id,
                    file_name=file_name[:500],
                    media_name=file_name[:500],
                    media_url=display_media_url,
                    media_type=media_type,
                    mime_type=self._string_or_none(payload.get('mimeType') or payload.get('contentType')),
                    file_size=normalized_file_size,
                    download_url=media_url,
                    raw_payload=payload,
                )
            )
        return attachments

    def _clear_ebay_image_url(self, media_url: str) -> str:
        match = self.EBAY_IMAGE_URL_PATTERN.match(media_url)
        if not match:
            return media_url
        return f'https://i.ebayimg.com/images/g/{match.group("image_id")}/s-l1600.jpg'

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

    def _notify_category_owners(self, conversation: Conversation, message_id) -> None:
        users = CategoryAssignmentService(self.db).users_for_category(conversation.category_id)
        notification_service = NotificationService(self.db)
        for user in users:
            notification_service.create(
                user_id=user.id,
                title='New incoming message',
                body=f'New message in {conversation.subject or conversation.provider_conversation_id}.',
                event_type='NEW_INCOMING_MESSAGE',
                event_key=f'new-message:{message_id}:{user.id}',
                resource_type='CONVERSATION',
                resource_id=conversation.id,
            )
