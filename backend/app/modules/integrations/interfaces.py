from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class ProviderConversation:
    provider: str
    provider_conversation_id: str
    provider_account_id: str | None
    subject: str | None
    buyer_identifier: str | None
    external_created_at: datetime | None
    last_message_at: datetime | None
    raw_payload: dict | None


@dataclass(frozen=True)
class ProviderMessage:
    provider: str
    provider_message_id: str
    provider_conversation_id: str
    sender_type: str
    sender_identifier: str | None
    body: str
    is_inbound: bool
    sent_at: datetime
    raw_payload: dict | None


class ConversationProvider(ABC):
    @abstractmethod
    def list_conversations(self) -> list[ProviderConversation]:
        raise NotImplementedError

    @abstractmethod
    def get_conversation(self, provider_conversation_id: str) -> ProviderConversation | None:
        raise NotImplementedError


class MessageProvider(ABC):
    @abstractmethod
    def list_messages(self, provider_conversation_id: str) -> list[ProviderMessage]:
        raise NotImplementedError

    @abstractmethod
    def send_message(self, provider_conversation_id: str, body: str) -> ProviderMessage:
        raise NotImplementedError
