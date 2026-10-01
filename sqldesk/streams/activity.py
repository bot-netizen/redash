"""
When a stream is worth consuming.

A stream is **active** while something that uses it has been looked at in the
last fifteen minutes, or while an administrator has pinned it always-on.

Both extremes are wrong. Always-on burns a worker and a disk for a dashboard
nobody has open -- and a stream's cost is continuous, unlike a query's, so an
unwatched stream is the one thing in SQLDesk that costs money while doing
nothing for anybody. Consuming only while a dashboard is literally open means
arriving at it to an empty chart every time, which makes the feature feel
broken on the first look every time. Fifteen minutes is the middle: long enough
that leaving a dashboard and coming back finds it still filling, short enough
that a topic nobody has opened since yesterday is not being stored.

The pin covers the few streams that genuinely have to be there at 3am, and it
is a deliberate act with a name on it rather than a default.

**On resume, seek to the end.** The window is "now", so replaying an hour of
backlog to fill five minutes is waste -- and worse, it fills the window with
events from an hour ago under an arrival time of now, which would be a chart
that lies. A consumer group per stream so the broker tracks us, and a
deliberate seek to latest so we do not use what it tracked.
"""

import datetime

from sqldesk import models, settings
from sqldesk.utils import utcnow


def is_active(stream, now=None):
    """Whether this stream should be being consumed."""
    if stream.pinned:
        return True
    if stream.last_viewed_at is None:
        return False
    now = now or utcnow()
    return (now - stream.last_viewed_at) <= datetime.timedelta(minutes=settings.STREAM_ACTIVE_MINUTES)


def active_streams(now=None):
    """
    Every stream worth a consumer, across every organisation.

    Asked by the worker that starts and stops them, so it is one query rather
    than one per stream: a hundred streams checked individually is a hundred
    round trips a minute for an answer that is mostly "no".
    """
    cutoff = (now or utcnow()) - datetime.timedelta(minutes=settings.STREAM_ACTIVE_MINUTES)
    return (
        models.Stream.query.filter(
            models.db.or_(
                models.Stream.pinned.is_(True),
                models.Stream.last_viewed_at >= cutoff,
            )
        )
        .order_by(models.Stream.id)
        .all()
    )


def note_viewed(stream, now=None):
    """
    Record that somebody looked at something using this stream.

    Written at most once a minute per stream. Every widget on every dashboard
    refresh would otherwise be an UPDATE, and the question this answers only
    has a fifteen-minute resolution -- writing it sixty times a minute buys
    nothing and turns reading a dashboard into writing to the database.
    """
    now = now or utcnow()
    if stream.last_viewed_at is not None and (now - stream.last_viewed_at) < datetime.timedelta(minutes=1):
        return False
    stream.last_viewed_at = now
    models.db.session.add(stream)
    models.db.session.commit()
    return True


def why_it_is_quiet(stream, now=None):
    """
    What the stream's page says when nothing is arriving, or None.

    Three different situations look identical on a chart -- nobody has looked at
    it lately, the consumer stopped with an error, or the topic genuinely has
    nothing on it -- and only one of them is a problem. Telling them apart is
    the difference between a page somebody can act on and a page that looks
    broken.
    """
    if stream.last_error:
        return stream.last_error
    if not is_active(stream, now=now):
        if stream.last_viewed_at is None:
            return (
                "Nothing has used this stream yet, so nothing is being consumed. "
                "Open a dashboard or a query that reads it, or pin it to keep it always on."
            )
        return (
            "Paused: nothing has used this stream in {} minutes. It starts again when something does, "
            "or pin it to keep it always on.".format(settings.STREAM_ACTIVE_MINUTES)
        )
    if not stream.rows:
        return "Consuming, but nothing has arrived on the topic yet."
    return None
