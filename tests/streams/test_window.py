"""
The row budget, the window that follows from it, and the sampling.

Pure arithmetic over numbers and bytes, which is why it is all checkable --
and worth checking, because every one of these decides either how much disk a
topic takes or whether a count on a chart means anything.
"""

from unittest import TestCase

from sqldesk.streams import window


class TestHowMuchToKeep(TestCase):
    def test_a_quiet_topic_gets_the_whole_half_hour(self):
        # 10 events/sec against 5M rows would be two weeks; the cap is what
        # stops "now" from meaning a fortnight.
        self.assertEqual(window.MAX_WINDOW, window.window_for(5_000_000, 10))

    def test_a_busy_one_settles_at_five_minutes(self):
        # 50,000/sec against 5M rows is 100 seconds, which is below the floor.
        # The honest answer to a topic that fast is to sample, not to shrink
        # the window until the chart has nine points on it.
        self.assertEqual(window.MIN_WINDOW, window.window_for(5_000_000, 50_000))

    def test_in_between_it_is_the_budget_divided_by_the_rate(self):
        self.assertEqual(500, window.window_for(5_000_000, 10_000))

    def test_a_topic_nothing_has_arrived_on_gets_the_full_window(self):
        # A new stream should not start out pretending to be busy, and an
        # empty one costs nothing to keep.
        self.assertEqual(window.MAX_WINDOW, window.window_for(5_000_000, 0))

    def test_and_so_does_one_with_no_budget_set(self):
        self.assertEqual(window.MAX_WINDOW, window.window_for(0, 10_000))

    def test_the_window_is_whole_seconds(self):
        self.assertIsInstance(window.window_for(5_000_000, 7_777), int)


class TestWhatTheChartSays(TestCase):
    def test_the_window_and_the_count(self):
        # Stated because the window moves: a reader comparing two charts needs
        # to know one covers six minutes and the other thirty.
        self.assertEqual("last 6 minutes · 4.9M events", window.describe(360, 4_900_000))

    def test_one_minute_is_singular(self):
        self.assertEqual("last 1 minute · 12 events", window.describe(60, 12))

    def test_thousands_are_abbreviated(self):
        self.assertEqual("last 5 minutes · 4.8k events", window.describe(300, 4_800))

    def test_and_small_numbers_are_not(self):
        self.assertEqual("last 5 minutes · 42 events", window.describe(300, 42))

    def test_a_window_under_a_minute_still_says_one(self):
        # It is only reached by a configuration below the floor; "last 0
        # minutes" would read as a bug.
        self.assertEqual("last 1 minute · 1 events", window.describe(20, 1))


class TestWhenToSample(TestCase):
    def test_under_the_ceiling_everything_is_kept(self):
        self.assertEqual(1, window.sample_rate_for(3_000, 5_000))

    def test_exactly_at_it_too(self):
        self.assertEqual(1, window.sample_rate_for(5_000, 5_000))

    def test_ten_times_over_is_one_in_ten(self):
        self.assertEqual(10, window.sample_rate_for(50_000, 5_000))

    def test_just_over_rounds_up_rather_than_down(self):
        # Rounding down would give 1, which is "keep everything" -- the exact
        # case the ceiling exists for.
        self.assertEqual(2, window.sample_rate_for(5_001, 5_000))

    def test_with_no_ceiling_nothing_is_sampled(self):
        self.assertEqual(1, window.sample_rate_for(50_000, 0))

    def test_a_silent_topic_is_one_in_one_rather_than_one_in_zero(self):
        # This is what the floor is for, and the only case that needs it: the
        # arithmetic already gives at least 1 for any rate above zero. A rate
        # of 0 would reach `keeps` as a modulo by zero.
        self.assertEqual(1, window.sample_rate_for(0, 5_000))
        self.assertTrue(window.keeps(b"k", window.sample_rate_for(0, 5_000)))
        self.assertTrue(window.keeps(None, window.sample_rate_for(0, 5_000), position=7))


class TestWhichEventsAreKept(TestCase):
    def test_at_one_in_one_everything_is(self):
        self.assertTrue(window.keeps(b"anything", 1))

    def test_the_same_key_always_gets_the_same_answer(self):
        # The point of hashing rather than choosing at random: the same keys
        # stay in across flushes, so a per-key count can be scaled back up.
        # Random sampling would give a different set of users every second.
        first = window.keeps(b"user-42", 20)
        for _ in range(50):
            self.assertEqual(first, window.keeps(b"user-42", 20))

    def test_roughly_one_in_twenty_of_many_keys(self):
        kept = sum(1 for n in range(20_000) if window.keeps("user-{}".format(n).encode(), 20))

        # Uniformity, not exactness: a hash is not a quota.
        self.assertGreater(kept, 800)
        self.assertLess(kept, 1_200)

    def test_a_string_key_is_treated_as_its_bytes(self):
        # A caller handing us a str is a caller who decoded something; the
        # answer still has to match the bytes it came from.
        self.assertEqual(window.keeps(b"user-42", 20), window.keeps("user-42", 20))

    def test_a_topic_with_no_keys_is_sampled_by_position(self):
        # Hashing the empty key puts every such message in one bucket, so a
        # keyless topic -- a perfectly ordinary topic -- would be entirely
        # kept or entirely dropped. It was entirely dropped, which looks just
        # like a broker problem and is miserable to diagnose.
        kept = [position for position in range(100) if window.keeps(None, 20, position=position)]

        self.assertEqual(5, len(kept))
        self.assertEqual([0, 20, 40, 60, 80], kept)

    def test_an_empty_key_is_the_same_as_no_key(self):
        # Kafka distinguishes them; sampling has no reason to.
        self.assertEqual(window.keeps(None, 20, position=3), window.keeps(b"", 20, position=3))

    def test_a_keyed_message_ignores_its_position(self):
        # So the same keys stay in however the flushes fall.
        self.assertEqual(window.keeps(b"user-42", 20, position=0), window.keeps(b"user-42", 20, position=7))

    def test_nothing_is_decoded_to_decide(self):
        # The key is bytes off the wire and may not be valid UTF-8, let alone
        # JSON. Deciding must never be the thing that raises.
        self.assertIn(window.keeps(b"\xff\xfe\x00not text", 20), (True, False))


class TestWhatASampledCountMeans(TestCase):
    def test_scaling_back_up(self):
        self.assertEqual(2_000, window.scale_up(100, 20))

    def test_an_unsampled_count_is_itself(self):
        self.assertEqual(100, window.scale_up(100, 1))

    def test_and_a_nonsense_rate_does_not_divide_it_away(self):
        self.assertEqual(100, window.scale_up(100, 0))
