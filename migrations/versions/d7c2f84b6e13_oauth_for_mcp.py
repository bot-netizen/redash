"""OAuth 2.1 for MCP clients.

An MCP client authenticating with a personal API key is a long-lived secret
outside SSO: not revoked when somebody leaves, invisible in the identity
provider, identical whether a person or a script holds it. These three tables
are what it takes to replace it with a token that expires, can be revoked, and
is listed on its owner's profile.

Tokens and codes are stored as SHA-256 digests. A bearer token is a password:
it is presented as proof, so anything that can read the table can be its
owner.

Revision ID: d7c2f84b6e13
Revises: b8d5e1f70a24
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "d7c2f84b6e13"
down_revision = "b8d5e1f70a24"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "oauth_clients",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("client_id", sa.String(length=48), nullable=False),
        sa.Column("redirect_uris", postgresql.ARRAY(sa.Unicode()), nullable=False),
        sa.Column("client_uri", sa.String(length=1024), nullable=True),
        sa.Column("registered_from", sa.String(length=64), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        # Not scoped to an organisation: the same client software is used by
        # everybody, and a registration carries no authority of its own.
        sa.UniqueConstraint("client_id"),
    )
    op.create_table(
        "oauth_authorization_codes",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("code_digest", sa.String(length=64), nullable=False),
        sa.Column("client_id", sa.String(length=48), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("redirect_uri", sa.String(length=1024), nullable=True),
        sa.Column("scope", sa.String(length=255), nullable=True),
        sa.Column("code_challenge", sa.String(length=128), nullable=False),
        sa.Column("code_challenge_method", sa.String(length=10), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code_digest"),
    )
    op.create_table(
        "oauth_tokens",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("client_id", sa.String(length=48), nullable=False),
        sa.Column("org_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("access_token_digest", sa.String(length=64), nullable=False),
        sa.Column("refresh_token_digest", sa.String(length=64), nullable=True),
        sa.Column("scope", sa.String(length=255), nullable=True),
        sa.Column("access_expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("refresh_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["org_id"], ["organizations.id"]),
        # The tokens die with the account. A row pointing at a deleted user is
        # a credential nobody can revoke from the UI.
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        # Unique, and therefore indexed: every MCP request is a lookup by it.
        sa.UniqueConstraint("access_token_digest"),
        sa.UniqueConstraint("refresh_token_digest"),
    )
    # "Which tokens does this person hold", for their profile and for revoking
    # all of them when the account is disabled.
    op.create_index("oauth_tokens_user_id", "oauth_tokens", ["user_id"])


def downgrade():
    op.drop_index("oauth_tokens_user_id", table_name="oauth_tokens")
    op.drop_table("oauth_tokens")
    op.drop_table("oauth_authorization_codes")
    op.drop_table("oauth_clients")
