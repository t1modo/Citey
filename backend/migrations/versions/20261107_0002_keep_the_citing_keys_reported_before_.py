"""Keep the citing keys reported before Postgres

works.known_citing_keys holds the identity keys of citing papers announced
while the data lived in Firestore (its notified_keys), so they are never
announced again.

Revision ID: 0002
Revises: 0001
Create Date: 2026-11-07 04:19:53.208235+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
import sqlmodel
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = '0002'
down_revision: str | Sequence[str] | None = '0001'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column('works', sa.Column('known_citing_keys', postgresql.ARRAY(sa.Text()), server_default=sa.text("'{}'::text[]"), nullable=False))


def downgrade() -> None:
    op.drop_column('works', 'known_citing_keys')
