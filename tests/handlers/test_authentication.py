import time

import mock

from sqldesk import limiter, settings
from sqldesk.authentication.account import VERIFY, invite_token, reset_token, token_for
from sqldesk.models import User, db
from tests import BaseTestCase


class TestResetPassword(BaseTestCase):
    def test_shows_reset_password_form(self):
        user = self.factory.create_user(is_invitation_pending=False)
        token = reset_token(user)
        response = self.get_request("/reset/{}".format(token), org=self.factory.org)
        self.assertEqual(response.status_code, 200)

    def test_a_reset_link_works_once(self):
        # The link stays in a mailbox for as long as the mailbox does. Setting
        # a password through it has to be the end of it.
        user = self.factory.create_user(is_invitation_pending=False)
        token = reset_token(user)
        first = self.post_request("/reset/{}".format(token), data={"password": "first-pass"}, org=self.factory.org)
        self.assertEqual(first.status_code, 302)

        again = self.post_request("/reset/{}".format(token), data={"password": "second-pass"}, org=self.factory.org)

        self.assertEqual(again.status_code, 400)
        user = User.query.get(user.id)
        self.assertTrue(user.verify_password("first-pass"))
        self.assertFalse(user.verify_password("second-pass"))

    def test_a_newer_reset_link_retires_the_older_one(self):
        user = self.factory.create_user(is_invitation_pending=False)
        older = reset_token(user)
        newer = reset_token(user)
        self.post_request("/reset/{}".format(newer), data={"password": "chosen-pass"}, org=self.factory.org)

        response = self.post_request("/reset/{}".format(older), data={"password": "other-pass"}, org=self.factory.org)

        self.assertEqual(response.status_code, 400)
        self.assertTrue(User.query.get(user.id).verify_password("chosen-pass"))

    def test_an_invite_link_is_not_a_reset_link(self):
        # Before the links were told apart, an accepted invite -- refused at
        # /invite -- was still a working password reset for a week.
        user = self.factory.create_user(is_invitation_pending=True)
        token = invite_token(user)
        self.post_request("/invite/{}".format(token), data={"password": "invited-pass"}, org=self.factory.org)

        response = self.post_request("/reset/{}".format(token), data={"password": "stolen-pass"}, org=self.factory.org)

        self.assertEqual(response.status_code, 400)
        self.assertTrue(User.query.get(user.id).verify_password("invited-pass"))

    def test_a_verify_link_is_not_a_reset_link(self):
        user = self.factory.create_user(is_invitation_pending=False)
        response = self.get_request("/reset/{}".format(token_for(user, VERIFY)), org=self.factory.org)
        self.assertEqual(response.status_code, 400)

    def test_a_disabled_users_link_is_refused(self):
        user = self.factory.create_user(is_invitation_pending=False)
        token = reset_token(user)
        user.disable()
        db.session.commit()

        response = self.post_request("/reset/{}".format(token), data={"password": "sneaky-pass"}, org=self.factory.org)

        self.assertEqual(response.status_code, 400)
        self.assertFalse(User.query.get(user.id).verify_password("sneaky-pass"))


class TestInvite(BaseTestCase):
    def test_expired_invite_token(self):
        with mock.patch("time.time") as patched_time:
            patched_time.return_value = time.time() - (7 * 24 * 3600) - 10
            token = invite_token(self.factory.user)

        response = self.get_request("/invite/{}".format(token), org=self.factory.org)
        self.assertEqual(response.status_code, 400)

    def test_invalid_invite_token(self):
        response = self.get_request("/invite/badtoken", org=self.factory.org)
        self.assertEqual(response.status_code, 400)

    def test_valid_token(self):
        user = self.factory.create_user(is_invitation_pending=True)
        token = invite_token(user)
        response = self.get_request("/invite/{}".format(token), org=self.factory.org)
        self.assertEqual(response.status_code, 200)

    def test_already_active_user(self):
        token = invite_token(self.factory.user)
        self.post_request(
            "/invite/{}".format(token),
            data={"password": "test1234"},
            org=self.factory.org,
        )
        response = self.get_request("/invite/{}".format(token), org=self.factory.org)
        self.assertEqual(response.status_code, 400)


