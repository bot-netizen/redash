"""A saved query a curator says is the right answer.

The strongest thing the catalog can offer a model, and the one part of it
that cannot be mined: somebody has to read the SQL and say yes. `query_hash`
records which SQL they read, so an edit afterwards stops the claim counting
rather than silently transferring it to text nobody checked.

Revision ID: b8d5e1f70a24
Revises: c4f1a8e05d37
"""

import sqlalchemy as sa
from alembic import op

revision = "b8d5e1f70a24"
down_revision = "c4f1a8e05d37"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "catalog_verified_queries",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("org_id", sa.Integer(), nullable=False),
        sa.Column("query_id", sa.Integer(), nullable=False),
        sa.Column("verified_by_id", sa.Integer(), nullable=False),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("query_hash", sa.String(length=32), nullable=False),
        sa.Column("question", sa.Text(), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        # The verification dies with the query. A row pointing at a deleted
        # query is a claim about nothing, and the catalog page would have to
        # carry code to hide it.
        sa.ForeignKeyConstraint(["query_id"], ["queries.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["org_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(["verified_by_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    # One verification per query: "verified" is a state, not a log. Who last
    # confirmed it and when is on the row.
    op.create_index(
        "catalog_verified_queries_query_id",
        "catalog_verified_queries",
        ["query_id"],
        unique=True,
    )


def downgrade():
    op.drop_index("catalog_verified_queries_query_id", table_name="catalog_verified_queries")
    op.drop_table("catalog_verified_queries")
