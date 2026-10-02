import React, { useCallback, useEffect, useMemo, useState } from "react";
import Alert from "antd/lib/alert";
import Button from "antd/lib/button";
import Input from "antd/lib/input";
import Select from "antd/lib/select";
import Table from "antd/lib/table";
import Tag from "antd/lib/tag";

import { axios } from "@/services/axios";
import notification from "@/services/notification";
import recordEvent from "@/services/recordEvent";

import "./streams.less";

/*
  Choosing which of a cluster's topics can be queried.

  This is the access decision on a Kafka cluster: the data source permission is
  per cluster, so whatever is enabled here is what everybody with access to
  that cluster can then query. Hence its own permission, and hence a page
  rather than a field on the data source -- an administrator registers the
  cluster, somebody who knows the data decides what is worth keeping.

  **Analyse before enabling.** The three things nobody can guess from a topic's
  name are what the messages contain, how fast they arrive, and what that means
  for how much history a window will hold. Enabling one blind and finding out
  an hour later that it is unparseable, or so fast that everything is sampled,
  is the afternoon this page exists to prevent.
*/

function seconds(value) {
  if (!value) {
    return "—";
  }
  if (value < 120) {
    return `${Math.round(value)} seconds`;
  }
  return `${Math.round(value / 60)} minutes`;
}

function Figure({ label, children }) {
  return (
    <span className="streams-figure">
      <strong>{children}</strong>
      <span className="streams-muted">{label}</span>
    </span>
  );
}

function Analysis({ found, onEnable, saving }) {
  return (
    <div className="streams-analysis" data-test="TopicAnalysis">
      <Figure label="messages read">{found.read}</Figure>
      <Figure label="could not be parsed">{found.malformed}</Figure>
      <Figure label="events a second">
        <span className="streams-rate">{found.events_per_second}</span>
      </Figure>
      <Figure label="of history that buys">{seconds(found.window_seconds)}</Figure>

      {found.malformed > 0 && (
        <Alert
          className="m-t-10"
          type="warning"
          showIcon
          message={`${found.malformed} of ${found.read} messages could not be read as JSON objects.`}
          description="Those are not stored and not counted. A schema inferred from the rest may be missing fields that only appear in them."
        />
      )}

      {found.sampled && (
        <Alert
          className="m-t-10"
          type="warning"
          showIcon
          message={`Faster than the ceiling, so 1 event in ${found.sample_rate} would be kept.`}
          description="Counts from a sampled stream are estimates, and every chart drawn from one says so. Raise the events-a-second ceiling if you need all of them."
        />
      )}

      <div className="m-t-10">
        <strong>Columns</strong>
        {found.columns.length === 0 ? (
          <p className="streams-muted">
            Nothing could be read from this topic. It may be empty, or it may not be JSON.
          </p>
        ) : (
          <p className="streams-muted">
            {found.columns.map((column) => (
              <Tag key={column.name}>
                {column.name} <span className="streams-muted">{column.type}</span>
              </Tag>
            ))}
          </p>
        )}
      </div>

      <Button type="primary" onClick={onEnable} loading={saving} data-test="EnableTopic">
        Enable this topic
      </Button>
    </div>
  );
}

