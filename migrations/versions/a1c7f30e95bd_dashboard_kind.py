"""A dashboard declares whether it is streaming

The kind used to be worked out from the widgets: a dashboard was streaming if
any widget drew on a window. Derived means it cannot be forgotten, which was
the reasoning -- but it also cannot answer for a dashboard that has no widgets
yet, and a new one therefore looked ordinary until its first streaming widget
landed. While the two lists were filters over one set that was merely untidy.
Now that they are halves of a partition, it reads as a dashboard disappearing
from under its author.

Backfilled with exactly the rule that used to be applied at read time, so no
existing dashboard changes which list it appears in.

Revision ID: a1c7f30e95bd
Revises: e8c1427d9f06
Create Date: 2026-10-03

"""

import sqlalchemy as sa
from alembic import op

revision = "a1c7f30e95bd"
down_revision = "e8c1427d9f06"
branch_labels = None
depends_on = None


def streaming_types():
    """
    The data source types whose tables are windows, asked of the registered
    runners the way the application asks.

    Falling back to the one type that existed when this was written, because a
    migration must still do the right thing in an environment where the
    optional Kafka dependency is not installed -- `import_query_runners()`
    skips a runner whose SDK is missing, and a backfill that read an empty list
    there would quietly file every streaming dashboard as an ordinary one.
    """
    try:
        from sqldesk.models import streaming_source_types

        found = [name for name in streaming_source_types() if name != "__none__"]
    except Exception:
        found = []
    return found or ["kafka_stream"]


def upgrade():
    op.add_column(
        "dashboards",
        sa.Column("kind", sa.String(length=20), nullable=False, server_default="saved"),
    )
    op.create_index("ix_dashboards_kind", "dashboards", ["kind"])

    op.execute(
        sa.text(
            """
            UPDATE dashboards SET kind = 'streaming'
             WHERE id IN (
                   SELECT w.dashboard_id
                     FROM widgets w
                     JOIN visualizations v ON v.id = w.visualization_id
                     JOIN queries q ON q.id = v.query_id
                     JOIN data_sources d ON d.id = q.data_source_id
                    WHERE d.type IN :types
             )
            """
        ).bindparams(sa.bindparam("types", value=tuple(streaming_types()), expanding=True))
    )


def downgrade():
    op.drop_index("ix_dashboards_kind", table_name="dashboards")
    op.drop_column("dashboards", "kind")
