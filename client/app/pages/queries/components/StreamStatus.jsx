import { find } from "lodash";
import React, { useEffect, useState } from "react";
import PropTypes from "prop-types";
import Tag from "antd/lib/tag";
import Tooltip from "antd/lib/tooltip";

import { axios } from "@/services/axios";

/*
  What the topic under this query is doing, beside the button that starts it.

  A stream query looks exactly like any other query until it runs, and the
  numbers that tell you whether to believe the answer -- the rate, how much
  history the window holds, whether it is sampled -- live nowhere else on this
  page. A count from a sampled stream is an estimate, and somebody reading a
  chart drawn from one has to be told so where they are looking, not in a
  settings page they will never open.

  It polls only while the stream is running. Asking every few seconds about a
  stream nobody started is a request per viewer per tab for an answer that will
  not change.
*/
const EVERY_MS = 5000;

function topicsIn(text, streams) {
  return streams.filter((stream) => new RegExp(`\\b${stream.table}\\b`, "i").test(text || ""));
}

export default function StreamStatus({ dataSource, query, streaming }) {
  const [streams, setStreams] = useState([]);
  const dataSourceId = dataSource && dataSource.id;

  useEffect(() => {
    let live = true;
    const ask = () =>
      axios
        .get("api/streams/running")
        .then((data) => live && setStreams((data && data.streams) || []))
        .catch(() => {});
    ask();
    if (!streaming) {
      return () => {
        live = false;
      };
    }
    const timer = setInterval(ask, EVERY_MS);
    return () => {
      live = false;
      clearInterval(timer);
    };
  }, [streaming, dataSourceId]);

  const mine = topicsIn(query.query, streams).filter(
    (stream) => !dataSource || stream.data_source_id === dataSource.id
  );
  const stream = find(mine, (one) => one.state === "running") || mine[0];

  if (!stream) {
    return (
      <span className="stream-status stream-status-idle" data-test="StreamStatus">
        <Tag>not started</Tag>
        <span className="stream-status-note">Press Start streaming to begin consuming.</span>
      </span>
    );
  }

  return (
    <span className="stream-status" data-test="StreamStatus">
      <Tag color={stream.state === "running" ? "green" : "orange"}>
        {stream.state === "running" ? "consuming" : "paused"}
      </Tag>
      <span className="stream-status-figure" data-test="StreamRate">
        {stream.observed_rate || 0}/s
      </span>
      <span className="stream-status-note">{stream.describes}</span>
      {stream.sampled && (
        <Tooltip
          title={`Faster than the ceiling allows, so 1 event in ${stream.sample_rate} is kept. Counts from this stream are estimates.`}
        >
          <Tag color="orange">1 in {stream.sample_rate}</Tag>
        </Tooltip>
      )}
      {stream.watchers > 1 && <span className="stream-status-note">{stream.watchers} watching</span>}
    </span>
  );
}

StreamStatus.propTypes = {
  dataSource: PropTypes.object,
  query: PropTypes.object.isRequired,
  streaming: PropTypes.bool,
};

StreamStatus.defaultProps = { dataSource: null, streaming: false };
