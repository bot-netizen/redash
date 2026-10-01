"""
How much of a topic to keep, and what to do when there is too much.

A fixed window is wrong in both directions. Thirty minutes of a 50,000/s topic
is gigabytes of JSON; five minutes of a 3/s topic is a chart with nine points
on it. So the budget is a number of rows -- which is what actually costs disk
and query time -- and the window is however many seconds that buys at the rate
the topic is doing right now.

Everything here is a pure function of numbers and bytes. None of it touches
Kafka, DuckDB or the database, which is why all of it can be checked.
"""

import hashlib

#: The window never shrinks below this, however busy the topic. Under five
#: minutes a "what is happening now" chart has too few points to read, and the
#: honest answer to a topic that fast is to sample rather than to shrink the
#: window until it is useless.
MIN_WINDOW = 300

#: And never grows past this, however quiet. Half an hour is as far back as
#: "now" means; past that the question is a historical one and the rollup --
#: or a warehouse -- is the right answer.
MAX_WINDOW = 1800


def window_for(row_budget, events_per_second):
    """
    How many seconds of raw events to keep.

    `row_budget / rate`, clamped. A quiet topic gets the full half hour; a busy
    one settles at five minutes and is sampled instead.

    A rate of zero means nothing has arrived yet, which is the full window: an
    empty stream costs nothing to keep and a new one should not start out
    pretending to be busy.
    """
    if row_budget <= 0:
        return MAX_WINDOW
    if events_per_second <= 0:
        return MAX_WINDOW
    return int(max(MIN_WINDOW, min(MAX_WINDOW, row_budget / events_per_second)))


def describe(window_seconds, rows):
    """
    What the dashboard says above the chart.

    The window is stated because it moves: a reader comparing two charts needs
    to know one is six minutes and the other is thirty, and a chart that
    silently changes the period it covers is a chart that lies slowly.
    """
    minutes = max(1, int(round(window_seconds / 60.0)))
    return "last {} minute{} · {} events".format(minutes, "" if minutes == 1 else "s", _short(rows))


def _short(count):
    for suffix, size in (("M", 1_000_000), ("k", 1_000)):
        if count >= size:
            value = count / size
            return "{:.1f}{}".format(value, suffix) if value < 10 else "{:.0f}{}".format(value, suffix)
    return str(count)


def sample_rate_for(events_per_second, ceiling):
    """
    One in how many events to keep, as an integer.

    1 means keep everything. Integer rather than a fraction so the decision per
    event is a comparison on a hash and nothing has to be random -- and so the
    figure on the chart ("1-in-20 sample") is a thing somebody can reason about
    rather than a percentage that moves every second.
    """
    if ceiling <= 0:
        return 1
    # Rounded up, and floored at 1. Rounding down would give "keep everything"
    # for a topic just over the ceiling, which is the case the ceiling exists
    # for; the floor is what makes a topic *under* it unsampled, so there is no
    # separate branch for that (an earlier version had one, and mutation
    # testing could not tell it from the arithmetic).
    return max(1, int(-(-events_per_second // ceiling)))


def keeps(key, sample_rate, position=0):
    """
    Whether to keep an event with this message key, at this sample rate.

    Deterministic on a hash of the key's **raw bytes** -- never decoded, never
    parsed. Two things follow and both matter: it costs a hash rather than a
    JSON parse, which is the entire point of the ingest design; and the same
    keys stay in across flushes, so a per-key count can be scaled back up
    honestly. Random sampling would give a different set of users every second
    and no count worth reporting.

    **A message with no key is sampled by its position instead.** Hashing the
    empty key puts every such message in one bucket, so a topic with no keys at
    all -- which is a perfectly ordinary topic -- would be either entirely kept
    or entirely dropped, and it was entirely dropped. A stream that silently
    stored nothing the moment it got busy looks exactly like a broker problem
    and is miserable to diagnose. Position gives a true one-in-N, and the
    "same keys stay in" property it gives up was never there for a topic with
    no keys to stay.
    """
    if sample_rate <= 1:
        return True
    if isinstance(key, str):
        key = key.encode("utf-8", "replace")
    if not key:
        return position % sample_rate == 0
    # First four bytes of SHA-1 is plenty: it only has to be uniform, and this
    # runs once per message at fifty thousand a second.
    bucket = int.from_bytes(hashlib.sha1(key).digest()[:4], "big")
    return bucket % sample_rate == 0


def scale_up(count, sample_rate):
    """
    What a sampled count means for the whole stream.

    Stated separately from the count so a caller has to decide to use it. A
    scaled figure is an estimate and the chart says so; a chart that quietly
    multiplied by twenty would be inventing nineteen events out of twenty.
    """
    return count * max(1, sample_rate)
