import logging
import os
import sys

import redis
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_mail import Mail
from flask_migrate import Migrate
from statsd import StatsClient

from sqldesk import settings
from sqldesk.app import create_app  # noqa
from sqldesk.destinations import import_destinations
from sqldesk.query_runner import import_query_runners

__version__ = "0.6.0-rc.4"


if os.environ.get("REMOTE_DEBUG"):
    # debugpy is a development dependency, so the released image does not
    # carry a debug server -- say so, rather than failing on the import.
    try:
        import debugpy
    except ImportError:
        sys.stderr.write("REMOTE_DEBUG is set, but debugpy is not installed. This image does not include it.\n")
    else:
        debugpy.listen(("0.0.0.0", 5678))
        debugpy.wait_for_client()


def setup_logging():
    handler = logging.StreamHandler(sys.stdout if settings.LOG_STDOUT else sys.stderr)
    formatter = logging.Formatter(settings.LOG_FORMAT)
    handler.setFormatter(formatter)
    logging.getLogger().addHandler(handler)
    logging.getLogger().setLevel(settings.LOG_LEVEL)

    # Make noisy libraries less noisy
    if settings.LOG_LEVEL != "DEBUG":
        for name in [
            "passlib",
            "requests.packages.urllib3",
            "snowflake.connector",
            "apiclient",
        ]:
            logging.getLogger(name).setLevel("ERROR")


setup_logging()

redis_connection = redis.from_url(settings.REDIS_URL)
rq_redis_connection = redis.from_url(settings.RQ_REDIS_URL)
mail = Mail()
migrate = Migrate(compare_type=True)
statsd_client = StatsClient(host=settings.STATSD_HOST, port=settings.STATSD_PORT, prefix=settings.STATSD_PREFIX)
limiter = Limiter(key_func=get_remote_address, storage_uri=settings.LIMITER_STORAGE)

import_query_runners(settings.QUERY_RUNNERS)
import_destinations(settings.DESTINATIONS)
