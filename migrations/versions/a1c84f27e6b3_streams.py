"""Kafka topics as data sources, and their per-minute rollups.

A stream is a window, not a pipeline: the raw events live in a DuckDB file per
stream and are truncated continuously, so nothing here is the data. These two
tables are the state a page reads and the settings a person sets, plus the
rollups -- which are the part that outlives a restart and the part a question
about this morning reads.

Revision ID: a1c84f27e6b3
Revises: f9b3d61c48a7
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "a1c84f27e6b3"
down_revision = "f9b3d61c48a7"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "streams",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("org_id", sa.Integer(), nullable=False),
        sa.Column("data_source_id", sa.Integer(), nullable=False),
        sa.Column("topic", sa.String(length=255), nullable=False),
        # 0 means "use the install's setting", so a stream carries an override
        # only where somebody set one.
        sa.Column("row_budget", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("events_per_second", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("observed_rate", postgresql.DOUBLE_PRECISION(), nullable=False, server_default="0"),
        sa.Column("window_seconds", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("sample_rate", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("rows", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("malformed", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("columns", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("schema_state", sa.String(length=16), nullable=False, server_default="inferred"),
        sa.Column("group_by", postgresql.ARRAY(sa.Unicode()), nullable=True),
        sa.Column("measures", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("last_viewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("pinned", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("last_flush_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["org_id"], ["organizations.id"]),
        # The stream dies with its data source. A stream whose source is gone
        # has no broker and no credentials; keeping the row would be keeping a
        # consumer nobody can start.
        sa.ForeignKeyConstraint(["data_source_id"], ["data_sources.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    # One stream per data source: a topic *is* the data source, so two would be
    # two answers to "what does this source read".
    op.create_index("streams_data_source_id", "streams", ["data_source_id"], unique=True)

    op.create_table(
        "stream_rollups",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("stream_id", sa.Integer(), nullable=False),
        sa.Column("minute", sa.DateTime(timezone=True), nullable=False),
        sa.Column("group_key", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("is_other", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("values", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        # What the stream was sampling at when this minute was rolled up, so a
        # count can be scaled back up honestly rather than quietly multiplied.
        sa.Column("sample_rate", sa.Integer(), nullable=False, server_default="1"),
        sa.ForeignKeyConstraint(["stream_id"], ["streams.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    # Every read is "this stream, this period", and the cleanup is "older than".
    op.create_index("stream_rollups_stream_minute", "stream_rollups", ["stream_id", "minute"])


def downgrade():
    op.drop_index("stream_rollups_stream_minute", table_name="stream_rollups")
    op.drop_table("stream_rollups")
    op.drop_index("streams_data_source_id", table_name="streams")
    op.drop_table("streams")
