from sqldesk import models
from sqldesk.models import db
from tests import BaseTestCase


class TestEvents(BaseTestCase):
    def test_a_crafted_event_does_not_break_the_admin_page(self):
        # A client may post any event. One shaped like an execution but
        # without its `query` raised KeyError when an admin listed events,
        # and the page was gone for good.
        db.session.add(
            models.Event(
                org=self.factory.org,
                user=self.factory.user,
                action="execute_query",
                object_type="data_source",
                object_id=1,
                additional_properties={},
            )
        )
        db.session.commit()

        listed = self.make_request("get", "/api/events", user=self.factory.create_admin())

        self.assertEqual(200, listed.status_code)

    def test_posting_events_is_a_list_or_nothing(self):
        posted = self.make_request(
            "post", "/api/events", data=[{"action": "view", "object_type": "page", "object_id": "x"}]
        )
        self.assertEqual(200, posted.status_code)
        self.assertEqual(400, self.make_request("post", "/api/events", data={"action": "view"}).status_code)