export default function ManageTopics() {
  const [clusters, setClusters] = useState(null);
  const [chosen, setChosen] = useState(null);
  const [topics, setTopics] = useState(null);
  const [problem, setProblem] = useState(null);
  const [loading, setLoading] = useState(false);
  const [filter, setFilter] = useState("");
  const [analysing, setAnalysing] = useState(null);
  const [analysis, setAnalysis] = useState({});
  const [saving, setSaving] = useState(null);

  useEffect(() => {
    recordEvent("view", "page", "streams/topics");
    axios
      .get("api/data_sources")
      .then((sources) => {
        const kafka = sources.filter((source) => source.streams_only);
        setClusters(kafka);
        if (kafka.length) {
          setChosen(kafka[0].id);
        }
      })
      .catch(() => setClusters([]));
  }, []);

  const load = useCallback((clusterId) => {
    setLoading(true);
    setProblem(null);
    axios
      .get(`api/data_sources/${clusterId}/topics`)
      .then((data) => setTopics(data.topics))
      .catch((error) => {
        setTopics([]);
        setProblem((error && error.message) || "Could not ask the cluster what topics it has.");
      })
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    if (chosen) {
      load(chosen);
    }
  }, [chosen, load]);

  const analyse = useCallback(
    (topic) => {
      setAnalysing(topic);
      axios
        .post(`api/data_sources/${chosen}/topics/${encodeURIComponent(topic)}/analyse`)
        .then((found) => setAnalysis((all) => ({ ...all, [topic]: found })))
        .catch((error) => notification.error("Could not read that topic", (error && error.message) || ""))
        .finally(() => setAnalysing(null));
    },
    [chosen]
  );

  const enable = useCallback(
    (topic, body) => {
      setSaving(topic);
      axios
        .post(`api/data_sources/${chosen}/topics/${encodeURIComponent(topic)}`, body || {})
        .then(() => {
          notification.success(`${topic} can now be queried.`);
          load(chosen);
        })
        .catch((error) => notification.error("Could not enable that topic", (error && error.message) || ""))
        .finally(() => setSaving(null));
    },
    [chosen, load]
  );

  const disable = useCallback(
    (topic) => {
      setSaving(topic);
      axios
        .delete(`api/data_sources/${chosen}/topics/${encodeURIComponent(topic)}`)
        .then(() => {
          notification.success(`${topic} can no longer be queried, and its window is gone.`);
          load(chosen);
        })
        .catch(() => notification.error("Could not turn that topic off"))
        .finally(() => setSaving(null));
    },
    [chosen, load]
  );

  const shown = useMemo(
    () => (topics || []).filter((topic) => topic.name.toLowerCase().includes(filter.toLowerCase())),
    [topics, filter]
  );

  const columns = [
    {
      title: "Topic",
      dataIndex: "name",
      render: (name, row) => (
        <span>
          <strong>{name}</strong>
          <div className="streams-muted">
            {row.partitions} partition{row.partitions === 1 ? "" : "s"}
            {row.problem && <span className="streams-error"> &middot; {row.problem}</span>}
          </div>
        </span>
      ),
    },
    {
      title: "",
      dataIndex: "enabled",
      width: 120,
      render: (enabled, row) =>
        enabled ? (
          <span>
            <Tag color="green">enabled</Tag>
            {row.columns > 0 && <div className="streams-muted">{row.columns} columns</div>}
          </span>
        ) : null,
    },
    {
      title: "",
      width: 220,
      align: "right",
      render: (_, row) => (
        <span>
          <Button
            size="small"
            loading={analysing === row.name}
            onClick={() => analyse(row.name)}
            data-test="AnalyseTopic"
          >
            Analyse
          </Button>
          {row.enabled ? (
            <Button
              size="small"
              danger
              className="m-l-5"
              loading={saving === row.name}
              onClick={() => disable(row.name)}
            >
              Turn off
            </Button>
          ) : (
            <Button
              size="small"
              type="primary"
              className="m-l-5"
              loading={saving === row.name}
              onClick={() => enable(row.name)}
            >
              Enable
            </Button>
          )}
        </span>
      ),
    },
  ];

  return (
    <div className="container streams-page" data-test="ManageTopics">
      <div className="streams-header">
        <h2>Manage topics</h2>
        <p className="streams-muted">
          What a cluster carries, and which of it can be queried. Everybody with access to the cluster can query what is
          enabled here, so this is the decision that matters.
        </p>
      </div>

      {clusters && clusters.length === 0 && (
        <Alert
          type="info"
          showIcon
          message="No Kafka clusters yet."
          description="An administrator adds one under Data Sources, with the brokers and whatever the cluster needs to let us in. Topics are chosen here afterwards."
        />
      )}

      {clusters && clusters.length > 0 && (
        <React.Fragment>
          <div className="m-b-15">
            <Select
              value={chosen}
              onChange={setChosen}
              style={{ minWidth: 240 }}
              data-test="ChooseCluster"
              options={clusters.map((cluster) => ({ value: cluster.id, label: cluster.name }))}
            />
            <Input.Search
              placeholder="Find a topic"
              className="m-l-10"
              style={{ maxWidth: 260 }}
              allowClear
              onChange={(event) => setFilter(event.target.value)}
            />
          </div>

          {problem && <Alert type="warning" showIcon message={problem} className="m-b-15" />}

          <Table
            className="streams-table"
            dataSource={shown}
            columns={columns}
            rowKey="name"
            size="small"
            loading={loading}
            pagination={{ pageSize: 20, hideOnSinglePage: true }}
            expandable={{
              expandedRowKeys: Object.keys(analysis),
              expandedRowRender: (row) =>
                analysis[row.name] ? (
                  <Analysis found={analysis[row.name]} saving={saving === row.name} onEnable={() => enable(row.name)} />
                ) : null,
              rowExpandable: (row) => !!analysis[row.name],
            }}
          />
        </React.Fragment>
      )}
    </div>
  );
}
