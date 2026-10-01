import datetime
from unittest import mock

from sqlalchemy import event

from sqldesk.ai.catalog.freshness import (
    INTERVALS_BEFORE_STALE,
    MANUAL_WINDOW_HOURS,
    harvested_at,
    in_days,
    stale_after,
    stale_sources,
)
from sqldesk.models import CatalogTable, db
from tests import BaseTestCase


def hours_ago(hours):
    return datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=hours)


class FreshnessTestCase(BaseTestCase):
    def harvested(self, when, name="orders", source=None):
        """One harvested table. `when` may be None: the column is nullable."""
        source = source or self.factory.data_source
        table = CatalogTable(
            org=self.factory.org,
            data_source=source,
            name=name,
            card="{}(id int)".format(name),
            harvested_at=when,
        )
        db.session.add(table)
        db.session.commit()
        return source


class TestHowOldIsTooOld(BaseTestCase):
    def test_three_harvest_intervals(self):
        # One missed run is a restart and two is a bad night. Three means the
        # schedule is not running.
        with mock.patch("sqldesk.settings.CATALOG_HARVEST_SCHEDULE", 24):
            self.assertEqual(datetime.timedelta(hours=24 * INTERVALS_BEFORE_STALE), stale_after())

    def test_a_shorter_interval_shortens_it(self):
        with mock.patch("sqldesk.settings.CATALOG_HARVEST_SCHEDULE", 6):
            self.assertEqual(datetime.timedelta(hours=18), stale_after())

    def test_with_the_schedule_off_a_fortnight_stands_in(self):
        # 0 means somebody harvests it themselves, so there is no interval to
        # multiply -- but a catalog nobody has touched in a fortnight is still
        # worth a word.
        with mock.patch("sqldesk.settings.CATALOG_HARVEST_SCHEDULE", 0):
            self.assertEqual(datetime.timedelta(hours=MANUAL_WINDOW_HOURS), stale_after())


class TestWhichSourcesAreStale(FreshnessTestCase):
    def test_a_recently_harvested_source_is_not(self):
        with mock.patch("sqldesk.settings.CATALOG_HARVEST_SCHEDULE", 24):
            source = self.harvested(hours_ago(2))

            self.assertEqual({}, stale_sources(self.factory.org, [source.id]))

    def test_one_past_three_intervals_is(self):
        with mock.patch("sqldesk.settings.CATALOG_HARVEST_SCHEDULE", 24):
            source = self.harvested(hours_ago(24 * 3 + 1))

            self.assertIn(source.id, stale_sources(self.factory.org, [source.id]))

    def test_exactly_at_the_limit_is_not_yet(self):
        # Exactly at it, through the `now` seam -- an hour short of the limit
        # cannot tell `>` from `>=`, which is how the first version of this
        # test survived the comparison being loosened.
        with mock.patch("sqldesk.settings.CATALOG_HARVEST_SCHEDULE", 24):
            harvested = datetime.datetime.now(datetime.timezone.utc)
            source = self.harvested(harvested)

            at_the_limit = harvested + stale_after()

            self.assertEqual({}, stale_sources(self.factory.org, [source.id], now=at_the_limit))
            self.assertIn(
                source.id,
                stale_sources(self.factory.org, [source.id], now=at_the_limit + datetime.timedelta(seconds=1)),
            )

    def test_the_newest_table_decides_it(self):
        # A harvest writes every table it found. One row left behind from an
        # old run must not make a current catalog look stale.
        with mock.patch("sqldesk.settings.CATALOG_HARVEST_SCHEDULE", 24):
            source = self.harvested(hours_ago(500), name="old_leftover")
            self.harvested(hours_ago(1), name="orders", source=source)

            self.assertEqual({}, stale_sources(self.factory.org, [source.id]))

    def test_a_source_with_nothing_in_the_catalog_is_not_stale(self):
        # Nothing to be out of date. Saying "stale" would send somebody
        # looking for a problem they do not have.
        source = self.factory.create_data_source(name="Fresh")

        self.assertEqual({}, stale_sources(self.factory.org, [source.id]))

    def test_nor_is_one_whose_rows_have_no_harvest_time(self):
        # `harvested_at` is nullable and always has been, so rows written
        # before it was set still exist. They are not evidence of a stale
        # catalog; they are evidence of an old SQLDesk.
        source = self.harvested(None)

        self.assertEqual({}, stale_sources(self.factory.org, [source.id]))

    def test_it_reports_how_old(self):
        with mock.patch("sqldesk.settings.CATALOG_HARVEST_SCHEDULE", 24):
            source = self.harvested(hours_ago(24 * 10))

            age = stale_sources(self.factory.org, [source.id])[source.id]

            self.assertEqual(10, age.days)

    def test_another_organisations_source_is_not_included(self):
        with mock.patch("sqldesk.settings.CATALOG_HARVEST_SCHEDULE", 24):
            other = self.factory.create_org()
            theirs = self.factory.create_data_source(org=other, name="Theirs")
            db.session.add(
                CatalogTable(
                    org=other, data_source=theirs, name="orders", card="orders(id int)", harvested_at=hours_ago(500)
                )
            )
            db.session.commit()

            self.assertEqual({}, stale_sources(self.factory.org))

    def test_asking_about_no_sources_asks_the_database_nothing(self):
        # Not for correctness -- SQLAlchemy turns `IN ()` into something that
        # matches nothing -- but the round trip is pointless and it warns
        # while making it. `find_context` asks on every call, and a user in no
        # groups has no readable sources. Counted, because asserting `{}`
        # cannot tell "skipped the query" from "ran it and found nothing".
        statements = []

        def record(conn, cursor, statement, *rest):
            statements.append(statement)

        event.listen(db.engine, "before_cursor_execute", record)
        try:
            self.assertEqual({}, harvested_at(self.factory.org, []))
        finally:
            event.remove(db.engine, "before_cursor_execute", record)

        self.assertEqual([], [sql for sql in statements if "catalog_tables" in sql])

    def test_a_harvest_time_comes_back_with_a_time_zone(self):
        # Which is why nothing here normalises it before subtracting. The
        # column is `DateTime(timezone=True)`, so the driver always hands back
        # an aware value -- an earlier version of this module carried a branch
        # for the naive case that no test could reach, and unreachable
        # defensive code is code nobody has run. Storing a naive value here
        # proves the point: it comes back aware.
        self.harvested(datetime.datetime(2020, 1, 1))

        stored = harvested_at(self.factory.org)[self.factory.data_source.id]

        self.assertIsNotNone(stored.tzinfo)


class TestSayingHowOld(BaseTestCase):
    def test_days(self):
        self.assertEqual("4 days", in_days(datetime.timedelta(days=4, hours=3)))

    def test_one_day_is_singular(self):
        self.assertEqual("1 day", in_days(datetime.timedelta(days=1)))

    def test_anything_under_a_day_still_says_a_day(self):
        # It is only reached past the staleness limit, which is days; "0 days"
        # would read as a bug.
        self.assertEqual("1 day", in_days(datetime.timedelta(hours=5)))
