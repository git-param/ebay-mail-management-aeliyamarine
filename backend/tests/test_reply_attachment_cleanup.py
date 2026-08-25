from app.models.conversation import MessageAttachment
from app.services.reply_attachment_service import ReplyAttachmentService


def test_delete_local_files_removes_file_and_clears_local_download(tmp_path):
    local_file = tmp_path / 'reply-image.png'
    local_file.write_bytes(b'image-bytes')
    attachment = MessageAttachment(
        provider='EBAY',
        provider_attachment_id='local-1',
        file_name='reply-image.png',
        media_name='reply-image.png',
        media_type='IMAGE',
        mime_type='image/png',
        file_size=11,
        storage_path=str(local_file),
        download_url='/api/v1/conversations/attachments/reply-image.png',
        media_url='https://i.ebayimg.com/uploaded/reply-image.png',
        raw_payload={'delivery': 'ebay_sent'},
    )

    service = ReplyAttachmentService.__new__(ReplyAttachmentService)

    service.delete_local_files(attachments=[attachment])

    assert not local_file.exists()
    assert attachment.storage_path is None
    assert attachment.download_url is None
    assert attachment.media_url == 'https://i.ebayimg.com/uploaded/reply-image.png'
    assert attachment.raw_payload['local_file_deleted'] is True
