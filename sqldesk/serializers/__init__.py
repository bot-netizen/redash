"""
This will eventually replace all the `to_dict` methods of the different model
classes we have. This will ensure cleaner code and better
separation of concerns.
"""

from flask_login import current_user
from funcy import project
from rq.job import JobStatus
from rq.timeouts import JobTimeoutException

from sqldesk import live, models
from sqldesk.models.parameterized_query import ParameterizedQuery
from sqldesk.permissions import has_access, view_only
from sqldesk.serializers.query_result import (
    serialize_query_result,
    serialize_query_result_json,
    serialize_query_result_to_dsv,
    serialize_query_result_to_xlsx,
)


def public_widget(widget):
    res = {
        "id": widget.id,
        "width": widget.width,
        "options": widget.options,
        "text": widget.text,
        "updated_at": widget.updated_at,
        "created_at": widget.created_at,
    }

    v = widget.visualization
    if v and v.id:
        res["visualization"] = {
            "type": v.type,
            "name": v.name,
            "description": v.description,
            "options": v.options,
            "updated_at": v.updated_at,
            "created_at": v.created_at,
            "query": {
                "id": v.query_rel.id,
                "name": v.query_rel.name,
                "description": v.query_rel.description,
                "options": v.query_rel.options,
            },
        }

    return res


def public_dashboard(dashboard):
    dashboard_dict = project(
        serialize_dashboard(dashboard, with_favorite_state=False),
        ("name", "layout", "dashboard_filters_enabled", "updated_at", "created_at", "options"),
    )

    dashboard_dict["widgets"] = [public_widget(w) for w in dashboard.loaded_widgets()]
    # A public viewer of a live dashboard watches it the same way.
    dashboard_dict["live"] = live.describe(dashboard)
    return dashboard_dict


def serialize_dashboard_subscription(subscription):
    """
    A subscription as the dashboard page shows it.

    Recipients are named rather than listed as ids: the page shows who gets
    this, and it has to be readable. Resolved now, so somebody who has left
    is simply not in the list.
    """
    return {
        "id": subscription.id,
        "dashboard_id": subscription.dashboard_id,
        "user": subscription.user.to_dict() if subscription.user else None,
        "schedule": subscription.schedule,
        "format": subscription.format,
        "recipients": [{"id": u.id, "name": u.name, "email": u.email} for u in subscription.recipients()],
        "active": subscription.active,
        "last_sent_at": subscription.last_sent_at,
        "last_error": subscription.last_error,
        "created_at": subscription.created_at,
    }


class Serializer:
    pass


class QuerySerializer(Serializer):
    def __init__(self, object_or_list, **kwargs):
        self.object_or_list = object_or_list
        self.options = kwargs

    def serialize(self):
        if isinstance(self.object_or_list, models.Query):
            result = serialize_query(self.object_or_list, **self.options)
            if self.options.get("with_favorite_state", True) and not current_user.is_api_user():
                result["is_favorite"] = models.Favorite.is_favorite(current_user.id, self.object_or_list)
        else:
            result = [serialize_query(query, **self.options) for query in self.object_or_list]
            if self.options.get("with_favorite_state", True):
                queries = list(self.object_or_list)
                favorites = models.Favorite.query.filter(
                    models.Favorite.object_id.in_([o.id for o in queries]),
                    models.Favorite.object_type == "Query",
                    models.Favorite.user_id == current_user.id,
                )
                favorites_dict = {fav.object_id: fav for fav in favorites}

                for query in result:
                    favorite = favorites_dict.get(query["id"])
                    query["is_favorite"] = favorite is not None
                    if favorite:
                        query["starred_at"] = favorite.created_at

        return result


