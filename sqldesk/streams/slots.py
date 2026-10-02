"""
How many topics may be consumed at once, and who holds the right to one.

A stream's cost is continuous. A query is expensive for thirty seconds; a
consumer holds a worker, a broker connection and a disk for as long as anybody
is watching, so the thing that has to be bounded is not how hard it works but
how many of them exist. Without a limit, ten people each opening a different
topic takes ten workers out of the pool and the dashboards everybody else is
reading stop refreshing -- and the people who caused it are the only ones who
can see anything working.

**A slot is a topic, not a viewer.** Five people watching `orders` share one
consumer and one window; they take one slot between them. That is what makes a
cap of five mean "five topics" rather than "five tabs", and it makes the case
this feature exists for -- a team round one dashboard during an incident --
nearly free.

Held in Redis, under a short lock, because the question "are there slots left"
is asked and answered by several processes at once and a count that two of them
pass simultaneously is a cap that does not cap. The lock is held for the
microseconds it takes to read a hash and write one field.

A slot is **renewed while the stream runs and expires on its own**. Nothing
depends on a worker getting the chance to release it: a worker that is killed,
a browser that is closed with the laptop lid, a network that goes away -- all
of them end the same way, with the slot free a couple of minutes later.
"""

import logging
import time

from sqldesk import redis_connection, settings

logger = logging.getLogger(__name__)

SLOTS_KEY = "stream:slots"
LOCK_KEY = "stream:slots:lock"

#: The lock is held across one read and one write. A second is generous; what
#: it is really for is making sure a process that dies holding it does not stop
#: anybody else acquiring a slot ever again.
LOCK_SECONDS = 1

#: How long to wait for the lock before giving up and refusing. A refusal says
#: "try again"; blocking a request for longer than this is worse.
LOCK_WAIT_SECONDS = 2


class _Lock:
    def __enter__(self):
        deadline = time.monotonic() + LOCK_WAIT_SECONDS
        while time.monotonic() < deadline:
            if redis_connection.set(LOCK_KEY, "1", ex=LOCK_SECONDS, nx=True):
                self.held = True
                return self
            time.sleep(0.02)
        self.held = False
        return self

    def __exit__(self, *_):
        if self.held:
            try:
                redis_connection.delete(LOCK_KEY)
            except Exception:
                logger.warning("could not release the stream slot lock", exc_info=True)
        return False


def _text(value):
    return value.decode("utf-8") if isinstance(value, bytes) else value


def held(now=None):
    """
    `{stream_id: who started it}` for every slot in use.

    Expired entries are dropped as they are read rather than by anything
    sweeping: the only moment the answer has to be right is when somebody is
    asking, and that is the moment this runs.
    """
    now = now or time.time()
    try:
        raw = redis_connection.hgetall(SLOTS_KEY) or {}
    except Exception:
        logger.warning("could not read the stream slots", exc_info=True)
        return {}

    live, stale = {}, []
    for key, value in raw.items():
        stream_id = _text(key)
        expires, _, owner = _text(value).partition(":")
        try:
            if float(expires) > now:
                live[int(stream_id)] = owner or None
            else:
                stale.append(stream_id)
        except (TypeError, ValueError):
            stale.append(stream_id)
    if stale:
        try:
            redis_connection.hdel(SLOTS_KEY, *stale)
        except Exception:
            logger.warning("could not drop expired stream slots", exc_info=True)
    return live


def acquire(stream_id, owner=None, now=None):
    """
    Take a slot for this topic, or say why not.

    Returns None when the slot is held -- including when this topic already
    holds one, because a second viewer of a topic already running is exactly
    the case that should cost nothing. Otherwise a sentence for the person who
    tried.
    """
    now = now or time.time()
    with _Lock() as lock:
        if not lock.held:
            return "Could not reach the stream limit just now. Try again."

        taken = held(now)
        if stream_id in taken:
            _write(stream_id, taken[stream_id] or owner, now)
            return None

        if settings.STREAM_MAX_CONCURRENT > 0 and len(taken) >= settings.STREAM_MAX_CONCURRENT:
            return "All {} streaming slots are in use. Stop one, or wait for one to finish.".format(
                settings.STREAM_MAX_CONCURRENT
            )

        mine = [one for one in taken.values() if owner and one == owner]
        if owner and settings.STREAM_MAX_PER_USER > 0 and len(mine) >= settings.STREAM_MAX_PER_USER:
            return "You already have {} streams running, which is the limit per person.".format(
                settings.STREAM_MAX_PER_USER
            )

        _write(stream_id, owner, now)
        return None


def renew(stream_id, now=None):
    """Keep a slot while its stream is still being watched."""
    taken = held(now)
    _write(stream_id, taken.get(stream_id), now or time.time())


def _write(stream_id, owner, now):
    try:
        redis_connection.hset(
            SLOTS_KEY,
            str(stream_id),
            "{}:{}".format(now + settings.STREAM_SLOT_GRACE_SECONDS, owner or ""),
        )
    except Exception:
        logger.warning("could not record the slot for stream %s", stream_id, exc_info=True)


def release(stream_id):
    try:
        redis_connection.hdel(SLOTS_KEY, str(stream_id))
    except Exception:
        logger.warning("could not release the slot for stream %s", stream_id, exc_info=True)
