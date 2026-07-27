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


def is_high_value_amount(*values) -> bool:
    for value in values:
        if value is None or value == '':
            continue
        if Decimal(str(value)) >= Decimal('500'):
            return True
    return False


def excel_date_token(from_date: date | None, to_date: date | None) -> str:
    today = date.today().isoformat()
    if from_date or to_date:
        return f'{from_date.isoformat() if from_date else today}_to_{to_date.isoformat() if to_date else today}'
    return today
