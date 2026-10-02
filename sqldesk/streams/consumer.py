"""
The loop: collect raw bytes for a second, hand them to DuckDB, repeat.

What it does **not** do is the design. It does not decode a message, it does not
queue anything it cannot write, and it does not replay a backlog.

**Never buffer the overflow.** An unbounded queue in front of a slow writer is
the crash, not the protection against it -- it turns a topic doing more than the
ceiling into a worker that runs out of memory half an hour later, somewhere
else, for reasons nobody can trace back. The one-second flush is the bound:
whatever arrives in a second is either written or sampled away within that
second, and nothing accumulates between flushes.

**Seek to the end on every start.** The window is "now". Replaying an hour of
backlog to fill five minutes is waste, and worse than waste -- it would stamp
hour-old events with an arrival time of now and draw a chart that is a lie. A
consumer group per stream so the broker tracks our position, and a deliberate
seek to latest so we never use what it tracked.

Kafka itself is behind `Broker`, which is the only part that needs a broker to
exercise. Everything above it -- the sampling decision, the flush, the window,
the rate, the ceilings -- is driven in tests by a fake that returns bytes.
"""

import logging
import time

from sqldesk import models, settings
from sqldesk.query_runner import deferred
from sqldesk.streams import window
from sqldesk.streams.store import Store
from sqldesk.utils import utcnow

logger = logging.getLogger(__name__)

#: Imported when a stream is actually consumed, not at startup. `confluent_kafka`
#: is librdkafka behind a C extension, and most installs have no streams at all
#: -- the same reason every other data source's SDK is deferred.
confluent = deferred("confluent_kafka")
# A submodule of its own: `import confluent_kafka` does not bring `admin` with
# it, so reaching for `confluent.admin` raises AttributeError at the point of
# use -- which is how listing a cluster's topics came to be written and never
# to have run.
confluent_admin = deferred("confluent_kafka.admin")

#: How long to wait for messages in one `consume` call. Shorter than the flush
#: so a quiet topic still comes back and lets the loop do its housekeeping.
POLL_SECONDS = 0.5

#: Messages asked for in one call. Large enough that a busy topic is a few
#: calls a second rather than thousands; the flush, not this, is what bounds
#: memory.
BATCH = 10_000


class Broker:
    """
    The only part that talks to Kafka.

    A thin wrapper rather than a subclass, so the loop above can be handed
    something else in a test and nothing has to pretend to be librdkafka.
    """

    def __init__(self, brokers, topic, group, options=None):
        self.brokers = brokers
        self.topic = topic
        self.group = group
        self.options = options or {}
        self._consumer = None

    def open(self):
        config = {
            "bootstrap.servers": self.brokers,
            "group.id": self.group,
            # We seek to the end ourselves on every start, so a stored offset
            # would only ever be a backlog waiting to be replayed. `latest`
            # here is the same decision stated to the broker.
            "auto.offset.reset": "latest",
            # Nothing commits, because nothing resumes. The group exists so the
            # broker can balance partitions, not so it can remember a position.
            "enable.auto.commit": False,
        }
        config.update(self.options)
        self._consumer = confluent.Consumer(config)
        self._consumer.subscribe([self.topic])
        return self

    def poll(self, limit=BATCH, timeout=POLL_SECONDS):
        """
        Raw `(key, value)` byte pairs. Never decoded, never parsed.

        A message the broker reports an error for is dropped here rather than
        raised: a partition that has gone away is the broker's business and
        recovers on its own, and a consumer that died for one is a consumer
        somebody has to restart.
        """
        messages = self._consumer.consume(num_messages=limit, timeout=timeout)
        pairs = []
        for message in messages or []:
            if message.error():
                logger.debug("stream %s: %s", self.topic, message.error())
                continue
            pairs.append((message.key(), message.value()))
        return pairs

    def seek_to_end(self):
        """
        Start from now, discarding whatever position the group held.

        Done by assignment rather than by configuration, because
        `auto.offset.reset` only applies when there is *no* committed offset --
        and a group that has run before has one.
        """
        assigned = self._consumer.assignment()
        if not assigned:
            # Assignment arrives with the first poll, so a caller that has not
            # polled yet has nothing to seek. Not an error: the next start
            # will.
            return False
        for partition in assigned:
            try:
                self._consumer.seek(confluent.TopicPartition(partition.topic, partition.partition, -1))
            except Exception:
                logger.warning("could not seek %s to the end", partition, exc_info=True)
        return True

    def close(self):
        if self._consumer is not None:
            self._consumer.close()
            self._consumer = None


def describe_topic(options, topic=None, seconds=5):
    """
    Whether the broker will let us in and, if one is named, the topic exists.

    Returns None when all is well, and otherwise something a person can act on.
    Called when somebody saves the data source, which is the moment to find
    out: the alternative is a stream that looks configured and quietly consumes
    nothing until somebody opens a dashboard and finds it empty.

    Deliberately not a rate measurement. The plan's idea of sniffing the topic
    to report "~48,000 events/sec, so you will see a 1-in-10 sample" is worth
    having, but it means holding a connection open for ten seconds inside a
    request that saves a form -- and the rate is measured properly on the first
    flush anyway, which is where the page reads it from. This answers the
    question that cannot wait: will it connect at all.
    """
    brokers = (options or {}).get("brokers")
    topic = topic or (options or {}).get("topic")
    if not brokers:
        return "No bootstrap servers given."

    try:
        found = _metadata(options, seconds)
    except Exception as error:
        return "Could not reach the broker at {}: {}".format(brokers, error)

    # No topic named: the question was only whether the cluster answers, which
    # is what saving a cluster data source asks.
    if not topic:
        return None
    if topic not in (found.topics or {}):
        return "The broker has no topic called {!r}.".format(topic)
    partitions = len(found.topics[topic].partitions or {})
    if not partitions:
        return "The topic {!r} has no partitions.".format(topic)
    return None


