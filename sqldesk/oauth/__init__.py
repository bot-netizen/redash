"""
OAuth 2.1 for MCP clients.

Why, in one sentence: an MCP client authenticating with a personal API key is
a long-lived secret pasted outside SSO -- not revoked when somebody leaves,
invisible in the identity provider, and identical whether a person or a script
is holding it. With OAuth the client opens a browser, the person signs in the
way they always do (which is SAML where SAML is on), and the client gets a
token that expires, can be revoked, and is listed on the person's own profile.

SQLDesk is both the resource server and the authorization server. That is the
small deployment the MCP specification expects, and splitting them would mean
running a second service for a feature most installs turn on for a handful of
people.

What is deliberately not here:

- **No implicit flow and no client secrets.** Authorization code with PKCE
  (S256 only), as OAuth 2.1 requires. A desktop client cannot keep a secret,
  so pretending it can buys nothing and invites a secret in a config file.
- **No JWTs.** Opaque random tokens looked up in a table. A self-contained
  token cannot be revoked before it expires, and revocation is the whole
  reason for doing this.
- **No scope negotiation.** One scope, `mcp:read`, because the tools are
  read-only and a consent screen with choices nobody can reason about is a
  consent screen nobody reads. A writing tool would get its own scope, and
  these tokens would not reach it.
- **No API key removal.** Scripts and headless setups need them.

Tokens are stored as SHA-256 digests. A bearer token is a password: it is
presented as proof, so anything that can read the table can be its owner.
"""

import datetime
import logging
import os
import time

from authlib.integrations.flask_oauth2 import AuthorizationServer
from authlib.oauth2.rfc6749 import grants
from authlib.oauth2.rfc6749.errors import InvalidRequestError
from authlib.oauth2.rfc7009 import RevocationEndpoint as BaseRevocationEndpoint
from authlib.oauth2.rfc7636 import CodeChallenge

from sqldesk import models, redis_connection, settings
from sqldesk.utils import generate_token, utcnow

logger = logging.getLogger(__name__)

#: Bytes of randomness in a token, before hex. 32 is 256 bits, which is what
#: makes the unsalted digest in the models safe: there is nothing to guess.
TOKEN_BYTES = 32

#: How long a code lives. The specification says short; a redirect back to a
#: waiting client has no honest reason to take longer.
CODE_SECONDS = 300

#: Both token kinds carry a prefix. Two reasons, and the second is the real
#: one: `/mcp` can tell an OAuth token from an API key with one lookup instead
#: of two, and a leaked token is recognisable -- in a log, in a paste, by a
#: secret scanner -- as a SQLDesk MCP credential rather than 64 anonymous hex
#: characters nobody can attribute or revoke.
ACCESS_PREFIX = "sdmcp_a_"
REFRESH_PREFIX = "sdmcp_r_"

#: `last_used_at` is written at most this often per token. Every MCP request
#: would otherwise be a write, and a client polling for tool lists would turn
#: a read-only endpoint into one UPDATE per call.
LAST_USED_RESOLUTION = 60


def _query_client(client_id):
    return models.OAuthClient.query.filter(models.OAuthClient.client_id == client_id).first()


def _save_token(token_data, request):
    """
    Store a granted token.

    Called for both the code exchange and a refresh. The digests go in, the
    plain values go back to the client in authlib's response and are never
    stored anywhere.
    """
    user = request.user
    refresh_token = token_data.get("refresh_token")
    existing = getattr(request, "sqldesk_previous_token", None)

    row = existing or models.OAuthToken(
        client_id=request.client.client_id,
        org_id=user.org_id,
        user_id=user.id,
    )
    row.access_token_digest = models._token_digest(token_data["access_token"])
    row.access_expires_at = utcnow() + _seconds(models.OAUTH_ACCESS_TOKEN_SECONDS)
    row.scope = token_data.get("scope") or models.OAUTH_SCOPE
    if refresh_token:
        # Rotated on every use, and the window starts again: a refresh token
        # that is never replaced is a long-lived secret with extra steps.
        row.refresh_token_digest = models._token_digest(refresh_token)
        row.refresh_expires_at = utcnow() + _seconds(models.OAUTH_REFRESH_TOKEN_SECONDS)
    row.revoked_at = None
    models.db.session.add(row)
    models.db.session.commit()


def _seconds(count):
    return datetime.timedelta(seconds=count)


