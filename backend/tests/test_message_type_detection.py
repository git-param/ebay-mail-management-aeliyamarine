from types import SimpleNamespace
from uuid import uuid4

from app.services.message_type_detection_service import MessageTypeDetectionService, normalize_message_type_text


def message_type(*keywords):
    return SimpleNamespace(
        id=uuid4(),
        keywords=[SimpleNamespace(keyword=keyword) for keyword in keywords],
    )


def test_normalization_ignores_case_and_punctuation():
    assert normalize_message_type_text('PAYMENT-proof, received!') == 'payment proof received'


def test_highest_keyword_score_can_be_selected():
    tracking = message_type('tracking', 'shipment', 'dhl', 'package')
    invoice = message_type('invoice', 'receipt')

    scores = MessageTypeDetectionService.score(
        'DHL tracking says the package shipped. Please send an invoice.',
        [tracking, invoice],
    )

    assert scores[tracking.id] == 3
    assert scores[invoice.id] == 1


def test_matching_uses_word_boundaries():
    cancellation = message_type('cancel')
    scores = MessageTypeDetectionService.score('The cancellation candidate changed.', [cancellation])
    assert scores[cancellation.id] == 0
