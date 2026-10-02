import { map } from "lodash";
import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import Alert from "antd/lib/alert";
import Button from "antd/lib/button";
import Select from "antd/lib/select";
import Table from "antd/lib/table";
import Tag from "antd/lib/tag";

import { axios } from "@/services/axios";
import recordEvent from "@/services/recordEvent";

import "./streams.less";

/*
  Watching a topic.

  The button says **Start streaming**, not Execute, because the two are not the
  same act. Executing runs something once; starting a stream takes a slot away
  from everybody else for as long as you have the tab open, and a button that
  did not say so would be a button people press without meaning to.

  While it runs the page checks in every ten seconds. Stop checking in -- close
  the tab, hide it, lose the network -- and the stream pauses within 45
  seconds, keeping its window so coming back resumes in seconds rather than
  from an empty chart. Ten minutes later it goes cold and the window is
  dropped.

  Nothing here is saved. The window is what the consumer has seen while
  somebody was watching, and writing it down would make a copy of a thing whose
  whole point is that it is current.
*/

const CHECK_IN_SECONDS = 10;
const REFRESH_OPTIONS = [
  { value: 2000, label: "every 2 seconds" },
  { value: 5000, label: "every 5 seconds" },
  { value: 10000, label: "every 10 seconds" },
];

function starter(table) {
  return `select *\nfrom ${table}\norder by _received_at desc\nlimit 100`;
}

