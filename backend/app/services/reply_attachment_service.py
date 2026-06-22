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
    'image/webp',
    'text/plain',
}


class ReplyAttachmentService:
    """Validate and persist local attachment files for outbound replies."""

    def __init__(self):
        self.settings = get_settings()
        self.upload_dir = self._upload_dir()

    async def save_uploads(self, *, uploads: list[UploadFile], message_id: UUID, account_id: UUID | None) -> list[MessageAttachment]:
        """Save uploaded files and return message attachment metadata rows."""
        attachments: list[MessageAttachment] = []
        self.upload_dir.mkdir(parents=True, exist_ok=True)
        for upload in uploads:
            if not upload.filename:
                continue
            mime_type = upload.content_type or 'application/octet-stream'
            if mime_type not in ALLOWED_REPLY_ATTACHMENT_TYPES:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f'Attachment type is not allowed: {mime_type}')
            content = await upload.read()
            if len(content) > self.settings.reply_attachment_max_bytes:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='Attachment exceeds the allowed file size')
            safe_name = Path(upload.filename).name[:500]
            stored_name = f'{uuid4()}-{safe_name}'
            storage_path = self.upload_dir / stored_name
            storage_path.write_bytes(content)
            attachments.append(
                MessageAttachment(
                    message_id=message_id,
                    account_id=account_id,
                    provider=EBAY_PROVIDER_NAME,
                    provider_attachment_id=f'local-{uuid4()}',
                    file_name=safe_name,
                    media_name=safe_name,
                    media_type=mime_type.split('/')[0],
                    mime_type=mime_type,
                    file_size=len(content),
                    storage_path=str(storage_path),
                    download_url=f'/api/v1/conversations/attachments/{stored_name}',
                    raw_payload={'delivery': 'local_only', 'ebay_attachment_supported': False},
                )
            )
        return attachments

    def resolve_download_path(self, stored_name: str) -> Path:
        """Return a stored attachment path when the requested file exists."""
        candidate = (self.upload_dir / Path(stored_name).name).resolve()
        if not str(candidate).startswith(str(self.upload_dir.resolve())) or not candidate.exists():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Attachment not found')
        return candidate

    def _upload_dir(self) -> Path:
        """Build an absolute upload directory from settings."""
        configured = Path(self.settings.reply_attachment_upload_dir)
        return configured if configured.is_absolute() else BACKEND_DIR / configured
