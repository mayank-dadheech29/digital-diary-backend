"""add_search_text_tsvector

Revision ID: c4d9f6e1a2b3
Revises: 8be6196bd921
Create Date: 2026-03-01 00:10:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'c4d9f6e1a2b3'
down_revision: Union[str, Sequence[str], None] = '8be6196bd921'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('contacts', sa.Column('search_text', postgresql.TSVECTOR(), nullable=True))
    op.add_column('transactions', sa.Column('search_text', postgresql.TSVECTOR(), nullable=True))

    op.execute("""
    CREATE OR REPLACE FUNCTION update_search_vectors() RETURNS trigger AS $$
    BEGIN
      IF TG_TABLE_NAME = 'contacts' THEN
        NEW.search_text :=
          setweight(to_tsvector('simple', coalesce(NEW.full_name, '')), 'A') ||
          setweight(to_tsvector('simple', coalesce(NEW.primary_title, '')), 'B') ||
          setweight(to_tsvector('simple', coalesce(NEW.primary_org, '')), 'B') ||
          setweight(to_tsvector('simple', coalesce(NEW.job_title_category, '')), 'B') ||
          setweight(to_tsvector('simple', coalesce(NEW.dynamic_details::text, '')), 'C');
        RETURN NEW;
      ELSIF TG_TABLE_NAME = 'transactions' THEN
        NEW.search_text :=
          setweight(to_tsvector('simple', coalesce(NEW.title, '')), 'A') ||
          setweight(to_tsvector('simple', coalesce(NEW.description, '')), 'B') ||
          setweight(to_tsvector('simple', coalesce(NEW.type, '')), 'B') ||
          setweight(to_tsvector('simple', coalesce(NEW.category, '')), 'B') ||
          setweight(to_tsvector('simple', coalesce(NEW.currency, '')), 'C') ||
          setweight(to_tsvector('simple', coalesce(NEW.amount::text, '')), 'C') ||
          setweight(
            to_tsvector(
              'simple',
              coalesce((SELECT c.full_name FROM contacts c WHERE c.id = NEW.contact_id), '') || ' ' ||
              coalesce((SELECT c.primary_org FROM contacts c WHERE c.id = NEW.contact_id), '')
            ),
            'A'
          );
        RETURN NEW;
      END IF;

      RETURN NEW;
    END
    $$ LANGUAGE plpgsql;
    """)

    op.execute("""
    CREATE TRIGGER contacts_search_text_tg
    BEFORE INSERT OR UPDATE ON contacts
    FOR EACH ROW EXECUTE FUNCTION update_search_vectors();
    """)

    op.execute("""
    CREATE TRIGGER transactions_search_text_tg
    BEFORE INSERT OR UPDATE ON transactions
    FOR EACH ROW EXECUTE FUNCTION update_search_vectors();
    """)

    op.execute("""
    UPDATE contacts
    SET search_text =
      setweight(to_tsvector('simple', coalesce(full_name, '')), 'A') ||
      setweight(to_tsvector('simple', coalesce(primary_title, '')), 'B') ||
      setweight(to_tsvector('simple', coalesce(primary_org, '')), 'B') ||
      setweight(to_tsvector('simple', coalesce(job_title_category, '')), 'B') ||
      setweight(to_tsvector('simple', coalesce(dynamic_details::text, '')), 'C');
    """)

    op.execute("""
    UPDATE transactions t
    SET search_text =
      setweight(to_tsvector('simple', coalesce(t.title, '')), 'A') ||
      setweight(to_tsvector('simple', coalesce(t.description, '')), 'B') ||
      setweight(to_tsvector('simple', coalesce(t.type, '')), 'B') ||
      setweight(to_tsvector('simple', coalesce(t.category, '')), 'B') ||
      setweight(to_tsvector('simple', coalesce(t.currency, '')), 'C') ||
      setweight(to_tsvector('simple', coalesce(t.amount::text, '')), 'C') ||
      setweight(to_tsvector('simple', coalesce(c.full_name, '') || ' ' || coalesce(c.primary_org, '')), 'A')
    FROM contacts c
    WHERE c.id = t.contact_id;
    """)

    op.create_index('ix_contacts_search_text', 'contacts', ['search_text'], unique=False, postgresql_using='gin')
    op.create_index('ix_transactions_search_text', 'transactions', ['search_text'], unique=False, postgresql_using='gin')


def downgrade() -> None:
    op.drop_index('ix_transactions_search_text', table_name='transactions', postgresql_using='gin')
    op.drop_index('ix_contacts_search_text', table_name='contacts', postgresql_using='gin')

    op.execute("DROP TRIGGER IF EXISTS transactions_search_text_tg ON transactions;")
    op.execute("DROP TRIGGER IF EXISTS contacts_search_text_tg ON contacts;")

    op.execute("DROP FUNCTION IF EXISTS update_search_vectors();")

    op.drop_column('transactions', 'search_text')
    op.drop_column('contacts', 'search_text')
