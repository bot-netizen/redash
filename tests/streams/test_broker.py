"""
The one part that needs a real broker: `Broker` itself.

Everything above it is driven by a fake elsewhere in this directory, which is
the right trade -- the sampling, the window and the rollup have nothing to do
with Kafka. What a fake cannot tell us is whether librdkafka behaves as
`Broker` assumes, and the assumption worth checking is the seek: the window is
"now", so a consumer that replayed a backlog would stamp hour-old events with
an arrival time of now and draw a chart that is a lie.

Skipped where no broker is running, and **loudly** -- a silent skip is how an
integration test stops running for six months without anybody noticing. Start
one with:

    docker compose --profile streams up -d broker
"""

import json
import os
import shutil
import tempfile
import time
import unittest
import uuid
from unittest import mock

from sqldesk import models
from sqldesk.models import db
from sqldesk.streams import consumer
from sqldesk.streams.store import Store
from tests import BaseTestCase

#: Inside the test container the broker is a compose service; from the host it
#: is the published port.
BROKERS = os.environ.get("SQLDESK_TEST_BROKERS", "broker:9092")


def broker_is_running():
    try:
        from sqldesk.query_runner import installed

        if not installed("confluent_kafka"):
            return False
        from confluent_kafka.admin import AdminClient

        AdminClient({"bootstrap.servers": BROKERS}).list_topics(timeout=5)
        return True
    except Exception:
        return False


HAVE_BROKER = broker_is_running()
WHY_NOT = "no broker at {} -- `docker compose --profile streams up -d broker`".format(BROKERS)


@unittest.skipUnless(HAVE_BROKER, WHY_NOT)
class BrokerTestCase(BaseTestCase):
    def setUp(self):
        super().setUp()
        from confluent_kafka import Producer
        from confluent_kafka.admin import AdminClient, NewTopic

        self.topic = "sqldesk-test-{}".format(uuid.uuid4().hex[:8])
        admin = AdminClient({"bootstrap.servers": BROKERS})
        for future in admin.create_topics([NewTopic(self.topic, num_partitions=1, replication_factor=1)]).values():
            future.result(timeout=20)
        self.addCleanup(lambda: admin.delete_topics([self.topic]))

        self.producer = Producer({"bootstrap.servers": BROKERS})
        self.folder = tempfile.mkdtemp()
        patch = mock.patch("sqldesk.settings.UPLOAD_ROOT", self.folder)
        patch.start()
        self.addCleanup(patch.stop)
        self.addCleanup(lambda: shutil.rmtree(self.folder, ignore_errors=True))

    def produce(self, *payloads, key=None):
        for payload in payloads:
            self.producer.produce(self.topic, json.dumps(payload).encode("utf-8"), key=key)
        self.producer.flush(10)

    def stream(self, **fields):
        source = self.factory.create_data_source(
            name="Topic", type="duckdb", options={"brokers": BROKERS, "topic": self.topic}
        )
        stream = models.Stream(org=self.factory.org, data_source=source, topic=self.topic, **fields)
        db.session.add(stream)
        db.session.commit()
        return stream

    def broker(self, group=None):
        made = consumer.Broker(
            brokers=BROKERS, topic=self.topic, group=group or "sqldesk-test-{}".format(uuid.uuid4().hex[:8])
        )
        self.addCleanup(made.close)
        return made

    def drain(self, broker, seconds=10):
        """Poll until something arrives or the time is up."""
        collected = []
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline and not collected:
            collected.extend(broker.poll(timeout=0.5))
        return collected


class TestTalkingToARealBroker(BrokerTestCase):
    def test_messages_come_back_as_raw_bytes(self):
        broker = self.broker().open()
        self.drain(broker, seconds=3)
        broker.seek_to_end()
        self.produce({"x": 1}, {"x": 2})

        collected = self.drain(broker)

        self.assertTrue(collected)
        for key, value in collected:
            # Undecoded, which is the contract the whole ingest path rests on.
            self.assertIsInstance(value, bytes)

    def test_the_key_comes_back_as_bytes_too(self):
        # Sampling hashes it without decoding, so a key that is not valid UTF-8
        # must not be a problem.
        broker = self.broker().open()
        self.drain(broker, seconds=3)
        broker.seek_to_end()
        self.produce({"x": 1}, key=b"\xff\xfe-not-text")

        collected = self.drain(broker)

        self.assertEqual(b"\xff\xfe-not-text", collected[0][0])

    def test_describe_topic_finds_a_topic_that_exists(self):
        self.assertIsNone(consumer.describe_topic({"brokers": BROKERS, "topic": self.topic}))

    def test_and_says_so_about_one_that_does_not(self):
        problem = consumer.describe_topic({"brokers": BROKERS, "topic": "no-such-topic-here"})

        self.assertIn("no topic called", problem)

    def test_and_about_a_broker_that_is_not_there(self):
        problem = consumer.describe_topic({"brokers": "127.0.0.1:1", "topic": self.topic}, seconds=2)

        self.assertIn("Could not reach the broker", problem)


