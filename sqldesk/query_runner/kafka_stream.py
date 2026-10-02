"""
Querying a stream: SQL over the window SQLDesk is holding.

A topic is a data source, so it has to answer the two questions every data
source answers -- what tables are here, and run this SQL -- and both are
answered from the stream's own DuckDB file rather than from Kafka. Kafka has no
query interface and SQLDesk is not going to pretend otherwise: what you can
query is the window, which is what the chart says above itself.

Two tables, deliberately:

- `events`, the raw window. Minutes of it, however many the row budget buys.
- `rollup`, per-minute buckets going back a day, read from Postgres through a
  view so one query can join "now" to "this morning" without two data sources.

The connection is the stream's store, locked down the same way an upload's is:
a stream's SQL is written by people, so DuckDB's defaults would be theirs.
"""

import logging

from sqldesk.query_runner import (
    TYPE_BOOLEAN,
    TYPE_DATETIME,
    TYPE_FLOAT,
    TYPE_INTEGER,
    TYPE_STRING,
    BaseSQLQueryRunner,
    JobTimeoutException,
    register,
)
from sqldesk.utils import json_dumps

logger = logging.getLogger(__name__)

#: DuckDB's own type names, as SQLDesk's. Anything unrecognised is a string,
#: which is the one answer that is never actively wrong.
TYPES = {
    "BOOLEAN": TYPE_BOOLEAN,
    "TINYINT": TYPE_INTEGER,
    "SMALLINT": TYPE_INTEGER,
    "INTEGER": TYPE_INTEGER,
    "BIGINT": TYPE_INTEGER,
    "HUGEINT": TYPE_INTEGER,
    "UBIGINT": TYPE_INTEGER,
    "FLOAT": TYPE_FLOAT,
    "DOUBLE": TYPE_FLOAT,
    "DECIMAL": TYPE_FLOAT,
    "DATE": TYPE_DATETIME,
    "TIMESTAMP": TYPE_DATETIME,
    "TIMESTAMP WITH TIME ZONE": TYPE_DATETIME,
}


def _described(connection, query):
    """
    `{column: DuckDB type}` for a query, or nothing if it cannot be planned.

    Normalised to the names `TYPES` is keyed by: a parameterised type arrives
    as `DECIMAL(18,3)`, and the part in brackets says nothing about how to
    chart it.
    """
    try:
        rows = connection.execute("DESCRIBE {}".format(query)).fetchall()
    except Exception:
        # The query itself will raise in a moment and say something better.
        return {}
    kinds = {}
    for row in rows:
        kinds[row[0]] = (row[1] or "").split("(")[0].strip().upper()
    return kinds


