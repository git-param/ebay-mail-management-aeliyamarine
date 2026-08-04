"""merge migration heads

Revision ID: 497fc21b0a15
Revises: 20260730_0042, 20260803_0110
Create Date: 2026-08-04 10:50:03.750681

"""
from alembic import op
import sqlalchemy as sa



revision = '497fc21b0a15'
down_revision = ('20260730_0042', '20260803_0110')
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
