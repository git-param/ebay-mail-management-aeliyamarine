import unittest

from app.modules.integrations.ebay.client.ebay_auth_client import EbayAuthClient


class EbayMessageSendFormattingTests(unittest.TestCase):
    def setUp(self):
        self.client = object.__new__(EbayAuthClient)

    def test_plain_message_body_is_not_changed_without_media(self):
        body = 'Hello\n\nWorld'

        self.assertEqual(
            body,
            self.client._message_body_for_send(body, has_media=False),
        )

    def test_empty_lines_get_spacers_when_media_is_present(self):
        body = 'Hello\r\n\r\nWorld\n\nRegards'

        self.assertEqual(
            'Hello\n \nWorld\n \nRegards',
            self.client._message_body_for_send(body, has_media=True),
        )


if __name__ == '__main__':
    unittest.main()
