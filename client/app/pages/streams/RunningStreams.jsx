import React, { useCallback, useEffect, useState } from "react";
import Alert from "antd/lib/alert";
import Button from "antd/lib/button";
import Progress from "antd/lib/progress";
import Table from "antd/lib/table";
import Tag from "antd/lib/tag";
import Tooltip from "antd/lib/tooltip";

import TimeAgo from "@/components/TimeAgo";
import { axios } from "@/services/axios";
import recordEvent from "@/services/recordEvent";

import "./streams.less";

/*
  What is consuming, and how much room is left.

  Readable by everybody on purpose. "All five slots are in use" is only
  actionable if you can see what is using them and who to ask -- a limit whose
  holders are invisible is a limit people file tickets about.

  A slot is a *topic*, not a viewer: five people watching one topic share one
  consumer and take one slot between them, which is why the numbers here can
  look small next to the number of people using it.
*/

const STATE = {
  running: { colour: "green", label: "consuming" },
  paused: { colour: "orange", label: "paused" },
};

export default function RunningStreams() {
  const [data, setData] = useState(null);
  const [failed, setFailed] = useState(false);
  const [loading, setLoading] = useState(true);

  const load = useCallback(() => {
    setLoading(true);
    axios
      .get("api/streams/running")
      .then(setData)
      .catch(() => setFailed(true))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    recordEvent("view", "page", "streams/running");
    load();
    // Slow on purpose: this page is about what is running, and what is running
    // changes on the scale of minutes. A second-by-second poll would cost more
    // than the thing it is watching.
    const timer = setInterval(load, 15000);
    return () => clearInterval(timer);
  }, [load]);

  const slots = (data && data.slots) || {};
  const columns = [
    {
      title: "Topic",
      dataIndex: "topic",
      render: (topic, row) => (
        <span>
          <strong>{topic}</strong>
          <div className="streams-muted">
            {row.data_source_name} &middot; queried as <code>{row.table}</code>
          </div>
        </span>
      ),
    },
    {
      title: "State",
      dataIndex: "state",
      width: 170,
      render: (state, row) => {
        const it = STATE[state] || STATE.paused;
        return (
          <span>
            <Tag color={it.colour}>{it.label}</Tag>
            {row.pinned && (
              <Tooltip title="Pinned by an administrator, so it consumes whether or not anybody is watching.">
                <Tag>pinned</Tag>
              </Tooltip>
            )}
          </span>
        );
      },
    },
    {
      title: "Watching",
      dataIndex: "watchers",
      width: 110,
      align: "right",
      render: (watchers, row) => (
        <span>
          {watchers}
          {row.started_by && <div className="streams-muted">{row.started_by} started it</div>}
        </span>
      ),
    },
    {
      title: "Window",
      dataIndex: "describes",
      render: (describes, row) => (
        <span>
          {describes}
          {row.sampled && (
            <Tooltip
              title={`Faster than the ceiling allows, so 1 event in ${row.sample_rate} is kept. Counts from this stream are estimates.`}
            >
              <Tag color="orange" className="m-l-5">
                1 in {row.sample_rate}
              </Tag>
            </Tooltip>
          )}
        </span>
      ),
    },
    {
      title: "Last flush",
      dataIndex: "last_flush_at",
      width: 130,
      render: (at) => (at ? <TimeAgo date={at} /> : <span className="streams-muted">never</span>),
    },
  ];

  return (
    <div className="container streams-page" data-test="RunningStreams">
      <div className="streams-header">
        <h2>Running streams</h2>
        <p className="streams-muted">
          A slot is a topic, not a viewer: everybody watching one topic shares one consumer and one window.
        </p>
      </div>

      {failed && <Alert type="warning" showIcon message="Could not load what is running." />}

      {data && (
        <div className="streams-slots">
          <div className="streams-slot-bar">
            <Progress
              percent={slots.limit ? Math.round((slots.used / slots.limit) * 100) : 0}
              status={slots.limit && slots.used >= slots.limit ? "exception" : "normal"}
              showInfo={false}
            />
          </div>
          <div>
            <strong>
              {slots.used} of {slots.limit || "∞"}
            </strong>{" "}
            <span className="streams-muted">
              slots in use &middot; {slots.per_user || "∞"} per person &middot; a stream runs for up to {slots.minutes}{" "}
              minutes before somebody says they still want it
            </span>
          </div>
          <Button size="small" onClick={load} loading={loading} data-test="RefreshRunning">
            Refresh
          </Button>
        </div>
      )}

      {data && data.streams.length === 0 && (
        <p className="streams-muted">
          Nothing is consuming. A stream starts when somebody watches it, and stops when nobody has for a minute.
        </p>
      )}

      {data && data.streams.length > 0 && (
        <Table
          className="streams-table"
          dataSource={data.streams}
          columns={columns}
          rowKey="id"
          size="small"
          pagination={false}
          expandable={{
            expandedRowRender: (row) => <span className="streams-error">{row.last_error}</span>,
            rowExpandable: (row) => !!row.last_error,
          }}
        />
      )}
    </div>
  );
}
