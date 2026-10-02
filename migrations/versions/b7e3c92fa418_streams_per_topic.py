"""A cluster has as many streams as it has enabled topics

A stream's data source used to be one topic, so one stream per data source was
right and the unique index said so. The data source is now the *cluster*, and
each topic somebody enables on it is a stream of its own -- so the pair is what
has to be unique, and enabling the same topic twice is the mistake worth
refusing.

Revision ID: b7e3c92fa418
Revises: a1c84f27e6b3
Create Date: 2026-10-02

"""

from alembic import op

revision = "b7e3c92fa418"
down_revision = "a1c84f27e6b3"
branch_labels = None
depends_on = None


def upgrade():
    op.drop_index("streams_data_source_id", table_name="streams")
    op.create_index("streams_data_source_topic", "streams", ["data_source_id", "topic"], unique=True)


def downgrade():
    # Going back means one stream per data source again, which a cluster with
    # two enabled topics cannot satisfy. The rows have to go first; they are a
    # window of the last few minutes, and the windows themselves are files that
    # the cleanup removes once nothing points at them.
    op.execute(
        "DELETE FROM streams WHERE id NOT IN "
        "(SELECT min(id) FROM streams GROUP BY data_source_id)"
    )
    op.drop_index("streams_data_source_topic", table_name="streams")
    op.create_index("streams_data_source_id", "streams", ["data_source_id"], unique=True)
