"""
The whole OAuth flow, driven the way a client drives it.

Written as one path from discovery to a working MCP call, because every step
exists only to make the next one possible and testing them apart would not
show that a real client can get through. The individual refusals get their
own tests below it.
"""

import base64
import hashlib
import json
import os
import re
from unittest import mock
from urllib.parse import parse_qs, urlparse

from flask import request

from sqldesk import models, oauth
from sqldesk.models import db
from tests import BaseTestCase, authenticate_request


def verifier_and_challenge(verifier="a" * 64):
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
    return verifier, challenge


class OAuthTestCase(BaseTestCase):
    """
    Driven over https throughout, because authlib refuses an authorization
    request that does not look like https and it is right to: a code or a token
    crossing a network in the clear is what the flow exists to avoid. The Flask
    test client takes a base URL, so this costs one line and tests the path a
    real deployment uses. `TestOverPlainHttp` covers the other case.
    """

    SECURE = "https://localhost"

    def setUp(self):
        super().setUp()
        self.client = self.app.test_client()
        for setting in ("sqldesk.settings.FEATURE_AI", "sqldesk.settings.MCP_OAUTH_ENABLED"):
            patch = mock.patch(setting, True)
            patch.start()
            self.addCleanup(patch.stop)
        self.factory.default_group.permissions = models.Group.DEFAULT_PERMISSIONS + ["use_mcp"]
        db.session.add(self.factory.default_group)
        db.session.commit()

    def register(self, **overrides):
        body = {
            "client_name": "Test Client",
            "redirect_uris": ["http://localhost:7777/callback"],
            "token_endpoint_auth_method": "none",
        }
        body.update(overrides)
        return self.client.post(
            self.SECURE + "/oauth/register", data=json.dumps(body), content_type="application/json"
        )

    def registered(self):
        return json.loads(self.register().data)["client_id"]

    def authorize(self, client_id, challenge, agree="yes", user=None, method="S256", **extra):
        params = {
            "response_type": "code",
            "client_id": client_id,
            "redirect_uri": "http://localhost:7777/callback",
            "scope": models.OAUTH_SCOPE,
            "state": "xyz",
        }
        if challenge is not None:
            params["code_challenge"] = challenge
        if method is not None:
            params["code_challenge_method"] = method
        params.update(extra)
        query = "&".join("{}={}".format(key, value) for key, value in params.items())
        authenticate_request(self.client, user or self.factory.user)
        return self.client.post(self.SECURE + "/oauth/authorize?" + query, data={"agree": agree})

    def code_from(self, response):
        location = response.headers["Location"]
        return parse_qs(urlparse(location).query)["code"][0]

    def exchange(self, client_id, code, verifier, **overrides):
        body = {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": "http://localhost:7777/callback",
            "client_id": client_id,
            "code_verifier": verifier,
        }
        body.update(overrides)
        return self.client.post(self.SECURE + "/oauth/token", data=body)

    def connect(self):
        """Register, agree, exchange. Returns the token response body."""
        client_id = self.registered()
        verifier, challenge = verifier_and_challenge()
        granted = self.authorize(client_id, challenge)
        tokens = json.loads(self.exchange(client_id, self.code_from(granted), verifier).data)
        return client_id, tokens

    def mcp(self, access_token):
        return self.client.post(
            self.SECURE + "/mcp",
            data=json.dumps({"jsonrpc": "2.0", "id": 1, "method": "tools/list"}),
            headers={"Authorization": "Bearer {}".format(access_token)},
            content_type="application/json",
        )


