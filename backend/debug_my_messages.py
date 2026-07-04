# debug_message_details.py
import xml.etree.ElementTree as ET
from urllib.request import Request, urlopen

from app.db.session import SessionLocal
from app.models.ebay_account import EbayAccount
from app.modules.integrations.ebay.oauth.token_service import EbayTokenService
from datetime import datetime, timezone

db = SessionLocal()

account = db.query(EbayAccount).filter(
    EbayAccount.ebay_username == "aeliya-ship110"
).first()

if not account:
    print("❌ Account not found")
    exit()

token_service = EbayTokenService(db)
client = token_service.client

# Ensure valid token
if account.access_token_expires_at and account.access_token_expires_at <= datetime.now(timezone.utc):
    account = token_service.refresh_access_token(account.id)

# One of the message IDs from earlier
message_id = "210180394715"  # Counteroffer submitted to buyer

print(f"📥 Fetching full details for message: {message_id}")
print("=" * 50)

# Correct XML format - MessageID as a parameter
xml = f'''<?xml version="1.0" encoding="utf-8"?>
<GetMyMessagesRequest xmlns="urn:ebay:apis:eBLBaseComponents">
    <DetailLevel>ReturnMessages</DetailLevel>
    <MessageIDs>
        <MessageID>{message_id}</MessageID>
    </MessageIDs>
</GetMyMessagesRequest>'''

headers = {
    'X-EBAY-API-CALL-NAME': 'GetMyMessages',
    'X-EBAY-API-SITEID': '0',
    'X-EBAY-API-COMPATIBILITY-LEVEL': '1455',
    'X-EBAY-API-IAF-TOKEN': account.access_token,
    'Content-Type': 'text/xml',
}

request = Request(client.trading_url, data=xml.encode('utf-8'), headers=headers, method='POST')

try:
    with urlopen(request, timeout=30) as response:
        xml_response = response.read().decode('utf-8')
        
        # Parse XML
        root = ET.fromstring(xml_response)
        ns = {'e': 'urn:ebay:apis:eBLBaseComponents'}
        
        ack = root.findtext('./e:Ack', namespaces=ns)
        
        if ack == 'Success':
            print("✅ Success!")
            print("-" * 50)
            
            # Extract message details
            for msg in root.findall('.//e:Message', ns):
                print(f"Message ID: {msg.findtext('./e:MessageID', namespaces=ns)}")
                print(f"Subject: {msg.findtext('./e:Subject', namespaces=ns)}")
                print(f"Sender: {msg.findtext('./e:Sender', namespaces=ns)}")
                print(f"Body: {msg.findtext('./e:Body', namespaces=ns)}")
                print(f"Item ID: {msg.findtext('./e:ItemID', namespaces=ns)}")
                print(f"Receive Date: {msg.findtext('./e:ReceiveDate', namespaces=ns)}")
        else:
            print(f"❌ Failed: {ack}")
            error = root.findtext('.//e:LongMessage', namespaces=ns)
            if error:
                print(f"Error: {error}")
            print("\nFull XML response:")
            print(xml_response)
            
except Exception as e:
    print(f"❌ Error: {e}")
    import traceback
    traceback.print_exc()