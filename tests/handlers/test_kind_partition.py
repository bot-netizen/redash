from unittest import mock

from sqldesk import features, models
from sqldesk.serializers import serialize_dashboard, serialize_query
from tests import BaseTestCase

"""
Streaming and saved are two halves of one set, not two views of it.

The rule: nothing appears in both. A query or a dashboard filed in two places
gives "where is my query" two answers, and the person who has to reconcile
them is whoever built it. So every list endpoint has to understand `?kind=`,
not merely the first one -- the version this replaces had it on
`/api/dashboards` alone, while Mine and Favorites went on showing both kinds.

Two exceptions, deliberate: search returns both, because somebody searching by
name does not know which half a thing is in, and a folder shows both, because
a folder is a place and not a type.

`streaming_source_types()` is patched throughout rather than trusting the
Kafka runner to be registered. It rides in an optional dependency group, and
in an image without it every test here would pass by accident -- nothing would
be streaming, and the two halves would agree about an empty set.
"""


def _streaming_is(*types):
    return mock.patch.object(models, "streaming_source_types", lambda: list(types))


def _streams_offered():
    """Hold the feature gate open; it is shut unless the deployment asked."""
    return mock.patch.object(features.by_name(features.USE_STREAMS), "_enabled", lambda: True)


class KindTestCase(BaseTestCase):
    def setUp(self):
        super().setUp()
        self.cluster = self.factory.create_data_source(
            name="Cluster", type="kafka_stream", group=self.factory.default_group
        )

    def ids(self, path):
        rv = self.make_request("get", path)
        self.assertEqual(rv.status_code, 200)
        return {row["id"] for row in rv.json["results"]}


class TestQueryLists(KindTestCase):
    def setUp(self):
        super().setUp()
        self.saved = self.factory.create_query(name="Saved one")
        self.streaming = self.factory.create_query(name="Streaming one", data_source=self.cluster)

    def test_the_ordinary_list_leaves_the_streaming_ones_out(self):
        with _streaming_is("kafka_stream"):
            self.assertEqual({self.saved.id}, self.ids("/api/queries?kind=saved"))

    def test_and_the_streaming_list_holds_only_those(self):
        with _streaming_is("kafka_stream"):
            self.assertEqual({self.streaming.id}, self.ids("/api/queries?kind=streaming"))

    def test_asking_for_neither_gets_both(self):
        # What search relies on, and the behaviour every caller had before
        # `kind` existed -- so an old client is not quietly shown half its
        # queries.
        with _streaming_is("kafka_stream"):
            self.assertEqual({self.saved.id, self.streaming.id}, self.ids("/api/queries"))

    def test_a_kind_nobody_recognises_is_ignored_rather_than_refused(self):
        with _streaming_is("kafka_stream"):
            self.assertEqual({self.saved.id, self.streaming.id}, self.ids("/api/queries?kind=wat"))

    def test_mine_is_split_too(self):
        with _streaming_is("kafka_stream"):
            self.assertEqual({self.saved.id}, self.ids("/api/queries/my?kind=saved"))
            self.assertEqual({self.streaming.id}, self.ids("/api/queries/my?kind=streaming"))

    def test_and_favorites(self):
        self.make_request("post", "/api/queries/{}/favorite".format(self.saved.id))
        self.make_request("post", "/api/queries/{}/favorite".format(self.streaming.id))

        with _streaming_is("kafka_stream"):
            self.assertEqual({self.saved.id}, self.ids("/api/queries/favorites?kind=saved"))
            self.assertEqual({self.streaming.id}, self.ids("/api/queries/favorites?kind=streaming"))

    def test_and_the_archive(self):
        for query in (self.saved, self.streaming):
            query.is_archived = True
            query.is_draft = False
        models.db.session.commit()

        with _streaming_is("kafka_stream"):
            self.assertEqual({self.saved.id}, self.ids("/api/queries/archive?kind=saved"))
            self.assertEqual({self.streaming.id}, self.ids("/api/queries/archive?kind=streaming"))

    def test_a_query_pointed_at_nothing_is_in_neither_half_and_in_no_list(self):
        # `NOT IN` against a NULL is NULL rather than true, so such a query
        # falls out of both halves. Harmless, and worth pinning: these lists
        # are built on `all_queries()`, which joins DataSourceGroup to decide
        # what somebody may see, so a query with no data source is invisible
        # anyway -- the partition is not what hides it. Anyone adding a list
        # without that join has to decide what to do with these rows.
        orphan = self.factory.create_query(name="Unpointed")
        orphan.data_source_id = None
        models.db.session.commit()

        with _streaming_is("kafka_stream"):
            self.assertNotIn(orphan.id, self.ids("/api/queries"))
            self.assertNotIn(orphan.id, self.ids("/api/queries?kind=saved"))
            self.assertNotIn(orphan.id, self.ids("/api/queries?kind=streaming"))

    def test_the_serializer_says_which_a_query_is(self):
        # What decides whether a link goes to the stream editor: a streaming
        # query has no stored result, so it has no view page to go to.
        with _streaming_is("kafka_stream"):
            self.assertTrue(serialize_query(self.streaming)["is_streaming"])
            self.assertFalse(serialize_query(self.saved)["is_streaming"])