export default function StreamQuery() {
  const [clusters, setClusters] = useState(null);
  const [cluster, setCluster] = useState(null);
  const [topics, setTopics] = useState([]);
  const [topic, setTopic] = useState(null);
  const [sql, setSql] = useState("");
  const [running, setRunning] = useState(false);
  const [stream, setStream] = useState(null);
  const [result, setResult] = useState(null);
  const [problem, setProblem] = useState(null);
  const [every, setEvery] = useState(2000);
  const watching = useRef(null);

  useEffect(() => {
    recordEvent("view", "page", "streams/query");
    axios
      .get("api/data_sources")
      .then((sources) => {
        const kafka = sources.filter((source) => source.streams_only);
        setClusters(kafka);
        if (kafka.length) {
          setCluster(kafka[0].id);
        }
      })
      .catch(() => setClusters([]));
  }, []);

  useEffect(() => {
    if (!cluster) {
      return;
    }
    // The enabled topics, which is what the schema browser would show: a topic
    // nobody has enabled is not queryable and offering it would be offering an
    // error.
    axios
      .get("api/streams/running")
      .then(() => {})
      .catch(() => {});
    axios
      .get(`api/data_sources/${cluster}`)
      .then((source) => {
        const tables = (source.schema || []).map((table) => table.name);
        setTopics(tables);
        if (tables.length) {
          setTopic(tables[0]);
          setSql(starter(tables[0]));
        }
      })
      .catch(() => setTopics([]));
  }, [cluster]);

  const stop = useCallback(() => {
    setRunning(false);
    if (watching.current) {
      axios.delete(`api/streams/${watching.current}/watch`).catch(() => {});
      watching.current = null;
    }
  }, []);

  // A tab that goes away without saying so is timed out in 45 seconds; saying
  // so frees the slot at once, which matters when slots are scarce.
  useEffect(() => () => stop(), [stop]);

  const start = useCallback(() => {
    setProblem(null);
    axios
      .get(`api/data_sources/${cluster}/topics`)
      .then((data) => {
        const found = (data.topics || []).find(
          (one) => one.enabled && one.name.replace(/[^a-zA-Z0-9_]/g, "_").toLowerCase() === topic
        );
        if (!found) {
          throw new Error("That topic is not enabled on this cluster any more.");
        }
        return axios.post(`api/streams/${found.stream_id}/watch`);
      })
      .then((started) => {
        watching.current = started.id;
        setStream(started);
        setRunning(true);
      })
      .catch((error) => setProblem((error && error.message) || "Could not start that stream."));
  }, [cluster, topic]);

  // The check-in, and the refresh, on their own clocks: one says "somebody is
  // still here" and the other asks what the window says now.
  useEffect(() => {
    if (!running || !watching.current) {
      return undefined;
    }
    const beat = setInterval(() => {
      axios
        .post(`api/streams/${watching.current}/watch`)
        .then(setStream)
        .catch(() => {
          setProblem("The stream stopped. Start it again when you are ready.");
          setRunning(false);
        });
    }, CHECK_IN_SECONDS * 1000);
    return () => clearInterval(beat);
  }, [running]);

  useEffect(() => {
    if (!running) {
      return undefined;
    }
    let live = true;
    const ask = () => {
      axios
        .post(`api/data_sources/${cluster}/stream_query`, { query: sql })
        .then((data) => live && setResult(data))
        .catch((error) => live && setProblem((error && error.message) || "That query did not run."));
    };
    ask();
    const timer = setInterval(ask, every);
    return () => {
      live = false;
      clearInterval(timer);
    };
  }, [running, cluster, sql, every]);

  const columns = useMemo(
    () =>
      map((result && result.columns) || [], (column) => ({
        title: column.name,
        dataIndex: column.name,
        key: column.name,
        render: (value) => (value === null || value === undefined ? "" : String(value)),
      })),
    [result]
  );

  return (
    <div className="container streams-page" data-test="StreamQuery">
      <div className="streams-header">
        <h2>Query a stream</h2>
        <p className="streams-muted">
          The last few minutes of a topic, as a table. It consumes while you are watching and pauses when you are not;
          nothing here is saved.
        </p>
      </div>

      {clusters && clusters.length === 0 && (
        <Alert
          type="info"
          showIcon
          message="No Kafka clusters yet."
          description="An administrator adds one under Data Sources; somebody with the streams permission then chooses which topics can be queried."
        />
      )}

      {clusters && clusters.length > 0 && (
        <React.Fragment>
          <div className="m-b-10">
            <Select
              value={cluster}
              onChange={setCluster}
              style={{ minWidth: 200 }}
              disabled={running}
              data-test="ChooseCluster"
              options={clusters.map((one) => ({ value: one.id, label: one.name }))}
            />
            <Select
              value={topic}
              onChange={(value) => {
                setTopic(value);
                setSql(starter(value));
              }}
              style={{ minWidth: 200 }}
              className="m-l-10"
              disabled={running || !topics.length}
              data-test="ChooseTopic"
              options={topics.map((one) => ({ value: one, label: one }))}
            />
            <Select
              value={every}
              onChange={setEvery}
              className="m-l-10"
              style={{ minWidth: 160 }}
              options={REFRESH_OPTIONS}
            />
            {running ? (
              <Button danger className="m-l-10" onClick={stop} data-test="StopStreaming">
                Stop
              </Button>
            ) : (
              <Button type="primary" className="m-l-10" onClick={start} disabled={!topic} data-test="StartStreaming">
                Start streaming
              </Button>
            )}
          </div>

          {topics.length === 0 && (
            <Alert
              type="info"
              showIcon
              className="m-b-10"
              message="No topics are enabled on this cluster."
              description="Somebody with the streams permission chooses them under Manage topics."
            />
          )}

          {problem && <Alert type="warning" showIcon message={problem} className="m-b-10" />}

          {running && stream && (
            <div className="streams-slots" data-test="StreamStats">
              <span>
                <Tag color="green">consuming</Tag>
              </span>
              <div>
                <strong className="streams-rate">{stream.observed_rate || 0}</strong>{" "}
                <span className="streams-muted">events a second</span>
                <span className="streams-muted"> &middot; {stream.describes}</span>
                {stream.sampled && (
                  <Tag color="orange" className="m-l-5">
                    1 in {stream.sample_rate} kept
                  </Tag>
                )}
                {stream.watchers > 1 && (
                  <span className="streams-muted"> &middot; {stream.watchers} people watching</span>
                )}
              </div>
            </div>
          )}

          <textarea
            className="form-control"
            rows={4}
            value={sql}
            onChange={(event) => setSql(event.target.value)}
            data-test="StreamSql"
          />

          {result && (
            <Table
              className="streams-table m-t-10"
              dataSource={(result.rows || []).map((row, index) => ({ ...row, __key: index }))}
              columns={columns}
              rowKey="__key"
              size="small"
              pagination={{ pageSize: 25, hideOnSinglePage: true }}
            />
          )}
        </React.Fragment>
      )}
    </div>
  );
}