def serialize_query(
    query,
    with_stats=False,
    with_visualizations=False,
    with_user=True,
    with_last_modified_by=True,
    with_api_key=False,
):
    d = {
        "id": query.id,
        "latest_query_data_id": query.latest_query_data_id,
        "name": query.name,
        "description": query.description,
        "query": query.query_text,
        "query_hash": query.query_hash,
        "schedule": query.schedule,
        "is_archived": query.is_archived,
        "is_draft": query.is_draft,
        "updated_at": query.updated_at,
        "created_at": query.created_at,
        "data_source_id": query.data_source_id,
        "options": query.options,
        "version": query.version,
        "tags": query.tags or [],
        "is_safe": query.parameterized.is_safe,
    }

    if with_api_key:
        d["api_key"] = query.api_key

    if with_user:
        d["user"] = query.user.to_dict()
    else:
        d["user_id"] = query.user_id

    if with_last_modified_by:
        d["last_modified_by"] = query.last_modified_by.to_dict() if query.last_modified_by is not None else None
    else:
        d["last_modified_by_id"] = query.last_modified_by_id

    if with_stats:
        if query.latest_query_data is not None:
            d["retrieved_at"] = query.retrieved_at
            d["runtime"] = query.runtime
            # None for results stored before row_count existed; the UI shows
            # those as unknown rather than claiming zero rows.
            d["row_count"] = query.latest_query_data.row_count
        else:
            d["retrieved_at"] = None
            d["runtime"] = None
            d["row_count"] = None

        # Execution health, so a list view can show query status without
        # fetching a result. This is a plain column on Query, already loaded
        # by Query.all_queries(), so it costs no extra round trip.
        #
        # Deliberately additive: further list-safe stats (a denormalized
        # row count, say) belong here too. Anything that would require
        # touching QueryResult.data must NOT go in — all_queries() narrows
        # that join to runtime/retrieved_at precisely to keep the result
        # payload out of list queries, and widening it would be a severe
        # regression on large result sets.
        d["schedule_failures"] = query.schedule_failures

    if with_visualizations:
        d["visualizations"] = [serialize_visualization(vis, with_query=False) for vis in query.visualizations]

    return d


def serialize_visualization(object, with_query=True):
    d = {
        "id": object.id,
        "type": object.type,
        "name": object.name,
        "description": object.description,
        "options": object.options,
        "updated_at": object.updated_at,
        "created_at": object.created_at,
    }

    if with_query:
        d["query"] = serialize_query(object.query_rel)

    return d


def serialize_widget(object):
    d = {
        "id": object.id,
        "width": object.width,
        "options": object.options,
        "dashboard_id": object.dashboard_id,
        "text": object.text,
        "updated_at": object.updated_at,
        "created_at": object.created_at,
    }

    if object.visualization and object.visualization.id:
        d["visualization"] = serialize_visualization(object.visualization)

    return d


def serialize_alert(alert, full=True):
    d = {
        "id": alert.id,
        "name": alert.name,
        "options": alert.options,
        "state": alert.state,
        "last_triggered_at": alert.last_triggered_at,
        "updated_at": alert.updated_at,
        "created_at": alert.created_at,
        "rearm": alert.rearm,
    }

    if full:
        d["query"] = serialize_query(alert.query_rel)
        d["user"] = alert.user.to_dict()
    else:
        d["query_id"] = alert.query_id
        d["user_id"] = alert.user_id

    return d


