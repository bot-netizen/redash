import { find } from "lodash";
import React, { useEffect, useState } from "react";
import PropTypes from "prop-types";
import Tag from "antd/lib/tag";
import Tooltip from "antd/lib/tooltip";

import { axios } from "@/services/axios";

import "./StreamStatus.less";

/*
  What the topic under this query is doing, beside the button that starts it.

  A stream query looks exactly like any other query until it runs, and the
  numbers that tell you whether to believe the answer -- the rate, how much
  history the window holds, whether it is sampled -- live nowhere else on this
  page. A count from a sampled stream is an estimate, and somebody reading a
  chart drawn from one has to be told so where they are looking.

  It polls only while the stream is running. Asking every few seconds about a
  stream nobody started is a request per viewer per tab for an answer that will
  not change.
*/
const EVERY_MS = 5000;

function topicsIn(text, streams) {
  return streams.filter((stream) => new RegExp(`\\b${stream.table}\\b`, "i").test(text || ""));
}

/** How long it has been running, in the largest unit that still reads. */
function elapsed(since, now) {
  const seconds = Math.max(0, Math.round((now - since) / 1000));
  if (seconds < 90) {
    return `${seconds}s`;
  }
  const minutes = Math.floor(seconds / 60);
  if (minutes < 90) {
    return `${minutes}m ${seconds % 60}s`;
  }
  return `${Math.floor(minutes / 60)}h ${minutes % 60}m`;
}

/*
  A rate a person can read.

  The server measures events over a window and divides, so a quiet topic
  arrives as 0.8166666666666667 — seventeen digits of false precision, and in a
  strip this size it pushed everything after it off the end. Nobody is making a
  decision on the sixteenth decimal place of a number that changes every two
  seconds.
*/
function rate(events) {
  const n = Number(events) || 0;
  if (n === 0) {
    return "0";
  }
  if (n >= 100) {
    return String(Math.round(n));
  }
  if (n >= 10) {
    return n.toFixed(1);
  }
  return n.toFixed(2).replace(/\.?0+$/, "");
}

export default function StreamStatus({ dataSource, query, streaming, startedAt, note, error }) {
  const [streams, setStreams] = useState([]);
  const [slots, setSlots] = useState(null);
  const [now, setNow] = useState(Date.now());
  const dataSourceId = dataSource && dataSource.id;

  // A second hand, only while it is running. "for 3m 20s" is how somebody
  // knows a stream drawing nothing has been drawing nothing for a while,
  // rather than having just started.
  useEffect(() => {
    if (!startedAt) {
      return undefined;
    }
    const timer = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(timer);
  }, [startedAt]);

  /*
    Asked once either way, and then repeatedly only while something is running.

    The repeated ask is about this query's topics, which only move while it is
    consuming -- a timer for a stream nobody started is a request per viewer
    per tab for an answer that will not change. The single ask is about the
    slots, and that *is* worth knowing before pressing Start: it is the
    difference between a button that does nothing and a button that does
    nothing because all five slots are taken by somebody else.
  */
  useEffect(() => {
    let live = true;
    if (!streaming) {
      // Whatever was on screen describes a stream this page has stopped.
      // Clearing it is what stops the strip insisting "consuming" at somebody
      // who has just pressed Stop.
      setStreams([]);
    }
    const ask = () =>
      axios
        .get("api/streams/running")
        .then((data) => {
          if (!live) {
            return;
          }
          setSlots((data && data.slots) || null);
          setStreams(streaming ? (data && data.streams) || [] : []);
        })
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
  // Gated on the local switch, not only on what the server last said. Stopping
  // is instant here and takes a moment there -- the consumer has to be told,
  // and other people may still be watching the same topic -- so a strip that
  // reported the server's answer went on saying "consuming" at somebody who
  // had just pressed Stop.
  const stream = streaming ? find(mine, (one) => one.state === "running") || mine[0] : null;

  if (!stream) {
    /*
      Why Start may do nothing.

      A slot is a topic, not a viewer: everybody watching one topic shares one
      consumer and one slot between them. The count used to be on a page of its
      own that nobody visited until it bit them -- and then it was two clicks
      away from the button that would not work. Said here only when it is full,
      because "3 of 5" is noise beside a button that is going to work.
    */
    const full = slots && slots.limit && slots.used >= slots.limit;
    return (
      <span className="stream-status stream-status-idle" data-test="StreamStatus">
        <Tag>not streaming</Tag>
        {full && (
          <Tooltip title="A slot is a topic, not a viewer. One frees up a minute after the last person stops watching it, or when a stream reaches its time limit.">
            <Tag color="orange" data-test="StreamSlotsFull">
              all {slots.limit} stream slots in use
            </Tag>
          </Tooltip>
        )}
      </span>
    );
  }

  const waiting = !!note;
  return (
    <span className="stream-status" data-test="StreamStatus">
      <Tag color={stream.state === "running" ? "cyan" : "orange"}>
        {stream.state === "running" ? "consuming" : "paused"}
      </Tag>
      {startedAt && (
        <span className="stream-status-item" data-test="StreamElapsed">
          {elapsed(startedAt, now)}
        </span>
      )}
      <span className="stream-status-item" data-test="StreamRate">
        <b>{rate(stream.observed_rate)}</b> /s
      </span>
      <span className="stream-status-item">{stream.describes}</span>
      {stream.sampled && (
        <Tooltip
          title={`Faster than the ceiling allows, so 1 event in ${stream.sample_rate} is kept. Counts from this stream are estimates.`}
        >
          <Tag color="orange">1 in {stream.sample_rate}</Tag>
        </Tooltip>
      )}
      {stream.watchers > 1 && <span className="stream-status-item">{stream.watchers} watching</span>}
      {/*
        Nothing has arrived yet: a state, not a fault. A quiet topic looks like
        this for its first few seconds and a topic nobody is producing to looks
        like it all day -- a red banner for either sends somebody to the broker
        to find a problem that is not there.
      */}
      {waiting && (
        <span className="stream-status-waiting" data-test="StreamWaiting">
          {note}
        </span>
      )}
      {!waiting && error && (
        <Tooltip title={error}>
          <span className="stream-status-error" data-test="StreamError">
            {error}
          </span>
        </Tooltip>
      )}
    </span>
  );
}

StreamStatus.propTypes = {
  dataSource: PropTypes.object,
  query: PropTypes.object.isRequired,
  streaming: PropTypes.bool,
  startedAt: PropTypes.number,
  note: PropTypes.string,
  error: PropTypes.string,
};

StreamStatus.defaultProps = {
  dataSource: null,
  streaming: false,
  startedAt: null,
  note: null,
  error: null,
};
