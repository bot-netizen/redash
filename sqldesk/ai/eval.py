"""
Does the catalog still answer the questions people actually ask?

The failure a semantic layer is supposed to prevent is quiet: a model that
cannot find `orders` writes something plausible against `order_archive_2019`
and returns a number. Nobody notices, because a number came back. The same
thing happens when a harvest drops a table, when somebody renames a column,
or when a measure is denied by mistake -- the catalog gets worse and every
answer still looks like an answer.

So: a file of questions, each with the tables, measures or saved queries a
good answer has to include, run through the same retrieval the MCP tools use.
No model, no API key, no scoring rubric -- just "was `orders` in what we
handed over, or not". Deterministic, which makes it a test rather than a
benchmark: it can run in CI, it can fail a deploy, and when it drops from
twelve out of twelve to ten there is a list of which two and why.

What it deliberately does not measure is whether the SQL a model then writes
is correct. That needs a model, costs money, and varies between runs. This
measures the one part we are responsible for.
"""

import datetime
import json
import logging

import yaml

from sqldesk import redis_connection
from sqldesk.ai.catalog.retrieve import context_for, find_saved_queries
from sqldesk.models import DataSource

logger = logging.getLogger(__name__)

#: Where the last run's score is kept, per organisation. Redis rather than a
#: table: it is a nightly job's output and the job runs again tomorrow, so
#: losing it to a restart costs a day of history nobody was keeping.
SCORE_KEY = "sqldesk:catalog-eval:{}"

#: How long a score stays worth showing. Longer than the nightly interval by
#: enough to survive a missed run, short enough that a page never shows a
#: month-old number as if it were current.
SCORE_TTL = 60 * 60 * 24 * 7


class EvalFileError(Exception):
    """The file is not a set of questions. Said plainly, with the line if we have it."""


def load_questions(path):
    """
    Read the questions file.

    Every error here is reported rather than raised past the caller: somebody
    is running a command against a file they just edited, and a traceback is a
    worse answer than a sentence about line 14.
    """
    try:
        with open(path) as handle:
            document = yaml.safe_load(handle)
    except OSError as error:
        raise EvalFileError("Could not read {}: {}".format(path, error))
    except yaml.YAMLError as error:
        raise EvalFileError("{} is not valid YAML: {}".format(path, error))

    if not isinstance(document, dict) or "questions" not in document:
        raise EvalFileError("{} needs a top-level `questions:` list.".format(path))
    questions = document["questions"]
    if not isinstance(questions, list) or not questions:
        raise EvalFileError("`questions:` in {} is empty.".format(path))

    cleaned = []
    for index, entry in enumerate(questions, start=1):
        if not isinstance(entry, dict) or not (entry.get("ask") or "").strip():
            raise EvalFileError("Question {} in {} has no `ask:`.".format(index, path))
        expects = {key: _names(entry.get(key)) for key in ("tables", "measures", "queries")}
        if not any(expects.values()):
            # A question with nothing expected passes whatever happens, which
            # is worse than not having it: the score goes up and means less.
            raise EvalFileError(
                "Question {} in {} expects nothing. Give it `tables:`, `measures:` or `queries:`.".format(index, path)
            )
        cleaned.append(
            {
                "ask": entry["ask"].strip(),
                "data_source": (entry.get("data_source") or "").strip() or None,
                **expects,
            }
        )
    return cleaned


def _names(value):
    if value is None:
        return []
    if isinstance(value, (str, int)):
        value = [value]
    return [str(item).strip().lower() for item in value if str(item).strip()]


def run_eval(org, questions):
    """
    Ask each question through the real retrieval and say what was missed.

    Matching is on lowercased names, and a table named `public.orders` counts
    as `orders`: the file is written by a person describing what they expect
    to be found, not transcribing a qualified identifier out of the catalog.
    """
    sources = {source.name.lower(): source for source in DataSource.query.filter(DataSource.org == org)}
    readable = [source.id for source in sources.values()]

    results = []
    for question in questions:
        source = sources.get((question["data_source"] or "").lower()) if question["data_source"] else None
        if question["data_source"] and source is None:
            results.append(
                {
                    "ask": question["ask"],
                    "passed": False,
                    "missing": {"data_source": [question["data_source"]]},
                    "found": {},
                }
            )
            continue

        context = context_for(
            org,
            question["ask"],
            data_source=source,
            data_source_ids=[source.id] if source else readable,
        )
        found = {
            "tables": {_bare(table["name"]) for table in context["tables"]},
            "measures": {measure["name"].lower() for measure in context["measures"]},
        }
        if question["queries"]:
            # Only asked for when the file expects one: it is a second search
            # and most questions are about tables.
            saved = find_saved_queries(org, question["ask"], readable if source is None else [source.id])
            found["queries"] = {str(query.id) for query in saved} | {(query.name or "").lower() for query in saved}
        else:
            found["queries"] = set()

        missing = {kind: sorted(set(question[kind]) - found[kind]) for kind in ("tables", "measures", "queries")}
        missing = {kind: names for kind, names in missing.items() if names}
        results.append(
            {
                "ask": question["ask"],
                "passed": not missing,
                "missing": missing,
                "found": {kind: sorted(names) for kind, names in found.items() if names},
            }
        )

    passed = sum(1 for result in results if result["passed"])
    return {
        "questions": len(results),
        "passed": passed,
        "score": round(passed / len(results), 3) if results else 0.0,
        "results": results,
    }


def _bare(name):
    """`public.orders` and `orders` are the same table to somebody writing the file."""
    return (name or "").lower().rsplit(".", 1)[-1]


def record_score(org, report):
    """Keep the headline numbers where the Catalog page can read them."""
    redis_connection.setex(
        SCORE_KEY.format(org.id),
        SCORE_TTL,
        json.dumps(
            {
                "questions": report["questions"],
                "passed": report["passed"],
                "score": report["score"],
                # The failures by name, so the page can say which ones rather
                # than only that the number went down.
                "missed": [result["ask"] for result in report["results"] if not result["passed"]][:20],
                "at": _now(),
            }
        ),
    )


def last_score(org):
    """The last recorded score, or None. Never raises: it decorates a page."""
    try:
        raw = redis_connection.get(SCORE_KEY.format(org.id))
        return json.loads(raw) if raw else None
    except Exception:
        logger.warning("could not read the last catalog eval score", exc_info=True)
        return None


def _now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()