class TestDashboardLists(KindTestCase):
    def setUp(self):
        super().setUp()
        self.saved = self.factory.create_dashboard(name="Saved board")
        self.streaming = self.factory.create_dashboard(name="Streaming board", kind="streaming")
        models.db.session.commit()

    def test_the_two_lists_do_not_overlap(self):
        self.assertEqual({self.saved.id}, self.ids("/api/dashboards?kind=saved"))
        self.assertEqual({self.streaming.id}, self.ids("/api/dashboards?kind=streaming"))

    def test_mine_is_split_too(self):
        self.assertEqual({self.saved.id}, self.ids("/api/dashboards/my?kind=saved"))
        self.assertEqual({self.streaming.id}, self.ids("/api/dashboards/my?kind=streaming"))

    def test_and_favorites(self):
        self.make_request("post", "/api/dashboards/{}/favorite".format(self.saved.id))
        self.make_request("post", "/api/dashboards/{}/favorite".format(self.streaming.id))

        self.assertEqual({self.saved.id}, self.ids("/api/dashboards/favorites?kind=saved"))
        self.assertEqual({self.streaming.id}, self.ids("/api/dashboards/favorites?kind=streaming"))

    def test_a_folder_shows_both_because_a_folder_is_a_place(self):
        folder = models.DashboardFolder(org=self.factory.org, name="Ops", created_by=self.factory.user)
        models.db.session.add(folder)
        self.saved.folder = folder
        self.streaming.folder = folder
        models.db.session.commit()

        self.assertEqual(
            {self.saved.id, self.streaming.id},
            self.ids("/api/dashboards?folder={}".format(folder.id)),
        )

    def test_an_empty_streaming_dashboard_still_knows_what_it_is(self):
        # The bug the column exists for. While the kind was worked out from the
        # widgets, a dashboard with none was indistinguishable from an ordinary
        # one -- so a new streaming board appeared in the ordinary list and
        # moved out of it when its first widget landed, under its author.
        self.assertEqual(0, self.streaming.widgets.count())
        self.assertTrue(self.streaming.is_streaming)
        self.assertTrue(serialize_dashboard(self.streaming)["is_streaming"])
        self.assertEqual({self.streaming.id}, self.ids("/api/dashboards?kind=streaming"))


