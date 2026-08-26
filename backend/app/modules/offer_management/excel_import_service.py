import re
from io import BytesIO
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation

import pandas as pd
from fastapi import HTTPException, UploadFile, status
from sqlalchemy import func, or_

from app.models.ebay_account import EbayAccount
from app.modules.config_management.service import ConfigService
from app.modules.offer_management.models import (
    OfferManagementEntry,
    OfferManagementOutcome,
    OfferManagementStatus,
)
from app.modules.offer_management.repository import OfferManagementRepository
from app.modules.offer_management.utils import (
    default_listing_url,
    extract_listing_id,
    is_high_value_amount,
)


HEADER_MAP = {
    'sr no': 'entry_number',
    'sr. no': 'entry_number',
    'date': 'offer_date',
    'account': 'account',
    'sku': 'sku',
    'old price': 'listed_price',
    'new price': 'revised_price',
    'automated offer': 'automated_offer_price',
    "buyer's offer": 'buyer_offer_price',
    'buyers offer': 'buyer_offer_price',
    'offered price': 'offered_price',
    'buyer id': 'buyer_id',
    'buyer name': 'buyer_id',
    'ebay link': 'listing_url',
    'ebay url': 'listing_url',
    'description': 'product_title',
    'condition': 'condition',
    'qty': 'listing_quantity',
    'quantity': 'listing_quantity',
    'fup': 'fup',
    'follow up': 'fup',
    'folow up 1': 'next_offer_followup',
    'follow up 1': 'next_offer_followup',
    'folow up 2': 'follow_up_1_notes',
    'follow up 2': 'follow_up_1_notes',
    'remarks': 'remarks',
}


