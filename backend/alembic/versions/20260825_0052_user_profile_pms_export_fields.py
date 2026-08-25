"""user profile fields for pms export

Revision ID: 20260825_0052
Revises: 20260825_0051
Create Date: 2026-08-25

"""
from alembic import op
import sqlalchemy as sa


revision = '20260825_0052'
down_revision = '20260825_0051'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('users', sa.Column('employee_id', sa.String(length=60), nullable=True))
    op.add_column('users', sa.Column('department', sa.String(length=120), nullable=True))
    op.add_column('users', sa.Column('designation', sa.String(length=120), nullable=True))
    op.add_column('users', sa.Column('date_of_joining', sa.Date(), nullable=True))


def downgrade() -> None:
    op.drop_column('users', 'date_of_joining')
    op.drop_column('users', 'designation')
    op.drop_column('users', 'department')
    op.drop_column('users', 'employee_id')