class TestTheWholeFlow(OAuthTestCase):
    def test_a_client_gets_from_an_unauthenticated_call_to_a_working_one(self):
        # 1. The client calls /mcp with nothing and is told where to look.
        refused = self.client.post(self.SECURE + "/mcp", data="{}", content_type="application/json")
        self.assertEqual(401, refused.status_code)
        challenge_header = refused.headers["WWW-Authenticate"]
        self.assertIn("resource_metadata=", challenge_header)

        # 2. It reads the resource metadata the header named.
        metadata_url = re.search(r'resource_metadata="([^"]+)"', challenge_header).group(1)
        resource = json.loads(self.client.get(metadata_url).data)
        self.assertEqual([models.OAUTH_SCOPE], resource["scopes_supported"])

        # 3. And from there, the authorization server's own metadata.
        issuer = resource["authorization_servers"][0]
        server = json.loads(self.client.get(issuer.rstrip("/") + "/.well-known/oauth-authorization-server").data)
        self.assertEqual(["S256"], server["code_challenge_methods_supported"])
        self.assertEqual(["none"], server["token_endpoint_auth_methods_supported"])

        # 4. It registers itself.
        client_id = json.loads(
            self.client.post(
                server["registration_endpoint"],
                data=json.dumps({"client_name": "Test Client", "redirect_uris": ["http://localhost:7777/callback"]}),
                content_type="application/json",
            ).data
        )["client_id"]

        # 5. A person signs in and agrees.
        verifier, challenge = verifier_and_challenge()
        granted = self.authorize(client_id, challenge)
        self.assertEqual(302, granted.status_code)
        self.assertEqual("xyz", parse_qs(urlparse(granted.headers["Location"]).query)["state"][0])

        # 6. The code becomes a token.
        tokens = json.loads(self.exchange(client_id, self.code_from(granted), verifier).data)
        self.assertEqual("Bearer", tokens["token_type"])
        self.assertEqual(models.OAUTH_SCOPE, tokens["scope"])
        self.assertIn("refresh_token", tokens)

        # 7. And the token works where the API key used to.
        answered = self.mcp(tokens["access_token"])
        self.assertEqual(200, answered.status_code)
        self.assertIn("tools", json.loads(answered.data)["result"])

    def test_the_token_is_not_stored_where_it_could_be_read(self):
        # A bearer token is a password: anything that can read the table can
        # be its owner.
        _client_id, tokens = self.connect()

        row = models.OAuthToken.query.one()
        self.assertNotIn(tokens["access_token"], (row.access_token_digest, row.refresh_token_digest))
        self.assertEqual(models._token_digest(tokens["access_token"]), row.access_token_digest)

    def test_refreshing_keeps_one_connection_rather_than_adding_another(self):
        client_id, tokens = self.connect()

        refreshed = json.loads(
            self.client.post(
                self.SECURE + "/oauth/token",
                data={
                    "grant_type": "refresh_token",
                    "refresh_token": tokens["refresh_token"],
                    "client_id": client_id,
                },
            ).data
        )

        self.assertNotEqual(tokens["access_token"], refreshed["access_token"])
        self.assertEqual(1, models.OAuthToken.query.count())
        self.assertEqual(200, self.mcp(refreshed["access_token"]).status_code)

    def test_and_the_old_access_token_stops_working(self):
        client_id, tokens = self.connect()

        self.client.post(
            self.SECURE + "/oauth/token",
            data={"grant_type": "refresh_token", "refresh_token": tokens["refresh_token"], "client_id": client_id},
        )

        self.assertEqual(401, self.mcp(tokens["access_token"]).status_code)

    def test_another_client_cannot_refresh_this_ones_token(self):
        # Registration is open, so without this check anybody could register a
        # client and extend somebody else's grant with a refresh token they got
        # hold of.
        _client_id, tokens = self.connect()
        somebody_else = self.registered()

        refused = self.client.post(
            self.SECURE + "/oauth/token",
            data={
                "grant_type": "refresh_token",
                "refresh_token": tokens["refresh_token"],
                "client_id": somebody_else,
            },
        )

        self.assertEqual(400, refused.status_code)
        self.assertEqual(200, self.mcp(tokens["access_token"]).status_code)

    def test_an_expired_refresh_token_is_refused(self):
        # Thirty days sliding. A client left running for a month and never used
        # has to send somebody back through the consent page.
        client_id, tokens = self.connect()
        row = models.OAuthToken.query.one()
        row.refresh_expires_at = models.utcnow() - models.datetime.timedelta(seconds=1)
        db.session.commit()

        refused = self.client.post(
            self.SECURE + "/oauth/token",
            data={
                "grant_type": "refresh_token",
                "refresh_token": tokens["refresh_token"],
                "client_id": client_id,
            },
        )

        self.assertEqual(400, refused.status_code)

    def test_a_spent_refresh_token_cannot_be_used_again(self):
        # Rotation. A refresh token that is never replaced is a long-lived
        # secret with extra steps.
        client_id, tokens = self.connect()
        self.client.post(
            self.SECURE + "/oauth/token",
            data={"grant_type": "refresh_token", "refresh_token": tokens["refresh_token"], "client_id": client_id},
        )

        again = self.client.post(
            self.SECURE + "/oauth/token",
            data={"grant_type": "refresh_token", "refresh_token": tokens["refresh_token"], "client_id": client_id},
        )

        self.assertEqual(400, again.status_code)


