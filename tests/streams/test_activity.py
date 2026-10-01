"""
When a stream is consumed, and what its page says when it is not.

The cost of getting this wrong is not a wrong number, it is a worker and a disk
running all night for a dashboard nobody has open -- a stream is the one thing
in SQLDesk that costs money continuously rather than per query.
"""

import datetime
from unittest import mock

from sqldesk import models, settings
from sqldesk.models import db
from sqldesk.streams import activity
from sqldesk.utils import utcnow
from tests import BaseTestCase


def minutes_ago(count):
    return utcnow() - datetime.timedelta(minutes=count)


class ActivityTestCase(BaseTestCase):
    def stream(self, topic="events", **fields):
        source = self.factory.create_data_source(name="Topic " + topic, type="duckdb")
        stream = models.Stream(org=self.factory.org, data_source=source, topic=topic, **fields)
        db.session.add(stream)
        db.session.commit()
        return stream


class TestWhenAStreamIsConsumed(ActivityTestCase):
    def test_one_somebody_just_looked_at(self):
        self.assertTrue(activity.is_active(self.stream(last_viewed_at=minutes_ago(1))))

    def test_one_nobody_has_looked_at_for_an_hour(self):
        self.assertFalse(activity.is_active(self.stream(last_viewed_at=minutes_ago(60))))

    def test_one_nobody_has_ever_looked_at(self):
        # A topic added this morning and not yet used should not be storing
        # events all afternoon.
        self.assertFalse(activity.is_active(self.stream()))

    def test_a_pinned_one_whatever_anybody_does(self):
        # The few streams that genuinely have to be there at 3am. A deliberate
        # act with a name on it, not a default.
        self.assertTrue(activity.is_active(self.stream(pinned=True, last_viewed_at=minutes_ago(600))))

    def test_and_a_pinned_one_nobody_has_ever_opened(self):
        self.assertTrue(activity.is_active(self.stream(pinned=True)))

    def test_just_inside_the_window(self):
        with mock.patch("sqldesk.settings.STREAM_ACTIVE_MINUTES", 15):
            self.assertTrue(activity.is_active(self.stream(last_viewed_at=minutes_ago(14))))

    def test_and_just_outside_it(self):
        with mock.patch("sqldesk.settings.STREAM_ACTIVE_MINUTES", 15):
            self.assertFalse(activity.is_active(self.stream(last_viewed_at=minutes_ago(16))))

    def test_the_window_is_the_installs_own(self):
        stream = self.stream(last_viewed_at=minutes_ago(30))

        with mock.patch("sqldesk.settings.STREAM_ACTIVE_MINUTES", 60):
            self.assertTrue(activity.is_active(stream))


class TestFindingThemAll(ActivityTestCase):
    def test_in_one_query_rather_than_one_each(self):
        # A hundred streams checked individually is a hundred round trips a
        # minute for an answer that is mostly no.
        watched = self.stream("watched", last_viewed_at=minutes_ago(1))
        pinned = self.stream("pinned", pinned=True)
        self.stream("forgotten", last_viewed_at=minutes_ago(600))
        self.stream("never-opened")

        found = activity.active_streams()

        self.assertEqual({watched.id, pinned.id}, {stream.id for stream in found})

    def test_nothing_active_is_an_empty_list_not_an_error(self):
        self.stream("forgotten", last_viewed_at=minutes_ago(600))

        self.assertEqual([], activity.active_streams())

    def test_streams_in_every_organisation_are_found(self):
        # The worker that starts consumers is not per organisation, and a
        # stream nobody found is a dashboard that stays empty.
        ours = self.stream("ours", pinned=True)
        other = self.factory.create_org()
        theirs_source = self.factory.create_data_source(org=other, name="Theirs", type="duckdb")
        theirs = models.Stream(org=other, data_source=theirs_source, topic="theirs", pinned=True)
        db.session.add(theirs)
        db.session.commit()

        found = {stream.id for stream in activity.active_streams()}

        self.assertEqual({ours.id, theirs.id}, found)


