"""
Who is watching a stream, and the three states that follow from it.

A stream is in one of three states, and the middle one is the one that makes
this bearable to use:

- **running** -- somebody has checked in within the last 45 seconds.
- **paused** -- nobody has, so the consumer stops. The window is kept, so
  coming back resumes in seconds rather than starting from an empty chart.
- **cold** -- nobody for ten minutes. The window is dropped, the disk comes
  back, and starting again is a deliberate act with a button that says so.

Check-ins live in Redis, not in the database. The question has a resolution of
seconds and every open tab asks it every ten; a row written per viewer per
check-in would turn reading a chart into writing to the database, which is the
mistake the live dashboards avoided for the same reason.

**A pause leaves a hole in the chart, and the chart has to say so.** Resuming
seeks to the end of the topic like starting does, because replaying the gap
would stamp old events with an arrival time of now. So the events for the
paused stretch are genuinely not there -- and a flat line that actually means
"nobody was watching" is the most misleading thing this could draw.
"""

import datetime
import logging
import time

from sqldesk import redis_connection, settings
from sqldesk.utils import utcnow

logger = logging.getLogger(__name__)

RUNNING = "running"
PAUSED = "paused"
COLD = "cold"


def _key(stream_id):
    return "stream:watchers:{}".format(stream_id)


def check_in(stream_id, viewer, now=None):
    """
    Record that this viewer still has the stream in front of them.

    One entry per viewer rather than a single flag, so the page can say how
    many people are watching -- which is the difference between "stop this, it
    is yours" and "stop this, four other people are looking at it".
    """
    now = now or time.time()
    try:
        key = _key(stream_id)
        redis_connection.zadd(key, {str(viewer): now})
        # Trim as we go: a viewer who never says goodbye otherwise stays in the
        # set for ever, and the count is what the page shows.
        redis_connection.zremrangebyscore(key, "-inf", now - settings.STREAM_WATCH_SECONDS)
        redis_connection.expire(key, settings.STREAM_COLD_MINUTES * 60 + 60)
    except Exception:
        logger.warning("could not record a viewer of stream %s", stream_id, exc_info=True)


def left(stream_id, viewer):
    """A viewer saying so, rather than being timed out. A hidden tab does this."""
    try:
        redis_connection.zrem(_key(stream_id), str(viewer))
    except Exception:
        logger.warning("could not remove a viewer of stream %s", stream_id, exc_info=True)


def watchers(stream_id, now=None):
    """How many people are watching, counting only recent check-ins."""
    now = now or time.time()
    try:
        return int(redis_connection.zcount(_key(stream_id), now - settings.STREAM_WATCH_SECONDS, "+inf") or 0)
    except Exception:
        # Say nobody. The consequence is a stream that pauses when it did not
        # have to, which costs a few seconds on the next check-in; saying
        # somebody would mean a stream that never stops.
        logger.warning("could not count the viewers of stream %s", stream_id, exc_info=True)
        return 0


def being_watched(now=None):
    """
    The ids of every stream somebody is checking in on.

    The supervisor needs this because the two signals are not the same. A
    check-in lives in Redis and lasts 45 seconds; `last_viewed_at` is a
    database column written at most once a minute. A stream somebody started
    watching a moment ago has the first and not necessarily the second, and a
    supervisor that only read the second would not start it -- which is a
    person pressing Start streaming and nothing happening.

    One SCAN a minute over a handful of keys, rather than a column that would
    have to be written by every viewer on every check-in.
    """
    now = now or time.time()
    found = set()
    try:
        for key in redis_connection.scan_iter(match=_key("*")):
            name = key.decode("utf-8") if isinstance(key, bytes) else key
            stream_id = name.rsplit(":", 1)[-1]
            try:
                if redis_connection.zcount(name, now - settings.STREAM_WATCH_SECONDS, "+inf"):
                    found.add(int(stream_id))
            except (TypeError, ValueError):
                continue
    except Exception:
        # Say nobody. A stream that is not started is a chart somebody can
        # start; a crash here would stop the supervisor doing anything at all.
        logger.warning("could not ask who is watching", exc_info=True)
    return found


def state(stream, now=None):
    """Which of the three a stream is in."""
    if watchers(stream.id):
        return RUNNING
    if stream.pinned:
        # Pinned streams are the few that genuinely have to be there at 3am.
        return RUNNING
    last = stream.last_viewed_at
    if last is None:
        return COLD
    now = now or utcnow()
    if (now - last) <= datetime.timedelta(minutes=settings.STREAM_COLD_MINUTES):
        return PAUSED
    return COLD
