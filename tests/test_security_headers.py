from sqldesk.models import db
from tests import BaseTestCase


class TestSecurityHeaders(BaseTestCase):
    """What every response carries, and what the two kinds of page differ in."""

    def test_forms_post_only_to_sqldesk_and_nothing_moves_the_base(self):
        csp = self.client.get("/default/login").headers.get("Content-Security-Policy", "")
        self.assertIn("form-action 'self'", csp)
        self.assertIn("base-uri 'self'", csp)

    def test_the_signed_in_dashboard_page_cannot_be_framed(self):
        response = self.make_request("get", "/dashboard/anything", is_json=False)
        csp = response.headers.get("Content-Security-Policy", "")
        self.assertIn("frame-ancestors 'none'", csp)
        self.assertNotIn("frame-ancestors *", csp)

    def test_a_public_dashboard_can_be_framed(self):
        # The embed policy replaces `frame-ancestors`; appended after the base
        # one, browsers ignored it and no embed was ever frameable.
        dashboard = self.factory.create_dashboard()
        token = self.factory.create_api_key(object=dashboard)
        db.session.commit()

        response = self.client.get("/default/public/dashboards/{}".format(token.api_key))

        self.assertEqual(200, response.status_code)
        csp = response.headers.get("Content-Security-Policy", "")
        self.assertIn("frame-ancestors *", csp)
        self.assertNotIn("frame-ancestors 'none'", csp)
        self.assertIsNone(response.headers.get("X-Frame-Options"))

    def test_the_session_cookie_is_not_sent_with_forms_from_other_sites(self):
        user = self.factory.create_user()
        user.hash_password("a-real-password")
        db.session.commit()

        response = self.client.post("/default/login", data={"email": user.email, "password": "a-real-password"})

        cookies = "\n".join(response.headers.getlist("Set-Cookie"))
        self.assertIn("session=", cookies)
        for cookie in cookies.split("\n"):
            if cookie.startswith("session=") or cookie.startswith("csrf_token="):
                self.assertIn("SameSite=Lax", cookie)

    def test_a_request_the_size_of_a_film_is_refused_before_it_is_read(self):
        limit = self.app.config["MAX_CONTENT_LENGTH"]
        self.assertTrue(200 * 1024 * 1024 < limit < 300 * 1024 * 1024)
