import React, { useCallback, useEffect, useState } from "react";
import Alert from "antd/lib/alert";
import Button from "antd/lib/button";
import Input from "antd/lib/input";
import Popconfirm from "antd/lib/popconfirm";
import Tag from "antd/lib/tag";

import TimeAgo from "@/components/TimeAgo";
import { axios } from "@/services/axios";
import notification from "@/services/notification";

/*
  The Slack app's bot token, pasted once by an administrator.

  Outside the form the rest of this page submits, deliberately. Everything else
  here is a preference that can be saved with everything else; this is a
  credential that is checked against Slack before it is stored, so it has its
  own button and its own answer. Batching it with "Save" would mean a wrong
  token silently failing alongside six settings that worked.

  The token is never shown back, not even partially. It posts as the app in
  every channel the app is in and does not expire, so there is no version of
  displaying it that is worth the risk -- the page says which workspace it
  belongs to, which is the question somebody actually has.
*/
export default function SlackSettings() {
  const [state, setState] = useState(null);
  const [token, setToken] = useState("");
  const [saving, setSaving] = useState(false);

  const load = useCallback(() => {
    axios
      .get("api/settings/slack")
      .then(setState)
      // Silent: an administrator looking at Formats should not be stopped by
      // Slack being unreachable.
      .catch(() => setState({ configured: false }));
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const save = useCallback(() => {
    setSaving(true);
    axios
      .post("api/settings/slack", { bot_token: token })
      .then((saved) => {
        setToken("");
        setState({ ...saved, working: true });
        notification.success(`Connected to ${saved.team_name || "Slack"}.`);
      })
      .catch((error) => {
        const message =
          error && error.response && error.response.data && error.response.data.message
            ? error.response.data.message
            : "Could not save that token.";
        // Slack's own reason, in words. "Could not save" alone sends somebody
        // to a search engine.
        notification.error(message);
      })
      .finally(() => setSaving(false));
  }, [token]);

  const disconnect = useCallback(() => {
    axios
      .delete("api/settings/slack")
      .then(() => {
        setState({ configured: false });
        notification.success("Disconnected from Slack.");
      })
      .catch(() => notification.error("Could not disconnect."));
  }, []);

  if (!state) {
    return null;
  }

  return (
    <div data-test="SlackSettings">
      <h4>Slack</h4>
      <p className="text-muted">
        Lets people send a dashboard to a channel: SQLDesk draws the picture and uploads it, so Slack never has to reach
        this install &mdash; it works behind a VPN. Create a Slack app in your workspace, give it{" "}
        <code>chat:write</code>, <code>files:write</code>, <code>channels:read</code> and <code>groups:read</code>,
        install it, and paste its bot token here.
      </p>

      {state.configured && (
        <p>
          Connected to <strong>{state.team_name || "a workspace"}</strong>
          {state.app_name ? ` as ${state.app_name}` : ""}
          {state.installed_by ? `, by ${state.installed_by}` : ""}
          {state.installed_at && (
            <span className="text-muted">
              {" "}
              <TimeAgo date={state.installed_at} />
            </span>
          )}{" "}
          {state.working ? <Tag color="green">working</Tag> : <Tag color="red">not working</Tag>}
        </p>
      )}

      {/*
        A revoked token looks exactly like a working one from here until
        something is sent, so the last failure is kept and shown rather than
        left in a worker's log.
      */}
      {state.configured && !state.working && state.last_error && (
        <Alert
          className="m-b-10"
          type="error"
          showIcon
          message="Slack refused the last request"
          description={
            <span>
              {state.last_error}
              {state.last_checked_at && (
                <span className="text-muted">
                  {" ("}
                  <TimeAgo date={state.last_checked_at} />
                  {")"}
                </span>
              )}
            </span>
          }
        />
      )}

      <Input.Group compact style={{ display: "flex", gap: 8, maxWidth: 560 }}>
        <Input.Password
          value={token}
          placeholder={state.configured ? "Paste a new token to replace it" : "xoxb-…"}
          onChange={(event) => setToken(event.target.value)}
          onPressEnter={() => token.trim() && save()}
        />
        <Button type="primary" loading={saving} disabled={!token.trim()} onClick={save}>
          {state.configured ? "Replace" : "Connect"}
        </Button>
        {state.configured && (
          <Popconfirm
            title="Disconnect Slack? Nobody will be able to send a dashboard to a channel."
            okText="Disconnect"
            onConfirm={disconnect}
          >
            <Button danger>Disconnect</Button>
          </Popconfirm>
        )}
      </Input.Group>
      <hr />
    </div>
  );
}
