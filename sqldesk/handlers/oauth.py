"""
The HTTP end of OAuth: discovery, consent, token, revocation, registration.

How a client finds all this, which is the part worth following: it posts to
`/mcp` with no credential, gets a 401 whose `WWW-Authenticate` names the
protected-resource metadata document (RFC 9728), reads from there which
authorization server to use, reads that server's metadata (RFC 8414), and only
then starts the flow. Nothing is configured by hand on the client beyond the
URL of this install.

Everything here is mounted at the root and under `/<org_slug>`, so a
multi-organisation install issues tokens per organisation and a client that
discovered one organisation's endpoints never reaches another's.
"""

import logging
import time
from urllib.parse import urlparse

from flask import jsonify, render_template, request
from flask_login import current_user, login_required

from sqldesk import features, models, oauth, redis_connection, settings
from sqldesk.authentication import current_org
from sqldesk.handlers.base import json_response, record_event, routes
from sqldesk.permissions import require_super_admin
from sqldesk.security import csrf

logger = logging.getLogger(__name__)

#: A registration is a claim, not an authority: anyone may register, and what
#: a registration can reach depends entirely on whose token it holds. The caps
#: are there so a loop cannot fill a table.
MAX_REDIRECT_URIS = 8
MAX_CLIENT_NAME = 120
REGISTRATIONS_PER_HOUR = 30


def _origin():
    """
    This install's base, as the client reached it.

    Built from the request rather than from `HOST`, because every URL in the
    discovery documents has to be one the client can actually open: a client
    that found us on a port-forward or behind a different name must not be
    sent to whatever an administrator typed into a setting. `HOST` is still
    used where no request exists, such as in an email.
    """
    root = request.url_root.rstrip("/")
    slug = (request.view_args or {}).get("org_slug")
    return "{}/{}".format(root, slug) if slug else root


def _unavailable():
    return not settings.FEATURE_AI or not settings.MCP_OAUTH_ENABLED


@csrf.exempt
@routes.route("/.well-known/oauth-protected-resource", methods=["GET"])
@routes.route("/<org_slug>/.well-known/oauth-protected-resource", methods=["GET"])
def oauth_protected_resource(org_slug=None):
    """
    RFC 9728. What this resource is and who vouches for tokens to it.

    Deliberately not behind a login: a client reads this *before* anyone has
    signed in, which is the whole point of it existing.
    """
    if _unavailable():
        return jsonify({"error": "not_found"}), 404
    origin = _origin()
    return jsonify(
        {
            "resource": "{}/mcp".format(origin),
            "authorization_servers": [origin],
            "scopes_supported": [models.OAUTH_SCOPE],
            # Header only. A token in a query string is written to every
            # access log between the client and here.
            "bearer_methods_supported": ["header"],
            "resource_name": "SQLDesk MCP",
        }
    )


@csrf.exempt
@routes.route("/.well-known/oauth-authorization-server", methods=["GET"])
@routes.route("/<org_slug>/.well-known/oauth-authorization-server", methods=["GET"])
def oauth_authorization_server(org_slug=None):
    """RFC 8414. What this authorization server supports -- and only that."""
    if _unavailable():
        return jsonify({"error": "not_found"}), 404
    origin = _origin()
    return jsonify(
        {
            "issuer": origin,
            "authorization_endpoint": "{}/oauth/authorize".format(origin),
            "token_endpoint": "{}/oauth/token".format(origin),
            "revocation_endpoint": "{}/oauth/revoke".format(origin),
            "registration_endpoint": "{}/oauth/register".format(origin),
            "scopes_supported": [models.OAUTH_SCOPE],
            "response_types_supported": ["code"],
            "grant_types_supported": ["authorization_code", "refresh_token"],
            # S256 only, and advertised as such so a client does not try
            # `plain` and get an error it could have avoided.
            "code_challenge_methods_supported": ["S256"],
            # Public clients. Nothing here keeps a secret.
            "token_endpoint_auth_methods_supported": ["none"],
            "revocation_endpoint_auth_methods_supported": ["none"],
        }
    )


