"""
The limit on how many topics may be consumed at once.

A stream's cost is continuous, so what has to be bounded is how many exist. The
rule that makes the number mean something is that **a slot is a topic, not a
viewer**: five people watching `orders` take one slot between them, which is
exactly the case this feature exists for.
"""

import time
from unittest import mock

from sqldesk import redis_connection
from sqldesk.streams import slots
from tests import BaseTestCase


class SlotTestCase(BaseTestCase):
    def setUp(self):
        super().setUp()
        redis_connection.delete(slots.SLOTS_KEY, slots.LOCK_KEY)


class TestTakingASlot(SlotTestCase):
    def test_the_first_one_is_free(self):
        with mock.patch("sqldesk.settings.STREAM_MAX_CONCURRENT", 2):
            self.assertIsNone(slots.acquire(1, owner="ada"))

        self.assertEqual({1: "ada"}, slots.held())

    def test_a_second_viewer_of_the_same_topic_costs_nothing(self):
        # The whole point of counting topics rather than tabs.
        with mock.patch("sqldesk.settings.STREAM_MAX_CONCURRENT", 1):
            slots.acquire(1, owner="ada")

            self.assertIsNone(slots.acquire(1, owner="grace"))

        self.assertEqual([1], list(slots.held()))

    def test_a_different_topic_past_the_limit_is_refused(self):
        with mock.patch("sqldesk.settings.STREAM_MAX_CONCURRENT", 1):
            slots.acquire(1, owner="ada")

            refusal = slots.acquire(2, owner="grace")

        self.assertIn("in use", refusal)
        self.assertNotIn(2, slots.held())

    def test_the_refusal_says_how_many_there_are(self):
        # So the answer to "no slot" is a number somebody can argue with their
        # administrator about, rather than a shrug.
        with mock.patch("sqldesk.settings.STREAM_MAX_CONCURRENT", 3):
            # The per-user limit off, so this is about the total one alone.
            with mock.patch("sqldesk.settings.STREAM_MAX_PER_USER", 0):
                for stream_id in (1, 2, 3):
                    slots.acquire(stream_id, owner="ada")

                refusal = slots.acquire(4, owner="grace")

        self.assertIn("3", refusal)

    def test_one_person_cannot_take_them_all(self):
        with mock.patch("sqldesk.settings.STREAM_MAX_CONCURRENT", 10):
            with mock.patch("sqldesk.settings.STREAM_MAX_PER_USER", 2):
                slots.acquire(1, owner="ada")
                slots.acquire(2, owner="ada")

                refusal = slots.acquire(3, owner="ada")
                self.assertIn("per person", refusal)

                # And somebody else is unaffected by that.
                self.assertIsNone(slots.acquire(4, owner="grace"))

    def test_no_limit_means_no_limit(self):
        with mock.patch("sqldesk.settings.STREAM_MAX_CONCURRENT", 0):
            with mock.patch("sqldesk.settings.STREAM_MAX_PER_USER", 0):
                for stream_id in range(20):
                    self.assertIsNone(slots.acquire(stream_id, owner="ada"))


class TestGivingOneBack(SlotTestCase):
    def test_releasing_frees_it(self):
        with mock.patch("sqldesk.settings.STREAM_MAX_CONCURRENT", 1):
            slots.acquire(1, owner="ada")
            slots.release(1)

            self.assertIsNone(slots.acquire(2, owner="grace"))

    def test_a_slot_nobody_renewed_expires(self):
        # Nothing depends on a worker getting the chance to release it: a
        # killed worker, a closed laptop and a dead network all end here.
        with mock.patch("sqldesk.settings.STREAM_SLOT_GRACE_SECONDS", 1):
            with mock.patch("sqldesk.settings.STREAM_MAX_CONCURRENT", 1):
                slots.acquire(1, owner="ada")

                self.assertEqual([1], list(slots.held(now=time.time())))
                self.assertEqual([], list(slots.held(now=time.time() + 5)))

    def test_renewing_keeps_it_and_keeps_the_owner(self):
        with mock.patch("sqldesk.settings.STREAM_SLOT_GRACE_SECONDS", 10):
            slots.acquire(1, owner="ada")
            slots.renew(1, now=time.time() + 5)

            self.assertEqual({1: "ada"}, slots.held(now=time.time() + 8))

    def test_an_expired_slot_does_not_count_against_the_limit(self):
        with mock.patch("sqldesk.settings.STREAM_SLOT_GRACE_SECONDS", 1):
            with mock.patch("sqldesk.settings.STREAM_MAX_CONCURRENT", 1):
                slots.acquire(1, owner="ada")
                time.sleep(1.1)

                self.assertIsNone(slots.acquire(2, owner="grace"))
