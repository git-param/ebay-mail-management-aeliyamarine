import unittest

from app.services.reply_attachment_service import ReplyAttachmentService


class ReplyAttachmentUploadErrorTests(unittest.TestCase):
    def test_transport_error_is_not_reported_as_ebay_rejection(self):
        service = object.__new__(ReplyAttachmentService)

        detail = service._upload_error_detail(
            {
                'error_type': 'transport_error',
                'errors': [
                    {
                        'longMessage': (
                            "Could not connect to eBay media upload service: "
                            "Failed to resolve 'apim.ebay.com'"
                        )
                    }
                ],
            },
            'photo.png',
        )

        self.assertIn('could not reach eBay', detail)
        self.assertIn('Check internet/DNS/VPN/proxy settings', detail)
        self.assertNotIn('eBay rejected', detail)


if __name__ == '__main__':
    unittest.main()
