"""
A stream's own settings: what it keeps, what it groups by, and whether it
stays on when nobody is looking.

Everything a stream *reads* comes through its data source like any other --
the query editor, the schema browser, permissions. What is here is the handful
of decisions that are only a stream's, and the page that shows what it is
doing.

Reading is for anybody who may use the data source. Changing is for an
administrator: a pin burns a worker and a disk indefinitely, a row budget
decides how much disk, and a rollup definition decides what a chart can ask --
none of those are a reader's to set.
"""

import logging

from flask import request
from flask_restful import abort

from sqldesk import models
from sqldesk.handlers.base import BaseResource, get_object_or_404
from sqldesk.permissions import require_access, require_admin, view_only
from sqldesk.streams import activity, rollup, window
from sqldesk.streams.store import Store

logger = logging.getLogger(__name__)


def _stream(data_source_id, org, user):
    source = get_object_or_404(models.DataSource.get_by_id_and_org, data_source_id, org)
    # The data source's own permission, not a new one: a stream is a data
    # source, and who may read it is already decided.
    require_access(source, user, view_only)
    stream = models.Stream.query.filter(models.Stream.data_source_id == source.id).first()
    if stream is None:
        abort(404, message="That data source is not a stream.")
    return stream


class StreamListResource(BaseResource):
    """
    Every stream in the organisation, for the page that watches them.

    Admin, because the page it feeds carries the pin and the budgets. A reader
    who may use one stream has no business knowing what else is configured.

    The `quiet` sentence is the field this page exists for: three different
    situations look identical on an empty chart -- nobody has looked at it
    lately, the consumer stopped with an error, or the topic genuinely has
    nothing on it -- and only one of them is somebody's problem.
    """

    @require_admin
    def get(self):
        streams = models.Stream.query.filter(models.Stream.org == self.current_org).order_by(models.Stream.topic).all()
        names = dict(
            models.db.session.query(models.DataSource.id, models.DataSource.name).filter(
                models.DataSource.org == self.current_org
            )
        )
        return {
            "streams": [
                {
                    "id": stream.id,
                    "data_source_id": stream.data_source_id,
                    "data_source_name": names.get(stream.data_source_id),
                    "topic": stream.topic,
                    "active": activity.is_active(stream),
                    "pinned": stream.pinned,
                    "quiet": activity.why_it_is_quiet(stream),
                    "rows": stream.rows,
                    "malformed": stream.malformed,
                    "observed_rate": round(stream.observed_rate or 0, 1),
                    "window_seconds": stream.window_seconds,
                    "sample_rate": stream.sample_rate,
                    "sampled": stream.sampled,
                    "describes": window.describe(stream.window_seconds, stream.rows),
                    "schema_state": stream.schema_state,
                    "columns": len(stream.columns or []),
                    "has_rollup": bool(stream.measures),
                    "last_flush_at": stream.last_flush_at,
                }
                for stream in streams
            ]
        }


class StreamResource(BaseResource):
    def get(self, data_source_id):
        """
        What the stream is doing, for its page.

        `quiet` is the field worth having: three different situations look
        identical on an empty chart -- nobody has looked at it lately, the
        consumer stopped with an error, or the topic genuinely has nothing on it
        -- and only one of them is a problem.
        """
        stream = _stream(data_source_id, self.current_org, self.current_user)
        return {
            "id": stream.id,
            "data_source_id": stream.data_source_id,
            "topic": stream.topic,
            "active": activity.is_active(stream),
            "pinned": stream.pinned,
            "quiet": activity.why_it_is_quiet(stream),
            "rows": stream.rows,
            "malformed": stream.malformed,
            "observed_rate": round(stream.observed_rate or 0, 1),
            "window_seconds": stream.window_seconds,
            "sample_rate": stream.sample_rate,
            "sampled": stream.sampled,
            # The line the chart puts above itself. Built here so the page and
            # a chart cannot word the same fact two ways.
            "describes": window.describe(stream.window_seconds, stream.rows),
            "row_budget": stream.budget,
            "events_per_second": stream.ceiling,
            "columns": list(stream.columns or []),
            "schema_state": stream.schema_state,
            "group_by": list(stream.group_by or []),
            "measures": list(stream.measures or []),
            "last_flush_at": stream.last_flush_at,
            "last_viewed_at": stream.last_viewed_at,
        }

    @require_admin
    def post(self, data_source_id):
        """
        Change what only an administrator may change.

        A rollup definition is checked against the store's real columns before
        it is saved, because the alternative is a definition that looks accepted
        and then fails in a worker once a minute with nobody reading the log.
        """
        stream = _stream(data_source_id, self.current_org, self.current_user)
        body = request.get_json(silent=True) or {}

        if "pinned" in body:
            stream.pinned = bool(body["pinned"])
        if "row_budget" in body:
            stream.row_budget = max(0, int(body["row_budget"] or 0))
        if "events_per_second" in body:
            stream.events_per_second = max(0, int(body["events_per_second"] or 0))

        if "columns" in body:
            columns = body["columns"]
            if not isinstance(columns, list) or not columns:
                abort(400, message="A schema needs at least one column.")
            stream.columns = columns
            # Settling the columns is what freezing means: they are not
            # re-inferred, so a producer adding a field no longer changes the
            # shape of anybody's chart.
            stream.schema_state = models.SCHEMA_FROZEN

        if "group_by" in body or "measures" in body:
            group_by = list(body.get("group_by", stream.group_by or []))
            measures = list(body.get("measures", stream.measures or []))
            if measures:
                problem = rollup.check(group_by, measures, self._columns(stream))
                if problem:
                    abort(400, message=problem)
            stream.group_by = group_by
            stream.measures = measures
            # A definition that was refused last time should stop being
            # complained about once it has been fixed.
            stream.last_error = None

        models.db.session.commit()
        self.record_event({"action": "edit", "object_id": stream.id, "object_type": "stream"})
        return self.get(data_source_id)

    def _columns(self, stream):
        """
        The columns to check a rollup against: the store's, or the stream's.

        The store's are the truth, but a stream that has never consumed anything
        has none -- and refusing to let somebody define a rollup before the
        first event has arrived would mean setting it up twice.
        """
        try:
            store = Store(stream.store_path())
            try:
                found = store.columns()
            finally:
                store.close()
            if found:
                return found
        except Exception:
            logger.warning("could not read stream %s's columns", stream.id, exc_info=True)
        return [(column["name"], column.get("type", "VARCHAR")) for column in (stream.columns or [])]


class StreamRollupResource(BaseResource):
    def get(self, data_source_id):
        """
        The per-minute buckets, for a chart asking about more than the window.

        `is_other` and `sample_rate` come with every row, because a chart that
        hid the capped tail or quietly multiplied a sampled count would be
        wrong while looking right.
        """
        stream = _stream(data_source_id, self.current_org, self.current_user)
        minutes = min(int(request.args.get("minutes", 180)), 60 * 48)
        rows = (
            stream.rollups.filter(
                models.StreamRollup.minute
                >= models.db.func.now() - models.db.text("INTERVAL '{} minutes'".format(minutes))
            )
            .order_by(models.StreamRollup.minute)
            .limit(20000)
            .all()
        )
        return {
            "minutes": minutes,
            "rows": [
                {
                    "minute": row.minute,
                    "group": row.group_key,
                    "is_other": row.is_other,
                    "values": row.values,
                    "sample_rate": row.sample_rate,
                }
                for row in rows
            ],
        }
