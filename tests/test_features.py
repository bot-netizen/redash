from unittest import mock

from sqldesk import features, settings
from sqldesk.models import db
from tests import BaseTestCase


class TestWhoCanUseAFeature(BaseTestCase):
    """
    A feature is something an administrator hands to a group. Nobody has one
    until somebody says so, and an administrator has all of them.
    """

    def _member_of(self, *permissions):
        group = self.factory.create_group(name="Ops", permissions=list(permissions))
        db.session.add(group)
        db.session.commit()
        return self.factory.create_user(group_ids=[group.id])

    def test_nobody_has_it_until_it_is_granted(self):
        with mock.patch.object(settings, "FEATURE_AI", True):
            self.assertFalse(features.can(self._member_of("view_query"), "use_mcp"))

    def test_a_group_that_was_granted_it_has_it(self):
        with mock.patch.object(settings, "FEATURE_AI", True):
            self.assertTrue(features.can(self._member_of("view_query", "use_mcp"), "use_mcp"))

    def test_an_administrator_has_every_feature_the_install_offers(self):
        admin = self.factory.create_admin()
        with mock.patch.object(settings, "FEATURE_AI", True):
            for feature in features.grantable():
                self.assertTrue(features.can(admin, feature.name), feature.name)

    def test_switching_the_feature_off_takes_it_away_from_everyone(self):
        # Granted in the database, but the install no longer offers it. The
        # row must not be what decides -- otherwise turning MCP off would
        # leave the permission granted and the endpoint reachable.
        granted = self._member_of("view_query", "use_mcp")
        admin = self.factory.create_admin()

        with mock.patch.object(settings, "FEATURE_AI", False):
            self.assertFalse(features.can(granted, "use_mcp"))
            self.assertFalse(features.can(admin, "use_mcp"))

    def test_a_name_nobody_defined_is_not_a_feature(self):
        self.assertFalse(features.can(self.factory.create_admin(), "make_coffee"))


class TestWhatAnInstallOffers(BaseTestCase):
    def test_only_features_that_are_switched_on(self):
        with mock.patch.object(settings, "FEATURE_AI", False):
            offered = [feature.name for feature in features.grantable()]

        self.assertIn("manage_live_dashboards", offered)
        self.assertNotIn("use_mcp", offered)
        self.assertNotIn("manage_catalog", offered)

    def test_and_all_of_them_when_it_is(self):
        with mock.patch.object(settings, "FEATURE_AI", True):
            offered = [feature.name for feature in features.grantable()]

        self.assertIn("use_mcp", offered)
        self.assertIn("manage_catalog", offered)

    def test_every_feature_says_what_it_is_for(self):
        # The Group page draws these; a checkbox with no sentence under it is
        # a checkbox nobody knows whether to tick.
        for feature in features.all_features():
            self.assertTrue(feature.label, feature.name)
            self.assertTrue(feature.description.endswith("."), feature.name)


class TestGrantingThroughTheEndpoint(BaseTestCase):
    def _path(self, group):
        return "/api/groups/{}/permissions".format(group.id)

    def test_a_feature_the_install_offers_can_be_granted(self):
        admin = self.factory.create_admin()
        group = self.factory.create_group(name="Analysts")
        db.session.add(group)
        db.session.commit()

        with mock.patch.object(settings, "FEATURE_AI", True):
            rv = self.make_request("post", self._path(group), data={"use_mcp": True}, user=admin)

        self.assertEqual(200, rv.status_code)
        self.assertIn("use_mcp", rv.json["permissions"])

    def test_one_it_does_not_offer_cannot_be(self):
        admin = self.factory.create_admin()
        group = self.factory.create_group(name="Analysts")
        db.session.add(group)
        db.session.commit()

        with mock.patch.object(settings, "FEATURE_AI", False):
            rv = self.make_request("post", self._path(group), data={"use_mcp": True}, user=admin)

        self.assertEqual(400, rv.status_code)
        self.assertNotIn("use_mcp", group.permissions or [])

    def test_the_client_is_told_what_can_be_granted(self):
        with mock.patch.object(settings, "FEATURE_AI", True):
            rv = self.make_request("get", "/api/session", user=self.factory.create_admin())

        offered = {feature["name"] for feature in rv.json["client_config"]["grantableFeatures"]}
        self.assertIn("use_mcp", offered)
        self.assertTrue(
            all("label" in f and "description" in f for f in rv.json["client_config"]["grantableFeatures"])
        )
