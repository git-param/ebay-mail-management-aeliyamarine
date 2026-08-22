from decimal import Decimal

from fastapi import HTTPException, status

from app.models.conversation import Conversation
from app.models.ebay_account import EbayAccount
from app.modules.offer_management.models import OfferManagementEntry, OfferManagementOutcome, OfferManagementStatus
from app.modules.offer_management.permissions import can_view_all_offer_entries, require_offer_entry_access, require_offer_entry_delete_access
from app.modules.offer_management.repository import OfferManagementRepository
from app.modules.offer_management.schemas import OfferEntryCreate, OfferEntryUpdate
from app.modules.offer_management.utils import default_listing_url, extract_listing_id, is_high_value_amount
from app.modules.config_management.service import ConfigService


class OfferManagementService:
    ACTIVE_STATUSES = {
        OfferManagementStatus.OPEN,
        OfferManagementStatus.CLOSED,
    }
    ACTIVE_OUTCOMES = {
        OfferManagementOutcome.PENDING,
        OfferManagementOutcome.DONE,
        OfferManagementOutcome.IGNORE,
        OfferManagementOutcome.SOLD,
        OfferManagementOutcome.NOT_ABLE_TO_MATCH_THE_PRICE,
    }
    CLOSED_OUTCOMES = ACTIVE_OUTCOMES - {
        OfferManagementOutcome.PENDING,
    }

    def __init__(self, db):
        self.db = db
        self.repo = OfferManagementRepository(db)

    def _prepare_values(self, payload, user, existing=None) -> dict:
        values = payload.model_dump(exclude_unset=True)
        if values.get('listing_id'):
            values['listing_id'] = extract_listing_id(values['listing_id'])
            values.setdefault('listing_url', default_listing_url(values['listing_id']))
        if values.get('currency'):
            values['currency'] = values['currency'].upper()
        account_id = values.get('ebay_account_id') or getattr(existing, 'ebay_account_id', None)
        if not account_id and values.get('related_conversation_id'):
            conversation = self.db.query(Conversation).filter(Conversation.id == values['related_conversation_id']).first()
            account_id = conversation.provider_account_id if conversation else None
            if account_id:
                values['ebay_account_id'] = account_id
        if not account_id:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail='Seller account is required.')
        account = self.db.query(EbayAccount).filter(EbayAccount.id == account_id).first()
        if not account:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='The selected eBay account was not found.')
        values['ebay_account_name'] = values.get('ebay_account_name') or account.account_name or account.store_name or account.ebay_username
        merged = {column.name: getattr(existing, column.name, None) for column in OfferManagementEntry.__table__.columns} if existing else {}
        merged.update(values)

        if merged.get('status') not in self.ACTIVE_STATUSES:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail='Status must be Open or Closed.',
            )

        if merged.get('outcome') not in self.ACTIVE_OUTCOMES:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail='Invalid offer outcome.',
            )

        if merged.get('status') == OfferManagementStatus.CLOSED:
            if merged.get('outcome') not in self.CLOSED_OUTCOMES:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail='Outcome is required before closing an offer.',
                )

            if not str(merged.get('remarks') or '').strip():
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail='Remarks are required before closing an offer.',
                )

            values['next_offer_followup'] = None
        elif merged.get('outcome') is None:
            values['outcome'] = OfferManagementOutcome.PENDING

        threshold = ConfigService(self.db).get_decimal('offer.high_value_amount', default=Decimal('500'))
        quantity = merged.get('offer_quantity') or merged.get('listing_quantity')
        values['is_high_value'] = is_high_value_amount(
            merged.get('listed_price'),
            merged.get('revised_price'),
            merged.get('automated_offer_price'),
            merged.get('buyer_offer_price'),
            merged.get('counteroffer_price'),
            merged.get('final_price'),
            threshold=threshold,
            quantity=quantity,
        )
        return values

    def create(self, payload: OfferEntryCreate, user) -> OfferManagementEntry:
        values = self._prepare_values(payload, user)
        existing = self.repo.get_by_listing_id(values['listing_id'])
        if existing:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f'Entry for listing {values["listing_id"]} is already done as entry #{existing.entry_number}. Please edit it from the list below.',
            )
        entry = OfferManagementEntry(
            **values,
            entry_number=self.repo.next_entry_number(),
            created_by_user_id=user.id,
            updated_by_user_id=user.id,
        )
        return self.repo.create(entry, user.id)

    def update(self, entry_id, payload: OfferEntryUpdate, user) -> OfferManagementEntry:
        entry = self.repo.get(entry_id)
        if not entry:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Offer entry not found.')
        require_offer_entry_access(user, entry)
        values = self._prepare_values(payload, user, entry)
        values.pop('created_by_user_id', None)
        values.pop('created_at', None)
        values.pop('entry_number', None)
        return self.repo.update(entry, values, user.id)

    def delete(self, entry_id, user) -> None:
        require_offer_entry_delete_access(user)
        entry = self.repo.get(entry_id)
        if not entry:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Offer entry not found.')
        self.repo.delete(entry)

    def delete_many(self, entry_ids, user) -> int:
        require_offer_entry_delete_access(user)
        unique_ids = list(dict.fromkeys(entry_ids))
        entries = []
        for entry_id in unique_ids:
            entry = self.repo.get(entry_id)
            if entry:
                entries.append(entry)
        return self.repo.delete_many(entries)

    def get(self, entry_id, user):
        entry = self.repo.get(entry_id)
        if not entry:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Offer entry not found.')
        require_offer_entry_access(user, entry)
        return entry

    def filters_for_user(self, params: dict, user) -> dict:
        filters = dict(params)
        filters['can_view_all'] = can_view_all_offer_entries(user)
        return filters

    def lookup(self, listing_value: str) -> dict:
        listing_id = extract_listing_id(listing_value)
        existing = self.repo.get_by_listing_id(listing_id)
        if existing:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f'Entry for listing {listing_id} is already done as entry #{existing.entry_number}. Please edit it from the list below.',
            )
        sources = self.repo.lookup_sources(listing_id)
        product = sources['product']
        order_line = sources['order_line']
        order_context = sources['order_context']
        conversation = sources['conversation']
        account = sources['account']
        details = {
            'listing_id': listing_id,
            'listing_url': product.item_url if product and product.item_url else default_listing_url(listing_id),
            'ebay_account_id': str(account.id) if account else None,
            'ebay_account_name': (account.account_name or account.store_name or account.ebay_username) if account else None,
            'sku': (product.sku if product else None) or (order_line.sku if order_line else None) or (order_context.sku if order_context else None),
            'product_title': (product.item_title if product else None) or (order_line.title if order_line else None) or (order_context.title if order_context else None),
            'condition': None,
            'listing_quantity': order_line.quantity if order_line else None,
            'listed_price': product.price_value if product else order_line.price_value if order_line else None,
            'currency': (product.price_currency if product else None) or (order_line.price_currency if order_line else None) or 'USD',
            'buyer_id': (order_context.buyer_username if order_context else None) or (conversation.buyer_identifier if conversation else None),
            'related_conversation_id': str(conversation.id) if conversation else str(order_context.conversation_id) if order_context else None,
        }
        matches = []
        for offer in sources['offers']:
            matches.append({
                'offer_id': offer.id,
                'buyer_id': offer.buyer_username,
                'offer_type': offer.offer_type or offer.direction,
                'offer_amount': offer.offer_amount,
                'currency': offer.currency,
                'offer_date': offer.created_at_provider or offer.created_at,
                'offer_status': offer.status,
                'seller_account': (offer.account.account_name or offer.account.store_name or offer.account.ebay_username) if offer.account else None,
                'seller_account_id': offer.account_id,
                'related_conversation_id': offer.conversation_id,
                'related_conversation': offer.conversation.provider_conversation_id if offer.conversation else None,
            })
        selected = None
        if len(matches) == 1:
            offer = sources['offers'][0]
            selected = {
                **details,
                'buyer_id': offer.buyer_username or details.get('buyer_id'),
                'offer_quantity': offer.quantity,
                'buyer_offer_price': offer.offer_amount if offer.direction == 'INCOMING' else None,
                'automated_offer_price': offer.offer_amount if offer.direction == 'OUTGOING' else None,
                'currency': offer.currency or details.get('currency'),
                'offer_date': (offer.created_at_provider or offer.created_at).date().isoformat(),
                'related_offer_id': str(offer.id),
                'related_conversation_id': str(offer.conversation_id) if offer.conversation_id else details.get('related_conversation_id'),
            }
        message = 'One stored offer matched and was populated.' if selected else 'Multiple stored offers matched. Select one to populate the form.' if matches else 'Listing details were populated where available. Enter offer details manually.'
        return {'listing_id': listing_id, 'listing_url': details['listing_url'], 'details': details, 'matches': matches, 'selected': selected, 'message': message}
