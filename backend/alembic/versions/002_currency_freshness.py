"""add currency to companies and last_scraped_at to competitors

Revision ID: 002_currency_freshness
Revises: 001_baseline
Create Date: 2026-10-05 20:05:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '002_currency_freshness'
down_revision: Union[str, None] = '001_baseline'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('companies', sa.Column('currency', sa.String(), nullable=False, server_default='USD'))
    op.add_column('competitors', sa.Column('last_scraped_at', sa.DateTime(), nullable=True))


def downgrade() -> None:
    op.drop_column('competitors', 'last_scraped_at')
    op.drop_column('companies', 'currency')