class TestInvitePost(BaseTestCase):
    def test_empty_password(self):
        token = invite_token(self.factory.user)
        response = self.post_request("/invite/{}".format(token), data={"password": ""}, org=self.factory.org)
        self.assertEqual(response.status_code, 400)

    def test_invalid_password(self):
        token = invite_token(self.factory.user)
        response = self.post_request("/invite/{}".format(token), data={"password": "1234"}, org=self.factory.org)
        self.assertEqual(response.status_code, 400)

    def test_bad_token(self):
        response = self.post_request(
            "/invite/{}".format("jdsnfkjdsnfkj"),
            data={"password": "1234"},
            org=self.factory.org,
        )
        self.assertEqual(response.status_code, 400)

    def test_user_invited_before_invitation_pending_check(self):
        user = self.factory.create_user(details={})
        token = invite_token(user)
        response = self.post_request(
            "/invite/{}".format(token),
            data={"password": "test1234"},
            org=self.factory.org,
        )
        self.assertEqual(response.status_code, 302)

    def test_already_active_user(self):
        token = invite_token(self.factory.user)
        self.post_request(
            "/invite/{}".format(token),
            data={"password": "test1234"},
            org=self.factory.org,
        )
        response = self.post_request(
            "/invite/{}".format(token),
            data={"password": "test1234"},
            org=self.factory.org,
        )
        self.assertEqual(response.status_code, 400)

    def test_valid_password(self):
        user = self.factory.create_user(is_invitation_pending=True)
        token = invite_token(user)
        password = "test1234"
        response = self.post_request(
            "/invite/{}".format(token),
            data={"password": password},
            org=self.factory.org,
        )
        self.assertEqual(response.status_code, 302)
        user = User.query.get(user.id)
        self.assertTrue(user.verify_password(password))
        self.assertFalse(user.is_invitation_pending)


class TestLogin(BaseTestCase):
    def test_throttle_login(self):
        limiter.enabled = True
        # Extract the limit from settings (ex: '50/day')
        limit = settings.THROTTLE_LOGIN_PATTERN.split("/")[0]
        for _ in range(0, int(limit)):
            self.get_request("/login", org=self.factory.org)

        response = self.get_request("/login", org=self.factory.org)
        self.assertEqual(response.status_code, 429)

    def test_throttle_password_reset(self):
        limiter.enabled = True
        # Extract the limit from settings (ex: '10/hour')
        limit = settings.THROTTLE_PASS_RESET_PATTERN.split("/")[0]
        for _ in range(0, int(limit)):
            self.get_request("/forgot", org=self.factory.org)

        response = self.get_request("/forgot", org=self.factory.org)
        self.assertEqual(response.status_code, 429)


class TestPublicTokens(BaseTestCase):
    def _shared(self):
        query = self.factory.create_query()
        dashboard = self.factory.create_dashboard()
        self.factory.create_widget(
            dashboard=dashboard, visualization=self.factory.create_visualization(query_rel=query)
        )
        token = self.factory.create_api_key(object=dashboard)
        db.session.commit()
        return query, token

    def test_a_token_stops_working_when_public_links_are_switched_off(self):
        # The pages checked the setting; the API a token holder actually
        # calls did not, so every link kept working.
        query, token = self._shared()
        self.factory.org.set_setting("disable_public_urls", True)
        db.session.commit()

        rv = self.client.get(
            "/api/queries/{}".format(query.id), headers={"Authorization": "Key {}".format(token.api_key)}
        )

        self.assertNotEqual(200, rv.status_code)

    def test_a_token_is_good_only_in_the_organization_that_made_it(self):
        query, token = self._shared()
        elsewhere = self.factory.create_org()
        db.session.commit()

        rv = self.client.get(
            "/{}/api/queries/{}".format(elsewhere.slug, query.id),
            headers={"Authorization": "Key {}".format(token.api_key)},
        )

        self.assertNotEqual(200, rv.status_code)

    def test_a_token_reads_the_chart_while_public_links_are_on(self):
        query, token = self._shared()

        rv = self.client.get(
            "/{}/api/queries/{}".format(self.factory.org.slug, query.id),
            headers={"Authorization": "Key {}".format(token.api_key)},
        )

        self.assertEqual(200, rv.status_code)


class TestSession(BaseTestCase):
    # really simple test just to trigger this route
    def test_get(self):
        self.make_request("get", "/default/api/session", user=self.factory.user, org=False)
