"""Who started a stream

The per-person limit on running streams needs to know whose each one is, and
the page that lists them needs to say so: "stop this, it is yours" and "stop
this, four other people are looking at it" are different sentences.

Null where a pin or a schedule started it rather than a person.

Revision ID: c4a81d6be207
Revises: b7e3c92fa418
Create Date: 2026-10-02

"""

import sqlalchemy as sa
from alembic import op

revision = "c4a81d6be207"
down_revision = "b7e3c92fa418"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("streams", sa.Column("started_by_id", sa.Integer(), nullable=True))
    op.create_foreign_key("streams_started_by_id_fkey", "streams", "users", ["started_by_id"], ["id"])


def downgrade():
    op.drop_constraint("streams_started_by_id_fkey", "streams", type_="foreignkey")
    op.drop_column("streams", "started_by_id")