class _RequiredS256Challenge(CodeChallenge):
    """
    PKCE, actually required, and S256 only.

    authlib 1.7.2 takes `required=True` and does not use it:
    `validate_code_challenge` returns early when neither `code_challenge` nor
    `code_challenge_method` is present, so a client that simply omits both is
    accepted, and the matching check at the token endpoint only fires when a
    verifier was sent without a challenge. Passing `required=True` and
    believing it is how a 2.1 server quietly becomes a 2.0 one.

    `plain` is refused as well. It is in the RFC and provides nothing: the
    verifier travels in the clear, so anyone who saw the challenge can produce
    it, and supporting it means a client may pick it.
    """

    def validate_code_challenge(self, grant, redirect_uri):
        payload = grant.request.payload
        challenge = payload.data.get("code_challenge")
        method = payload.data.get("code_challenge_method")
        # One check rather than two. Separate ones read better and the first is
        # unreachable as the deciding test: a request with no challenge arrives
        # either with no method or a method that is not S256, which the second
        # catches, or with S256, which authlib's own check catches. Mutation
        # testing found the "missing challenge" branch could be deleted with no
        # test able to tell -- so it is not a check, it is a comment, and this
        # is the honest shape.
        if not challenge or method != "S256":
            raise InvalidRequestError("PKCE is required: send code_challenge with code_challenge_method=S256.")
        return super().validate_code_challenge(grant, redirect_uri)


class _AuthorizationCodeGrant(grants.AuthorizationCodeGrant):
    """
    The one flow. PKCE is enforced by the `CodeChallenge(required=True)`
    extension registered below, and S256 by `CODE_CHALLENGE_METHODS`.
    """

    #: No secret, so no way to authenticate at the token endpoint. This is
    #: what makes the client public, and it is checked rather than assumed:
    #: a client presenting a secret is refused rather than quietly accepted.
    TOKEN_ENDPOINT_AUTH_METHODS = ["none"]
    #: `plain` is in the PKCE RFC and provides nothing: the verifier travels
    #: in the clear and anyone who saw the challenge can produce it.
    CODE_CHALLENGE_METHODS = ["S256"]

    def save_authorization_code(self, code, request):
        challenge = request.payload.data.get("code_challenge")
        method = request.payload.data.get("code_challenge_method")
        models.db.session.add(
            models.OAuthAuthorizationCode(
                code_digest=models._token_digest(code),
                client_id=request.client.client_id,
                user_id=request.user.id,
                redirect_uri=request.payload.redirect_uri,
                scope=request.payload.scope or models.OAUTH_SCOPE,
                code_challenge=challenge,
                code_challenge_method=method,
                expires_at=utcnow() + _seconds(CODE_SECONDS),
            )
        )
        models.db.session.commit()

    def query_authorization_code(self, code, client):
        row = models.OAuthAuthorizationCode.query.filter(
            models.OAuthAuthorizationCode.code_digest == models._token_digest(code),
            models.OAuthAuthorizationCode.client_id == client.client_id,
        ).first()
        if row is not None and not row.is_expired():
            return row
        return None

    def delete_authorization_code(self, authorization_code):
        # Single use. Deleted rather than marked, because a spent code has no
        # question anyone asks of it later.
        models.db.session.delete(authorization_code)
        models.db.session.commit()

    def authenticate_user(self, authorization_code):
        user = authorization_code.user
        # Checked here and not only at the consent page: the gap between
        # agreeing and exchanging is five minutes, and disabling an account
        # has to take effect inside it.
        if user is None or user.is_disabled:
            return None
        return user


class _RefreshTokenGrant(grants.RefreshTokenGrant):
    TOKEN_ENDPOINT_AUTH_METHODS = ["none"]
    #: The access token is replaced and so is the refresh token; see
    #: `_save_token`.
    INCLUDE_NEW_REFRESH_TOKEN = True

    def authenticate_refresh_token(self, refresh_token):
        row = models.OAuthToken.query.filter(
            models.OAuthToken.refresh_token_digest == models._token_digest(refresh_token)
        ).first()
        if row is None or row.is_revoked() or row.refresh_token_expired:
            return None
        # Refreshing updates this row rather than adding another, so the
        # person's list of connected apps stays a list of connections.
        self.request.sqldesk_previous_token = row
        return row

    def authenticate_user(self, credential):
        user = credential.user
        if user is None or user.is_disabled:
            return None
        return user

    def revoke_old_credential(self, credential):
        # Nothing to do: `_save_token` overwrites this row's digests, so the
        # old pair stops working the moment the new one is stored.
        pass


class _RevocationEndpoint(BaseRevocationEndpoint):
    """
    RFC 7009. A client that is uninstalled should be able to hand the token
    back rather than leave it valid until it expires.
    """

    CLIENT_AUTH_METHODS = ["none"]

    def query_token(self, token_string, token_type_hint):
        digest = models._token_digest(token_string)
        query = models.OAuthToken.query
        if token_type_hint == "access_token":
            return query.filter(models.OAuthToken.access_token_digest == digest).first()
        if token_type_hint == "refresh_token":
            return query.filter(models.OAuthToken.refresh_token_digest == digest).first()
        return (
            query.filter(models.OAuthToken.access_token_digest == digest).first()
            or query.filter(models.OAuthToken.refresh_token_digest == digest).first()
        )

    def revoke_token(self, token, request):
        token.revoke()
        models.db.session.commit()


