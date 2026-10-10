from unittest.mock import Mock

import pytest

from app.modules.integrations.ebay.client.ebay_auth_client import EbayAuthClient


@pytest.mark.parametrize('new_buyer', [True, False])
@pytest.mark.parametrize('with_attachments', [True, False])
@pytest.mark.parametrize('newline', ['\n', '\r\n', '\r'])
def test_outbound_messages_preserve_paragraph_spacing(new_buyer, with_attachments, newline):
    client = EbayAuthClient(
        client_id='test', client_secret='test', redirect_uri='test',
        runame='test', environment='PRODUCTION',
    )
    client._request_message_api_raw = Mock()
    paragraphs = [
        'Hi,', '', 'Your order has been shipped.', '', '',
        '  Tracking Number - 2749253205', '', 'Best regards,', 'Nidhi Patel',
    ]
    media = [{'mediaName': 'photo', 'mediaUrl': 'image-url'}] if with_attachments else None
    kwargs = {
        'message_body': newline.join(paragraphs),
        'message_media': media,
    }

    if new_buyer:
        client.start_conversation_message('token', buyer_username='buyer', **kwargs)
    else:
        client.send_conversation_message('token', conversation_id='thread-123', **kwargs)

    payload = client._request_message_api_raw.call_args.kwargs['payload']
    assert payload['messageText'] == (
        'Hi,\n \nYour order has been shipped.\n \n \n'
        '  Tracking Number - 2749253205\n \nBest regards,\nNidhi Patel'
    )
    assert payload['messageText'].splitlines()[5].startswith('  Tracking')


def test_single_line_message_is_preserved():
    client = EbayAuthClient(
        client_id='test', client_secret='test', redirect_uri='test',
        runame='test', environment='PRODUCTION',
    )
    assert client._message_body_for_send('Hello  buyer') == 'Hello  buyer'


@pytest.mark.parametrize('new_buyer', [True, False])
@pytest.mark.parametrize('listing_id', [' 236988914323 ', None, ' '])
def test_listing_reference_is_sent_only_for_known_items(new_buyer, listing_id):
    client = EbayAuthClient(
        client_id='test', client_secret='test', redirect_uri='test',
        runame='test', environment='PRODUCTION',
    )
    client._request_message_api_raw = Mock()
    kwargs = {'message_body': 'Hello', 'listing_id': listing_id}
    if new_buyer:
        client.start_conversation_message('token', buyer_username='buyer', **kwargs)
    else:
        client.send_conversation_message('token', conversation_id='thread-123', **kwargs)
    payload = client._request_message_api_raw.call_args.kwargs['payload']
    if listing_id and listing_id.strip():
        assert payload['reference'] == {'referenceId': '236988914323', 'referenceType': 'LISTING'}
    else:
        assert 'reference' not in payload
