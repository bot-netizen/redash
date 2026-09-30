from unittest import mock

from sqldesk import features, settings
from sqldesk.models import DashboardSubscription, db
from tests import BaseTestCase


class TestTheSubscriptionItself(BaseTestCase):
    """
    A dashboard, mailed to some people, on a schedule. What it holds and, more
    to the point, what it refuses to hold.
    """

    def _subscription(self, **overrides):
        dashboard = overrides.pop("dashboard", None) or self.factory.create_dashboard()
        db.session.commit()

        fields = {
            "org": self.factory.org,
            "dashboard": dashboard,
            "user": self.factory.user,
            "schedule": {"interval": 86400, "time": "09:00"},
            "format": DashboardSubscription.PNG,
            "recipient_ids": [self.factory.user.id],
        }
        fields.update(overrides)
        subscription = DashboardSubscription(**fields)
        db.session.add(subscription)
        db.session.commit()
        return subscription

    def test_it_stores_what_a_send_needs(self):
        subscription = self._subscription()

        self.assertEqual(self.factory.org.id, subscription.org_id)
        self.assertTrue(subscription.active)
        self.assertIsNone(subscription.last_sent_at)
        self.assertIsNone(subscription.last_error)

    def test_recipients_are_resolved_rather_than_remembered(self):
        colleague = self.factory.create_user()
        db.session.commit()
        subscription = self._subscription(recipient_ids=[self.factory.user.id, colleague.id])

        self.assertEqual(
            sorted([self.factory.user.id, colleague.id]),
            sorted(user.id for user in subscription.recipients()),
        )

    def test_somebody_deleted_since_simply_stops_being_one(self):
        colleague = self.factory.create_user()
        db.session.commit()
        subscription = self._subscription(recipient_ids=[self.factory.user.id, colleague.id])

        db.session.delete(colleague)
        db.session.commit()

        self.assertEqual([self.factory.user.id], [user.id for user in subscription.recipients()])

    def test_and_so_does_somebody_in_another_organization(self):
        # An id is only an id. Resolving it has to be scoped, or a
        # subscription could name a stranger's user id and mail them.
        elsewhere = self.factory.create_org()
        stranger = self.factory.create_user(org=elsewhere)
        db.session.commit()
        subscription = self._subscription(recipient_ids=[self.factory.user.id, stranger.id])

        self.assertEqual([self.factory.user.id], [user.id for user in subscription.recipients()])

    def test_a_subscription_with_nobody_on_it_resolves_to_nobody(self):
        self.assertEqual([], self._subscription(recipient_ids=[]).recipients())
        self.assertEqual([], self._subscription(recipient_ids=None).recipients())

    def test_deleting_the_dashboard_takes_its_subscriptions(self):
        dashboard = self.factory.create_dashboard()
        self._subscription(dashboard=dashboard)

        db.session.delete(dashboard)
        db.session.commit()

        self.assertEqual(0, DashboardSubscription.query.count())

    def test_they_are_scoped_to_their_organization(self):
        self._subscription()
        elsewhere = self.factory.create_org()

        self.assertEqual(1, DashboardSubscription.all(self.factory.org).count())
        self.assertEqual(0, DashboardSubscription.all(elsewhere).count())

    def test_a_dashboard_knows_its_own(self):
        dashboard = self.factory.create_dashboard()
        self._subscription(dashboard=dashboard)
        self._subscription()  # somebody else's

        self.assertEqual(1, DashboardSubscription.for_dashboard(dashboard).count())


class TestWhoMaySendADashboard(BaseTestCase):
    """
    Sending needs the renderer, because there is nothing to send without a
    picture. Offering the feature where no renderer is configured would be
    offering a button that cannot work.
    """

    def _rendering(self, on):
        return mock.patch.multiple(
            settings,
            FEATURE_ALERT_SCREENSHOTS=on,
            SCREENSHOT_URL="http://screenshots:3000" if on else "",
        )

    def test_it_is_offered_where_a_renderer_is_configured(self):
        with self._rendering(True):
            self.assertIn("send_dashboards", [f.name for f in features.grantable()])

    def test_and_not_where_none_is(self):
        with self._rendering(False):
            self.assertNotIn("send_dashboards", [f.name for f in features.grantable()])

    def test_a_group_granted_it_has_it(self):
        group = self.factory.create_group(name="Ops", permissions=["view_query", "send_dashboards"])
        db.session.add(group)
        db.session.commit()
        member = self.factory.create_user(group_ids=[group.id])

        with self._rendering(True):
            self.assertTrue(features.can(member, features.SEND_DASHBOARDS))

    def test_but_not_once_the_renderer_goes_away(self):
        # Granted in the database, and there is now nothing to draw with.
        group = self.factory.create_group(name="Ops", permissions=["view_query", "send_dashboards"])
        db.session.add(group)
        db.session.commit()
        member = self.factory.create_user(group_ids=[group.id])

        with self._rendering(False):
            self.assertFalse(features.can(member, features.SEND_DASHBOARDS))
            self.assertFalse(features.can(self.factory.create_admin(), features.SEND_DASHBOARDS))