class TestDeclaringAKind(BaseTestCase):
    def test_an_ordinary_dashboard_is_what_you_get_by_default(self):
        rv = self.make_request("post", "/api/dashboards", data={"name": "Board"})

        self.assertEqual(rv.status_code, 200)
        self.assertFalse(rv.json["is_streaming"])

    def test_and_a_streaming_one_when_asked_for(self):
        admin = self.factory.create_admin()

        with _streams_offered():
            rv = self.make_request("post", "/api/dashboards", data={"name": "Board", "kind": "streaming"}, user=admin)

        self.assertEqual(rv.status_code, 200)
        self.assertTrue(rv.json["is_streaming"])

    def test_a_kind_that_is_neither_is_refused(self):
        rv = self.make_request("post", "/api/dashboards", data={"name": "Board", "kind": "sideways"})

        self.assertEqual(rv.status_code, 400)

    def test_and_streaming_is_refused_to_somebody_who_may_not_stream(self):
        # With the feature held open, so this fails on the grant and not on
        # whether the install offers streams at all -- otherwise it would pass
        # just as well with no permission check here.
        with _streams_offered():
            rv = self.make_request("post", "/api/dashboards", data={"name": "Board", "kind": "streaming"})

        self.assertEqual(rv.status_code, 403)
        self.assertEqual(0, models.Dashboard.query.filter_by(name="Board").count())

    def test_and_when_the_install_does_not_offer_streams_at_all(self):
        # Not even to an administrator, who may otherwise grant themselves any
        # feature the install offers. Shut explicitly rather than relying on
        # the environment: this image has both librdkafka and
        # SQLDESK_STREAMS_ENABLED, so the gate here is open by default and the
        # test would pass for no reason.
        admin = self.factory.create_admin()

        with mock.patch.object(features.by_name(features.USE_STREAMS), "_enabled", lambda: False):
            rv = self.make_request("post", "/api/dashboards", data={"name": "Board", "kind": "streaming"}, user=admin)

        self.assertEqual(rv.status_code, 403)


class TestTheWidgetGuard(KindTestCase):
    def _add(self, dashboard, visualization):
        return self.make_request(
            "post",
            "/api/widgets",
            data={
                "dashboard_id": dashboard.id,
                "visualization_id": visualization.id,
                "options": {},
                "width": 1,
                "text": "",
            },
        )

    def test_a_stream_does_not_go_on_an_ordinary_dashboard(self):
        dashboard = self.factory.create_dashboard()
        models.db.session.commit()
        streaming = self.factory.create_visualization(query_rel=self.factory.create_query(data_source=self.cluster))

        rv = self._add(dashboard, streaming)

        self.assertEqual(rv.status_code, 400)
        self.assertIn("ordinary dashboard", rv.json["message"])

    def test_and_a_saved_query_does_not_go_on_a_streaming_one(self):
        # The case the old rule could not catch. It compared against the
        # widgets already there, so an empty dashboard accepted anything and
        # the refusal could only ever arrive at the second panel -- after
        # somebody had built half a board on the strength of the first.
        dashboard = self.factory.create_dashboard(kind="streaming")
        models.db.session.commit()
        ordinary = self.factory.create_visualization()

        rv = self._add(dashboard, ordinary)

        self.assertEqual(rv.status_code, 400)
        self.assertIn("streaming dashboard", rv.json["message"])

    def test_a_matching_panel_is_allowed(self):
        dashboard = self.factory.create_dashboard(kind="streaming")
        models.db.session.commit()
        streaming = self.factory.create_visualization(query_rel=self.factory.create_query(data_source=self.cluster))

        rv = self._add(dashboard, streaming)

        self.assertEqual(rv.status_code, 200)

    def test_and_a_textbox_belongs_on_either(self):
        dashboard = self.factory.create_dashboard(kind="streaming")
        models.db.session.commit()

        rv = self.make_request(
            "post",
            "/api/widgets",
            data={
                "dashboard_id": dashboard.id,
                "visualization_id": None,
                "text": "A note",
                "options": {},
                "width": 1,
            },
        )

        self.assertEqual(rv.status_code, 200)
