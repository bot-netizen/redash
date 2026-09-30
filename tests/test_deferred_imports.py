import json
import subprocess
import sys
from unittest import TestCase

from sqldesk.query_runner import deferred, installed, query_runners


class TestTheDeferredHelper(TestCase):
    """
    Query runners are imported at startup, because that is how each registers
    its type. Their SDKs are not: 155 MB of connectors in every gunicorn
    worker and every worker pod, for data sources most installs do not have.
    """

    def test_it_does_not_import_until_something_is_asked_of_it(self):
        # `colorsys` is in the standard library, tiny, and nothing here
        # imports it -- which is what makes it a usable canary.
        sys.modules.pop("colorsys", None)
        module = deferred("colorsys")

        self.assertNotIn("colorsys", sys.modules)

        module.rgb_to_hls  # noqa: B018 -- asking is the point

        self.assertIn("colorsys", sys.modules)

    def test_attribute_access_gives_the_real_thing(self):
        self.assertEqual(0.5, deferred("statistics").median([0, 1]))

    def test_a_name_from_a_module_can_be_called(self):
        self.assertEqual(3, deferred("statistics", "median")([1, 3, 5]))

    def test_an_exception_class_reached_through_it_still_catches(self):
        # `except proxy.SomeError:` is how two runners use this, and it works
        # because the attribute is resolved when the clause is evaluated. If
        # the proxy itself were named there it would not.
        errors = deferred("json")

        try:
            raise errors.JSONDecodeError("no", "", 0)
        except errors.JSONDecodeError:
            caught = True
        self.assertTrue(caught)

    def test_dunders_do_not_trigger_an_import(self):
        # A debugger, `copy` or `pickle` probes `__deepcopy__` and friends on
        # anything it is handed. Answering those by importing would undo the
        # whole point at the least convenient moment.
        sys.modules.pop("colorsys", None)
        module = deferred("colorsys")

        with self.assertRaises(AttributeError):
            module.__deepcopy__

        self.assertNotIn("colorsys", sys.modules)

    def test_it_says_what_it_is_without_importing(self):
        sys.modules.pop("colorsys", None)
        module = deferred("colorsys")

        self.assertIn("colorsys", repr(module))
        self.assertIn("not yet", repr(module))
        self.assertNotIn("colorsys", sys.modules)


class TestAskingWhetherAnSdkIsThere(TestCase):
    def test_a_module_that_exists(self):
        self.assertTrue(installed("json"))

    def test_and_one_that_does_not(self):
        self.assertFalse(installed("no_such_module_anywhere"))

    def test_all_of_them_have_to_be_there(self):
        self.assertFalse(installed("json", "no_such_module_anywhere"))

    def test_asking_does_not_import(self):
        sys.modules.pop("colorsys", None)

        self.assertTrue(installed("colorsys"))
        self.assertNotIn("colorsys", sys.modules)

    def test_a_missing_parent_is_not_an_error(self):
        # `find_spec("a.b")` raises when `a` is absent, rather than returning
        # None. The answer is still no.
        self.assertFalse(installed("no_such_parent.child"))


class TestWhatStartupStillCarries(TestCase):
    """
    The regression this guards: somebody adds `import boto3` to a runner, and
    every process grows by sixteen megabytes again with nothing to show for
    it.
    """

    #: SDKs no process should be carrying unless it is running a query
    #: against that kind of data source.
    SHOULD_NOT_BE_LOADED = [
        "boto3",
        "botocore",
        "cassandra",
        "duckdb",
        "influxdb",
        "influxdb_client",
        "numpy",
        "oracledb",
        "pandas",
        "snowflake.connector",
    ]

    def test_importing_sqldesk_does_not_drag_in_the_connectors(self):
        # In a *fresh* interpreter. Asking `sys.modules` from inside the suite
        # would answer about the suite, which imports pandas and the rest for
        # the runner tests -- the first version of this test did exactly that
        # and failed for the wrong reason.
        script = (
            "import sys, json\n"
            "import sqldesk\n"
            "print(json.dumps([n for n in {!r} if n in sys.modules]))\n".format(self.SHOULD_NOT_BE_LOADED)
        )
        result = subprocess.run(
            [sys.executable, "-c", script],
            capture_output=True,
            text=True,
            timeout=300,
        )
        self.assertEqual(0, result.returncode, result.stderr[-2000:])
        still_here = json.loads(result.stdout.strip().splitlines()[-1])

        self.assertEqual(
            [],
            still_here,
            "imported at startup, which costs every worker and every web worker: {}".format(still_here),
        )

    def test_and_every_runner_still_registered(self):
        # Deferring an SDK must not stop a runner announcing its type; that
        # would quietly remove a data source from the list.
        self.assertGreater(len(query_runners), 50)

    def test_and_every_runner_can_still_say_whether_it_works(self):
        # `enabled()` is asked for the data source form. It must answer
        # without raising, and without importing anything.
        for name, runner in query_runners.items():
            self.assertIn(runner.enabled(), (True, False), name)