class TestNotingThatSomebodyLooked(ActivityTestCase):
    def test_the_first_look_is_recorded(self):
        stream = self.stream()

        self.assertTrue(activity.note_viewed(stream))
        self.assertIsNotNone(stream.last_viewed_at)

    def test_a_dashboard_refreshing_does_not_write_every_widget(self):
        # Every widget on every refresh would be an UPDATE, for an answer whose
        # resolution is fifteen minutes.
        stream = self.stream()
        activity.note_viewed(stream)
        first = stream.last_viewed_at

        self.assertFalse(activity.note_viewed(stream))
        self.assertEqual(first, stream.last_viewed_at)

    def test_but_a_minute_later_it_does(self):
        stream = self.stream(last_viewed_at=minutes_ago(2))
        before = stream.last_viewed_at

        self.assertTrue(activity.note_viewed(stream))
        self.assertGreater(stream.last_viewed_at, before)

    def test_and_it_brings_a_paused_stream_back(self):
        stream = self.stream(last_viewed_at=minutes_ago(600))
        self.assertFalse(activity.is_active(stream))

        activity.note_viewed(stream)

        self.assertTrue(activity.is_active(stream))


class TestWhatThePageSaysWhenNothingArrives(ActivityTestCase):
    def test_a_stream_nobody_has_used_says_how_to_start_it(self):
        said = activity.why_it_is_quiet(self.stream())

        self.assertIn("Nothing has used this stream yet", said)
        self.assertIn("pin", said)

    def test_a_paused_one_says_it_is_paused_and_will_come_back(self):
        said = activity.why_it_is_quiet(self.stream(last_viewed_at=minutes_ago(600)))

        self.assertIn("Paused", said)
        self.assertIn("starts again", said)

    def test_an_error_is_said_instead_of_being_called_quiet(self):
        # Three situations look identical on a chart and only one is a problem.
        stream = self.stream(pinned=True, last_error="The broker refused the credentials.")

        self.assertEqual("The broker refused the credentials.", activity.why_it_is_quiet(stream))

    def test_an_active_stream_with_nothing_on_the_topic_says_so(self):
        said = activity.why_it_is_quiet(self.stream(pinned=True))

        self.assertIn("nothing has arrived", said)

    def test_and_a_working_one_says_nothing_at_all(self):
        stream = self.stream(pinned=True, rows=5000)

        self.assertIsNone(activity.why_it_is_quiet(stream))

    def test_the_error_is_preferred_over_the_pause(self):
        # A consumer that stopped with an error and then went unwatched has two
        # true things to say; the actionable one wins.
        stream = self.stream(last_viewed_at=minutes_ago(600), last_error="The topic does not exist.")

        self.assertEqual("The topic does not exist.", activity.why_it_is_quiet(stream))


class TestTheSettingsItReads(BaseTestCase):
    def test_the_defaults_are_the_ones_the_design_argues_for(self):
        # Pinned here because each of these is a cost decision: a budget that
        # is really a window, a ceiling that is really a sampling threshold,
        # and fifteen minutes of grace.
        self.assertEqual(5_000_000, settings.STREAM_ROW_BUDGET)
        self.assertEqual(5_000, settings.STREAM_EVENTS_PER_SECOND)
        self.assertEqual(20_000, settings.STREAM_GLOBAL_EVENTS_PER_SECOND)
        self.assertEqual(15, settings.STREAM_ACTIVE_MINUTES)
        self.assertEqual(1, settings.STREAM_FLUSH_SECONDS)

    def test_the_global_ceiling_is_above_one_streams(self):
        # Otherwise a single stream could never reach its own ceiling, and the
        # per-stream setting would be decoration.
        self.assertGreater(settings.STREAM_GLOBAL_EVENTS_PER_SECOND, settings.STREAM_EVENTS_PER_SECOND)
