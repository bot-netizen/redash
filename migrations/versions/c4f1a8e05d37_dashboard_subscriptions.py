"""Dashboard subscriptions: a dashboard, mailed to some people, on a schedule

Named `dashboard_subscriptions` rather than `subscriptions` because
`alert_subscriptions` already exists and means something else -- who hears
about an alert. The two have nothing to do with each other.

`recipient_ids` is a JSONB list of user ids rather than a join table. The only
question ever asked of it is "who, now", and that has to be re-answered at
send time anyway: access changes, and people leave. Never addresses -- a
subscription that could name one would be a way to mail a dashboard's contents
anywhere.

The index is the one the scheduler uses every minute: the active
subscriptions, oldest send first.

Revision ID: c4f1a8e05d37
Revises: a7e3c9d2b416
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "c4f1a8e05d37"
down_revision = "a7e3c9d2b416"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "dashboard_subscriptions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("org_id", sa.Integer(), nullable=True),
        sa.Column("dashboard_id", sa.Integer(), nullable=True),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("schedule", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("format", sa.String(length=10), nullable=True),
        sa.Column("recipient_ids", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("last_sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["dashboard_id"], ["dashboards.id"]),
        sa.ForeignKeyConstraint(["org_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )

    # What the scheduler asks every minute: which active subscriptions are due.
    op.create_index(
        "dashboard_subscriptions_due",
        "dashboard_subscriptions",
        ["active", "last_sent_at"],
    )

    # And what the dashboard page asks: who is subscribed to this one.
    op.create_index(
        "dashboard_subscriptions_dashboard_id",
        "dashboard_subscriptions",
        ["dashboard_id"],
    )


def downgrade():
    op.drop_index("dashboard_subscriptions_dashboard_id", table_name="dashboard_subscriptions")
    op.drop_index("dashboard_subscriptions_due", table_name="dashboard_subscriptions")
    op.drop_table("dashboard_subscriptions")