class TestPkceIsNotOptional(OAuthTestCase):
    """
    authlib 1.7.2 accepts `CodeChallenge(required=True)` and does not act on
    it: an authorization request with no challenge at all returns early from
    its validation. These are the tests that would have caught believing it.
    """

    def test_an_authorization_request_with_no_challenge_is_refused(self):
        client_id = self.registered()

        refused = self.authorize(client_id, None, method=None)

        self.assertNotIn("code=", refused.headers.get("Location", ""))

    def test_even_when_it_names_the_method_it_is_not_using(self):
        # The two checks mask each other otherwise: a request with neither a
        # challenge nor a method is already refused by the S256 check, so
        # deleting the "challenge is required" line changed nothing and the
        # earlier version of this class survived it.
        client_id = self.registered()

        refused = self.authorize(client_id, None, method="S256")

        self.assertNotIn("code=", refused.headers.get("Location", ""))

    def test_plain_is_refused_even_though_the_rfc_allows_it(self):
        # The verifier travels in the clear, so anyone who saw the challenge
        # can produce it.
        client_id = self.registered()
        verifier, _challenge = verifier_and_challenge()

        refused = self.authorize(client_id, verifier, method="plain")

        self.assertNotIn("code=", refused.headers.get("Location", ""))

    def test_the_wrong_verifier_does_not_get_a_token(self):
        client_id = self.registered()
        _verifier, challenge = verifier_and_challenge()
        granted = self.authorize(client_id, challenge)

        refused = self.exchange(client_id, self.code_from(granted), "b" * 64)

        self.assertEqual(400, refused.status_code)
        self.assertEqual(0, models.OAuthToken.query.count())

    def test_nor_does_no_verifier_at_all(self):
        client_id = self.registered()
        _verifier, challenge = verifier_and_challenge()
        granted = self.authorize(client_id, challenge)

        body = {
            "grant_type": "authorization_code",
            "code": self.code_from(granted),
            "redirect_uri": "http://localhost:7777/callback",
            "client_id": client_id,
        }

        self.assertEqual(400, self.client.post(self.SECURE + "/oauth/token", data=body).status_code)


class TestWhatTheCodeIsGoodFor(OAuthTestCase):
    def test_a_code_is_spent_once(self):
        client_id = self.registered()
        verifier, challenge = verifier_and_challenge()
        granted = self.authorize(client_id, challenge)
        code = self.code_from(granted)
        self.assertEqual(200, self.exchange(client_id, code, verifier).status_code)

        self.assertEqual(400, self.exchange(client_id, code, verifier).status_code)

    def test_a_code_cannot_be_redeemed_by_another_client(self):
        first = self.registered()
        second = self.registered()
        verifier, challenge = verifier_and_challenge()
        granted = self.authorize(first, challenge)

        refused = self.exchange(second, self.code_from(granted), verifier)

        self.assertEqual(400, refused.status_code)

    def test_a_different_redirect_uri_at_exchange_is_refused(self):
        client_id = self.registered()
        verifier, challenge = verifier_and_challenge()
        granted = self.authorize(client_id, challenge)

        refused = self.exchange(
            client_id, self.code_from(granted), verifier, redirect_uri="http://localhost:7777/elsewhere"
        )

        self.assertEqual(400, refused.status_code)

    def test_an_expired_code_is_refused(self):
        client_id = self.registered()
        verifier, challenge = verifier_and_challenge()
        granted = self.authorize(client_id, challenge)
        code = models.OAuthAuthorizationCode.query.one()
        code.expires_at = code.expires_at - models.datetime.timedelta(seconds=oauth.CODE_SECONDS + 10)
        db.session.commit()

        self.assertEqual(400, self.exchange(client_id, self.code_from(granted), verifier).status_code)

    def test_an_unregistered_redirect_uri_is_refused_at_authorization(self):
        # The loosest redirect rule is how a code gets handed to somebody else.
        client_id = self.registered()
        _verifier, challenge = verifier_and_challenge()

        refused = self.authorize(client_id, challenge, redirect_uri="http://localhost:7777/evil")

        self.assertNotIn("code=", refused.headers.get("Location", ""))


