"""mark stored offer notification messages

Revision ID: 20260710_0029
Revises: 20260710_0028
Create Date: 2026-07-10 00:00:01.000000
"""
from alembic import op


revision = '20260710_0029'
down_revision = '20260710_0028'
branch_labels = None
depends_on = None


OFFER_TEXT_PREDICATE = """
    lower(
        concat_ws(
            ' ',
            m.body,
            m.raw_payload ->> 'subject',
            m.raw_payload ->> 'Subject',
            m.raw_payload ->> 'messageSubject',
            m.raw_payload ->> 'title'
        )
    ) SIMILAR TO '%(buyer sent an offer|you have a new offer|new offer for|offer from|sent an offer|you sent an offer|your offer on|offer submitted to|counteroffer submitted to buyer|you sent a counteroffer|buyer made a counteroffer|sent a counteroffer|accepted an offer|accepted your offer|buyer accepted|offer accepted|best offer accepted|counteroffer accepted|offer expired|best offer expired|counteroffer expired|offer has expired|counteroffer has expired|offer declined|declined your offer|counteroffer declined)%'
"""


def upgrade() -> None:
    op.execute(
        f"""
        UPDATE messages AS m
        SET offer_data = '{{"notification_type":"OFFER"}}'
        FROM conversations AS c
        WHERE c.id = m.conversation_id
          AND upper(coalesce(c.provider_conversation_type, '')) = 'FROM_MEMBERS'
          AND (
              upper(coalesce(m.sender_type::text, '')) IN ('SYSTEM', 'PROVIDER')
              OR lower(coalesce(m.sender_identifier, '')) IN ('ebay', 'ebay system')
          )
          AND ({OFFER_TEXT_PREDICATE})
        """
    )


def downgrade() -> None:
    op.execute(
        """
        UPDATE messages
        SET offer_data = NULL
        WHERE offer_data ->> 'notification_type' = 'OFFER'
        """
    )
