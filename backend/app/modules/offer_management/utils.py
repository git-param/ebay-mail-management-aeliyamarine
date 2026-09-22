import re
from datetime import date
from decimal import Decimal


LISTING_ID_RE = re.compile(r'(?:/itm/|itm=|item=)?(\d{9,15})(?:[/?#&]|$)', re.IGNORECASE)


def extract_listing_id(value: str | None) -> str:
    text = str(value or '').strip()
    if not text:
        raise ValueError('Enter a listing ID or eBay listing URL.')
    if text.isdigit() and 9 <= len(text) <= 15:
        return text
    match = LISTING_ID_RE.search(text)
    if match:
        return match.group(1)
    raise ValueError('Enter a valid eBay listing ID or URL.')


def default_listing_url(listing_id: str) -> str:
    return f'https://www.ebay.com/itm/{listing_id}'


def is_high_value_amount(*values, threshold: Decimal = Decimal('500'), quantity: int | None = None) -> bool:
    for value in values:
        if value is None or value == '':
            continue
        amount = Decimal(str(value))
        if amount >= threshold:
            return True
        if quantity and amount * Decimal(str(quantity)) >= threshold:
            return True
    return False


def is_offer_entry_high_value(
    listed_price,
    revised_price,
    required_quantity: int | None = None,
    threshold: Decimal = Decimal('500'),
) -> bool:
    price = revised_price if revised_price is not None and revised_price != '' else listed_price
    if price is None or price == '':
        return False
    amount = Decimal(str(price))
    if amount > threshold:
        return True
    quantity = required_quantity or 0
    return bool(quantity and amount * Decimal(str(quantity)) > threshold)


def excel_date_token(from_date: date | None, to_date: date | None) -> str:
    today = date.today().isoformat()
    if from_date or to_date:
        return f'{from_date.isoformat() if from_date else today}_to_{to_date.isoformat() if to_date else today}'
    return today