class TestSayingNo(OAuthTestCase):
    def test_cancelling_tells_the_client_rather_than_hanging(self):
        client_id = self.registered()
        _verifier, challenge = verifier_and_challenge()

        denied = self.authorize(client_id, challenge, agree="no")

        self.assertIn("access_denied", denied.headers["Location"])
        self.assertEqual(0, models.OAuthAuthorizationCode.query.count())

    def test_the_consent_page_names_the_client_and_says_who_claims_it(self):
        client_id = self.registered()
        _verifier, challenge = verifier_and_challenge()
        query = "response_type=code&client_id={}&redirect_uri=http://localhost:7777/callback&scope={}".format(
            client_id, models.OAUTH_SCOPE
        ) + "&code_challenge={}&code_challenge_method=S256".format(challenge)

        authenticate_request(self.client, self.factory.user)
        page = self.client.get(self.SECURE + "/oauth/authorize?" + query)

        body = page.data.decode("utf-8")
        self.assertIn("Test Client", body)
        # The name is the client's own claim and the page has to say so: it is
        # exactly the lie a phishing client needs.
        self.assertIn("cannot vouch", body)

    def test_somebody_without_mcp_permission_is_told_before_agreeing(self):
        self.factory.default_group.permissions = models.Group.DEFAULT_PERMISSIONS
        db.session.add(self.factory.default_group)
        db.session.commit()
        client_id = self.registered()
        _verifier, challenge = verifier_and_challenge()
        query = (
            "response_type=code&client_id={}&redirect_uri=http://localhost:7777/callback"
            "&code_challenge={}&code_challenge_method=S256".format(client_id, challenge)
        )

        authenticate_request(self.client, self.factory.user)
        page = self.client.get(self.SECURE + "/oauth/authorize?" + query)

        self.assertEqual(403, page.status_code)
        self.assertIn("may not use MCP", page.data.decode("utf-8"))


class TestWhoMayAgree(OAuthTestCase):
    def test_a_request_with_no_session_does_not_grant_anything(self):
        # `@login_required` on the consent page is what sends a person through
        # this install's own login, which is SAML or Google where those are on.
        # Removing it leaves `current_user` anonymous and every test that signs
        # in first still passes, which is how this gap stayed open.
        client_id = self.registered()
        _verifier, challenge = verifier_and_challenge()
        query = (
            "response_type=code&client_id={}&redirect_uri=http://localhost:7777/callback"
            "&code_challenge={}&code_challenge_method=S256".format(client_id, challenge)
        )

        anonymous = self.app.test_client()
        granted = anonymous.post(self.SECURE + "/oauth/authorize?" + query, data={"agree": "yes"})

        self.assertEqual(0, models.OAuthAuthorizationCode.query.count())
        self.assertNotIn("code=", granted.headers.get("Location", ""))

    def test_nor_does_opening_the_page_without_one(self):
        client_id = self.registered()
        _verifier, challenge = verifier_and_challenge()
        query = (
            "response_type=code&client_id={}&redirect_uri=http://localhost:7777/callback"
            "&code_challenge={}&code_challenge_method=S256".format(client_id, challenge)
        )

        anonymous = self.app.test_client()
        page = anonymous.get(self.SECURE + "/oauth/authorize?" + query)

        # Sent to log in, rather than shown a consent page for nobody.
        self.assertIn(page.status_code, (302, 401))
        self.assertNotIn("Test Client", page.data.decode("utf-8"))


class TestOnlyPublicClients(OAuthTestCase):
    """
    A desktop or CLI client cannot keep a secret, so pretending it can buys
    nothing and invites one into a config file. PKCE is what stands in.
    """

    def test_a_client_presenting_a_secret_at_the_token_endpoint_is_refused(self):
        client_id = self.registered()
        verifier, challenge = verifier_and_challenge()
        granted = self.authorize(client_id, challenge)

        refused = self.exchange(client_id, self.code_from(granted), verifier, client_secret="pretend-i-have-one")

        self.assertEqual(400, refused.status_code)
        self.assertEqual(0, models.OAuthToken.query.count())

    def test_and_no_secret_is_ever_the_right_one(self):
        # Directly, because the flow above never reaches this: a client that
        # presents a secret is turned away at the auth-method check first. The
        # contract still has to be "there is no secret", not "any secret".
        self.registered()
        client = models.OAuthClient.query.one()

        self.assertFalse(client.check_client_secret(""))
        self.assertFalse(client.check_client_secret("anything"))
        self.assertFalse(client.check_endpoint_auth_method("client_secret_post", "token"))
        self.assertTrue(client.check_endpoint_auth_method("none", "token"))