def _generate_token(grant_type, client, user=None, scope=None, expires_in=None, include_refresh_token=True):
    """
    The tokens themselves: 32 random bytes each, behind a prefix.

    Registered rather than left to authlib's default so the prefixes above are
    guaranteed -- and so the access token's lifetime is this server's decision
    in one place rather than a grant's class attribute.
    """
    token = {
        "token_type": "Bearer",
        "access_token": ACCESS_PREFIX + generate_token(TOKEN_BYTES * 2),
        "expires_in": models.OAUTH_ACCESS_TOKEN_SECONDS,
        "scope": scope or models.OAUTH_SCOPE,
    }
    if include_refresh_token:
        token["refresh_token"] = REFRESH_PREFIX + generate_token(TOKEN_BYTES * 2)
    return token


def looks_like_an_oauth_token(value):
    """
    Whether this bearer string is one of ours rather than an API key.

    Asked by `/mcp` so it knows which table to look in. A false answer costs
    nothing but a failed lookup -- it is a routing hint, never a credential
    check.
    """
    return bool(value) and value.startswith((ACCESS_PREFIX, REFRESH_PREFIX))


server = AuthorizationServer()


def init_app(app):
    """Wire the grants onto the app. Called from sqldesk.app.create_app."""
    if settings.MCP_OAUTH_ALLOW_HTTP:
        # authlib's own switch, and the only one it reads. Set here rather than
        # left to whoever starts the process, so the decision is a SQLDesk
        # setting an administrator can see in their values file instead of an
        # environment variable with a library's name on it.
        os.environ["AUTHLIB_INSECURE_TRANSPORT"] = "1"
        logger.warning(
            "SQLDESK_MCP_OAUTH_ALLOW_HTTP is on: authorization codes and tokens may cross the "
            "network in the clear. Intended for a local install only."
        )
    server.init_app(app, query_client=_query_client, save_token=_save_token)
    server.register_token_generator("default", _generate_token)
    # Our own subclass, because authlib's `required=True` does not require
    # anything in this version. See `_RequiredS256Challenge`.
    server.register_grant(_AuthorizationCodeGrant, [_RequiredS256Challenge(required=True)])
    server.register_grant(_RefreshTokenGrant)
    server.register_endpoint(_RevocationEndpoint)


def new_client_id():
    return generate_token(32)


def token_for_bearer(value, org):
    """
    The live token behind a bearer string, or None.

    Checked in one place so `/mcp` cannot accidentally accept a revoked or
    expired one. The organisation is part of the question: a token is issued
    to a user, a user belongs to one organisation, and a token presented to
    another organisation's endpoint is refused rather than silently answered
    with that organisation's data.
    """
    if not value:
        return None
    if not settings.MCP_OAUTH_ENABLED or not settings.FEATURE_AI:
        # Switching it off has to mean no token is accepted. Otherwise an
        # administrator who turns it off because they want API keys only has
        # changed nothing people can see: every connected client keeps working
        # until its refresh window runs out, which is a month.
        return None
    row = models.OAuthToken.query.filter(models.OAuthToken.access_token_digest == models._token_digest(value)).first()
    if row is None or row.is_revoked() or row.is_expired():
        return None
    if org is not None and row.org_id != org.id:
        return None
    if row.user is None or row.user.is_disabled:
        return None
    return row


def note_used(token):
    """
    Record that a token was used, at most once a minute.

    Through Redis rather than by reading the column: the point is to avoid a
    write per request, and checking the column to decide whether to write is
    still a read per request on the row we are about to lock.
    """
    try:
        key = "oauth:used:{}".format(token.id)
        if not redis_connection.set(key, int(time.time()), ex=LAST_USED_RESOLUTION, nx=True):
            return
    except Exception:
        # Without Redis, note it every time rather than never: a wrong
        # "last used" is worse than a frequent write.
        logger.warning("could not rate-limit the oauth last-used write", exc_info=True)
    token.last_used_at = utcnow()
    models.db.session.commit()


def revoke_for_user(user, reason):
    """
    Every token this person holds. Called when an account is disabled.

    The reason is logged rather than stored: the row says when, the log says
    why, and a column would be a second thing to keep in step with the
    handful of places that call this.
    """
    tokens = models.OAuthToken.query.filter(
        models.OAuthToken.user_id == user.id, models.OAuthToken.revoked_at.is_(None)
    ).all()
    for token in tokens:
        token.revoke()
    if tokens:
        models.db.session.commit()
        logger.info("revoked %s oauth token(s) for user=%s reason=%s", len(tokens), user.id, reason)
    return len(tokens)
