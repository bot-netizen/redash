"""
Settings → Slack, and sending a dashboard to a channel.

Two audiences in one file, with two different permission checks. An
administrator installs the app and pastes its token, once. Anybody with
`send_dashboards` picks a channel and sends. Keeping them together is
deliberate: the send has to know what the setup stored, and splitting them
would mean two modules importing each other.
"""

import logging

from flask import request
from flask_restful import abort

from sqldesk import features, models, one_page, screenshots, slack
from sqldesk.handlers.base import BaseResource, get_object_or_404
from sqldesk.permissions import can_see_dashboard, require_admin
from sqldesk.utils import base_url, utcnow

logger = logging.getLogger(__name__)

#: A line somebody types above the picture. Long enough for a sentence of
#: context, short enough that the message is still mostly the dashboard.
MAX_MESSAGE = 1000


def _workspace(org, required=True):
    found = models.SlackWorkspace.query.filter(models.SlackWorkspace.org_id == org.id).first()
    if found is None and required:
        abort(400, message="Slack is not set up. An administrator adds the app's token under Settings.")
    return found


class SlackSettingsResource(BaseResource):
    """
    What is installed, and a token to replace it with.

    The token is never sent back, not even partially. A bot token posts as the
    app in every channel the app is in and does not expire, so there is no
    version of showing it that is worth the risk -- the page says which
    workspace it belongs to, which is the question somebody actually has.
    """

    @require_admin
    def get(self):
        found = _workspace(self.current_org, required=False)
        if found is None:
            return {"configured": False}
        return {
            "configured": True,
            "team_name": found.team_name,
            "app_name": found.app_name,
            "installed_by": found.installed_by.name if found.installed_by else None,
            "installed_at": found.created_at,
            "working": found.working,
            "last_error": found.last_error,
            "last_checked_at": found.last_checked_at,
        }

    @require_admin
    def post(self):
        body = request.get_json(silent=True) or {}
        token = (body.get("bot_token") or "").strip()
        if not token:
            abort(400, message="Paste the Slack app's bot token.")

        # Checked against Slack before it is stored, so a wrong token is
        # refused while somebody is still looking at the field rather than the
        # first time a dashboard fails to send.
        who, error = slack.check(token)
        if error:
            abort(400, message=error)

        found = _workspace(self.current_org, required=False)
        if found is None:
            found = models.SlackWorkspace(org=self.current_org)
            models.db.session.add(found)
        found.bot_token = token
        found.team_name = who.get("team")
        found.app_name = who.get("app")
        found.installed_by = self.current_user
        found.last_error = None
        found.last_checked_at = utcnow()
        models.db.session.commit()

        self.record_event({"action": "configure", "object_type": "slack"})
        return {"configured": True, "team_name": found.team_name, "app_name": found.app_name, "working": True}

    @require_admin
    def delete(self):
        found = _workspace(self.current_org, required=False)
        if found is not None:
            models.db.session.delete(found)
            models.db.session.commit()
        self.record_event({"action": "disconnect", "object_type": "slack"})
        return {"configured": False}


class SlackChannelsResource(BaseResource):
    """
    The channels the app can post to.

    Asked by the Send dialog rather than typed by hand, so a typo cannot
    produce a message that goes nowhere. Behind `send_dashboards` and not
    admin: whoever may send needs the list.
    """

    def get(self):
        if not features.can(self.current_user, features.SEND_DASHBOARDS):
            abort(403, message="You may not send dashboards.")
        found = _workspace(self.current_org)
        channels, error = slack.channels(found.bot_token)
        if error:
            _remember(found, error)
            abort(400, message=error)
        _remember(found, None)
        return {"channels": channels}


def _remember(workspace, error):
    """
    Keep the last thing Slack said.

    A revoked token looks exactly like a working one from here until something
    is sent, so the settings page needs somewhere to read the failure from
    other than a worker's log.
    """
    workspace.last_error = error
    workspace.last_checked_at = utcnow()
    models.db.session.commit()