class TestRevoking(OAuthTestCase):
    def test_a_person_can_disconnect_a_client_from_their_profile(self):
        _client_id, tokens = self.connect()

        authenticate_request(self.client, self.factory.user)
        listed = json.loads(self.client.get(self.SECURE + "/api/oauth/tokens").data)["tokens"]
        self.assertEqual("Test Client", listed[0]["client_name"])
        self.client.delete(self.SECURE + "/api/oauth/tokens/{}".format(listed[0]["id"]))

        self.assertEqual(401, self.mcp(tokens["access_token"]).status_code)

    def test_one_person_cannot_revoke_another_persons_connection(self):
        _client_id, tokens = self.connect()
        token_id = models.OAuthToken.query.one().id
        other = self.factory.create_user()

        authenticate_request(self.client, other)
        refused = self.client.delete(self.SECURE + "/api/oauth/tokens/{}".format(token_id))

        self.assertEqual(404, refused.status_code)
        self.assertEqual(200, self.mcp(tokens["access_token"]).status_code)

    def test_a_client_can_hand_a_token_back(self):
        client_id, tokens = self.connect()

        handed_back = self.client.post(
            self.SECURE + "/oauth/revoke", data={"token": tokens["access_token"], "client_id": client_id}
        )

        self.assertEqual(200, handed_back.status_code)
        self.assertEqual(401, self.mcp(tokens["access_token"]).status_code)

    def test_disabling_the_account_revokes_everything_it_holds(self):
        _client_id, tokens = self.connect()
        user = self.factory.user

        oauth.revoke_for_user(user, "disabled")

        self.assertEqual(401, self.mcp(tokens["access_token"]).status_code)

    def test_a_code_cannot_be_spent_after_the_account_is_disabled(self):
        # The gap between agreeing and exchanging is five minutes, and
        # disabling an account has to take effect inside it.
        client_id = self.registered()
        verifier, challenge = verifier_and_challenge()
        granted = self.authorize(client_id, challenge)
        self.factory.user.disabled_at = models.utcnow()
        db.session.commit()

        refused = self.exchange(client_id, self.code_from(granted), verifier)

        self.assertEqual(400, refused.status_code)
        self.assertEqual(0, models.OAuthToken.query.count())

    def test_a_disabled_user_is_refused_even_before_that(self):
        # Belt and braces, and the braces matter: revoking is a loop over rows
        # and a row added by a refresh racing the disable would survive it.
        _client_id, tokens = self.connect()
        self.factory.user.disabled_at = models.utcnow()
        db.session.commit()

        self.assertEqual(401, self.mcp(tokens["access_token"]).status_code)


class TestWhatATokenMayReach(OAuthTestCase):
    def test_a_token_from_another_organisation_is_refused(self):
        _client_id, tokens = self.connect()
        token = models.OAuthToken.query.one()
        token.org_id = self.factory.create_org().id
        db.session.commit()

        self.assertEqual(401, self.mcp(tokens["access_token"]).status_code)

    def test_an_expired_access_token_is_refused(self):
        _client_id, tokens = self.connect()
        token = models.OAuthToken.query.one()
        token.access_expires_at = models.utcnow() - models.datetime.timedelta(seconds=1)
        db.session.commit()

        self.assertEqual(401, self.mcp(tokens["access_token"]).status_code)

    def test_an_api_key_still_works(self):
        # Scripts and headless setups need one, and behind a VPN it is fine.
        answered = self.client.post(
            self.SECURE + "/mcp",
            data=json.dumps({"jsonrpc": "2.0", "id": 1, "method": "tools/list"}),
            headers={"Authorization": "Bearer {}".format(self.factory.user.api_key)},
            content_type="application/json",
        )

        self.assertEqual(200, answered.status_code)

    def test_a_revoked_token_is_never_retried_as_an_api_key(self):
        # The prefix decides which table to look in, and a credential of ours
        # that has been revoked must be refused rather than quietly
        # re-interpreted as something else.
        _client_id, tokens = self.connect()
        models.OAuthToken.query.one().revoke()
        db.session.commit()

        self.assertEqual(401, self.mcp(tokens["access_token"]).status_code)

    def test_the_audit_names_the_client_that_held_the_token(self):
        # Not the name it gives at initialize, which is whatever it chose to
        # say this minute. This one was agreed to on a consent page.
        _client_id, tokens = self.connect()

        self.mcp(tokens["access_token"])

        row = models.McpEvent.query.order_by(models.McpEvent.id.desc()).first()
        self.assertEqual("Test Client", row.client)

    def test_using_it_records_when(self):
        _client_id, tokens = self.connect()

        self.mcp(tokens["access_token"])

        self.assertIsNotNone(models.OAuthToken.query.one().last_used_at)


