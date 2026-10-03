"""Folders for dashboards, and locked ones

Dashboards accumulate and the ones that matter get lost among the ones somebody
made on a Tuesday. A folder gives a set of them a stated meaning, and a locked
folder is one only administrators can change -- which is what turns "business
KPIs" from a label into a statement about what has been through review.

Revision ID: d5f93ac17b82
Revises: c4a81d6be207
Create Date: 2026-10-02

"""

import sqlalchemy as sa
from alembic import op

revision = "d5f93ac17b82"
down_revision = "c4a81d6be207"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "dashboard_folders",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("org_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("meaning", sa.Text(), nullable=True),
        sa.Column("locked", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_by_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["org_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(["created_by_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("dashboard_folders_org_name", "dashboard_folders", ["org_id", "name"], unique=True)
    op.add_column("dashboards", sa.Column("folder_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "dashboards_folder_id_fkey",
        "dashboards",
        "dashboard_folders",
        ["folder_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade():
    op.drop_constraint("dashboards_folder_id_fkey", "dashboards", type_="foreignkey")
    op.drop_column("dashboards", "folder_id")
    op.drop_index("dashboard_folders_org_name", table_name="dashboard_folders")
    op.drop_table("dashboard_folders")