@csrf.exempt
@routes.route("/oauth/register", methods=["POST"])
@routes.route("/<org_slug>/oauth/register", methods=["POST"])
def oauth_register(org_slug=None):
    """
    RFC 7591 dynamic client registration.

    Open, because that is what the specification intends for public clients
    and because the alternative is an administrator pasting a client id for
    every person who installs a client. A registration grants nothing: it
    names a client and a set of redirect URIs, and until somebody signs in and
    agrees on the consent page it can read nothing at all.

    What is checked is the shape. Redirect URIs must be absolute, and either
    https or a loopback address -- the two forms a native client is allowed to
    use. `http://` to anywhere else would let a code be sent in the clear.
    """
    if _unavailable():
        return jsonify({"error": "not_found"}), 404
    if not _registration_allowed():
        return jsonify({"error": "too_many_requests"}), 429

    body = request.get_json(force=True, silent=True)
    if not isinstance(body, dict):
        return jsonify({"error": "invalid_client_metadata", "error_description": "A JSON object is expected."}), 400

    uris = body.get("redirect_uris")
    if not isinstance(uris, list) or not uris:
        return jsonify({"error": "invalid_redirect_uri", "error_description": "`redirect_uris` is required."}), 400
    if len(uris) > MAX_REDIRECT_URIS:
        return (
            jsonify(
                {"error": "invalid_redirect_uri", "error_description": "At most {} URIs.".format(MAX_REDIRECT_URIS)}
            ),
            400,
        )
    for uri in uris:
        problem = _redirect_uri_problem(uri)
        if problem:
            return jsonify({"error": "invalid_redirect_uri", "error_description": problem}), 400

    method = body.get("token_endpoint_auth_method", "none")
    if method != "none":
        return (
            jsonify(
                {
                    "error": "invalid_client_metadata",
                    "error_description": "Only public clients are supported: token_endpoint_auth_method must be none.",
                }
            ),
            400,
        )

    name = str(body.get("client_name") or "An MCP client")[:MAX_CLIENT_NAME]
    client = models.OAuthClient(
        name=name,
        client_id=oauth.new_client_id(),
        redirect_uris=list(uris),
        client_uri=str(body.get("client_uri") or "")[:1024] or None,
        registered_from=(request.remote_addr or "")[:64] or None,
    )
    models.db.session.add(client)
    models.db.session.commit()

    return (
        jsonify(
            {
                "client_id": client.client_id,
                "client_id_issued_at": int(client.created_at.timestamp()),
                "client_name": client.name,
                "redirect_uris": client.redirect_uris,
                "grant_types": ["authorization_code", "refresh_token"],
                "response_types": ["code"],
                "token_endpoint_auth_method": "none",
                "scope": models.OAUTH_SCOPE,
            }
        ),
        201,
    )