class TestRegistration(OAuthTestCase):
    def test_an_http_redirect_uri_off_localhost_is_refused(self):
        # A code must not cross a network in the clear.
        refused = self.register(redirect_uris=["http://example.com/cb"])

        self.assertEqual(400, refused.status_code)
        self.assertIn("localhost", json.loads(refused.data)["error_description"])

    def test_https_anywhere_is_accepted(self):
        self.assertEqual(201, self.register(redirect_uris=["https://example.com/cb"]).status_code)

    def test_so_is_a_private_use_scheme(self):
        # How a desktop client is handed a code.
        self.assertEqual(201, self.register(redirect_uris=["com.example.app:/oauth"]).status_code)

    def test_a_javascript_url_is_refused(self):
        self.assertEqual(400, self.register(redirect_uris=["javascript:alert(1)"]).status_code)

    def test_a_fragment_is_refused(self):
        self.assertEqual(400, self.register(redirect_uris=["https://example.com/cb#x"]).status_code)

    def test_a_relative_uri_is_refused(self):
        self.assertEqual(400, self.register(redirect_uris=["/callback"]).status_code)

    def test_a_client_claiming_to_keep_a_secret_is_refused(self):
        refused = self.register(token_endpoint_auth_method="client_secret_post")

        self.assertEqual(400, refused.status_code)

    def test_no_redirect_uris_at_all(self):
        self.assertEqual(400, self.register(redirect_uris=[]).status_code)

    def test_the_registration_says_what_it_may_do_and_no_more(self):
        registered = json.loads(self.register().data)

        self.assertEqual("none", registered["token_endpoint_auth_method"])
        self.assertEqual(["code"], registered["response_types"])
        self.assertEqual(models.OAUTH_SCOPE, registered["scope"])


class TestWhenItIsSwitchedOff(OAuthTestCase):
    def test_discovery_is_absent_rather_than_refusing(self):
        # A 404 makes a client fall back to an API key. A 403 makes it loop on
        # an error it cannot act on.
        with mock.patch("sqldesk.settings.MCP_OAUTH_ENABLED", False):
            self.assertEqual(404, self.client.get(self.SECURE + "/.well-known/oauth-protected-resource").status_code)
            self.assertEqual(404, self.client.get(self.SECURE + "/.well-known/oauth-authorization-server").status_code)
            self.assertEqual(404, self.register().status_code)

    def test_and_the_challenge_does_not_advertise_it(self):
        with mock.patch("sqldesk.settings.MCP_OAUTH_ENABLED", False):
            refused = self.client.post(self.SECURE + "/mcp", data="{}", content_type="application/json")

        self.assertEqual("Bearer", refused.headers["WWW-Authenticate"])

    def test_a_token_issued_before_it_was_switched_off_stops_working(self):
        _client_id, tokens = self.connect()

        with mock.patch("sqldesk.settings.MCP_OAUTH_ENABLED", False):
            refused = self.mcp(tokens["access_token"])

        self.assertEqual(401, refused.status_code)


class TestOverPlainHttp(OAuthTestCase):
    """
    http is refused unless somebody has turned it on.

    A code or a bearer token crossing a network in the clear is what the flow
    exists to avoid, so the default cannot be "allow it when the hostname looks
    local" -- a hostname is not evidence about a network. It is a setting an
    administrator turns on, and the log says so when they have.
    """

    INSECURE = "http://localhost"

    def test_the_authorize_endpoint_refuses_it_by_default(self):
        client_id = self.registered()
        _verifier, challenge = verifier_and_challenge()
        query = (
            "response_type=code&client_id={}&redirect_uri=http://localhost:7777/callback"
            "&code_challenge={}&code_challenge_method=S256".format(client_id, challenge)
        )
        authenticate_request(self.client, self.factory.user)

        with mock.patch.dict("os.environ", {}, clear=False):
            os.environ.pop("AUTHLIB_INSECURE_TRANSPORT", None)
            refused = self.client.get(self.INSECURE + "/oauth/authorize?" + query)

        self.assertEqual(400, refused.status_code)

    def test_and_says_something_a_person_can_act_on(self):
        client_id = self.registered()
        _verifier, challenge = verifier_and_challenge()
        query = (
            "response_type=code&client_id={}&redirect_uri=http://localhost:7777/callback"
            "&code_challenge={}&code_challenge_method=S256".format(client_id, challenge)
        )
        authenticate_request(self.client, self.factory.user)

        with mock.patch.dict("os.environ", {}, clear=False):
            os.environ.pop("AUTHLIB_INSECURE_TRANSPORT", None)
            refused = self.client.get(self.INSECURE + "/oauth/authorize?" + query)

        # A page, not JSON: a person is looking at this in a browser.
        self.assertIn("could not be used", refused.data.decode("utf-8"))

    def test_turning_the_setting_on_allows_it(self):
        # Which is how somebody tries this against a local install reached
        # through a port-forward with no TLS anywhere.
        from sqldesk import oauth as oauth_module

        client_id = self.registered()
        verifier, challenge = verifier_and_challenge()
        query = (
            "response_type=code&client_id={}&redirect_uri=http://localhost:7777/callback"
            "&code_challenge={}&code_challenge_method=S256".format(client_id, challenge)
        )
        authenticate_request(self.client, self.factory.user)

        with mock.patch("sqldesk.settings.MCP_OAUTH_ALLOW_HTTP", True):
            oauth_module.init_app(self.app)
            try:
                granted = self.client.post(self.INSECURE + "/oauth/authorize?" + query, data={"agree": "yes"})
                code = parse_qs(urlparse(granted.headers["Location"]).query)["code"][0]
                exchanged = self.client.post(
                    self.INSECURE + "/oauth/token",
                    data={
                        "grant_type": "authorization_code",
                        "code": code,
                        "redirect_uri": "http://localhost:7777/callback",
                        "client_id": client_id,
                        "code_verifier": verifier,
                    },
                )
            finally:
                os.environ.pop("AUTHLIB_INSECURE_TRANSPORT", None)

        self.assertEqual(200, exchanged.status_code)