def serialize_dashboard(obj, with_widgets=False, user=None, with_favorite_state=True):
    layout = obj.layout

    widgets = []
    # Whether this is a streaming dashboard, accumulated while the widgets are
    # walked rather than asked of the dashboard afterwards. `loaded_widgets`
    # has already joined the visualization, the query and the data source, so
    # reading it here costs nothing -- where asking the dashboard would walk
    # the dynamic relationship again and lazily fetch the lot, one widget at a
    # time. That is the cost `test_dashboard_load_cost` exists to hold flat,
    # and the first version of this put it straight back.
    streaming = False

    if with_widgets:
        for w in obj.loaded_widgets():
            streaming = streaming or models._widget_is_streaming(w)
            if w.visualization_id is None:
                widgets.append(serialize_widget(w))
            elif user and has_access(w.visualization.query_rel, user, view_only):
                widgets.append(serialize_widget(w))
            else:
                widget = project(
                    serialize_widget(w),
                    (
                        "id",
                        "width",
                        "dashboard_id",
                        "options",
                        "created_at",
                        "updated_at",
                    ),
                )
                widget["restricted"] = True
                widgets.append(widget)
    else:
        widgets = None

    d = {
        "id": obj.id,
        "slug": obj.name_as_slug,
        "name": obj.name,
        "user_id": obj.user_id,
        "user": {
            "id": obj.user.id,
            "name": obj.user.name,
            "email": obj.user.email,
            "profile_image_url": obj.user.profile_image_url,
        },
        "layout": layout,
        "dashboard_filters_enabled": obj.dashboard_filters_enabled,
        "widgets": widgets,
        "options": obj.options,
        "is_archived": obj.is_archived,
        "is_draft": obj.is_draft,
        "tags": obj.tags or [],
        "updated_at": obj.updated_at,
        "created_at": obj.created_at,
        "version": obj.version,
        "live": live.describe(obj),
        # Which folder it is filed under, and whether that folder is one only
        # administrators may change. The page reads `can_edit` for what it may
        # offer; this is for saying *why* it cannot.
        "folder_id": obj.folder_id,
        "folder": obj.folder.to_dict() if obj.folder else None,
        # Derived from what is on it: a streaming dashboard is one whose
        # widgets draw on windows. The page needs it to know which refresh
        # intervals to offer and what to say when nothing is watching -- and
        # the page is the caller that asks for widgets, so it is never wrong
        # where it is read. A list of dashboards does not load widgets and does
        # not need it.
        "is_streaming": streaming if with_widgets else None,
    }

    return d


class DashboardSerializer(Serializer):
    def __init__(self, object_or_list, **kwargs):
        self.object_or_list = object_or_list
        self.options = kwargs

    def serialize(self):
        if isinstance(self.object_or_list, models.Dashboard):
            result = serialize_dashboard(self.object_or_list, **self.options)
            if self.options.get("with_favorite_state", True) and not current_user.is_api_user():
                result["is_favorite"] = models.Favorite.is_favorite(current_user.id, self.object_or_list)
        else:
            result = [serialize_dashboard(obj, **self.options) for obj in self.object_or_list]

            # Panel and distinct-query counts for the whole page in one
            # grouped query. Serializing these per dashboard would mean a
            # lazy load per row plus one per widget.
            dashboard_list = list(self.object_or_list)
            counts = models.Dashboard.content_counts([o.id for o in dashboard_list])
            for item in result:
                item_counts = counts.get(item["id"], {})
                item["widget_count"] = item_counts.get("widget_count", 0)
                item["query_count"] = item_counts.get("query_count", 0)

            if self.options.get("with_favorite_state", True):
                dashboards = list(self.object_or_list)
                favorites = models.Favorite.query.filter(
                    models.Favorite.object_id.in_([o.id for o in dashboards]),
                    models.Favorite.object_type == "Dashboard",
                    models.Favorite.user_id == current_user.id,
                )
                favorites_dict = {fav.object_id: fav for fav in favorites}

                for query in result:
                    favorite = favorites_dict.get(query["id"])
                    query["is_favorite"] = favorite is not None
                    if favorite:
                        query["starred_at"] = favorite.created_at

        return result


def serialize_job(job):
    # TODO: this is mapping to the old Job class statuses. Need to update the client side and remove this
    STATUSES = {
        JobStatus.QUEUED: 1,
        JobStatus.STARTED: 2,
        JobStatus.FINISHED: 3,
        JobStatus.FAILED: 4,
        JobStatus.CANCELED: 5,
        JobStatus.DEFERRED: 6,
        JobStatus.SCHEDULED: 7,
    }

    job_status = job.get_status()
    if job.is_started:
        updated_at = job.started_at or 0
    else:
        updated_at = 0

    status = STATUSES[job_status]
    result = query_result_id = None

    if job.is_cancelled:
        error = "Query cancelled by user."
        status = 4
    elif isinstance(job.result, Exception):
        error = str(job.result)
        status = 4
    elif isinstance(job.result, dict) and "error" in job.result:
        error = job.result["error"]
        status = 4
    else:
        error = ""
        result = query_result_id = job.result

    return {
        "job": {
            "id": job.id,
            "updated_at": updated_at,
            "status": status,
            "error": error,
            "result": result,
            "query_result_id": query_result_id,
        }
    }
