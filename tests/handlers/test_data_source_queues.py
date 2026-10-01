"""
Giving a data source a queue of its own, from the page.

Until now the only way was an UPDATE against the `data_sources` table, which
the Administration page actually told people to run. It is the single most
useful thing an administrator can do to stop a slow warehouse starving
everything else, and it should not require psql.
"""

from tests import BaseTestCase


class QueueTestCase(BaseTestCase):
    def source(self, **fields):
        return self.factory.create_data_source(name="Slow warehouse", type="pg", **fields)

    def save(self, source, user=None, **body):
        payload = {"name": source.name, "type": source.type, "options": {"dbname": "test"}}
        payload.update(body)
        return self.make_request(
            "post",
            "/api/data_sources/{}".format(source.id),
            data=payload,
            user=user or self.factory.create_admin(),
        )


class TestSettingAQueue(QueueTestCase):
    def test_an_administrator_may_set_one(self):
        source = self.source()

        response = self.save(source, queue_name="slow_warehouse")

        self.assertEqual(200, response.status_code, response.json)
        self.assertEqual("slow_warehouse", response.json["queue_name"])

    def test_and_a_separate_one_for_scheduled_refreshes(self):
        # Keeping them apart is what stops a refresh storm delaying somebody
        # waiting at a dashboard.
        source = self.source()

        response = self.save(source, scheduled_queue_name="slow_warehouse_scheduled")

        self.assertEqual("slow_warehouse_scheduled", response.json["scheduled_queue_name"])

    def test_somebody_who_is_not_an_administrator_may_not(self):
        source = self.source()

        response = self.save(source, user=self.factory.user, queue_name="mine")

        self.assertEqual(403, response.status_code)

    def test_leaving_it_out_leaves_it_alone(self):
        # The form is saved for all sorts of reasons and none of them should
        # silently move a data source's queries to another queue.
        source = self.source(queue_name="slow_warehouse")

        response = self.save(source)

        self.assertEqual("slow_warehouse", response.json["queue_name"])

    def test_emptying_it_puts_it_back_on_the_default(self):
        # A queue name somebody has emptied is one they have withdrawn.
        source = self.source(queue_name="slow_warehouse")

        response = self.save(source, queue_name="")

        self.assertEqual("queries", response.json["queue_name"])

    def test_and_the_scheduled_default_is_its_own(self):
        source = self.source(scheduled_queue_name="slow_scheduled")

        response = self.save(source, scheduled_queue_name="  ")

        self.assertEqual("scheduled_queries", response.json["scheduled_queue_name"])

    def test_a_name_with_spaces_is_refused(self):
        # It builds Redis keys and is read by a worker from an environment
        # variable, so it has to survive both.
        source = self.source()

        response = self.save(source, queue_name="slow warehouse")

        self.assertEqual(400, response.status_code)
        self.assertIn("letters, digits", response.json["message"])

    def test_so_is_one_with_a_comma(self):
        # QUEUES is a comma-separated list; a comma in a name would split it.
        source = self.source()

        self.assertEqual(400, self.save(source, queue_name="a,b").status_code)

    def test_and_an_absurdly_long_one(self):
        source = self.source()

        response = self.save(source, queue_name="q" * 200)

        self.assertEqual(400, response.status_code)
        self.assertIn("at most", response.json["message"])

    def test_dashes_and_underscores_are_fine(self):
        source = self.source()

        self.assertEqual(200, self.save(source, queue_name="slow-warehouse_2").status_code)

    def test_a_refused_name_is_not_saved(self):
        from sqldesk import models

        source = self.source(queue_name="original")

        self.save(source, queue_name="not a queue")

        models.db.session.expire_all()
        self.assertEqual("original", models.DataSource.query.get(source.id).queue_name)


class TestWhatTheApiShows(QueueTestCase):
    def test_an_administrator_sees_the_queues(self):
        source = self.source(queue_name="slow_warehouse")

        response = self.make_request("get", "/api/data_sources/{}".format(source.id), user=self.factory.create_admin())

        self.assertEqual("slow_warehouse", response.json["queue_name"])

    def test_somebody_else_does_not(self):
        # It says where somebody's queries run, which is operational detail a
        # reader has no use for.
        source = self.source(queue_name="slow_warehouse", group=self.factory.default_group)

        response = self.make_request("get", "/api/data_sources/{}".format(source.id), user=self.factory.user)

        self.assertNotIn("queue_name", response.json)