class TestTheForwardedScheme(BaseTestCase):
    """
    Behind a TLS-terminating proxy the hop SQLDesk can see is http, so the
    whole flow rests on `X-Forwarded-Proto` being read: authlib refuses an
    authorization request whose URL does not look like https.

    werkzeug's ProxyFix reads it by default, which is why this passed before
    the scheme was written down in `app.py` -- the point of the test is that it
    keeps working, not that anything was broken. A werkzeug default changing
    under us would otherwise show up as every OAuth request failing on an
    HTTPS install and passing here.
    """

    def test_an_x_forwarded_proto_header_decides_the_scheme(self):
        seen = {}

        @self.app.route("/_scheme_probe")
        def probe():
            seen["url"] = request.url
            return "ok"

        self.app.test_client().get("http://localhost/_scheme_probe", headers={"X-Forwarded-Proto": "https"})

        self.assertTrue(seen["url"].startswith("https://"), seen["url"])

    def test_and_without_the_header_nothing_changes(self):
        seen = {}

        @self.app.route("/_scheme_probe_plain")
        def probe_plain():
            seen["url"] = request.url
            return "ok"

        self.app.test_client().get("http://localhost/_scheme_probe_plain")

        self.assertTrue(seen["url"].startswith("http://"), seen["url"])


class TestDisablingAnAccount(OAuthTestCase):
    def test_it_revokes_the_connected_clients(self):
        _client_id, tokens = self.connect()
        admin = self.factory.create_admin()

        authenticate_request(self.client, admin)
        disabled = self.client.post(
            self.SECURE + "/{}/api/users/{}/disable".format(self.factory.org.slug, self.factory.user.id),
            data="{}",
            content_type="application/json",
        )

        self.assertEqual(200, disabled.status_code)
        self.assertEqual(401, self.mcp(tokens["access_token"]).status_code)
        self.assertIsNotNone(models.OAuthToken.query.one().revoked_at)

    def test_and_enabling_it_again_does_not_bring_them_back(self):
        # The refresh token is gone, so a client that was connected has to be
        # connected again by a person. Re-enabling an account is not a way to
        # restore a credential nobody has looked at since.
        _client_id, tokens = self.connect()
        admin = self.factory.create_admin()
        authenticate_request(self.client, admin)
        self.client.post(
            self.SECURE + "/{}/api/users/{}/disable".format(self.factory.org.slug, self.factory.user.id),
            data="{}",
            content_type="application/json",
        )

        self.client.delete(
            self.SECURE + "/{}/api/users/{}/disable".format(self.factory.org.slug, self.factory.user.id)
        )

        self.assertEqual(401, self.mcp(tokens["access_token"]).status_code)