def _metadata(options, seconds=5):
    admin = confluent_admin.AdminClient({"bootstrap.servers": (options or {}).get("brokers"), **_security(options)})
    return admin.list_topics(timeout=seconds)


def list_topics(options, seconds=5):
    """
    Every topic the cluster will tell us about.

    Metadata only -- no consumer, no messages, and fast enough to answer a page
    load. Internal topics are left out: `__consumer_offsets` and its kind are
    Kafka's own bookkeeping, and offering them as something to analyse is an
    invitation to a confusing afternoon.
    """
    found = _metadata(options, seconds)
    topics = []
    for name, described in (found.topics or {}).items():
        if name.startswith("_"):
            continue
        topics.append(
            {
                "name": name,
                "partitions": len(described.partitions or {}),
                # A topic the cluster is reporting an error for -- not
                # authorised, under-replicated -- is still worth listing, with
                # the reason, rather than silently missing.
                "problem": str(described.error) if described.error else None,
            }
        )
    return sorted(topics, key=lambda topic: topic["name"])


def _security(options):
    """The librdkafka settings a broker needs to let us in."""
    chosen = {}
    protocol = (options or {}).get("security_protocol")
    if protocol and protocol != "PLAINTEXT":
        chosen["security.protocol"] = protocol
    for key, setting in (
        ("sasl_mechanism", "sasl.mechanism"),
        ("sasl_username", "sasl.username"),
        ("sasl_password", "sasl.password"),
    ):
        value = (options or {}).get(key)
        if value:
            chosen[setting] = value
    return chosen


class Flush:
    """What one second of a topic came to. Returned so a caller can log it."""

    def __init__(self, received=0, kept=0, stored=0, malformed=0, sampled_at=1):
        self.received = received
        self.kept = kept
        self.stored = stored
        self.malformed = malformed
        self.sampled_at = sampled_at

    @property
    def dropped(self):
        return self.received - self.kept

    def __repr__(self):
        return "<Flush received={} stored={} malformed={} 1-in-{}>".format(
            self.received, self.stored, self.malformed, self.sampled_at
        )


def flush_once(stream, store, messages, now=None):
    """
    One flush: sample, write, trim, and update what the page reads.

    Takes the messages rather than fetching them, which is what makes the whole
    of this testable without a broker -- and makes the ordering explicit. The
    sampling decision comes first, because the point of sampling is to not do
    the work.
    """
    now = now or utcnow()
    rate = stream.sample_rate or 1

    kept = [
        value
        for position, (key, value) in enumerate(messages)
        if value is not None and window.keeps(key, rate, position=position)
    ]

    stored, malformed = store.append(kept)

    # Measured, then used. The window for the *next* flush follows from the rate
    # this one observed, which is the only honest order: a window chosen from a
    # rate nobody has measured is a guess with a number on it.
    observed = store.observed_rate()
    stream.observed_rate = observed
    stream.window_seconds = window.window_for(stream.budget, observed)
    stream.sample_rate = window.sample_rate_for(observed * rate, stream.ceiling)
    store.truncate(stream.window_seconds)
    stream.rows = store.rows()
    stream.malformed = (stream.malformed or 0) + malformed
    stream.last_flush_at = now
    if not stream.columns:
        stream.columns = [{"name": name, "type": kind} for name, kind in store.columns()]

    models.db.session.add(stream)
    models.db.session.commit()

    return Flush(received=len(messages), kept=len(kept), stored=stored, malformed=malformed, sampled_at=rate)


def consume(stream, broker, should_continue, now=None):
    """
    Run until `should_continue()` says otherwise.

    `should_continue` rather than a loop condition of its own, so the thing that
    decides -- is anybody watching, has an administrator paused it, is the
    worker shutting down -- stays outside and this stays testable.
    """
    store = Store(stream.store_path())
    try:
        broker.open()
        # One poll to get a partition assignment, then seek past whatever
        # position the group held. Whatever that poll returned is **thrown
        # away**: it is from before the seek, so storing it would put one stale
        # event into the window on every start -- stamped with an arrival time
        # of now, which is exactly the lie the seek exists to prevent.
        broker.poll(limit=1, timeout=POLL_SECONDS)
        broker.seek_to_end()

        while should_continue():
            started = time.monotonic()
            collected = []
            # At least one poll per flush, then as many more as the interval
            # allows. A plain `while elapsed < interval` polls zero times when
            # the interval is small or the clock is coarse, so the loop spun
            # flushing nothing while the topic piled up behind it.
            while True:
                collected.extend(broker.poll())
                if not should_continue():
                    break
                if time.monotonic() - started >= settings.STREAM_FLUSH_SECONDS:
                    break
            flush_once(stream, store, collected, now=now)
            # The window is a file and DuckDB gives it to one process at a
            # time. Held open for the whole run -- minutes -- this consumer
            # locked out every reader: the Streams page quietly fell back to
            # the schema stored on the row, and a query against the stream
            # failed outright with a conflicting lock. Closed after each flush,
            # the lock is held for the moment it is written and the seconds in
            # between belong to whoever wants to read. The next flush reopens
            # it; `Store.connection` is lazy.
            store.close()
    finally:
        broker.close()
        store.close()
