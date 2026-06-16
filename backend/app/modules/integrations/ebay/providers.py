from app.modules.integrations.interfaces import (
    ConversationProvider,
    MessageProvider,
    ProviderConversation,
    ProviderMessage,
)

EBAY_PROVIDER_NAME = 'ebay'


class EbayConversationProvider(ConversationProvider, MessageProvider):
    def __init__(self, account_id: str):
        self.account_id = account_id

    def list_conversations(self) -> list[ProviderConversation]:
        return []

    def get_conversation(self, provider_conversation_id: str) -> ProviderConversation | None:
        return None

    def list_messages(self, provider_conversation_id: str) -> list[ProviderMessage]:
        return []

    def send_message(self, provider_conversation_id: str, body: str) -> ProviderMessage:
        raise NotImplementedError('eBay message sending will be implemented with the sync integration')
