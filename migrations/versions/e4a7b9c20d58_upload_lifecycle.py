"""Uploaded files get a life.

An uploaded file is the only copy of itself, and until now nothing bounded how
long SQLDesk kept one. On 2026-09-28 the development disk reached 100% and took
Postgres with it.

Existing uploads are given an expiry dated from *now* rather than from when
they were uploaded. Dating from upload would make every file on an install that
has been running a week expire the moment this migration lands, which is the
one thing the policy promises never to do: nothing goes without a warning
somebody could act on, and nobody has been warned about these.

Revision ID: e4a7b9c20d58
Revises: d7c2f84b6e13
"""

import sqlalchemy as sa
from alembic import op

revision = "e4a7b9c20d58"
down_revision = "d7c2f84b6e13"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("uploaded_files", sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("uploaded_files", sa.Column("kept_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("uploaded_files", sa.Column("kept_by_id", sa.Integer(), nullable=True))
    op.add_column("uploaded_files", sa.Column("last_queried_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("uploaded_files", sa.Column("unloaded_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column(
        "uploaded_files", sa.Column("expiry_warning_sent_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.create_foreign_key(
        "uploaded_files_kept_by_id_fkey", "uploaded_files", "users", ["kept_by_id"], ["id"]
    )
    # Dated from now, so the first warning goes out a day before anything
    # actually expires. `now()` is the database's clock, which is the same one
    # the application compares against.
    op.execute(
        "UPDATE uploaded_files SET expires_at = now() + interval '7 days' WHERE expires_at IS NULL"
    )
    # The two columns the lifecycle scans every hour.
    op.create_index("uploaded_files_expires_at", "uploaded_files", ["expires_at"])
    op.create_index("uploaded_files_last_queried_at", "uploaded_files", ["last_queried_at"])


def downgrade():
    op.drop_index("uploaded_files_last_queried_at", table_name="uploaded_files")
    op.drop_index("uploaded_files_expires_at", table_name="uploaded_files")
    op.drop_constraint("uploaded_files_kept_by_id_fkey", "uploaded_files", type_="foreignkey")
    for column in (
        "expiry_warning_sent_at",
        "unloaded_at",
        "last_queried_at",
        "kept_by_id",
        "kept_at",
        "expires_at",
    ):
        op.drop_column("uploaded_files", column)
