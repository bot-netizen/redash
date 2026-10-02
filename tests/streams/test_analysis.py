"""
What a topic looks like before anybody commits to keeping it.

The three things somebody choosing topics needs, none of which can be guessed
from a name: what the messages contain, how fast they arrive, and what that
means for how much history a window will hold.

The parsing and the arithmetic are tested here with messages in hand; reading
them off a broker is `test_broker.py`, which needs one running.
"""

from unittest import TestCase, mock

from sqldesk.streams import analysis


def message(payload, when=0):
    import json

    return (json.dumps(payload).encode("utf-8"), (1, when))


class TestWhatIsInTheMessages(TestCase):
    def describe(self, messages, options=None):
        return analysis._describe(messages, "orders", options or {})

    def test_the_columns_and_their_types(self):
        found = self.describe([message({"id": 1, "region": "east", "paid": True, "total": 1.5})])

        self.assertEqual(
            [
                {"name": "id", "type": "integer"},
                {"name": "paid", "type": "boolean"},
                {"name": "region", "type": "string"},
                {"name": "total", "type": "number"},
            ],
            found["columns"],
        )

    def test_columns_from_across_the_sample(self):
        # A field only some messages carry is still a column, because a query
        # naming it is valid and a schema that hid it would be wrong.
        found = self.describe([message({"id": 1}), message({"id": 2, "note": "late"})])

        self.assertEqual(["id", "note"], [column["name"] for column in found["columns"]])

    def test_a_nested_value_is_json(self):
        found = self.describe([message({"id": 1, "items": [1, 2]})])

        self.assertEqual("json", dict((c["name"], c["type"]) for c in found["columns"])["items"])

    def test_what_cannot_be_parsed_is_counted_not_hidden(self):
        # The number somebody most needs before enabling a topic: a schema
        # inferred from a tenth of the messages is a trap.
        found = self.describe([message({"id": 1}), (b"not json at all", (1, 0))])

        self.assertEqual(1, found["malformed"])
        self.assertEqual(["id"], [column["name"] for column in found["columns"]])

    def test_a_message_that_is_not_an_object_counts_as_malformed(self):
        # One of them would otherwise collapse the schema to a single column.
        found = self.describe([message({"id": 1}), message([1, 2, 3])])

        self.assertEqual(1, found["malformed"])
        self.assertEqual(["id"], [column["name"] for column in found["columns"]])


class TestTheRate(TestCase):
    def test_it_comes_from_the_timestamps(self):
        # Ten messages over a second is nine intervals, so nine a second.
        messages = [message({"n": n}, when=n * 100) for n in range(11)]

        self.assertEqual(10.0, analysis._describe(messages, "orders", {})["events_per_second"])

    def test_one_message_has_no_rate(self):
        self.assertEqual(0, analysis._describe([message({"n": 1})], "orders", {})["events_per_second"])

    def test_nor_does_a_burst_inside_one_millisecond(self):
        # Dividing by zero to describe a burst would be worse than saying
        # nothing about it.
        messages = [message({"n": n}, when=5) for n in range(10)]

        self.assertEqual(0, analysis._describe(messages, "orders", {})["events_per_second"])


class TestWhatThatBuys(TestCase):
    def messages(self, rate, count=11):
        step = int(1000 / rate)
        return [message({"n": n}, when=n * step) for n in range(count)]

    def test_a_slow_topic_gets_a_long_window(self):
        with mock.patch("sqldesk.settings.STREAM_ROW_BUDGET", 100000):
            found = analysis._describe(self.messages(10), "orders", {})

        self.assertGreater(found["window_seconds"], 0)
        self.assertFalse(found["sampled"])

    def test_a_topic_over_the_ceiling_is_marked_as_sampled(self):
        # Said before anybody enables it, because a count from a sampled stream
        # is an estimate and finding that out afterwards is the bad way.
        found = analysis._describe(self.messages(100), "orders", {"events_per_second": 10})

        self.assertTrue(found["sampled"])
        self.assertGreaterEqual(found["sample_rate"], 2)

    def test_and_one_under_it_is_not(self):
        found = analysis._describe(self.messages(10), "orders", {"events_per_second": 1000})

        self.assertFalse(found["sampled"])
        self.assertEqual(1, found["sample_rate"])
