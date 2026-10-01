import logging
from functools import partial, wraps

from rq import get_current_job
from rq.decorators import job as rq_job

from sqldesk import rq_redis_connection, settings
from sqldesk.tasks.worker import Queue as SQLDeskQueue

default_operational_queues = ["periodic", "emails", "default"]
# `streams` is here so a default install works at all: a consumer enqueued onto
# a queue no worker takes from is a stream that never consumes and a chart that
# is always empty, with nothing in any log to say why. A busy install should
# give it a worker of its own -- a consumer holds one for minutes at a time, and
# behind the queries people are waiting for is the wrong place for that.
default_query_queues = ["scheduled_queries", "queries", "schemas", "streams"]
default_queues = default_operational_queues + default_query_queues


class StatsdRecordingJobDecorator(rq_job):  # noqa
    """
    RQ Job Decorator mixin that uses our Queue class to ensure metrics are accurately incremented in Statsd
    """

    queue_class = SQLDeskQueue

    def __call__(self, f):
        f = super().__call__(f)
        plain_delay = f.delay

        @wraps(f)
        def delay(*args, **kwargs):
            """
            RQ's own `delay`, plus `meta=`: whose job this is, stamped at
            enqueue time. `/api/jobs/<id>` answers only the job's own
            organization and user, and stamping after the fact races the
            worker, which saves its own copy of the meta when the job ends.
            """
            meta = kwargs.pop("meta", None)
            if not meta:
                return plain_delay(*args, **kwargs)

            queue = (
                self.queue_class(name=self.queue, connection=self.connection)
                if isinstance(self.queue, str)
                else self.queue
            )
            depends_on = kwargs.pop("depends_on", None) or self.depends_on
            job_id = kwargs.pop("job_id", None)
            at_front = kwargs.pop("at_front", False) or self.at_front
            return queue.enqueue_call(
                f,
                args=args,
                kwargs=kwargs,
                timeout=self.timeout,
                result_ttl=self.result_ttl,
                ttl=self.ttl,
                depends_on=depends_on,
                job_id=job_id,
                at_front=at_front,
                meta={**(self.meta or {}), **meta},
                description=self.description,
                failure_ttl=self.failure_ttl,
                retry=self.retry,
                on_failure=self.on_failure,
                on_success=self.on_success,
                on_stopped=self.on_stopped,
            )

        f.delay = delay
        return f


job = partial(
    StatsdRecordingJobDecorator, connection=rq_redis_connection, failure_ttl=settings.JOB_DEFAULT_FAILURE_TTL
)


class CurrentJobFilter(logging.Filter):
    def filter(self, record):
        current_job = get_current_job()

        record.job_id = current_job.id if current_job else ""
        record.job_func_name = current_job.func_name if current_job else ""

        return True


def get_job_logger(name):
    logger = logging.getLogger("rq.job." + name)

    handler = logging.StreamHandler()
    handler.formatter = logging.Formatter(settings.RQ_WORKER_JOB_LOG_FORMAT)
    handler.addFilter(CurrentJobFilter())

    logger.addHandler(handler)
    logger.propagate = False

    return logger
