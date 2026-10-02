"""
The three states, and what decides which one a stream is in.

The middle one is the point. Binary -- running or not -- means either a stream
nobody is watching keeps consuming, or stepping away for two minutes costs you
the window and you come back to an empty chart. Paused keeps the window and
drops the consumer, so coming back resumes in seconds.
"""

import datetime
import time
from unittest import mock

from sqldesk import redis_connection
from sqldesk.streams import watching
from sqldesk.utils import utcnow
from tests import BaseTestCase


class WatchingTestCase(BaseTestCase):
    def stream(self, last_viewed_at=None, pinned=False):
        from sqldesk import models

        source = self.factory.create_data_source(name="Cluster", type="kafka_stream")
        stream = models.Stream(
            org=source.org,
            data_source=source,
            topic="orders",
            pinned=pinned,
            last_viewed_at=last_viewed_at,
        )
        models.db.session.add(stream)
        models.db.session.commit()
        redis_connection.delete(watching._key(stream.id))
        return stream


class TestWhoIsWatching(WatchingTestCase):
    def test_a_check_in_counts(self):
        stream = self.stream()

        watching.check_in(stream.id, "ada")

        self.assertEqual(1, watching.watchers(stream.id))

    def test_two_people_count_as_two(self):
        # What the page needs to say "four other people are looking at this".
        stream = self.stream()

        watching.check_in(stream.id, "ada")
        watching.check_in(stream.id, "grace")

        self.assertEqual(2, watching.watchers(stream.id))

    def test_the_same_person_twice_counts_once(self):
        stream = self.stream()

        watching.check_in(stream.id, "ada")
        watching.check_in(stream.id, "ada")

        self.assertEqual(1, watching.watchers(stream.id))

    def test_a_check_in_that_has_aged_out_does_not(self):
        stream = self.stream()

        watching.check_in(stream.id, "ada", now=time.time() - 300)

        self.assertEqual(0, watching.watchers(stream.id))

    def test_leaving_says_so_at_once(self):
        # A hidden tab does this rather than waiting to be timed out, so a
        # stream nobody is looking at stops within seconds rather than within
        # the window.
        stream = self.stream()
        watching.check_in(stream.id, "ada")

        watching.left(stream.id, "ada")

        self.assertEqual(0, watching.watchers(stream.id))


class TestTheThreeStates(WatchingTestCase):
    def test_somebody_watching_is_running(self):
        stream = self.stream()
        watching.check_in(stream.id, "ada")

        self.assertEqual(watching.RUNNING, watching.state(stream))

    def test_nobody_watching_but_seen_recently_is_paused(self):
        stream = self.stream(last_viewed_at=utcnow() - datetime.timedelta(minutes=1))

        self.assertEqual(watching.PAUSED, watching.state(stream))

    def test_nobody_for_a_long_time_is_cold(self):
        stream = self.stream(last_viewed_at=utcnow() - datetime.timedelta(hours=2))

        self.assertEqual(watching.COLD, watching.state(stream))

    def test_one_nobody_has_ever_watched_is_cold(self):
        self.assertEqual(watching.COLD, watching.state(self.stream()))

    def test_a_pinned_stream_is_always_running(self):
        # The few that genuinely have to be there at 3am.
        stream = self.stream(pinned=True)

        self.assertEqual(watching.RUNNING, watching.state(stream))

    def test_the_cold_threshold_is_the_setting(self):
        stream = self.stream(last_viewed_at=utcnow() - datetime.timedelta(minutes=5))

        with mock.patch("sqldesk.settings.STREAM_COLD_MINUTES", 10):
            self.assertEqual(watching.PAUSED, watching.state(stream))
        with mock.patch("sqldesk.settings.STREAM_COLD_MINUTES", 2):
            self.assertEqual(watching.COLD, watching.state(stream))
