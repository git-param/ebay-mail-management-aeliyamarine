from decimal import Decimal

import pytest

from app.modules.offer_management.utils import default_listing_url, extract_listing_id, is_high_value_amount


@pytest.mark.parametrize(
    ('value', 'expected'),
    [
        ('236077399513', '236077399513'),
        ('https://www.ebay.com/itm/236077399513', '236077399513'),
        ('https://www.ebay.co.uk/itm/287412885686?hash=abc', '287412885686'),
    ],
)
def test_extract_listing_id(value, expected):
    assert extract_listing_id(value) == expected


def test_extract_listing_id_rejects_invalid_values():
    with pytest.raises(ValueError):
        extract_listing_id('not-an-ebay-listing')


def test_default_listing_url():
    assert default_listing_url('236077399513') == 'https://www.ebay.com/itm/236077399513'


def test_high_value_calculation_uses_any_meaningful_amount():
    assert is_high_value_amount(None, Decimal('499.99'), Decimal('500.00'))
    assert not is_high_value_amount(None, Decimal('100.00'), '')