class TestTheSeekThatMattersMost(BrokerTestCase):
    def test_a_backlog_is_not_replayed_on_a_fresh_start(self):
        """
        The window is "now". A consumer that replayed an hour of backlog would
        fill five minutes of window with events from an hour ago, stamped with
        an arrival time of now -- a chart that is a lie rather than merely
        stale.
        """
        self.produce({"old": 1}, {"old": 2}, {"old": 3})
        stream = self.stream(pinned=True)
        broker = self.broker()
        flushes = []

        with mock.patch("sqldesk.settings.STREAM_FLUSH_SECONDS", 0.2):
            with mock.patch.object(
                consumer, "flush_once", side_effect=lambda *a, **k: flushes.append(a[2]) or consumer.Flush()
            ):
                consumer.consume(stream, broker, lambda: len(flushes) < 2)

        stored = [value for batch in flushes for _key, value in batch]
        self.assertEqual([], stored)

    def test_but_what_arrives_afterwards_is(self):
        # The other half: seeking to the end must not mean seeing nothing ever.
        self.produce({"old": 1})
        stream = self.stream(pinned=True)
        broker = self.broker()
        collected = []

        def flush(stream_arg, store_arg, messages, **kwargs):
            collected.extend(messages)
            if len(collected) == 0:
                self.produce({"fresh": 1})
            return consumer.Flush()

        with mock.patch("sqldesk.settings.STREAM_FLUSH_SECONDS", 0.2):
            with mock.patch.object(consumer, "flush_once", side_effect=flush):
                consumer.consume(stream, broker, lambda: len(collected) < 1)

        self.assertTrue(collected)
        self.assertIn(b"fresh", collected[0][1])

    def test_a_group_that_has_run_before_still_starts_at_the_end(self):
        """
        `auto.offset.reset=latest` only applies when the group has *no*
        committed offset. A group that has run before has one, which is why the
        seek is done by assignment rather than left to configuration -- and this
        is the test that would catch somebody simplifying it away.
        """
        group = "sqldesk-test-returning-{}".format(uuid.uuid4().hex[:8])
        first = self.broker(group=group).open()
        self.drain(first, seconds=3)
        self.produce({"seen": 1})
        self.drain(first)
        first.close()

        self.produce({"backlog": 1}, {"backlog": 2})
        second = self.broker(group=group).open()
        self.drain(second, seconds=3)
        second.seek_to_end()
        after_seek = []
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            after_seek.extend(second.poll(timeout=0.5))

        self.assertEqual([], [value for _key, value in after_seek if b"backlog" in value])


class TestEndToEndThroughTheStore(BrokerTestCase):
    def test_events_from_a_real_topic_land_in_the_store(self):
        stream = self.stream(pinned=True)
        broker = self.broker()
        store = Store(stream.store_path())
        self.addCleanup(store.close)

        def produce_once(*_args, **_kwargs):
            self.produce({"region": "eu", "amount": 10}, {"region": "us", "amount": 5})

        broker.open()
        self.drain(broker, seconds=3)
        broker.seek_to_end()
        produce_once()
        collected = self.drain(broker)

        added, malformed = store.append([value for _key, value in collected])

        self.assertEqual(2, added)
        self.assertEqual(0, malformed)
        rows = store.connection.execute("SELECT region, amount FROM events ORDER BY region").fetchall()
        self.assertEqual([("eu", 10), ("us", 5)], rows)


class TestTheSkipIsLoud(unittest.TestCase):
    def test_the_reason_says_how_to_start_a_broker(self):
        # A silent skip is how an integration test stops running for six months
        # without anybody noticing.
        self.assertIn("docker compose", WHY_NOT)
        self.assertIn(BROKERS, WHY_NOT)
