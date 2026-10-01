"""
Whether what the catalog says is still true.

`harvested_at` has been recorded since the catalog existed; nothing ever read
it. That is the dangerous half of a stale catalog: the tables, the columns and
the cards are all still there, perfectly formatted, describing a warehouse
from three weeks ago. A model handed them writes confident SQL against a
column that was renamed, and the error it gets back -- if it gets one -- is
about syntax rather than about the catalog being old.

The policy is deliberately crude: a source is stale once its newest harvest is
older than three times the harvest interval. Three, because one missed run is
a restart and two is a bad night, while three means the schedule is not
running. Crude is the point -- the alternative is a per-source setting nobody
sets, and the question being answered is only ever "should somebody look".

Where a harvest has never happened, the source is not stale. There is nothing
to be out of date, and saying "stale" about an empty catalog would send
somebody looking for a problem they do not have; the Catalog page already
says "never harvested" for that.
"""

import datetime

from sqldesk import settings
from sqldesk.models import CatalogTable, db

#: Missed runs before anyone is told. See the module docstring.
INTERVALS_BEFORE_STALE = 3

#: The fallback window when the schedule is off (`CATALOG_HARVEST_SCHEDULE=0`,
#: which means somebody harvests it themselves). A catalog nobody has touched
#: in a fortnight is worth a word either way.
MANUAL_WINDOW_HOURS = 24 * 14


def stale_after():
    """How old a harvest may be before it is called stale."""
    hours = settings.CATALOG_HARVEST_SCHEDULE
    if hours and hours > 0:
        return datetime.timedelta(hours=hours * INTERVALS_BEFORE_STALE)
    return datetime.timedelta(hours=MANUAL_WINDOW_HOURS)


def harvested_at(org, data_source_ids=None):
    """The newest harvest per data source, as a dict. One query."""
    rows = db.session.query(
        CatalogTable.data_source_id,
        db.func.max(CatalogTable.harvested_at),
    ).filter(CatalogTable.org == org)
    if data_source_ids is not None:
        ids = list(data_source_ids)
        if not ids:
            # Not for correctness -- SQLAlchemy turns `IN ()` into something
            # that matches nothing -- but to not make the round trip, and not
            # warn while doing it. `find_context` asks this on every call, and
            # a user in no groups has no readable sources.
            return {}
        rows = rows.filter(CatalogTable.data_source_id.in_(ids))
    return dict(rows.group_by(CatalogTable.data_source_id).all())


def stale_sources(org, data_source_ids=None, now=None):
    """
    The data source ids whose catalog is too old, and how old.

    `now` is a seam for the tests rather than a feature: everything else in
    here would otherwise have to wait three days to be checked.
    """
    now = now or datetime.datetime.now(datetime.timezone.utc)
    limit = stale_after()

    stale = {}
    for source_id, last in harvested_at(org, data_source_ids).items():
        if last is None:
            # Never harvested: nothing to be out of date. See the docstring.
            continue
        age = now - last
        if age > limit:
            stale[source_id] = age
    return stale


def in_days(age):
    """An age as a plain phrase. Days, because nobody acts on hours here."""
    days = max(1, int(age.total_seconds() // 86400))
    return "{} day{}".format(days, "" if days == 1 else "s")