class OfferExcelImportService:
    def __init__(self, db):
        self.db = db
        self.repo = OfferManagementRepository(db)

    async def import_file(self, upload: UploadFile, user) -> dict:
        filename = upload.filename or ''
        if not filename.lower().endswith(('.xlsx', '.xls')):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail='Upload an Excel file with .xlsx or .xls extension.',
            )

        try:
            content = await upload.read()
            frame = pd.read_excel(BytesIO(content), dtype=object)
        except Exception as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f'Unable to read the Excel file: {exc}',
            ) from exc

        frame = frame.dropna(how='all')
        if frame.empty:
            return {'created_count': 0, 'skipped_count': 0, 'error_count': 0, 'errors': []}

        frame = frame.rename(columns={column: self._mapped_column(column) for column in frame.columns})
        accounts = self._account_lookup()
        next_entry_number = self.repo.next_entry_number()
        used_entry_numbers = set(
            number
            for (number,) in self.db.query(OfferManagementEntry.entry_number).all()
        )
        threshold = ConfigService(self.db).get_decimal('offer.high_value_amount', default=Decimal('500'))

        created = 0
        skipped = 0
        errors = []

        for index, row in frame.iterrows():
            row_number = int(index) + 2
            try:
                values = self._row_values(row, accounts, user, threshold)
                requested_entry_number = self._integer(row.get('entry_number'))
                if requested_entry_number and requested_entry_number not in used_entry_numbers:
                    entry_number = requested_entry_number
                else:
                    while next_entry_number in used_entry_numbers:
                        next_entry_number += 1
                    entry_number = next_entry_number

                entry = OfferManagementEntry(
                    **values,
                    entry_number=entry_number,
                    created_by_user_id=user.id,
                    updated_by_user_id=user.id,
                )
                self.db.add(entry)
                self.db.flush()
                self.repo.add_history(entry.id, user.id, 'IMPORT', None, self.repo.snapshot(entry))
                used_entry_numbers.add(entry_number)
                next_entry_number = max(next_entry_number, entry_number + 1)
                created += 1
            except Exception as exc:
                skipped += 1
                errors.append({'row_number': row_number, 'reason': str(exc)})

        self.db.commit()
        return {
            'created_count': created,
            'skipped_count': skipped,
            'error_count': len(errors),
            'errors': errors[:50],
        }

    def _row_values(self, row, accounts: dict[str, EbayAccount], user, threshold: Decimal) -> dict:
        listing_url = self._text(row.get('listing_url'))
        listing_id = extract_listing_id(listing_url)
        account = self._resolve_account(row.get('account'), accounts)
        listed_price, currency = self._money(row.get('listed_price'))
        revised_price, revised_currency = self._money(row.get('revised_price'))
        automated_offer_price, automated_currency = self._money(row.get('automated_offer_price'))
        buyer_offer_price, buyer_currency = self._money(row.get('buyer_offer_price'))
        offered_price = self._text(row.get('offered_price'))
        counteroffer_price, counter_currency = self._money(offered_price, listed_price)
        quantity = self._quantity(row.get('listing_quantity'))
        offer_date = self._date(row.get('offer_date')) or date.today()
        next_followup = self._date(row.get('next_offer_followup'))

        resolved_currency = (
            currency
            or revised_currency
            or automated_currency
            or buyer_currency
            or counter_currency
            or 'USD'
        )
        remarks = self._text(row.get('remarks'))

        return {
            'offer_date': offer_date,
            'ebay_account_id': account.id,
            'ebay_account_name': account.account_name or account.store_name or account.ebay_username,
            'listing_id': listing_id,
            'listing_url': listing_url or default_listing_url(listing_id),
            'sku': self._sku(row.get('sku')),
            'product_title': self._text(row.get('product_title')),
            'condition': self._text(row.get('condition')),
            'listing_quantity': quantity,
            'offer_quantity': quantity,
            'currency': resolved_currency,
            'listed_price': listed_price,
            'revised_price': revised_price,
            'automated_offer_price': automated_offer_price,
            'buyer_offer_price': buyer_offer_price,
            'offered_price': offered_price,
            'counteroffer_price': counteroffer_price,
            'final_price': None,
            'buyer_id': self._text(row.get('buyer_id')),
            'status': OfferManagementStatus.OPEN,
            'outcome': OfferManagementOutcome.PENDING,
            'is_high_value': is_high_value_amount(
                listed_price,
                revised_price,
                automated_offer_price,
                buyer_offer_price,
                counteroffer_price,
                threshold=threshold,
                quantity=quantity,
            ),
            'is_vip_lead': False,
            'next_offer_followup': next_followup,
            'follow_up_1_notes': self._text(row.get('follow_up_1_notes')),
            'follow_up_2_notes': None,
            'remarks': remarks,
        }

    def _account_lookup(self) -> dict[str, EbayAccount]:
        accounts = self.db.query(EbayAccount).filter(EbayAccount.is_active.is_(True)).all()
        lookup = {}
        for account in accounts:
            for value in (account.account_name, account.store_name, account.ebay_username):
                if value:
                    lookup[self._key(value)] = account
        return lookup

    def _resolve_account(self, value, accounts: dict[str, EbayAccount]) -> EbayAccount:
        key = self._key(value)
        if not key:
            raise ValueError('Account is required.')
        account = accounts.get(key)
        if account:
            return account
        matches = (
            self.db.query(EbayAccount)
            .filter(or_(
                func.lower(EbayAccount.account_name) == key,
                func.lower(EbayAccount.store_name) == key,
                func.lower(EbayAccount.ebay_username) == key,
            ))
            .all()
        )
        if len(matches) == 1:
            return matches[0]
        raise ValueError(f'Account "{self._text(value)}" was not found.')

    @staticmethod
    def _mapped_column(value) -> str:
        cleaned = re.sub(r'\s+', ' ', str(value or '').strip().lower())
        return HEADER_MAP.get(cleaned, cleaned.replace(' ', '_'))

    @staticmethod
    def _key(value) -> str:
        return re.sub(r'\s+', ' ', str(value or '').strip().lower())

    @staticmethod
    def _is_blank(value) -> bool:
        return pd.isna(value) or str(value).strip() == ''

    def _text(self, value) -> str | None:
        if self._is_blank(value):
            return None
        text = str(value).strip()
        if re.fullmatch(r'\d+\.0', text):
            return text[:-2]
        return text

    def _sku(self, value) -> str | None:
        return self._text(value)

    def _integer(self, value) -> int | None:
        if self._is_blank(value):
            return None
        match = re.search(r'\d+', str(value))
        return int(match.group(0)) if match else None

    def _quantity(self, value) -> int | None:
        return self._integer(value)

    def _date(self, value) -> date | None:
        if self._is_blank(value):
            return None
        if isinstance(value, datetime):
            return value.date()
        if isinstance(value, date):
            return value
        if isinstance(value, (int, float)) and value > 10000:
            return date(1899, 12, 30) + timedelta(days=int(value))
        text = str(value).strip()
        if re.fullmatch(r'\d+(\.0)?', text):
            return date(1899, 12, 30) + timedelta(days=int(float(text)))
        for fmt in ('%d-%m-%Y', '%m-%d-%Y', '%Y-%m-%d', '%d/%m/%Y', '%m/%d/%Y'):
            try:
                return datetime.strptime(text, fmt).date()
            except ValueError:
                continue
        parsed = pd.to_datetime(text, errors='coerce', dayfirst=True)
        return None if pd.isna(parsed) else parsed.date()

    def _money(self, value, base: Decimal | None = None) -> tuple[Decimal | None, str | None]:
        if self._is_blank(value):
            return None, None
        text = str(value).strip()
        currency = self._currency(text)
        percent_match = re.search(r'(\d+(?:\.\d+)?)\s*%', text)
        if percent_match and base is not None:
            discount = Decimal(percent_match.group(1)) / Decimal('100')
            return (base * (Decimal('1') - discount)).quantize(Decimal('0.01')), currency
        amount_match = re.search(r'-?\d[\d,]*(?:\.\d+)?', text)
        if not amount_match:
            return None, currency
        try:
            return Decimal(amount_match.group(0).replace(',', '')).quantize(Decimal('0.01')), currency
        except (InvalidOperation, ValueError):
            return None, currency

    @staticmethod
    def _currency(value: str) -> str | None:
        if '$' in value:
            return 'USD'
        if '£' in value or '�' in value:
            return 'GBP'
        if '€' in value:
            return 'EUR'
        match = re.search(r'\b([A-Z]{3})\b', value.upper())
        return match.group(1) if match else None
