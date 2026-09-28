from mock import patch
from redis.exceptions import AuthenticationError, RedisError

from sqldesk import version_check
from sqldesk.models import Organization
from sqldesk.version_check import run_version_check
from tests import BaseTestCase

ENDPOINT = "https://versions.example.invalid/check"


class TestStartingWithoutRedis(BaseTestCase):
    """
    The version badge is refreshed inside `create_app`, so anything it raises
    stops the server, every `manage.py` command, and the migration job --
    which is how a chart upgrade that gives Redis a password bricked itself:
    the migration ran before Redis had it.
    """

    def test_an_unreachable_redis_does_not_stop_the_app_starting(self):
        with patch("sqldesk.version_check.redis_connection.get", side_effect=RedisError("no answer")) as unreachable:
            version_check.reset_new_version_status()

        self.assertTrue(unreachable.called)

    def test_a_password_redis_refuses_does_not_stop_it_either(self):
        with patch(
            "sqldesk.version_check.redis_connection.get",
            side_effect=AuthenticationError("AUTH called without any password configured"),
        ):
            version_check.reset_new_version_status()

    def test_nor_a_cached_value_that_is_not_a_version(self):
        with patch("sqldesk.version_check.redis_connection.get", return_value="not-a-version"):
            version_check.reset_new_version_status()


class TestRunVersionCheck(BaseTestCase):
    """The daily version check.

    There is no default endpoint -- SQLDesk reports to nobody unless an
    operator names somewhere to report to -- so the no-endpoint path is the one
    nearly every install takes.
    """

    @patch("sqldesk.version_check.usage_data")
    @patch("sqldesk.version_check.requests.post")
    @patch("sqldesk.settings.VERSION_CHECK_URL", "")
    def test_reports_nothing_when_no_endpoint_is_configured(self, post, usage_data):
        # Consent granted, so the only thing stopping the usage counts being
        # gathered is that there is nowhere to send them.
        self.factory.org.set_setting("beacon_consent", True)

        run_version_check()

        post.assert_not_called()
        # Gathering usage counts means six aggregates across every table. With
        # nowhere to send them it is a day's worth of wasted scanning.
        usage_data.assert_not_called()

    @patch("sqldesk.version_check.requests.post")
    @patch("sqldesk.settings.VERSION_CHECK_URL", ENDPOINT)
    def test_survives_a_database_with_no_organization(self, post):
        # Between `create_db` and somebody submitting the setup form there are
        # no organizations at all, and the job can fire in that window.
        self.db.session.close()
        self.db.drop_all()
        self.db.create_all()
        self.assertIsNone(Organization.query.first())
        post.return_value.json.return_value = {"release": {"version": "0.0.1"}}

        run_version_check()

        post.assert_called_once()
        self.assertNotIn("usage", post.call_args.kwargs["json"])

    @patch("sqldesk.version_check.usage_data", return_value={"users_count": 1})
    @patch("sqldesk.version_check.requests.post")
    @patch("sqldesk.settings.VERSION_CHECK_URL", ENDPOINT)
    def test_sends_usage_only_when_the_organization_consented(self, post, usage_data):
        post.return_value.json.return_value = {"release": {"version": "0.0.1"}}

        self.factory.org.set_setting("beacon_consent", False)
        run_version_check()
        self.assertNotIn("usage", post.call_args.kwargs["json"])

        self.factory.org.set_setting("beacon_consent", True)
        run_version_check()
        self.assertEqual(post.call_args.kwargs["json"]["usage"], {"users_count": 1})
