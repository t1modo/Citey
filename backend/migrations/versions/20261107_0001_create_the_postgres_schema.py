"""Create the Postgres schema

The tables in src/app/db_models.py: users, works, user_works, citing_works,
citing_work_keys, citations, alerts and support_limits. Firestore data is
not copied here; that is a separate step.

Revision ID: 0001
Revises: 
Create Date: 2026-11-07 03:20:52.912755+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
import sqlmodel
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = '0001'
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table('citing_works',
    sa.Column('id', sa.BigInteger(), nullable=False),
    sa.Column('key', sa.Text(), nullable=False),
    sa.Column('doi', sa.Text(), nullable=True),
    sa.Column('openalex_id', sa.Text(), nullable=True),
    sa.Column('url', sa.Text(), nullable=True),
    sa.Column('title', sa.Text(), nullable=False),
    sa.Column('authors', postgresql.ARRAY(sa.Text()), server_default=sa.text("'{}'::text[]"), nullable=False),
    sa.Column('affiliations', postgresql.ARRAY(sa.Text()), server_default=sa.text("'{}'::text[]"), nullable=False),
    sa.Column('year', sa.Integer(), nullable=True),
    sa.Column('publication_date', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_citing_works')),
    sa.UniqueConstraint('key', name=op.f('uq_citing_works_key'))
    )
    op.create_index(op.f('ix_citing_works_doi'), 'citing_works', ['doi'], unique=False)
    op.create_index(op.f('ix_citing_works_openalex_id'), 'citing_works', ['openalex_id'], unique=False)
    op.create_table('support_limits',
    sa.Column('key', sa.Text(), nullable=False),
    sa.Column('window_start', sa.DateTime(timezone=True), nullable=False),
    sa.Column('count', sa.Integer(), nullable=False),
    sa.PrimaryKeyConstraint('key', name=op.f('pk_support_limits'))
    )
    op.create_table('users',
    sa.Column('id', sqlmodel.sql.sqltypes.AutoString(length=128), nullable=False),
    sa.Column('email', sa.Text(), server_default=sa.text("''"), nullable=False),
    sa.Column('display_name', sa.Text(), nullable=True),
    sa.Column('notification_email', sa.Text(), nullable=True),
    sa.Column('verified_notification_email', sa.Text(), nullable=True),
    sa.Column('notify_enabled', sa.Boolean(), server_default=sa.text('true'), nullable=False),
    sa.Column('notify_new_publications', sa.Boolean(), server_default=sa.text('true'), nullable=False),
    sa.Column('scholar_url', sa.Text(), nullable=True),
    sa.Column('linked_author_id', sa.Text(), nullable=True),
    sa.Column('linked_author_name', sa.Text(), nullable=True),
    sa.Column('additional_linked_authors', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'[]'::jsonb"), nullable=False),
    sa.Column('name_aliases', postgresql.ARRAY(sa.Text()), server_default=sa.text("'{}'::text[]"), nullable=False),
    sa.Column('dismissed_work_keys', postgresql.ARRAY(sa.Text()), server_default=sa.text("'{}'::text[]"), nullable=False),
    sa.Column('last_import_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('last_manual_check_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('last_manual_sync_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('last_publication_sync_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('last_email_test_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('last_verification_email_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('last_confirm_email_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_users'))
    )
    op.create_index(op.f('ix_users_linked_author_id'), 'users', ['linked_author_id'], unique=False)
    op.create_table('works',
    sa.Column('id', sa.BigInteger(), nullable=False),
    sa.Column('key', sa.Text(), nullable=False),
    sa.Column('doi', sa.Text(), nullable=True),
    sa.Column('openalex_id', sa.Text(), nullable=True),
    sa.Column('title', sa.Text(), nullable=False),
    sa.Column('authors', postgresql.ARRAY(sa.Text()), server_default=sa.text("'{}'::text[]"), nullable=False),
    sa.Column('year', sa.Integer(), nullable=True),
    sa.Column('venue', sa.Text(), nullable=True),
    sa.Column('work_type', sa.Text(), nullable=True),
    sa.Column('topics', postgresql.ARRAY(sa.Text()), server_default=sa.text("'{}'::text[]"), nullable=False),
    sa.Column('openalex_citation_count', sa.Integer(), nullable=True),
    sa.Column('s2_citation_count', sa.Integer(), nullable=True),
    sa.Column('last_checked_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('last_check_failed_sources', postgresql.ARRAY(sa.Text()), server_default=sa.text("'{}'::text[]"), nullable=False),
    sa.Column('citation_window', sa.Integer(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_works')),
    sa.UniqueConstraint('doi', name=op.f('uq_works_doi')),
    sa.UniqueConstraint('key', name=op.f('uq_works_key'))
    )
    op.create_index(op.f('ix_works_openalex_id'), 'works', ['openalex_id'], unique=False)
    op.create_table('citations',
    sa.Column('id', sa.BigInteger(), nullable=False),
    sa.Column('work_id', sa.BigInteger(), nullable=False),
    sa.Column('citing_work_id', sa.BigInteger(), nullable=False),
    sa.Column('found_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['citing_work_id'], ['citing_works.id'], name=op.f('fk_citations_citing_work_id_citing_works'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['work_id'], ['works.id'], name=op.f('fk_citations_work_id_works'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_citations')),
    sa.UniqueConstraint('work_id', 'citing_work_id', name=op.f('uq_citations_work_id_citing_work_id'))
    )
    op.create_index(op.f('ix_citations_citing_work_id'), 'citations', ['citing_work_id'], unique=False)
    op.create_table('citing_work_keys',
    sa.Column('key', sa.Text(), nullable=False),
    sa.Column('citing_work_id', sa.BigInteger(), nullable=False),
    sa.ForeignKeyConstraint(['citing_work_id'], ['citing_works.id'], name=op.f('fk_citing_work_keys_citing_work_id_citing_works'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('key', name=op.f('pk_citing_work_keys'))
    )
    op.create_index(op.f('ix_citing_work_keys_citing_work_id'), 'citing_work_keys', ['citing_work_id'], unique=False)
    op.create_table('user_works',
    sa.Column('user_id', sqlmodel.sql.sqltypes.AutoString(length=128), nullable=False),
    sa.Column('work_id', sa.BigInteger(), nullable=False),
    sa.Column('added_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_user_works_user_id_users'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['work_id'], ['works.id'], name=op.f('fk_user_works_work_id_works'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('user_id', 'work_id', name=op.f('pk_user_works'))
    )
    op.create_index(op.f('ix_user_works_work_id'), 'user_works', ['work_id'], unique=False)
    op.create_table('alerts',
    sa.Column('id', sa.BigInteger(), nullable=False),
    sa.Column('user_id', sqlmodel.sql.sqltypes.AutoString(length=128), nullable=False),
    sa.Column('citation_id', sa.BigInteger(), nullable=False),
    sa.Column('seen', sa.Boolean(), server_default=sa.text('false'), nullable=False),
    sa.Column('emailed', sa.Boolean(), server_default=sa.text('false'), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['citation_id'], ['citations.id'], name=op.f('fk_alerts_citation_id_citations'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_alerts_user_id_users'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_alerts')),
    sa.UniqueConstraint('user_id', 'citation_id', name=op.f('uq_alerts_user_id_citation_id'))
    )
    op.create_index(op.f('ix_alerts_citation_id'), 'alerts', ['citation_id'], unique=False)
    op.create_index('ix_alerts_unemailed', 'alerts', ['user_id'], unique=False, postgresql_where=sa.text('NOT emailed'))
    op.create_index('ix_alerts_unseen', 'alerts', ['user_id'], unique=False, postgresql_where=sa.text('NOT seen'))
    op.create_index(op.f('ix_alerts_user_id_created_at'), 'alerts', ['user_id', 'created_at'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_alerts_user_id_created_at'), table_name='alerts')
    op.drop_index('ix_alerts_unseen', table_name='alerts', postgresql_where=sa.text('NOT seen'))
    op.drop_index('ix_alerts_unemailed', table_name='alerts', postgresql_where=sa.text('NOT emailed'))
    op.drop_index(op.f('ix_alerts_citation_id'), table_name='alerts')
    op.drop_table('alerts')
    op.drop_index(op.f('ix_user_works_work_id'), table_name='user_works')
    op.drop_table('user_works')
    op.drop_index(op.f('ix_citing_work_keys_citing_work_id'), table_name='citing_work_keys')
    op.drop_table('citing_work_keys')
    op.drop_index(op.f('ix_citations_citing_work_id'), table_name='citations')
    op.drop_table('citations')
    op.drop_index(op.f('ix_works_openalex_id'), table_name='works')
    op.drop_table('works')
    op.drop_index(op.f('ix_users_linked_author_id'), table_name='users')
    op.drop_table('users')
    op.drop_table('support_limits')
    op.drop_index(op.f('ix_citing_works_openalex_id'), table_name='citing_works')
    op.drop_index(op.f('ix_citing_works_doi'), table_name='citing_works')
    op.drop_table('citing_works')
