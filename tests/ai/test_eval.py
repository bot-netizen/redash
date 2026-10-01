import os
import tempfile
from unittest import mock

import yaml

from sqldesk import models
from sqldesk.ai.catalog.harvest import harvest_data_source
from sqldesk.ai.eval import (
    EvalFileError,
    last_score,
    load_questions,
    record_score,
    run_eval,
)
from sqldesk.models import db
from tests import BaseTestCase
from tests.ai.test_semantic import SCHEMA


def write(document):
    handle = tempfile.NamedTemporaryFile("w", suffix=".yml", delete=False)
    yaml.safe_dump(document, handle)
    handle.close()
    return handle.name


class TestReadingTheFile(BaseTestCase):
    """
    Somebody is running this against a file they just edited, so every
    complaint has to be a sentence they can act on rather than a traceback.
    """

    def test_a_missing_file(self):
        with self.assertRaises(EvalFileError) as caught:
            load_questions("/nonexistent/questions.yml")
        self.assertIn("Could not read", str(caught.exception))

    def test_something_that_is_not_yaml(self):
        path = tempfile.NamedTemporaryFile("w", suffix=".yml", delete=False)
        path.write("questions: [\n  - ask: unclosed")
        path.close()

        with self.assertRaises(EvalFileError) as caught:
            load_questions(path.name)
        self.assertIn("not valid YAML", str(caught.exception))

    def test_yaml_that_is_not_a_question_file(self):
        with self.assertRaises(EvalFileError) as caught:
            load_questions(write({"somethingelse": []}))
        self.assertIn("questions:", str(caught.exception))

    def test_an_empty_list(self):
        with self.assertRaises(EvalFileError) as caught:
            load_questions(write({"questions": []}))
        self.assertIn("empty", str(caught.exception))

    def test_a_question_with_nothing_asked(self):
        with self.assertRaises(EvalFileError) as caught:
            load_questions(write({"questions": [{"tables": ["orders"]}]}))
        self.assertIn("no `ask:`", str(caught.exception))

    def test_a_question_that_expects_nothing_is_refused(self):
        # It would pass whatever happened, which is worse than not being
        # there: the score goes up and means less.
        with self.assertRaises(EvalFileError) as caught:
            load_questions(write({"questions": [{"ask": "revenue by region"}]}))
        self.assertIn("expects nothing", str(caught.exception))

    def test_a_single_name_does_not_have_to_be_a_list(self):
        questions = load_questions(write({"questions": [{"ask": "revenue", "tables": "orders"}]}))
        self.assertEqual(["orders"], questions[0]["tables"])

    def test_names_are_compared_without_case(self):
        questions = load_questions(write({"questions": [{"ask": "revenue", "tables": ["Orders"]}]}))
        self.assertEqual(["orders"], questions[0]["tables"])


class EvalTestCase(BaseTestCase):
    def _harvested(self):
        source = self.factory.create_data_source(name="Warehouse")
        query = self.factory.create_query(
            query_text="select region, sum(amount) as gross_revenue from orders group by 1",
            data_source=source,
        )
        query.latest_query_data = self.factory.create_query_result(data_source=source)
        db.session.commit()
        with mock.patch.object(type(source), "get_schema", return_value=SCHEMA):
            harvest_data_source(source)
        return source

    def _run(self, *questions):
        return run_eval(self.factory.org, load_questions(write({"questions": list(questions)})))


