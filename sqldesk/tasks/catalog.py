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