class TestHowManyProxiesAreTrusted(BaseTestCase):
    """
    `x_for` is set from `PROXIES_COUNT` and `x_proto` was left to werkzeug,
    which defaults it to 1. With two proxies in front that reads the address
    from two hops out and the scheme from one, which is the kind of mismatch
    that produces an http URL on an https install -- and authlib refuses an
    authorization request whose URL is not https.

    Tested against ProxyFix directly, because `PROXIES_COUNT` is read when the
    app is built and building a second one to check a middleware argument is a
    lot of machinery for one question.
    """

    def scheme_seen(self, x_proto, forwarded):
        from werkzeug.middleware.proxy_fix import ProxyFix
        from werkzeug.test import Client

        def app(environ, start_response):
            start_response("200 OK", [("Content-Type", "text/plain")])
            return [environ["wsgi.url_scheme"].encode("ascii")]

        wrapped = ProxyFix(app, x_for=2, x_proto=x_proto, x_host=1)
        response = Client(wrapped).get("/", headers={"X-Forwarded-Proto": forwarded})
        return response.data.decode("ascii")

    def test_with_two_proxies_the_outer_one_decides(self):
        # The browser spoke https to the outer proxy; the inner hop is plain.
        # Reading one hop out answers "http", which is the wrong answer.
        self.assertEqual("https", self.scheme_seen(x_proto=2, forwarded="https,http"))

    def test_and_the_default_of_one_gets_it_wrong(self):
        # Which is what the explicit `x_proto` in app.py is for.
        self.assertEqual("http", self.scheme_seen(x_proto=1, forwarded="https,http"))

    def test_the_app_is_configured_with_the_setting_rather_than_the_default(self):
        # With two proxies configured, which is the only way to tell the
        # setting from werkzeug's default of 1 -- and the whole reason the
        # argument is written down. A fresh app rather than this test's,
        # because `PROXIES_COUNT` is read when the app is constructed.
        from sqldesk.app import SQLDesk

        with mock.patch("sqldesk.settings.PROXIES_COUNT", 2):
            app = SQLDesk()

        self.assertEqual(2, app.wsgi_app.x_proto)
        self.assertEqual(2, app.wsgi_app.x_for)


class TestWhatAnAdministratorSees(OAuthTestCase):
    def test_every_connection_in_the_organisation(self):
        _client_id, _tokens = self.connect()
        admin = self.factory.create_admin()

        authenticate_request(self.client, admin)
        listed = json.loads(self.client.get(self.SECURE + "/api/admin/oauth/tokens").data)["tokens"]

        self.assertEqual(1, len(listed))
        self.assertEqual("Test Client", listed[0]["client_name"])
        self.assertEqual(self.factory.user.name, listed[0]["user_name"])

    def test_and_may_end_any_of_them(self):
        _client_id, tokens = self.connect()
        admin = self.factory.create_admin()
        token_id = models.OAuthToken.query.one().id

        authenticate_request(self.client, admin)
        revoked = self.client.delete(self.SECURE + "/api/admin/oauth/tokens/{}".format(token_id))

        self.assertEqual(200, revoked.status_code)
        self.assertEqual(401, self.mcp(tokens["access_token"]).status_code)

    def test_a_revoked_one_is_still_listed(self):
        # "Did that client have access last Tuesday" is a question asked after
        # the fact, so the row stays.
        _client_id, _tokens = self.connect()
        models.OAuthToken.query.one().revoke()
        db.session.commit()
        admin = self.factory.create_admin()

        authenticate_request(self.client, admin)
        listed = json.loads(self.client.get(self.SECURE + "/api/admin/oauth/tokens").data)["tokens"]

        self.assertEqual(1, len(listed))
        self.assertIsNotNone(listed[0]["revoked_at"])

    def test_somebody_who_is_not_an_administrator_may_not_look(self):
        self.connect()

        authenticate_request(self.client, self.factory.user)
        refused = self.client.get(self.SECURE + "/api/admin/oauth/tokens")

        self.assertEqual(403, refused.status_code)

    def test_nor_revoke_through_the_admin_route(self):
        _client_id, tokens = self.connect()
        token_id = models.OAuthToken.query.one().id

        authenticate_request(self.client, self.factory.user)
        refused = self.client.delete(self.SECURE + "/api/admin/oauth/tokens/{}".format(token_id))

        self.assertEqual(403, refused.status_code)
        self.assertEqual(200, self.mcp(tokens["access_token"]).status_code)

    def test_another_organisations_connection_is_not_listed_or_revokable(self):
        _client_id, _tokens = self.connect()
        token = models.OAuthToken.query.one()
        token.org_id = self.factory.create_org().id
        db.session.commit()
        admin = self.factory.create_admin()

        authenticate_request(self.client, admin)
        listed = json.loads(self.client.get(self.SECURE + "/api/admin/oauth/tokens").data)["tokens"]
        refused = self.client.delete(self.SECURE + "/api/admin/oauth/tokens/{}".format(token.id))

        self.assertEqual([], listed)
        self.assertEqual(404, refused.status_code)
