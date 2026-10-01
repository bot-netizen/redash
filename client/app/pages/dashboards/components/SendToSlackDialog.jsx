import React, { useCallback, useEffect, useState } from "react";
import PropTypes from "prop-types";
import Alert from "antd/lib/alert";
import Input from "antd/lib/input";
import Modal from "antd/lib/modal";
import Select from "antd/lib/select";
import Tag from "antd/lib/tag";

import { wrap as wrapDialog, DialogPropType } from "@/components/DialogWrapper";
import { axios } from "@/services/axios";
import notification from "@/services/notification";

/*
  Send this dashboard to a Slack channel, now.

  Channels come from Slack rather than being typed, so a typo cannot produce a
  message that goes nowhere: the list is what the app can actually post to, and
  a private channel the app has not been invited to is simply not in it.

  Sending happens while the dialog is open and waits for the answer. A
  dashboard takes a few seconds to draw, and the thing somebody needs to know
  after pressing Send is whether it arrived -- on a queue, a revoked token or an
  archived channel becomes a log line nobody reads.
*/
function SendToSlackDialog({ dialog, dashboard }) {
  const [channels, setChannels] = useState(null);
  const [problem, setProblem] = useState(null);
  const [channel, setChannel] = useState(undefined);
  const [text, setText] = useState("");
  const [sending, setSending] = useState(false);

  useEffect(() => {
    axios
      .get("api/slack/channels")
      .then((data) => setChannels(data.channels))
      .catch((error) => {
        const message =
          error && error.response && error.response.data && error.response.data.message
            ? error.response.data.message
            : "Could not read the channel list from Slack.";
        // Slack's own reason, which is usually actionable: the app has been
        // removed, the token revoked, an administrator has not set it up.
        setProblem(message);
        setChannels([]);
      });
  }, []);

  const send = useCallback(() => {
    setSending(true);
    axios
      .post(`api/dashboards/${dashboard.id}/share/slack`, { channel, text })
      .then(() => {
        notification.success(`Sent to Slack.`);
        dialog.close();
      })
      .catch((error) => {
        const message =
          error && error.response && error.response.data && error.response.data.message
            ? error.response.data.message
            : "Could not send it.";
        setProblem(message);
      })
      .finally(() => setSending(false));
  }, [channel, text, dashboard.id, dialog]);

  const chosen = (channels || []).find((item) => item.id === channel);

  return (
    <Modal
      {...dialog.props}
      title="Send to Slack"
      okText={sending ? "Sending…" : "Send"}
      okButtonProps={{ disabled: !channel || sending, loading: sending }}
      onOk={send}
      data-test="SendToSlackDialog"
    >
      {problem && <Alert className="m-b-15" type="error" showIcon message={problem} />}

      <p className="text-muted">
        The channel gets a picture of <strong>{dashboard.name}</strong> as it looks now, with a button that opens it.
        SQLDesk draws and uploads the picture, so Slack never has to reach this install.
      </p>

      <label htmlFor="slack-channel">Channel</label>
      <Select
        id="slack-channel"
        style={{ width: "100%" }}
        placeholder={channels === null ? "Asking Slack…" : "Pick a channel"}
        loading={channels === null}
        showSearch
        optionFilterProp="label"
        value={channel}
        onChange={setChannel}
        options={(channels || []).map((item) => ({
          value: item.id,
          label: `#${item.name}`,
          // Said rather than hidden: a public channel the app is not in can
          // still be posted to, and somebody choosing one should know the app
          // is about to appear there.
          title: item.member ? undefined : "The app is not in this channel yet",
        }))}
      />
      {chosen && !chosen.member && (
        <p className="text-muted m-t-5">
          <Tag>new</Tag> The app will join this channel when it posts.
        </p>
      )}

      <label className="m-t-15" htmlFor="slack-text">
        Anything you want to say (optional)
      </label>
      <Input.TextArea
        id="slack-text"
        rows={2}
        value={text}
        placeholder="Q3 came in ahead of plan."
        maxLength={1000}
        onChange={(event) => setText(event.target.value)}
      />
    </Modal>
  );
}

SendToSlackDialog.propTypes = {
  dialog: DialogPropType.isRequired,
  dashboard: PropTypes.shape({ id: PropTypes.number, name: PropTypes.string }).isRequired,
};

export default wrapDialog(SendToSlackDialog);
