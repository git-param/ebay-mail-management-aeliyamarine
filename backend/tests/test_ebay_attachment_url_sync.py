import unittest
from types import SimpleNamespace
from uuid import uuid4

from app.modules.integrations.ebay.services.ebay_message_service import EbayMessageService


class EbayAttachmentUrlSyncTests(unittest.TestCase):
    def setUp(self):
        self.service = object.__new__(EbayMessageService)
        self.service.provider = 'EBAY'
        self.account = SimpleNamespace(id=uuid4())

    def test_sync_converts_ebay_attachment_display_url_and_preserves_original(self):
        original_url = 'https://i.ebayimg.com/00/s/MTYwMFgxMTM5/z/6CIAAeSw0ttqX8rN/$_1.JPG?set_id=8800005007'
        payload = {
            'messageMedia': [
                {
                    'mediaName': 'photo.jpg',
                    'mediaType': 'IMAGE',
                    'mediaUrl': original_url,
                }
            ]
        }

        attachments = self.service._attachments_from_message_payload(self.account, payload)

        self.assertEqual(1, len(attachments))
        self.assertEqual(
            'https://i.ebayimg.com/images/g/6CIAAeSw0ttqX8rN/s-l1600.jpg',
            attachments[0].media_url,
        )
        self.assertEqual(original_url, attachments[0].download_url)
        self.assertEqual(original_url, attachments[0].raw_payload['mediaUrl'])

    def test_sync_leaves_unrecognized_attachment_url_unchanged(self):
        original_url = 'https://i.ebayimg.com/images/g/abc123/s-l1600.jpg'
        payload = {
            'messageMedia': [
                {
                    'mediaName': 'photo.jpg',
                    'mediaType': 'IMAGE',
                    'mediaUrl': original_url,
                }
            ]
        }

        attachments = self.service._attachments_from_message_payload(self.account, payload)

        self.assertEqual(original_url, attachments[0].media_url)
        self.assertEqual(original_url, attachments[0].download_url)


if __name__ == '__main__':
    unittest.main()
