from unittest import mock

from sqldesk import models, settings, unsubscribe
from sqldesk.models import db
from tests import BaseTestCase


class UnsubscribeTestCase(BaseTestCase):
    def setUp(self):
        super().setUp()
        self.owner = self.factory.create_admin()
        self.colleague = self.factory.create_admin(email="colleague@example.com")
        self.dashboard = self.factory.create_dashboard()
        db.session.commit()

        self.subscription = models.DashboardSubscription(
            org=self.factory.org,
            dashboard=self.dashboard,
            user=self.owner,
            schedule={"interval": 3600},
            format=models.DashboardSubscription.PNG,
            recipient_ids=[self.owner.id, self.colleague.id],
            active=True,
        )
        db.session.add(self.subscription)
        db.session.commit()


class TestTheLink(UnsubscribeTestCase):
    def test_it_names_one_person_and_one_subscription(self):
        token = unsubscribe.token_for(self.subscription, self.colleague)

        subscription, user = unsubscribe.load(token)

        self.assertEqual(self.subscription.id, subscription.id)
        self.assertEqual(self.colleague.id, user.id)

    def test_a_forged_one_names_nobody(self):
        token = unsubscribe.token_for(self.subscription, self.colleague)

        self.assertEqual((None, None), unsubscribe.load(token[:-4] + "aaaa"))

    def test_one_signed_with_another_key_names_nobody(self):
        with mock.patch.object(settings, "SECRET_KEY", "somebody-elses-key"):
            token = unsubscribe.token_for(self.subscription, self.colleague)

        self.assertEqual((None, None), unsubscribe.load(token))

    def test_one_for_a_subscription_since_deleted_names_nobody(self):
        token = unsubscribe.token_for(self.subscription, self.colleague)
        db.session.delete(self.subscription)
        db.session.commit()

        self.assertEqual((None, None), unsubscribe.load(token))

    def test_one_naming_somebody_in_another_organization_names_nobody(self):
        # Both halves are signed together, so this needs the world to have
        # changed under the link -- somebody moved between organizations
        # since the email was sent. The check costs nothing and the
        # alternative is taking a stranger off somebody else's subscription.
        elsewhere = self.factory.create_org()
        stranger = self.factory.create_user(org=elsewhere)
        db.session.commit()
        token = unsubscribe.token_for(self.subscription, stranger)

        self.assertEqual((None, None), unsubscribe.load(token))

    def test_it_does_not_expire(self):
        # An email stays in a mailbox for years, and the link in it should
        # still work. What it can do is what is bounded, not for how long.
        token = unsubscribe.token_for(self.subscription, self.colleague)

        with mock.patch("sqldesk.unsubscribe.URLSafeSerializer", wraps=unsubscribe.URLSafeSerializer) as serializer:
            unsubscribe.load(token)

        # No max_age anywhere: a timed serializer would be the wrong tool.
        self.assertNotIn("max_age", str(serializer.mock_calls))


class TestTakingSomebodyOff(UnsubscribeTestCase):
    def test_it_removes_only_them(self):
        unsubscribe.remove(self.subscription, self.colleague)
        db.session.commit()

        self.assertEqual([self.owner.id], self.subscription.recipient_ids)
        self.assertTrue(self.subscription.active)

    def test_clicking_twice_is_the_same_as_clicking_once(self):
        # Mail clients pre-fetch, people double-click, and neither should see
        # an error about not being subscribed.
        self.assertTrue(unsubscribe.remove(self.subscription, self.colleague))
        self.assertFalse(unsubscribe.remove(self.subscription, self.colleague))

        self.assertEqual([self.owner.id], self.subscription.recipient_ids)

    def test_the_last_one_off_stops_the_subscription(self):
        # Left active it would wake every hour, draw a dashboard and mail it
        # to nobody.
        unsubscribe.remove(self.subscription, self.colleague)
        unsubscribe.remove(self.subscription, self.owner)
        db.session.commit()

        self.assertEqual([], self.subscription.recipient_ids)
        self.assertFalse(self.subscription.active)
        self.assertIn("unsubscribed", self.subscription.last_error)


class TestThePage(UnsubscribeTestCase):
    def _url(self, token):
        return "/unsubscribe/{}".format(token)

    def _post(self, token):
        # The org slug matters: only the org-scoped rules are registered in
        # the tests, and an unprefixed path falls through to the SPA
        # catch-all and answers 405. `base_url` adds the same prefix when the
        # install is multi-organization, so the link in a real email matches
        # the route either way.
        return self.client.post("/{}{}".format(self.factory.org.slug, self._url(token)))

    def test_opening_the_link_does_not_unsubscribe_anybody(self):
        # The whole point: mail clients and security scanners fetch every link
        # in a message before anybody has read it.
        token = unsubscribe.token_for(self.subscription, self.colleague)

        rv = self.get_request(self._url(token), org=self.factory.org)

        self.assertEqual(200, rv.status_code)
        self.assertIn(self.colleague.id, self.subscription.recipient_ids)

    def test_the_page_names_the_dashboard_and_the_person(self):
        token = unsubscribe.token_for(self.subscription, self.colleague)

        rv = self.get_request(self._url(token), org=self.factory.org)

        self.assertIn(self.dashboard.name.encode(), rv.data)
        self.assertIn(self.colleague.name.encode(), rv.data)

    def test_posting_does(self):
        token = unsubscribe.token_for(self.subscription, self.colleague)

        rv = self._post(token)

        self.assertEqual(200, rv.status_code)
        self.assertNotIn(self.colleague.id, self.subscription.recipient_ids)
        self.assertIn(b"unsubscribed", rv.data)

    def test_and_needs_no_csrf_token(self):
        # A mail client's own Unsubscribe button posts here with no page
        # behind it (RFC 8058), so a CSRF token is not something it could
        # have. The token in the URL is the credential.
        token = unsubscribe.token_for(self.subscription, self.colleague)

        rv = self._post(token)

        self.assertEqual(200, rv.status_code)

    def test_a_link_for_a_subscription_that_has_gone_says_so(self):
        token = unsubscribe.token_for(self.subscription, self.colleague)
        db.session.delete(self.subscription)
        db.session.commit()

        rv = self.get_request(self._url(token), org=self.factory.org)

        self.assertEqual(404, rv.status_code)
        self.assertIn(b"Nothing to unsubscribe from", rv.data)

    def test_a_tampered_link_says_the_same_thing(self):
        # Not "invalid signature": somebody holding a bad link learns nothing
        # about whether the subscription exists.
        rv = self.get_request(self._url("not-a-real-token"), org=self.factory.org)

        self.assertEqual(404, rv.status_code)
        self.assertIn(b"Nothing to unsubscribe from", rv.data)
