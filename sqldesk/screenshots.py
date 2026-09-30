"""
Pictures of dashboards and queries, for attaching to an alert.

Nothing in this image can draw one. Producing a picture of a dashboard means
running the dashboard, which means a browser, and putting a browser in here
would add several hundred megabytes to an image the server and the worker
share -- for a feature most installs never turn on. So the browser lives in
its own optional service and this module is the client for it: a POST with a
URL, a PNG back. Point SQLDESK_SCREENSHOT_URL at one and the feature turns on;
leave it unset and everything here declines quietly.

Grafana reached the same arrangement for the same reason, and Superset, which
did not, tells its users to build their own image instead.

The rule that matters here: **a picture is a nice-to-have and an alert is
not.** Every failure in this file is caught and logged, and the alert goes out
without the image. Nothing in here is allowed to be the reason a threshold
breach went unreported.
"""

import logging

import requests

from sqldesk import models, render_pass, settings
from sqldesk.permissions import has_access, view_only

logger = logging.getLogger(__name__)

#: What a renderer is asked to wait for before it captures. The embed page
#: sets this once the result is in and the chart has drawn; without it the
#: normal failure is a picture of a spinner.
READY_SELECTOR = "[data-rendered='true']"

DASHBOARD = "dashboard"
QUERY = "query"


def enabled():
    return settings.FEATURE_ALERT_SCREENSHOTS and bool(settings.SCREENSHOT_URL)


def _target_url(kind, obj, token):
    """
    The page to photograph, as the renderer will ask for it.

    Both are pages the application already serves -- there is no separate
    rendering path to keep in step with what people actually see.

    A dashboard's page takes its credential in the path, because that is how
    the route is shaped; it is a pass good for five minutes rather than a link
    anybody keeps. A query's goes in a header instead, since that route has
    somewhere to put it.
    """
    base = settings.INTERNAL_BASE_URL.rstrip("/")
    if kind == DASHBOARD:
        return f"{base}/public/dashboards/{token}?screenshot=1"

    visualization = _first_visualization(obj)
    if visualization is None:
        return None
    return f"{base}/embed/query/{obj.id}/visualization/{visualization.id}?screenshot=1"


def _first_visualization(query):
    """
    Which of a query's visualizations to draw.

    Anything but the table, if there is one: somebody attaching a query to an
    alert wants the chart they built, and the table is what a query has when
    nobody has made one.
    """
    visualizations = sorted(query.visualizations, key=lambda v: v.id)
    drawn = [v for v in visualizations if v.type != "TABLE"]
    return (drawn or visualizations or [None])[0]


def _renderer_headers():
    """The token the renderer expects, when one is set."""
    return {"X-Screenshot-Token": settings.SCREENSHOT_TOKEN} if settings.SCREENSHOT_TOKEN else {}


def capture(kind, obj, viewer):
    """
    A PNG of one dashboard or query, or None.

    None covers every way this can fail, because they all mean the same thing
    to the caller: send the alert without a picture.

    `viewer` is whose sight of it this is -- the alert's owner. A pass is
    minted for them, for this object alone, and withdrawn as soon as the
    renderer answers. Before this the renderer was handed the dashboard's
    *public* link, so a dashboard could only be pictured once it had been
    shared with the internet; a picture in an email is not a reason to make
    one public.
    """
    if not enabled():
        return None

    token = render_pass.issue(viewer, obj)
    if token is None:
        logger.warning("Could not issue a render pass for %s %s.", kind, getattr(obj, "id", "?"))
        return None

    url = _target_url(kind, obj, token)
    if url is None:
        logger.warning("Nothing to draw for %s %s; skipping its screenshot.", kind, getattr(obj, "id", "?"))
        render_pass.withdraw(token)
        return None

    try:
        response = requests.post(
            f"{settings.SCREENSHOT_URL.rstrip('/')}/screenshot",
            headers=_renderer_headers(),
            json={
                "url": url,
                # The pass goes in a header, not the URL, wherever the
                # route allows it: two services would otherwise write a
                # working credential into their logs.
                "headers": {"Authorization": f"Key {token}"},
                "wait_for": READY_SELECTOR,
                "timeout": settings.SCREENSHOT_TIMEOUT,
                # A dashboard is usually taller than a window. The renderer
                # captures the whole page rather than the first screen of it.
                "full_page": kind == DASHBOARD,
            },
            timeout=settings.SCREENSHOT_TIMEOUT + 5,
        )
        response.raise_for_status()
    except requests.RequestException:
        logger.exception("Could not get a screenshot of %s %s.", kind, getattr(obj, "id", "?"))
        return None
    finally:
        # Whatever happened, this pass has had its turn.
        render_pass.withdraw(token)

    image = response.content
    if not image:
        logger.warning("The renderer returned an empty image for %s %s.", kind, getattr(obj, "id", "?"))
        return None

    return image


def _load(kind, object_id, org):
    try:
        if kind == DASHBOARD:
            return models.Dashboard.get_by_id_and_org(object_id, org)
        if kind == QUERY:
            return models.Query.get_by_id_and_org(object_id, org)
    except Exception:
        # Deleted since it was attached, or never in this organization.
        logger.warning("Alert attachment %s %s could not be loaded.", kind, object_id)
    return None


def _owner_may_see(kind, obj, owner):
    """
    Access is checked when an attachment is saved; it is checked again here
    because access changes, and a picture rendered with the query's own key
    would otherwise outlive the owner's right to look at it.
    """
    if kind == QUERY:
        return has_access(obj, owner, view_only)
    return (
        owner.has_permission("admin")
        or models.Dashboard.all(obj.org, owner.group_ids, owner.id).filter(models.Dashboard.id == obj.id).count() > 0
    )


def for_alert(alert):
    """
    Every picture an alert asks for.

    Each one carries its own title as well as its bytes, because the email has
    to name them: a recipient whose client blocks images -- which many do by
    default -- otherwise gets five empty boxes saying nothing at all.

    Capped, and the cap is the point: an alert carrying twenty dashboards
    would take minutes to send and arrive as something nobody opens.
    """
    if not enabled():
        return []

    attachments = (alert.options or {}).get("attachments") or []
    org = alert.query_rel.org

    images = []
    for attachment in attachments[: settings.MAX_ALERT_ATTACHMENTS]:
        kind = attachment.get("type")
        obj = _load(kind, attachment.get("id"), org)
        if obj is None or not _owner_may_see(kind, obj, alert.user):
            continue

        image = capture(kind, obj, alert.user)
        if image is None:
            continue

        images.append(
            {
                "filename": f"{kind}-{obj.id}.png",
                "image": image,
                # The object's own name, read now rather than the one saved on
                # the alert, which goes stale the moment anybody renames it.
                "title": obj.name,
                "kind": kind,
            }
        )

    return images
