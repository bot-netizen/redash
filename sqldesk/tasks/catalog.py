"""
Keeping the catalog current.

The context tools answer from the catalog rather than from a live schema
read, which means an install where nothing ever fills it has tools that
answer with nothing -- and until this existed, filling it was a command
somebody had to remember to run.

It is cheap enough to schedule. `get_schema()` reads the same Redis-cached
copy the schema browser uses and `refresh_schemas` is already keeping that
warm, so on an ordinary run this touches no warehouse at all: it parses SQL
already stored in `queries.query_text` and writes a few hundred rows.
"""

import logging
import time

from rq.job import JobStatus

from sqldesk import models, rq_redis_connection, settings
from sqldesk.ai.catalog.harvest import harvest_data_source
from sqldesk.tasks.worker import Job
from sqldesk.worker import job

logger = logging.getLogger(__name__)


@job("schemas", timeout=settings.CATALOG_HARVEST_TIMEOUT)
def harvest_catalog(data_source_id):
    """
    One data source, on the `schemas` queue.

    The same queue as schema refreshes on purpose: this is the same kind of
    work against the same sources, and it should queue behind them rather
    than compete with the queries people are waiting for.
    """
    source = models.DataSource.query.get(data_source_id)
    if source is None:
        logger.info("task=harvest_catalog state=skip ds_id=%s reason=gone", data_source_id)
        return

    started = time.time()
    try:
        result = harvest_data_source(source)
    except Exception:
        # One source's catalog failing is not worth losing the others, and
        # it must never be worth losing a worker.
        logger.exception("task=harvest_catalog state=error ds_id=%s", data_source_id)
        return

    logger.info(
        "task=harvest_catalog state=finish ds_id=%s tables=%s queries_mined=%s runtime=%.2f",
        data_source_id,
        result["tables"],
        result["queries_mined"],
        time.time() - started,
    )


#: What a harvest that has not finished yet is called where somebody reads it.
#: Keyed by the plain string, because that is what a fetched job's status is.
WAITING = {JobStatus.QUEUED.value: "queued", JobStatus.DEFERRED.value: "queued", JobStatus.STARTED.value: "running"}


def harvest_job_id(data_source_id):
    """
    One id per data source, so a harvest that is already waiting or running
    is found rather than queued a second time behind itself -- by a button
    clicked twice, or by the schedule arriving while an admin's is running.
    """
    return "catalog-harvest-{}".format(data_source_id)


def harvest_states(data_source_ids):
    """`queued` or `running` for each source with a harvest in flight."""
    ids = list(data_source_ids)
    jobs = Job.fetch_many([harvest_job_id(i) for i in ids], connection=rq_redis_connection)
    states = {}
    for source_id, found in zip(ids, jobs):
        status = found.get_status() if found else None
        state = WAITING.get(getattr(status, "value", status))
        if state:
            states[source_id] = state
    return states


def enqueue_harvest(source):
    """
    Queue one source's harvest, unless it cannot or need not run. Returns why
    not, or None when it was queued.
    """
    if source.paused:
        return "paused"
    if source.org.is_disabled:
        return "organization disabled"
    if harvest_states([source.id]):
        return "already queued"
    harvest_catalog.delay(source.id, job_id=harvest_job_id(source.id))
    return None


def harvest_catalogs():
    """Every data source worth harvesting, one job each."""
    if not settings.FEATURE_AI:
        return

    for source in models.DataSource.query:
        reason = enqueue_harvest(source)
        if reason:
            logger.info("task=harvest_catalog state=skip ds_id=%s reason=%s", source.id, reason.replace(" ", "_"))


@job("schemas", timeout=600)
def eval_catalog():
    """
    Score the catalog against the questions somebody wrote down.

    Daily, on its own interval -- deliberately not chained to the harvest.
    Chaining would mean waiting on a job per data source and deciding what to
    do when one of them fails, and the thing being measured moves slowly: if a
    run happens to land before the day's harvest it scores yesterday's
    catalog, which delays the signal by a day and never makes it wrong.

    The score lands in Redis for the Catalog page. Nothing is emailed and
    nothing fails: a nightly job that pages somebody because retrieval got
    worse by one question would be turned off within a week. The page is where
    it belongs, and CI is where it is allowed to be loud.
    """
    if not settings.FEATURE_AI or not settings.CATALOG_EVAL_FILE:
        return

    # Imported here: `sqldesk.ai.eval` reaches retrieval, which reaches the
    # models, and this module is imported by the scheduler at startup.
    from sqldesk.ai.eval import EvalFileError, load_questions, record_score, run_eval

    try:
        questions = load_questions(settings.CATALOG_EVAL_FILE)
    except EvalFileError as error:
        # Said once per run and no more. The file is somebody's, and the
        # worker is not the place to argue about it.
        logger.warning("task=eval_catalog state=error reason=%s", error)
        return

    for org in models.Organization.query:
        try:
            report = run_eval(org, questions)
        except Exception:
            logger.exception("task=eval_catalog state=error org_id=%s", org.id)
            continue
        record_score(org, report)
        logger.info(
            "task=eval_catalog state=finish org_id=%s passed=%s of=%s",
            org.id,
            report["passed"],
            report["questions"],
        )