class KafkaStream(BaseSQLQueryRunner):
    should_annotate_query = False

    @classmethod
    def name(cls):
        return "Kafka stream"

    @classmethod
    def type(cls):
        return "kafka_stream"

    @classmethod
    def configuration_schema(cls):
        return {
            "type": "object",
            "properties": {
                "brokers": {
                    "type": "string",
                    "title": "Bootstrap servers",
                    "default": "localhost:9092",
                },
                "topic": {"type": "string", "title": "Topic"},
                # Everything a broker needs to let us in, in the shape
                # librdkafka wants, because there are too many combinations of
                # SASL and TLS to put each on a form -- and inventing a subset
                # would be the one that does not cover somebody's cluster.
                "security_protocol": {
                    "type": "string",
                    "title": "Security protocol",
                    "default": "PLAINTEXT",
                    "extendedEnum": [
                        {"value": "PLAINTEXT", "name": "PLAINTEXT"},
                        {"value": "SSL", "name": "SSL"},
                        {"value": "SASL_PLAINTEXT", "name": "SASL_PLAINTEXT"},
                        {"value": "SASL_SSL", "name": "SASL_SSL"},
                    ],
                },
                "sasl_mechanism": {"type": "string", "title": "SASL mechanism", "default": ""},
                "sasl_username": {"type": "string", "title": "SASL username"},
                "sasl_password": {"type": "string", "title": "SASL password"},
                "row_budget": {
                    "type": "number",
                    "title": "Rows to keep",
                    "default": 0,
                    "info": "0 uses the install's setting. The window follows from this and the rate.",
                },
                "events_per_second": {
                    "type": "number",
                    "title": "Events a second to store",
                    "default": 0,
                    "info": "Past this, events are sampled and every chart says so. 0 uses the install's setting.",
                },
            },
            "required": ["brokers", "topic"],
            "secret": ["sasl_password"],
            "order": [
                "brokers",
                "topic",
                "security_protocol",
                "sasl_mechanism",
                "sasl_username",
                "sasl_password",
                "row_budget",
                "events_per_second",
            ],
        }

    @classmethod
    def enabled(cls):
        # Needs librdkafka, which is in the optional dependency group with
        # every other data source's SDK. A missing one makes this runner
        # unavailable, not the application broken.
        from sqldesk.query_runner import installed

        return installed("confluent_kafka")

    def __init__(self, configuration):
        super().__init__(configuration)
        self._store = None
        self._data_source_id = None

    def for_data_source(self, data_source_id):
        """
        Which data source this runner was built for.

        A runner is normally told nothing about the row it came from -- its
        configuration is the connection and nothing else. This one needs it,
        because the window it queries belongs to the `Stream` that hangs off
        the data source, and `DataSource.query_runner` is the only place that
        knows which one that is.
        """
        self._data_source_id = data_source_id

    # --- what the rest of SQLDesk asks of a data source --------------------

    def _stream(self):
        """
        The `Stream` row for this data source.

        Looked up rather than held, because a runner is constructed per query
        and the row carries the window and the sample rate -- both of which the
        consumer is changing underneath us.
        """
        from sqldesk import models

        # The configuration fallback is for a runner built by hand, in a test
        # or a shell; through the application it arrives by `for_data_source`.
        source_id = self._data_source_id or self.configuration.get("data_source_id")
        if not source_id:
            return None
        return models.Stream.query.filter(models.Stream.data_source_id == source_id).first()

    def _opened_store(self, stream):
        from sqldesk.streams.store import Store

        if self._store is None:
            # Read-only, and waiting out a flush rather than failing on one:
            # the consumer owns the write lock, and a query is a reader.
            self._store = Store(stream.store_path(), read_only=True)
        return self._store

    def run_query(self, query, user):
        stream = self._stream()
        if stream is None:
            return None, "This data source has no stream yet. Save it, and SQLDesk will start consuming."

        # Querying a stream is what "somebody is watching" means. Without this
        # nothing is ever active except a pinned stream, so the window would be
        # empty for everybody who had not asked an administrator to pin their
        # topic. At most one write a minute; see `activity.note_viewed`.
        from sqldesk.streams import activity

        try:
            activity.note_viewed(stream)
        except Exception:
            logger.warning("could not note that stream %s was viewed", stream.id, exc_info=True)

        store = self._opened_store(stream)
        try:
            cursor = store.connection.cursor()
            # The column types come from DESCRIBE rather than from the cursor.
            # DuckDB's DB-API `description` reports the generic DB-API codes --
            # every number is "NUMBER", every string "STRING" -- so reading
            # types from it typed every column as text, and a chart cannot plot
            # a number it has been told is a word. DESCRIBE answers in DuckDB's
            # own names, which is what `TYPES` is keyed by, and it plans the
            # query rather than running it.
            kinds = _described(store.connection, query)
            cursor.execute(query)
            columns = self.fetch_columns(
                [(column[0], TYPES.get(kinds.get(column[0], ""), TYPE_STRING)) for column in cursor.description]
            )
            rows = [dict(zip((column["name"] for column in columns), row)) for row in cursor.fetchall()]
            return json_dumps({"columns": columns, "rows": rows}), None
        except JobTimeoutException:
            raise
        except Exception as error:
            # A stream nothing has arrived on has no `events` table at all, and
            # "Table with name events does not exist" is a confusing way to
            # learn that nobody has looked at the dashboard yet.
            from sqldesk.streams import activity

            quiet = activity.why_it_is_quiet(stream)
            if quiet and "events" in str(error):
                return None, quiet
            return None, str(error)

    def get_schema(self, get_stats=False):
        """
        What a person sees in the schema browser.

        From the stream's recorded columns rather than from the file, so a
        stream that is paused still shows what it holds -- a schema browser that
        empties itself when a consumer pauses would read as the data being gone.
        """
        stream = self._stream()
        if stream is None or not stream.columns:
            return []
        return [
            {
                "name": "events",
                "columns": [column["name"] for column in stream.columns],
            }
        ]

    def test_connection(self):
        """
        Whether the broker will let us in, and whether the topic exists.

        Asked when somebody saves the data source, which is the moment to find
        out -- the alternative is a stream that looks configured and quietly
        consumes nothing.
        """
        from sqldesk.streams.consumer import describe_topic

        error = describe_topic(self.configuration)
        if error:
            raise Exception(error)
        return True


register(KafkaStream)
