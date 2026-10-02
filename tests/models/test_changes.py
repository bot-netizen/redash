from sqldesk.models import Change, ChangeTrackingMixin, Query, db
from tests import BaseTestCase


def create_object(factory):
    obj = Query(
        name="Query",
        description="",
        query_text="SELECT 1",
        user=factory.user,
        data_source=factory.data_source,
        org=factory.org,
    )

    return obj


class TestChangesProperty(BaseTestCase):
    def test_returns_initial_state(self):
        obj = create_object(self.factory)

        for change in Change.query.filter(Change.object == obj):
            self.assertIsNone(change.change["previous"])


class TestLogChange(BaseTestCase):
    def obj(self):
        obj = Query(
            name="Query",
            description="",
            query_text="SELECT 1",
            user=self.factory.user,
            data_source=self.factory.data_source,
            org=self.factory.org,
        )

        return obj

    def test_properly_logs_first_creation(self):
        obj = create_object(self.factory)
        obj.record_changes(changed_by=self.factory.user)
        change = Change.last_change(obj)

        self.assertIsNotNone(change)
        self.assertEqual(change.object_version, 1)

    def test_skips_unnecessary_fields(self):
        obj = create_object(self.factory)
        obj.record_changes(changed_by=self.factory.user)
        change = Change.last_change(obj)

        self.assertIsNotNone(change)
        self.assertEqual(change.object_version, 1)
        for field in ChangeTrackingMixin.skipped_fields:
            self.assertNotIn(field, change.change)

    def test_properly_log_modification(self):
        obj = create_object(self.factory)
        obj.record_changes(changed_by=self.factory.user)
        obj.name = "Query 2"
        obj.description = "description"
        db.session.flush()
        obj.record_changes(changed_by=self.factory.user)

        change = Change.last_change(obj)

        self.assertIsNotNone(change)
        # TODO: changes are not recorded for every field yet.
        # self.assertEqual(change.object_version, 2)
        self.assertEqual(change.object_version, obj.version)
        self.assertIn("name", change.change)
        self.assertIn("description", change.change)

    def test_logs_create_method(self):
        q = Query(
            name="Query",
            description="",
            query_text="",
            user=self.factory.user,
            data_source=self.factory.data_source,
            org=self.factory.org,
        )
        change = Change.last_change(q)

        self.assertIsNotNone(change)
        self.assertEqual(q.user, change.user)


class TestWhatOneEditRecords(BaseTestCase):
    """
    The `previous` half of a change record.

    It was wrong for every field but the last one set: `__setattr__` re-read
    every column on every assignment, so setting a second field overwrote the
    first field's "previous" with the value it had just been given. Nothing
    read these records, so nothing noticed -- and the moment a page showed
    them it would have been showing a name that went from its new value to its
    new value.
    """

    def query(self):
        obj = Query(
            name="Query",
            description="first",
            query_text="SELECT 1",
            user=self.factory.user,
            data_source=self.factory.data_source,
            org=self.factory.org,
        )
        db.session.flush()
        return obj

    def test_two_fields_changed_at_once_both_remember_what_they_said(self):
        obj = self.query()
        obj.record_changes(changed_by=self.factory.user)

        obj.name = "Query 2"
        obj.description = "second"
        obj.record_changes(changed_by=self.factory.user)

        change = Change.last_change(obj).change

        self.assertEqual("Query", change["name"]["previous"])
        self.assertEqual("first", change["description"]["previous"])

    def test_a_record_is_measured_from_the_one_before_it(self):
        obj = self.query()
        obj.record_changes(changed_by=self.factory.user)
        obj.name = "Query 2"
        obj.record_changes(changed_by=self.factory.user)

        obj.name = "Query 3"
        obj.record_changes(changed_by=self.factory.user)

        change = Change.last_change(obj).change

        self.assertEqual("Query 2", change["name"]["previous"])
        self.assertEqual("Query 3", change["name"]["current"])

    def test_every_tracked_field_is_recorded_not_only_the_ones_that_moved(self):
        # A version somebody can be shown and restore. Recording the
        # differences alone would mean reading version four by replaying the
        # three before it.
        obj = self.query()
        obj.record_changes(changed_by=self.factory.user)
        obj.name = "Query 2"
        obj.record_changes(changed_by=self.factory.user)

        change = Change.last_change(obj).change

        self.assertEqual("SELECT 1", change["query"]["current"])

    def test_pending_changes_names_what_moved(self):
        obj = self.query()
        obj.record_changes(changed_by=self.factory.user)

        obj.name = "Query 2"

        self.assertEqual(["name"], list(obj.pending_changes()))

    def test_and_is_empty_when_nothing_did(self):
        # The editor sends the whole query whether or not anything in it moved.
        obj = self.query()
        obj.record_changes(changed_by=self.factory.user)

        obj.name = "Query"

        self.assertEqual({}, obj.pending_changes())

    def test_the_api_key_is_never_recorded(self):
        # It is a credential, and a change record is a copy of it that nothing
        # ever expires.
        obj = self.query()
        obj.record_changes(changed_by=self.factory.user)

        change = Change.last_change(obj).change

        self.assertNotIn("api_key", change)
        self.assertNotIn("search_vector", change)
