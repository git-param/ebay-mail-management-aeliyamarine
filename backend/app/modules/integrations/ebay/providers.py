from app.modules.integrations.interfaces import (
    ConversationProvider,
    MessageProvider,
    ProviderConversation,
    ProviderMessage,
)

from dataclasses import dataclass
from typing import Any

import requests

EBAY_PROVIDER_NAME = 'EBAY'


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


@dataclass
class EbayApiResponse:
    ok: bool
    status_code: int
    payload: Any
    headers: dict[str, str]


def upload_message_media(
    self,
    access_token: str,
    *,
    file_bytes: bytes,
    mime_type: str,
    media_name: str,
) -> EbayApiResponse:
    """
    Upload reply image to eBay Media API and return an object compatible with
    ReplyAttachmentService.upload_to_ebay().
    """

    # Production:
    media_base_url = getattr(
        self,
        "media_base_url",
        "https://apim.ebay.com/commerce/media/v1_beta",
    )

    # If your app is using sandbox, set this somewhere in your client:
    # self.media_base_url = "https://apim.sandbox.ebay.com/commerce/media/v1_beta"

    url = f"{media_base_url.rstrip('/')}/image/create_image_from_file"

    headers = {
        "Authorization": f"Bearer {access_token}",
        "Accept": "application/json",
    }

    files = {
        "image": (
            media_name,
            file_bytes,
            mime_type,
        )
    }

    try:
        response = requests.post(
            url,
            headers=headers,
            files=files,
            timeout=60,
        )

        try:
            payload = response.json()
        except ValueError:
            payload = {"raw": response.text}

        # eBay Media API commonly returns imageUrl.
        # Your ReplyAttachmentService expects mediaUrl, so normalize it.
        if isinstance(payload, dict):
            image_url = payload.get("maxDimensionImageUrl") or payload.get("imageUrl")
            if image_url:
                payload.setdefault("mediaUrl", image_url)

            location = response.headers.get("Location")
            if location:
                payload.setdefault("location", location)

        return EbayApiResponse(
            ok=response.ok,
            status_code=response.status_code,
            payload=payload,
            headers=dict(response.headers),
        )

    except requests.RequestException as exc:
        return EbayApiResponse(
            ok=False,
            status_code=0,
            payload={
                "errors": [
                    {
                        "message": str(exc),
                        "longMessage": f"eBay media upload request failed: {exc}",
                    }
                ]
            },
            headers={},
        )
