import re


CONTACT_PATTERNS = [
    (re.compile(r'\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b', re.IGNORECASE), 'Email addresses are not allowed in eBay replies.'),
    (re.compile(r'(\+?\d[\d\s().-]{7,}\d)'), 'Phone numbers are not allowed in eBay replies.'),
    (re.compile(r'\b(?:https?://|www\.)\S+', re.IGNORECASE), 'External links are not allowed in eBay replies.'),
    (re.compile(r'\b(?:whatsapp|telegram|instagram|facebook|gmail|yahoo|outlook)\b', re.IGNORECASE), 'Off-platform contact references are not allowed.'),
]

ABUSIVE_TERMS = {
    'idiot',
    'stupid',
    'moron',
    'scam',
    'scammer',
    'fraud',
    'damn',
}


class ReplyPolicyService:
    def validate(self, body: str) -> list[str]:
        violations = []
        normalized_body = ' '.join(body.split())
        for pattern, message in CONTACT_PATTERNS:
            if pattern.search(normalized_body):
                violations.append(message)

        words = {word.strip(".,!?;:'\"()[]{}").lower() for word in normalized_body.split()}
        abusive_matches = sorted(words.intersection(ABUSIVE_TERMS))
        if abusive_matches:
            violations.append('Reply contains language that may violate eBay messaging policy.')

        return violations
