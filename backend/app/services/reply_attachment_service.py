import logging
from pathlib import Path
from uuid import UUID, uuid4

from fastapi import HTTPException, UploadFile, status

from app.core.config import BACKEND_DIR, get_settings
from app.models.conversation import MessageAttachment
from app.modules.integrations.ebay.providers import EBAY_PROVIDER_NAME


ALLOWED_REPLY_ATTACHMENT_TYPES = {
    'application/pdf',
    'image/jpeg',
    'image/png',
    'text/plain',
}
MAX_REPLY_ATTACHMENT_COUNT = 5
EBAY_MEDIA_TYPE_BY_MIME_TYPE = {
    'application/pdf': 'DOC',
    'image/jpeg': 'IMAGE',
    'image/png': 'IMAGE',
    'text/plain': 'TXT',
}

logger = logging.getLogger(__name__)


class ReplyAttachmentService:
    """Validate and persist local attachment files for outbound replies."""

    def __init__(self):
        self.settings = get_settings()
        self.upload_dir = self._upload_dir()

    def validate_uploads(self, uploads: list[UploadFile]) -> None:
        """Validate reply attachment limits before storing or sending files."""
        real_uploads = [upload for upload in uploads if upload.filename]
        if len(real_uploads) > MAX_REPLY_ATTACHMENT_COUNT:
            logger.warning('Reply attachment validation failed count=%s', len(real_uploads))
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f'eBay allows a maximum of {MAX_REPLY_ATTACHMENT_COUNT} attachments per reply',
            )
        for upload in real_uploads:
            mime_type = upload.content_type or 'application/octet-stream'
            if mime_type not in ALLOWED_REPLY_ATTACHMENT_TYPES:
                logger.warning('Reply attachment validation failed filename=%s mime_type=%s', upload.filename, mime_type)
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f'Attachment type is not allowed for eBay replies: {mime_type}',
                )

    async def save_uploads(self, *, uploads: list[UploadFile], message_id: UUID, account_id: UUID | None) -> list[MessageAttachment]:
        """Save uploaded files and return message attachment metadata rows."""
        self.validate_uploads(uploads)
        attachments: list[MessageAttachment] = []
        self.upload_dir.mkdir(parents=True, exist_ok=True)
        for upload in uploads:
            if not upload.filename:
                continue
            mime_type = upload.content_type or 'application/octet-stream'
            content = await upload.read()
            if len(content) > self.settings.reply_attachment_max_bytes:
                logger.warning('Reply attachment size validation failed filename=%s size=%s', upload.filename, len(content))
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='Attachment exceeds the allowed file size')
            safe_name = Path(upload.filename).name[:500]
            stored_name = f'{uuid4()}-{safe_name}'
            storage_path = self.upload_dir / stored_name
            storage_path.write_bytes(content)
            logger.info('Stored reply attachment filename=%s path=%s size=%s', safe_name, storage_path, len(content))
            attachments.append(
                MessageAttachment(
                    message_id=message_id,
                    account_id=account_id,
                    provider=EBAY_PROVIDER_NAME,
                    provider_attachment_id=f'local-{uuid4()}',
                    file_name=safe_name,
                    media_name=safe_name,
                    media_type=EBAY_MEDIA_TYPE_BY_MIME_TYPE[mime_type],
                    mime_type=mime_type,
                    file_size=len(content),
                    storage_path=str(storage_path),
                    download_url=f'/api/v1/conversations/attachments/{stored_name}',
                    raw_payload={'delivery': 'local_saved', 'ebay_attachment_supported': True},
                )
            )
        return attachments

    def public_download_url(self, attachment: MessageAttachment) -> str | None:
        """Build an HTTPS URL that eBay can fetch for an attachment."""
        base_url = self.settings.reply_attachment_public_base_url
        if not base_url or not base_url.startswith('https://'):
            logger.warning('Cannot build eBay attachment URL because PUBLIC_BACKEND_URL is not HTTPS')
            return None
        media_url = f'{base_url}/api/v1/conversations/public/attachments/{attachment.id}/download'
        logger.info('Generated eBay attachment URL attachment_id=%s media_url=%s', attachment.id, media_url)
        return media_url

    def build_ebay_message_media(self, attachments: list[MessageAttachment]) -> list[dict]:
        """Convert stored local attachments into eBay MessageMedia payloads."""
        message_media = []
        for attachment in attachments:
            media_url = self.public_download_url(attachment)
            if not media_url:
                return []
            attachment.media_url = media_url
            message_media.append(
                {
                    'mediaName': attachment.media_name or attachment.file_name,
                    'mediaType': attachment.media_type,
                    'mediaUrl': media_url,
                }
            )
        return message_media

    def mark_delivery_result(
        self,
        *,
        attachments: list[MessageAttachment],
        delivery: str,
        ebay_error: object | None = None,
    ) -> None:
        """Store eBay attachment delivery status on local metadata."""
        for attachment in attachments:
            attachment.raw_payload = {
                **(attachment.raw_payload or {}),
                'delivery': delivery,
                'ebay_error': ebay_error,
            }

    def resolve_download_path(self, stored_name: str) -> Path:
        """Return a stored attachment path when the requested file exists."""
        candidate = (self.upload_dir / Path(stored_name).name).resolve()
        if not str(candidate).startswith(str(self.upload_dir.resolve())) or not candidate.exists():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Attachment not found')
        return candidate

    def resolve_storage_path(self, storage_path: str) -> Path:
        """Return a stored attachment path from database metadata."""
        candidate = Path(storage_path).resolve()
        if not str(candidate).startswith(str(self.upload_dir.resolve())) or not candidate.exists():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Attachment not found')
        return candidate

    def _upload_dir(self) -> Path:
        """Build an absolute upload directory from settings."""
        configured = Path(self.settings.reply_attachment_upload_dir)
        return configured if configured.is_absolute() else BACKEND_DIR / configured
