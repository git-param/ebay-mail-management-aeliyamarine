# backfill_offers.py
from app.db.session import SessionLocal
from app.models.conversation import Message
from app.models.offer import Offer, OfferDirection, OfferStatus
from app.models.ebay_account import EbayAccount
import re
from decimal import Decimal

def run_backfill(account_id):
    db = SessionLocal()

    account = db.query(EbayAccount).filter(
        EbayAccount.id == account_id
    ).first()

    if not account:
        print("❌ Account not found")
        exit()

    # Find ALL messages for this account
    messages = db.query(Message).filter(
        Message.recipient_identifier == account.ebay_username,
    ).all()

    print(f"📨 Found {len(messages)} total messages for {account.ebay_username}")

    # Filter for offer messages (contain 'offer' or 'counteroffer')
    offer_messages = [
        msg for msg in messages 
        if 'offer' in msg.body.lower() or 'counteroffer' in msg.body.lower()
    ]

    print(f"🎯 Found {len(offer_messages)} offer-related messages")

    created = 0
    skipped = 0

    for msg in offer_messages:
        # Check if offer already exists
        existing = db.query(Offer).filter(
            Offer.provider_offer_id == msg.provider_message_id,
            Offer.account_id == account.id
        ).first()
        
        if existing:
            skipped += 1
            continue
        
        # Parse amount
        amount_match = re.search(r'(?:USD|EUR|US\$)\s*([\d,]+\.?\d*)', msg.body)
        if not amount_match:
            amount_match = re.search(r'\$([\d,]+\.?\d*)', msg.body)
        if not amount_match:
            continue
        
        amount = Decimal(amount_match.group(1).replace(',', ''))
        
        # Extract listing_id from body (looks for (406266724016) at end)
        listing_match = re.search(r'\((\d+)\)\s*$', msg.body)
        listing_id = listing_match.group(1) if listing_match else None
        
        # If not found at end, try to find anywhere in body
        if not listing_id:
            listing_match = re.search(r'\((\d+)\)', msg.body)
            listing_id = listing_match.group(1) if listing_match else None
        
        # Determine direction
        if 'You sent' in msg.body:
            direction = OfferDirection.OUTGOING
        else:
            direction = OfferDirection.INCOMING
        
        # Determine status
        if 'expired' in msg.body.lower():
            status = OfferStatus.EXPIRED
        elif 'accepted' in msg.body.lower():
            status = OfferStatus.ACCEPTED
        elif 'declined' in msg.body.lower():
            status = OfferStatus.DECLINED
        else:
            status = OfferStatus.PENDING
        
        # Extract buyer username
        buyer_match = re.search(r'(?:to|for)\s+([a-zA-Z0-9_-]+)', msg.body)
        buyer = buyer_match.group(1) if buyer_match else None
        
        offer = Offer(
            account_id=account.id,
            conversation_id=msg.conversation_id,
            provider_offer_id=msg.provider_message_id,
            listing_id=listing_id,  # Now set from body
            buyer_username=buyer,
            offer_amount=amount,
            currency='USD',
            status=status,
            direction=direction,
            offer_type='OFFER',
            quantity=1,
            created_at=msg.sent_at,
            raw_payload=msg.raw_payload,
        )
        db.add(offer)
        created += 1
        
        if created % 50 == 0:
            print(f"✅ Created {created} offers so far...")

    db.commit()
    print(f"\n✅ Created {created} offers")
    print(f"⏭️ Skipped {skipped} existing offers")