class DashboardSlackShareResource(BaseResource):
    def post(self, dashboard_id):
        """
        Draw the dashboard, upload it, and post it with a button.

        Done while the caller waits, rather than on a worker. Somebody has just
        pressed Send and the thing they need to know is whether it arrived --
        on a queue, a revoked token or an archived channel becomes a log line
        nobody reads. It costs a web worker for a few seconds, which is what an
        explicit button press is allowed to cost.
        """
        if not features.can(self.current_user, features.SEND_DASHBOARDS):
            abort(403, message="You may not send dashboards.")

        dashboard = get_object_or_404(models.Dashboard.get_by_id_and_org, dashboard_id, self.current_org)
        # Sending a dashboard's contents to a channel is at least as much
        # access as opening it, so it is the same check subscribing uses.
        if not can_see_dashboard(dashboard.id, self.current_org, self.current_user):
            abort(403, message="You cannot see that dashboard.")

        body = request.get_json(silent=True) or {}
        channel = (body.get("channel") or "").strip()
        if not channel:
            abort(400, message="Pick a channel.")
        message = (body.get("text") or "").strip()[:MAX_MESSAGE]

        # Before anything is drawn or sent, because the answer does not depend
        # on either and a person should not wait eight seconds to be told no.
        too_big = one_page.too_big_to_send(dashboard.widgets)
        if too_big:
            abort(400, message=too_big)

        workspace = _workspace(self.current_org)
        picture, error = self._draw(dashboard)
        if error:
            abort(400, message=error)

        file_id, error = slack.upload(workspace.bot_token, "{}.png".format(dashboard.slug), picture)
        if error:
            _remember(workspace, error)
            abort(400, message=error)

        sender = self.current_user.name
        text = (
            "{}\n\n_{} shared *{}*_".format(message, sender, dashboard.name)
            if message
            else ("*{}*, shared by {}".format(dashboard.name, sender))
        )
        posted, error = slack.post(
            workspace.bot_token,
            channel,
            text,
            file_id=file_id,
            footer=self._freshness(dashboard),
            button={"text": "Open dashboard", "url": self._link(dashboard)},
        )
        if error:
            _remember(workspace, error)
            abort(400, message=error)

        _remember(workspace, None)
        self.record_event({"action": "share_slack", "object_id": dashboard.id, "object_type": "dashboard"})
        return {"sent": True, "channel": posted["channel"]}

    def _draw(self, dashboard):
        """
        A PNG of the dashboard as this person sees it.

        The same render pass §1 built: minted for them, for this dashboard
        alone, withdrawn as soon as the renderer answers. Nothing is made
        public to take a picture of it.
        """
        # No check that a renderer exists: `send_dashboards` is not granted at
        # all without one (see features.py), so somebody who reaches this line
        # has one. A branch for it would be unreachable code, which is code
        # nobody has run.
        picture = screenshots.capture(screenshots.DASHBOARD, dashboard, self.current_user)
        if not picture:
            # `capture` folds every failure into None, because to an alert they
            # all mean "send it without a picture". Here they mean "do not
            # send", so the message says what to look at.
            return None, "Could not draw the dashboard. The renderer's log will say why."
        return picture, None

    def _link(self, dashboard):
        """
        Where the button goes.

        The public link when there is one, so anybody in the channel can open
        it without an account here. Otherwise the dashboard's own address,
        where they sign in -- which is the honest fallback rather than a link
        that half the channel cannot use and nobody told them about.
        """
        if not self.current_org.get_setting("disable_public_urls"):
            # A dashboard's public link is an `ApiKey` row against it, not a
            # column: there is one only if somebody turned sharing on.
            key = models.ApiKey.get_by_object(dashboard)
            if key is not None:
                return "{}/public/dashboards/{}".format(base_url(self.current_org), key.api_key)
        return "{}/dashboards/{}".format(base_url(self.current_org), dashboard.slug or dashboard.id)

    def _freshness(self, dashboard):
        """ "As of" the oldest result on it, which is the honest figure."""
        oldest = None
        for widget in dashboard.widgets:
            query = widget.visualization.query_rel if widget.visualization else None
            retrieved = query.latest_query_data.retrieved_at if query and query.latest_query_data else None
            if retrieved and (oldest is None or retrieved < oldest):
                oldest = retrieved
        return "as of {}".format(oldest.strftime("%H:%M on %-d %B")) if oldest else None