def _registration_allowed():
    """A cap per address per hour, so a loop cannot fill the table."""
    try:
        key = "oauth:register:{}:{}".format(request.remote_addr, int(time.time() // 3600))
        count = redis_connection.incr(key)
        if count == 1:
            redis_connection.expire(key, 7200)
        return count <= REGISTRATIONS_PER_HOUR
    except Exception:
        # Without Redis, let it through. Refusing every registration because
        # the cache is down would break the feature to protect a table.
        logger.warning("could not rate-limit client registration", exc_info=True)
        return True


def _redirect_uri_problem(uri):
    """
    Why this redirect URI is not acceptable, or None.

    https anywhere, http only on loopback. Those are the two forms RFC 8252
    allows a native client, and the reason is the same for both: a code must
    not cross a network in the clear. A custom scheme (`myapp://`) is allowed
    too, which is the other native pattern.
    """
    if not isinstance(uri, str) or len(uri) > 1024:
        return "A redirect URI must be a string under 1024 characters."
    parsed = urlparse(uri)
    if not parsed.scheme or not uri.strip():
        return "{!r} is not an absolute URI.".format(uri[:80])
    if parsed.fragment:
        # RFC 6749 3.1.2: the endpoint URI must not include a fragment, and
        # the browser would drop it anyway.
        return "A redirect URI may not have a fragment."
    if parsed.scheme == "https":
        return None if parsed.hostname else "An https redirect URI needs a host."
    if parsed.scheme == "http":
        if parsed.hostname in ("localhost", "127.0.0.1", "::1", "[::1]"):
            return None
        return "http is only accepted on localhost. Use https."
    if parsed.scheme in ("javascript", "data", "file", "vbscript"):
        return "That scheme is not accepted."
    # A private-use scheme, which is how a desktop client is handed a code.
    return None if ":" in uri else "{!r} is not an absolute URI.".format(uri[:80])


@routes.route("/oauth/authorize", methods=["GET", "POST"])
@routes.route("/<org_slug>/oauth/authorize", methods=["GET", "POST"])
@login_required
def oauth_authorize(org_slug=None):
    """
    Where a person agrees, having signed in the way they always sign in.

    `login_required` is doing the heavy lifting: it redirects to this
    install's login, which is SAML or Google where those are configured. That
    is the entire reason this feature exists -- the identity provider decides
    who gets in, and when somebody leaves, they stop getting in.
    """
    if _unavailable():
        return render_template("error.html", error_message="OAuth for MCP is off on this instance."), 404

    user = current_user._get_current_object()
    if request.method == "GET":
        try:
            grant = oauth.server.get_consent_grant(end_user=user)
        except Exception as error:
            # A malformed authorization request. Shown as a page rather than
            # JSON: a person is looking at this in a browser.
            logger.info("oauth authorize refused: %s", error)
            return render_template("error.html", error_message=_readable(error)), 400

        if not features.can(user, features.USE_MCP):
            # Said here rather than after they agree. An administrator grants
            # it per group, and the message says so.
            return (
                render_template(
                    "error.html",
                    error_message=(
                        "Your account may not use MCP, so there is nothing to connect. "
                        "An administrator grants it to a group under Settings -> Groups."
                    ),
                ),
                403,
            )

        return render_template(
            "oauth_consent.html",
            client=grant.client,
            scope=models.OAUTH_SCOPE,
            user=user,
            org=current_org,
            # Carried through the form so the POST authorizes the same request
            # the person was shown, rather than whatever is in the session.
            query=request.query_string.decode("utf-8", "replace"),
        )

    if not features.can(user, features.USE_MCP):
        return oauth.server.create_authorization_response(grant_user=None)

    if request.form.get("agree") != "yes":
        # A denial is a real OAuth answer: the client is redirected with
        # `access_denied` so it can say so, rather than hanging.
        record_event(current_org, user, {"action": "oauth_denied", "object_type": "mcp"})
        return oauth.server.create_authorization_response(grant_user=None)

    record_event(current_org, user, {"action": "oauth_granted", "object_type": "mcp"})
    return oauth.server.create_authorization_response(grant_user=user)


def _readable(error):
    description = getattr(error, "description", None) or getattr(error, "error", None)
    return "That authorization request could not be used: {}".format(description or "it was malformed.")


@csrf.exempt
@routes.route("/oauth/token", methods=["POST"])
@routes.route("/<org_slug>/oauth/token", methods=["POST"])
def oauth_token(org_slug=None):
    """
    Code for token, or refresh for token.

    CSRF-exempt like every other endpoint a non-browser client posts to: there
    is no cookie involved, the credential is the code plus the PKCE verifier,
    and a client has no page to have read a token from.
    """
    if _unavailable():
        return jsonify({"error": "invalid_request"}), 404
    return oauth.server.create_token_response()


@csrf.exempt
@routes.route("/oauth/revoke", methods=["POST"])
@routes.route("/<org_slug>/oauth/revoke", methods=["POST"])
def oauth_revoke(org_slug=None):
    """RFC 7009. A client handing a token back when it is uninstalled."""
    if _unavailable():
        return jsonify({"error": "invalid_request"}), 404
    return oauth.server.create_endpoint_response("revocation")


@routes.route("/api/oauth/tokens", methods=["GET"])
@login_required
def my_oauth_tokens():
    """
    The clients this person has connected. "Connected apps" on their profile.

    Theirs, not the organisation's: an administrator sees everyone's under
    Admin, and mixing the two in one endpoint is how a permission check gets
    forgotten.
    """
    user = current_user._get_current_object()
    return json_response({"tokens": [_described(token) for token in _live_tokens_for(user)]})


@routes.route("/api/oauth/tokens/<int:token_id>", methods=["DELETE"])
@login_required
def revoke_my_oauth_token(token_id):
    """Revoke one of this person's own tokens."""
    user = current_user._get_current_object()
    token = models.OAuthToken.query.filter(
        models.OAuthToken.id == token_id, models.OAuthToken.user_id == user.id
    ).first()
    if token is None:
        return jsonify({"message": "No such connection."}), 404
    token.revoke()
    models.db.session.commit()
    record_event(current_org, user, {"action": "oauth_revoked", "object_id": token_id, "object_type": "oauth_token"})
    return json_response({"id": token_id, "revoked": True})


@routes.route("/api/admin/oauth/tokens", methods=["GET"])
@login_required
@require_super_admin
def all_oauth_tokens():
    """
    Every connected client in the organisation, for Admin -> MCP.

    Separate from the endpoint that lists somebody's own, because mixing "mine"
    and "everyone's" in one route behind an `if` is how a permission check gets
    forgotten. Revoked ones are included: an administrator asking "did that
    client have access last Tuesday" needs the row to still be there.
    """
    tokens = (
        models.OAuthToken.query.filter(models.OAuthToken.org_id == current_org.id)
        .order_by(models.OAuthToken.created_at.desc())
        .limit(500)
        .all()
    )
    names = _client_names(tokens)
    users = dict(
        models.db.session.query(models.User.id, models.User.name).filter(
            models.User.id.in_([token.user_id for token in tokens] or [0])
        )
    )
    return json_response(
        {
            "tokens": [
                dict(
                    _described(token, names),
                    user_id=token.user_id,
                    user_name=users.get(token.user_id),
                    revoked_at=token.revoked_at,
                )
                for token in tokens
            ]
        }
    )


@routes.route("/api/admin/oauth/tokens/<int:token_id>", methods=["DELETE"])
@login_required
@require_super_admin
def revoke_any_oauth_token(token_id):
    """Revoke anyone's, within this organisation."""
    token = models.OAuthToken.query.filter(
        models.OAuthToken.id == token_id, models.OAuthToken.org_id == current_org.id
    ).first()
    if token is None:
        return jsonify({"message": "No such connection."}), 404
    token.revoke()
    models.db.session.commit()
    record_event(
        current_org,
        current_user._get_current_object(),
        {"action": "oauth_revoked", "object_id": token_id, "object_type": "oauth_token"},
    )
    return json_response({"id": token_id, "revoked": True})


def _live_tokens_for(user):
    return (
        models.OAuthToken.query.filter(models.OAuthToken.user_id == user.id, models.OAuthToken.revoked_at.is_(None))
        .order_by(models.OAuthToken.created_at.desc())
        .all()
    )


def _described(token, names=None):
    names = names if names is not None else _client_names([token])
    return {
        "id": token.id,
        "client_id": token.client_id,
        # The client's own claim about itself, which is why the page says so.
        "client_name": names.get(token.client_id) or "An MCP client",
        "connected_at": token.created_at,
        "last_used_at": token.last_used_at,
        "scope": token.scope,
        "expires_at": token.access_expires_at,
    }


def _client_names(tokens):
    ids = {token.client_id for token in tokens}
    if not ids:
        return {}
    return dict(
        models.db.session.query(models.OAuthClient.client_id, models.OAuthClient.name).filter(
            models.OAuthClient.client_id.in_(list(ids))
        )
    )