class TestRunningIt(EvalTestCase):
    def test_a_table_the_retrieval_finds_passes(self):
        self._harvested()

        report = self._run({"ask": "orders by region", "tables": ["orders"]})

        self.assertTrue(report["results"][0]["passed"], report["results"][0])
        self.assertEqual(1.0, report["score"])

    def test_a_table_it_does_not_find_is_reported_by_name(self):
        self._harvested()

        report = self._run({"ask": "orders by region", "tables": ["invoices"]})

        self.assertFalse(report["results"][0]["passed"])
        self.assertEqual(["invoices"], report["results"][0]["missing"]["tables"])

    def test_and_what_it_handed_over_instead(self):
        # "orders was missing" and "we handed over order_archive_2019 instead"
        # are different problems, and the second is the one that produces a
        # wrong number nobody questions.
        self._harvested()

        report = self._run({"ask": "orders by region", "tables": ["invoices"]})

        self.assertIn("orders", report["results"][0]["found"]["tables"])

    def test_a_qualified_name_matches_a_bare_one(self):
        # The file is written by a person saying what they expect to be found,
        # not transcribing identifiers out of the catalog.
        source = self._harvested()
        table = models.CatalogTable.query.filter_by(data_source_id=source.id, name="orders").one()
        table.name = "public.orders"
        db.session.commit()

        report = self._run({"ask": "orders by region", "tables": ["orders"]})

        self.assertTrue(report["results"][0]["passed"], report["results"][0])

    def test_an_agreed_measure_counts(self):
        source = self._harvested()
        measure = models.CatalogMeasure.query.filter_by(data_source_id=source.id).first()
        self.assertIsNotNone(measure, "the harvest should have proposed one from the saved SQL")
        measure.status = models.MEASURE_APPROVED
        db.session.commit()

        report = self._run({"ask": "orders revenue", "measures": [measure.name]})

        self.assertTrue(report["results"][0]["passed"], report["results"][0])

    def test_a_measure_nobody_agreed_does_not(self):
        # Exactly the regression this is for: a measure denied by mistake
        # silently stops reaching every model, and nothing else would say so.
        source = self._harvested()
        measure = models.CatalogMeasure.query.filter_by(data_source_id=source.id).first()
        measure.status = models.MEASURE_DENIED
        db.session.commit()

        report = self._run({"ask": "orders revenue", "measures": [measure.name]})

        self.assertFalse(report["results"][0]["passed"])

    def test_a_saved_query_found_by_name(self):
        source = self._harvested()
        self.factory.create_query(name="Revenue by region", data_source=source, is_draft=False)
        db.session.commit()

        report = self._run({"ask": "revenue by region", "queries": ["Revenue by region"]})

        self.assertTrue(report["results"][0]["passed"], report["results"][0])

    def test_or_by_id(self):
        source = self._harvested()
        query = self.factory.create_query(name="Revenue by region", data_source=source, is_draft=False)
        db.session.commit()

        report = self._run({"ask": "revenue by region", "queries": [query.id]})

        self.assertTrue(report["results"][0]["passed"], report["results"][0])

    def test_naming_a_data_source_that_does_not_exist_fails_the_question(self):
        # Rather than quietly searching everything, which would pass and mean
        # nothing.
        self._harvested()

        report = self._run({"ask": "orders", "data_source": "Nowhere", "tables": ["orders"]})

        self.assertFalse(report["results"][0]["passed"])
        self.assertEqual(["Nowhere"], report["results"][0]["missing"]["data_source"])

    def test_naming_the_right_one_still_passes(self):
        self._harvested()

        report = self._run({"ask": "orders by region", "data_source": "Warehouse", "tables": ["orders"]})

        self.assertTrue(report["results"][0]["passed"], report["results"][0])

    def test_the_score_is_the_fraction_that_passed(self):
        self._harvested()

        report = self._run(
            {"ask": "orders by region", "tables": ["orders"]},
            {"ask": "orders by region", "tables": ["invoices"]},
        )

        self.assertEqual(2, report["questions"])
        self.assertEqual(1, report["passed"])
        self.assertEqual(0.5, report["score"])

    def test_it_gives_the_same_answer_twice(self):
        # Deterministic is the whole claim: it is a test, not a benchmark.
        self._harvested()
        question = {"ask": "orders by region", "tables": ["orders"], "measures": ["nope"]}

        self.assertEqual(self._run(question), self._run(question))


class TestRecordingTheScore(EvalTestCase):
    def test_the_last_score_is_readable_afterwards(self):
        self._harvested()
        report = self._run({"ask": "orders by region", "tables": ["orders"]})

        record_score(self.factory.org, report)

        kept = last_score(self.factory.org)
        self.assertEqual(1.0, kept["score"])
        self.assertEqual(1, kept["questions"])
        self.assertEqual([], kept["missed"])

    def test_it_keeps_which_questions_were_missed(self):
        # So the page can say which two, not only that the number went down.
        self._harvested()
        report = self._run({"ask": "a question about invoices", "tables": ["invoices"]})

        record_score(self.factory.org, report)

        self.assertEqual(["a question about invoices"], last_score(self.factory.org)["missed"])

    def test_with_nothing_recorded_there_is_no_score(self):
        self.assertIsNone(last_score(self.factory.org))

    def test_another_organisations_score_is_not_ours(self):
        self._harvested()
        record_score(self.factory.org, self._run({"ask": "orders by region", "tables": ["orders"]}))

        self.assertIsNone(last_score(self.factory.create_org()))

    def test_a_broken_redis_does_not_take_the_page_down(self):
        # It decorates a page. Failing to read it must never be the reason
        # somebody cannot see their catalog.
        with mock.patch("sqldesk.ai.eval.redis_connection.get", side_effect=RuntimeError("down")):
            self.assertIsNone(last_score(self.factory.org))


def tearDownModule():
    for name in os.listdir(tempfile.gettempdir()):
        if name.endswith(".yml") and name.startswith("tmp"):
            try:
                os.unlink(os.path.join(tempfile.gettempdir(), name))
            except OSError:
                pass
