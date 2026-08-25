"""
reply_attachment_service.py
---------------------------
Validates and persists outbound reply attachments locally, then uploads them
directly to eBay's media-upload API so that eBay-hosted URLs can be embedded
in outbound MessageMedia payloads.

Public-URL / PUBLIC_BACKEND_URL approach has been removed.  eBay now receives
its own hosted URL instead of an application-generated download link.

Supported attachment types (images only, per eBay verification requirements):
  - image/jpeg
  - image/png

Rejected types (rejected immediately, no fallback):
  - application/pdf, text/plain, image/webp, and all other MIME types
"""

import logging
from pathlib import Path
from uuid import UUID, uuid4

from fastapi import HTTPException, UploadFile, status

from app.core.config import BACKEND_DIR, get_settings
from app.models.conversation import MessageAttachment
from app.modules.integrations.ebay.providers import EBAY_PROVIDER_NAME


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

ALLOWED_REPLY_ATTACHMENT_TYPES: set[str] = {
    'image/jpeg',
    'image/png',
}
"""Only JPEG and PNG are accepted until additional formats are verified with eBay."""

MAX_REPLY_ATTACHMENT_COUNT: int = 5
"""eBay messaging API maximum attachments per reply."""

EBAY_MEDIA_TYPE_BY_MIME_TYPE: dict[str, str] = {
    'image/jpeg': 'IMAGE',
    'image/png': 'IMAGE',
}
"""Maps local MIME types to the eBay MessageMedia.mediaType enum value."""

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------


