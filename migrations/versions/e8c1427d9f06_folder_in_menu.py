"""Which folders earn a place in the Dashboards menu

An install ends up with more folders than fit in a dropdown, and a menu of
thirty is a menu nobody reads. The few people use daily are chosen; the rest
live on the folders page.

Revision ID: e8c1427d9f06
Revises: d5f93ac17b82
Create Date: 2026-10-03

"""

import sqlalchemy as sa
from alembic import op

revision = "e8c1427d9f06"
down_revision = "d5f93ac17b82"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "dashboard_folders",
        sa.Column("in_menu", sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade():
    op.drop_column("dashboard_folders", "in_menu")