class ReplyAttachmentService:
    """
    Validate, store locally, and upload outbound reply attachments to eBay.

    Responsibilities:
      1. Validate upload count and MIME type before any I/O.
      2. Write the raw file bytes to local storage for helpdesk history.
      3. Upload each attachment directly to eBay's media API.
      4. Return eBay-hosted URLs to be embedded in MessageMedia payloads.
      5. Record delivery outcomes on the local MessageAttachment rows.

    All public methods that communicate with eBay require an ``access_token``
    argument so the service remains stateless with respect to authentication.
    """

    def __init__(self) -> None:
        self.settings = get_settings()
        self.upload_dir = self._upload_dir()

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    def validate_uploads(self, uploads: list[UploadFile]) -> None:
        """
        Raise HTTP 400 when uploads violate count or MIME-type constraints.

        Only real uploads (those with a filename) count toward limits.
        PDF, TXT, WEBP, and all non-image types are rejected immediately;
        no text-only fallback will be attempted.

        Args:
            uploads: The list of UploadFile objects from the multipart request.

        Raises:
            HTTPException 400: When count or MIME type is invalid.
        """
        real_uploads = [upload for upload in uploads if upload.filename]

        if len(real_uploads) > MAX_REPLY_ATTACHMENT_COUNT:
            logger.warning(
                'Reply attachment validation failed: count=%s exceeds max=%s',
                len(real_uploads),
                MAX_REPLY_ATTACHMENT_COUNT,
            )
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f'eBay allows a maximum of {MAX_REPLY_ATTACHMENT_COUNT} attachments per reply',
            )

        for upload in real_uploads:
            mime_type = upload.content_type or 'application/octet-stream'
            if mime_type not in ALLOWED_REPLY_ATTACHMENT_TYPES:
                logger.warning(
                    'Reply attachment validation failed: filename=%s mime_type=%s not in allowed set',
                    upload.filename,
                    mime_type,
                )
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=(
                        f'Attachment type "{mime_type}" is not supported for eBay replies. '
                        f'Only JPEG and PNG images are accepted.'
                    ),
                )

    # ------------------------------------------------------------------
    # Local storage
    # ------------------------------------------------------------------

    async def save_uploads(
        self,
        *,
        uploads: list[UploadFile],
        message_id: UUID,
        account_id: UUID | None,
    ) -> list[MessageAttachment]:
        """
        Write uploaded files to local storage and return ORM attachment rows.

        The returned rows are not yet flushed to the database; callers must
        append them to ``message.attachments`` and flush/commit themselves.

        Args:
            uploads:    Validated UploadFile objects from the HTTP request.
            message_id: The ID of the Message these attachments belong to.
            account_id: The eBay account ID associated with the reply.

        Returns:
            A list of unsaved MessageAttachment instances with ``storage_path``
            and ``download_url`` set for internal helpdesk use.

        Raises:
            HTTPException 400: If a file exceeds the configured size limit.
        """
        self.validate_uploads(uploads)
        attachments: list[MessageAttachment] = []
        self.upload_dir.mkdir(parents=True, exist_ok=True)

        for upload in uploads:
            if not upload.filename:
                continue

            mime_type = upload.content_type or 'application/octet-stream'
            content = await upload.read()

            if len(content) > self.settings.reply_attachment_max_bytes:
                logger.warning(
                    'Reply attachment size validation failed: filename=%s size=%s max=%s',
                    upload.filename,
                    len(content),
                    self.settings.reply_attachment_max_bytes,
                )
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail='Attachment exceeds the allowed file size',
                )

            safe_name = Path(upload.filename).name[:500]
            stored_name = f'{uuid4()}-{safe_name}'
            storage_path = self.upload_dir / stored_name
            storage_path.write_bytes(content)

            logger.warning(
                'Stored reply attachment locally: filename=%s path=%s size=%s',
                safe_name,
                storage_path,
                len(content),
            )

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

    # ------------------------------------------------------------------
    # eBay upload
    # ------------------------------------------------------------------

    async def upload_to_ebay(
        self,
        *,
        attachments: list[MessageAttachment],
        access_token: str,
        ebay_client,
    ) -> list[dict]:
        """
        Upload all locally stored attachments to eBay's media API.

        Each attachment is read from local storage and POSTed to eBay.
        If any single upload fails the method raises immediately so the
        caller can abort the entire reply transaction — no partial sends.

        On success each attachment's ``media_url`` field is set to the
        eBay-hosted URL and its raw_payload records the eBay response.

        Args:
            attachments:  The MessageAttachment rows saved by ``save_uploads``.
            access_token: A valid eBay OAuth access token.
            ebay_client:  An eBay API client instance that exposes
                          ``upload_message_media(token, file_bytes, mime_type,
                          media_name) -> response``.

        Returns:
            A list of eBay MessageMedia dicts ready for the send-message payload::

                [{"mediaName": "photo.jpg", "mediaType": "IMAGE", "mediaUrl": "https://ir.ebaystatic.com/..."}]

        Raises:
            HTTPException 400: When any attachment's local file is missing.
            HTTPException 502: When eBay rejects the upload for any attachment.
        """
        message_media: list[dict] = []

        for attachment in attachments:
            storage_path = Path(attachment.storage_path)
            if not storage_path.exists():
                logger.error(
                    'Attachment file missing before eBay upload: attachment_id=%s path=%s',
                    attachment.id,
                    storage_path,
                )
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f'Attachment file not found for upload: {attachment.file_name}',
                )

            file_bytes = storage_path.read_bytes()
            media_name = attachment.media_name or attachment.file_name
            mime_type = attachment.mime_type or 'image/jpeg'

            logger.warning(
                'Uploading attachment to eBay: attachment_id=%s media_name=%s mime_type=%s size=%s',
                attachment.id,
                media_name,
                mime_type,
                len(file_bytes),
            )

            response = ebay_client.upload_message_media(
                access_token,
                file_bytes=file_bytes,
                mime_type=mime_type,
                media_name=media_name,
            )

            logger.warning(
                'eBay upload response: attachment_id=%s ok=%s payload=%s',
                attachment.id,
                response.ok,
                response.payload,
            )

            if not response.ok:
                error_detail = self._upload_error_detail(response.payload, media_name)
                logger.error(
                    'eBay attachment upload failed: attachment_id=%s media_name=%s error=%s',
                    attachment.id,
                    media_name,
                    error_detail,
                )
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail=error_detail,
                )

            ebay_media_url = self._extract_ebay_media_url(response.payload)
            if not ebay_media_url:
                logger.error(
                    'eBay upload succeeded but no media URL returned: attachment_id=%s payload=%s',
                    attachment.id,
                    response.payload,
                )
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail=f'eBay did not return a hosted URL for attachment "{media_name}". Cannot send reply.',
                )

            logger.warning(
                'eBay-hosted media URL obtained: attachment_id=%s url=%s',
                attachment.id,
                ebay_media_url,
            )

            # Persist the eBay-hosted URL for helpdesk display and auditing.
            attachment.media_url = ebay_media_url
            attachment.raw_payload = {
                **(attachment.raw_payload or {}),
                'delivery': 'ebay_uploaded',
                'ebay_media_url': ebay_media_url,
                'ebay_response': response.payload,
            }

            message_media.append(
                {
                    'mediaName': media_name,
                    'mediaType': attachment.media_type,
                    'mediaUrl': ebay_media_url,
                }
            )

        return message_media

    # ------------------------------------------------------------------
    # Delivery outcome recording
    # ------------------------------------------------------------------

    def mark_delivery_result(
        self,
        *,
        attachments: list[MessageAttachment],
        delivery: str,
        ebay_error: object | None = None,
    ) -> None:
        """
        Record the final delivery status on local attachment metadata rows.

        Args:
            attachments: Attachment rows to update.
            delivery:    A short delivery-status string stored in raw_payload,
                         e.g. ``"ebay_sent"``, ``"ebay_failed"``.
            ebay_error:  Optional eBay error payload for failure diagnostics.
        """
        for attachment in attachments:
            attachment.raw_payload = {
                **(attachment.raw_payload or {}),
                'delivery': delivery,
                'ebay_error': ebay_error,
            }

    def delete_local_files(
        self,
        *,
        attachments: list[MessageAttachment],
    ) -> None:
        """
        Remove local upload files after eBay has accepted and hosted them.

        The MessageAttachment rows are kept for conversation history, but
        storage_path/download_url are cleared so the app no longer points at
        files that have intentionally been removed.
        """
        for attachment in attachments:
            raw_payload = attachment.raw_payload or {}
            storage_path_value = attachment.storage_path

            if storage_path_value:
                storage_path = Path(storage_path_value)
                try:
                    if storage_path.exists():
                        storage_path.unlink()
                        raw_payload['local_file_deleted'] = True
                    else:
                        raw_payload['local_file_deleted'] = True
                        raw_payload['local_file_delete_note'] = 'file already missing'
                except OSError as exc:
                    logger.warning(
                        'Could not delete local reply attachment: attachment_id=%s path=%s error=%s',
                        attachment.id,
                        storage_path,
                        exc,
                    )
                    raw_payload['local_file_deleted'] = False
                    raw_payload['local_file_delete_error'] = str(exc)
                    attachment.raw_payload = raw_payload
                    continue

            attachment.storage_path = None
            attachment.download_url = None
            attachment.raw_payload = raw_payload

    # ------------------------------------------------------------------
    # Local file resolution (used by helpdesk download endpoints)
    # ------------------------------------------------------------------

    def resolve_download_path(self, stored_name: str) -> Path:
        """
        Return the filesystem path for a locally stored attachment file.

        Validates that the resolved path stays inside the upload directory
        (path-traversal guard) and that the file actually exists.

        Args:
            stored_name: The filename component of the attachment's stored path.

        Raises:
            HTTPException 404: When the file is not found or resolves outside
                               the upload directory.
        """
        candidate = (self.upload_dir / Path(stored_name).name).resolve()
        if not str(candidate).startswith(str(self.upload_dir.resolve())) or not candidate.exists():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Attachment not found')
        return candidate

    def resolve_storage_path(self, storage_path: str) -> Path:
        """
        Return the filesystem path from a database ``storage_path`` value.

        Args:
            storage_path: Absolute path string stored in MessageAttachment.

        Raises:
            HTTPException 404: When the file does not exist or is outside the
                               configured upload directory.
        """
        candidate = Path(storage_path).resolve()
        if not str(candidate).startswith(str(self.upload_dir.resolve())) or not candidate.exists():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Attachment not found')
        return candidate

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _upload_dir(self) -> Path:
        """
        Resolve the attachment upload directory from application settings.

        Returns an absolute path; relative paths are resolved from the
        backend package root (``BACKEND_DIR``).
        """
        configured = Path(self.settings.reply_attachment_upload_dir)
        return configured if configured.is_absolute() else BACKEND_DIR / configured

    def _extract_ebay_media_url(self, payload: object) -> str | None:
        """
        Parse the eBay upload response and return the hosted media URL.

        eBay may return the URL under different keys depending on the API
        version.  We check common candidates in priority order.

        Args:
            payload: The deserialized response body from eBay.

        Returns:
            The URL string if found and non-empty, otherwise ``None``.
        """
        if not isinstance(payload, dict):
            return None

        # Try known eBay response keys in priority order.
        for key in ('mediaUrl', 'media_url', 'imageUrl', 'maxDimensionImageUrl', 'url'):
            value = payload.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()

        return None

    def _upload_error_detail(self, payload: object, media_name: str) -> str:
        """
        Build a user-facing error message from an eBay upload failure payload.

        Args:
            payload:    The deserialized eBay error response body.
            media_name: The attachment filename for context in the message.

        Returns:
            A plain-English error string suitable for an HTTP 502 detail field.
        """
        if isinstance(payload, dict):
            if payload.get('error_type') == 'transport_error':
                errors = payload.get('errors')
                message = None
                if isinstance(errors, list) and errors and isinstance(errors[0], dict):
                    value = errors[0].get('longMessage') or errors[0].get('message')
                    if isinstance(value, str) and value.strip():
                        message = value.strip()
                if not message:
                    message = 'Could not connect to eBay media upload service'
                return (
                    f'Could not upload attachment "{media_name}" because the app could not reach eBay. '
                    f'{message}. Check internet/DNS/VPN/proxy settings, then try again. The reply was not sent.'
                )

            errors = payload.get('errors')
            if isinstance(errors, list) and errors:
                first = errors[0]
                if isinstance(first, dict):
                    message = first.get('longMessage') or first.get('message')
                    if isinstance(message, str) and message.strip():
                        return (
                            f'eBay rejected the attachment "{media_name}": {message.strip()}. '
                            f'The reply was not sent.'
                        )

        return (
            f'eBay could not process the attachment "{media_name}". '
            f'The reply was not sent. Please try again or remove the attachment.'
        )
