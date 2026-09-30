import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import Alert from "antd/lib/alert";
import Button from "antd/lib/button";
import Input from "antd/lib/input";
import Select from "antd/lib/select";
import Switch from "antd/lib/switch";
import Table from "antd/lib/table";
import Tabs from "antd/lib/tabs";
import Tag from "antd/lib/tag";

import HelpTrigger from "@/components/HelpTrigger";
import TimeAgo from "@/components/TimeAgo";
import Tooltip from "@/components/Tooltip";
import { axios } from "@/services/axios";
import notification from "@/services/notification";

import "./catalog.less";

/*
  Reviewing what the MCP tools will say about your warehouse.

  Sorted by usage and filtered to the undescribed, because the job is
  otherwise impossible: nobody writes three thousand sentences, and the
  twenty tables anyone actually queries are most of the value. The point of
  the page is to make the work finite.
*/

function DescriptionCell({ table, onSaved }) {
  const [value, setValue] = useState(table.description || "");
  const [saving, setSaving] = useState(false);
  const dirty = value !== (table.description || "");

  const save = useCallback(() => {
    setSaving(true);
    axios
      .post(`/api/catalog/tables/${table.id}`, { description: value })
      .then((saved) => {
        onSaved(table.id, saved);
        notification.success(`Described ${table.name}.`);
      })
      .catch(() => notification.error("Could not save that."))
      .finally(() => setSaving(false));
  }, [table.id, table.name, value, onSaved]);

  return (
    <div className="catalog-describe">
      <Input.TextArea
        rows={2}
        value={value}
        placeholder="What is this table for? What is a row? What should nobody trust?"
        onChange={(event) => setValue(event.target.value)}
      />
      <div className="catalog-describe-actions">
        {/* Where the sentence came from, because it decides what happens to
            it next: a harvest may replace the engine's, never a person's. */}
        {table.description_source === "human" && <Tag>yours</Tag>}
        {table.description_source === "engine" && <Tag color="blue">from the warehouse</Tag>}
        <Button size="small" type="primary" disabled={!dirty} loading={saving} onClick={save}>
          Save
        </Button>
      </div>
    </div>
  );
}

//: What each state is called where somebody reads it, rather than in the
//: database. "Denied" is a decision, not an error, so it is not red.
const SAID = { proposed: "back on the list", approved: "agreed", denied: "denied" };

function Measures({ sourceId }) {
  const [measures, setMeasures] = useState([]);
  const [pending, setPending] = useState(true);
  const [loading, setLoading] = useState(true);

  const load = useCallback(() => {
    setLoading(true);
    const params = [];
    if (sourceId) {
      params.push(`data_source_id=${sourceId}`);
    }
    if (pending) {
      params.push("pending=1");
    }
    axios
      .get(`/api/catalog/measures${params.length ? `?${params.join("&")}` : ""}`)
      .then((data) => setMeasures(data.measures))
      .catch(() => notification.error("Could not load the measures."))
      .finally(() => setLoading(false));
  }, [sourceId, pending]);

  useEffect(() => {
    load();
  }, [load]);

  const review = useCallback((measure, status) => {
    axios
      .post(`/api/catalog/measures/${measure.id}`, { status })
      .then((saved) => {
        setMeasures((current) => current.map((m) => (m.id === saved.id ? { ...m, ...saved } : m)));
        notification.success(`${measure.name} ${SAID[saved.status]}.`);
      })
      .catch(() => notification.error("Could not save that."));
  }, []);

  const columns = [
    {
      title: "Table",
      dataIndex: "table_name",
      width: 200,
      render: (name) => <span className="catalog-name">{name}</span>,
    },
    {
      title: "Definition",
      dataIndex: "name",
      render: (name, row) => (
        <span className="catalog-name">
          {name} = {(row.kind || "").toUpperCase()}({row.column_name})
        </span>
      ),
    },
    {
      title: "Written in",
      dataIndex: "usage_count",
      width: 130,
      align: "right",
      // Four teams writing the same definition independently is a different
      // proposition from one person trying it once.
      render: (count) => (count ? `${count} queries` : <span className="catalog-muted">—</span>),
    },
    {
      title: "",
      dataIndex: "status",
      width: 210,
      align: "right",
      // Three states, because "nobody has looked at this" and "we looked and
      // it is wrong" are different answers -- and only one of them should
      // keep coming back on the worklist.
      render: (status, row) => {
        if (status === "proposed") {
          return (
            <span className="catalog-review">
              <Button size="small" type="primary" onClick={() => review(row, "approved")}>
                Agree
              </Button>
              <Button size="small" danger onClick={() => review(row, "denied")}>
                Deny
              </Button>
            </span>
          );
        }
        return (
          <span className="catalog-review">
            <Tag color={status === "approved" ? "green" : null}>{SAID[status]}</Tag>
            <Button size="small" onClick={() => review(row, "proposed")}>
              Undo
            </Button>
          </span>
        );
      },
    },
  ];

  return (
    <div>
      <p className="catalog-muted">
        <HelpTrigger type="MCP_MEASURES" /> Numbers people already compute, found in saved SQL. Nothing here reaches a
        model until you agree it &mdash; a definition that is merely plausible is worse than none, because the wrong
        revenue figure is still a revenue figure.
      </p>
      <div className="catalog-controls">
        <span className="catalog-toggle">
          <Switch
            size="small"
            checked={pending}
            onChange={setPending}
            aria-label="Show only measures nobody has decided on"
          />{" "}
          Only ones nobody has decided on
        </span>
        <Button size="small" onClick={load} loading={loading}>
          Refresh
        </Button>
      </div>
      <Table
        dataSource={measures}
        columns={columns}
        rowKey="id"
        size="small"
        loading={loading}
        pagination={{ pageSize: 20, showSizeChanger: false }}
      />
    </div>
  );
}

/*
  Harvesting now rather than at the next scheduled run: for a data source
  added this morning, or a schema that changed an hour ago.

  "Only what has not been harvested" is the default, because it is the cheap
  answer to the common case: a source with nothing in the catalog yet, filled
  without re-reading every other one. Each source is its own job on the
  worker, so the page asks the server what is still waiting rather than
  guessing, and stops asking once nothing is.
*/
function plural(count, word) {
  return `${count} ${word}${count === 1 ? "" : "s"}`;
}

function useHarvest(onFinished) {
  const [sources, setSources] = useState([]);
  const [busy, setBusy] = useState(false);

  const loadSources = useCallback(
    () =>
      axios
        .get("/api/catalog/sources")
        .then((data) => setSources(data.sources))
        .catch(() => {}),
    []
  );

  useEffect(() => {
    loadSources();
  }, [loadSources]);

  const inFlight = sources.some((source) => source.state);

  useEffect(() => {
    if (!inFlight) {
      return undefined;
    }
    const timer = setInterval(loadSources, 3000);
    return () => clearInterval(timer);
  }, [inFlight, loadSources]);

  // The moment the last harvest in flight finishes, the tables it wrote are
  // worth showing -- without anybody pressing Refresh to find out.
  const wasInFlight = useRef(false);
  useEffect(() => {
    if (wasInFlight.current && !inFlight) {
      notification.success("Harvest finished.");
      onFinished();
    }
    wasInFlight.current = inFlight;
  }, [inFlight, onFinished]);

  const harvest = useCallback(
    (body) => {
      setBusy(true);
      return axios
        .post("/api/catalog/harvest", body)
        .then(({ queued, skipped }) => {
          if (queued.length) {
            notification.success(`Harvesting ${plural(queued.length, "data source")}.`);
          }
          if (skipped.length) {
            notification.info(
              "Not harvested",
              skipped.map((source) => `${source.name}: ${source.reason}`).join(". ") + "."
            );
          }
          if (!queued.length && !skipped.length) {
            notification.info("Every data source is already in the catalog.");
          }
          return loadSources();
        })
        .catch(() => notification.error("Could not start the harvest."))
        .finally(() => setBusy(false));
    },
    [loadSources]
  );

  // Not harvested: nothing in the catalog, not paused, and not already on its way.
  const unharvested = sources.filter((source) => !source.tables && !source.paused && !source.state);

  return { sources, busy, inFlight, unharvested, harvest };
}

function HarvestButton({ harvesting, sourceId }) {
  const { sources, busy, unharvested, harvest } = harvesting;

  if (sourceId) {
    const source = sources.find((candidate) => candidate.id === sourceId);
    return (
      <Button
        size="small"
        type="primary"
        loading={busy}
        disabled={!source || source.paused || !!source.state}
        onClick={() => harvest({ data_source_id: sourceId })}
      >
        {source && source.state ? "Harvesting…" : `Harvest ${source ? source.name : "this data source"}`}
      </Button>
    );
  }

  const button = (
    <Button
      size="small"
      type="primary"
      loading={busy}
      disabled={!unharvested.length}
      onClick={() => harvest({ only: "unharvested" })}
    >
      {unharvested.length ? `Harvest ${plural(unharvested.length, "new data source")}` : "Harvest new data sources"}
    </Button>
  );
  if (unharvested.length) {
    return button;
  }
  return (
    <Tooltip title="Every data source is in the catalog already. Pick one to harvest it again, or use the Data sources tab.">
      {/* A disabled button swallows the hover its tooltip needs. */}
      <span className="catalog-harvest-disabled">{button}</span>
    </Tooltip>
  );
}

function Sources({ harvesting }) {
  const { sources, busy, harvest } = harvesting;

  const columns = [
    {
      title: "Data source",
      dataIndex: "name",
      render: (name, row) => (
        <div>
          <div>{name}</div>
          <div className="catalog-muted">{row.type}</div>
        </div>
      ),
    },
    {
      title: "In the catalog",
      dataIndex: "tables",
      width: 150,
      align: "right",
      render: (tables) => (tables ? plural(tables, "table") : <span className="catalog-muted">not harvested</span>),
    },
    {
      title: "Last harvested",
      dataIndex: "harvested_at",
      width: 170,
      render: (when) => (when ? <TimeAgo date={when} /> : <span className="catalog-muted">—</span>),
    },
    {
      title: "",
      dataIndex: "state",
      width: 140,
      align: "right",
      render: (state, row) => {
        if (state === "running") {
          return <Tag color="blue">Harvesting…</Tag>;
        }
        if (state === "queued") {
          return <Tag>Waiting</Tag>;
        }
        if (row.paused) {
          return <Tag>Paused</Tag>;
        }
        return (
          <Button size="small" onClick={() => harvest({ data_source_id: row.id })}>
            Harvest
          </Button>
        );
      },
    },
  ];

  return (
    <div>
      <p className="catalog-muted">
        Harvesting reads each data source&apos;s schema and the saved SQL that ran against it recently. It happens on a
        schedule; harvest here when you would rather not wait. It never touches a description somebody wrote.
      </p>
      <div className="catalog-controls">
        <Button size="small" loading={busy} onClick={() => harvest({})}>
          Harvest every data source again
        </Button>
      </div>
      <Table dataSource={sources} columns={columns} rowKey="id" size="small" pagination={false} />
    </div>
  );
}

export default function Catalog() {
  const [tables, setTables] = useState([]);
  const [sources, setSources] = useState([]);
  const [sourceId, setSourceId] = useState(null);
  const [undescribed, setUndescribed] = useState(false);
  const [loading, setLoading] = useState(true);

  const load = useCallback(() => {
    setLoading(true);
    const params = [];
    if (sourceId) {
      params.push(`data_source_id=${sourceId}`);
    }
    if (undescribed) {
      params.push("undescribed=1");
    }
    axios
      .get(`/api/catalog${params.length ? `?${params.join("&")}` : ""}`)
      .then((data) => setTables(data.tables))
      .catch(() => notification.error("Could not load the catalog."))
      .finally(() => setLoading(false));
  }, [sourceId, undescribed]);

  useEffect(() => {
    load();
  }, [load]);

  useEffect(() => {
    axios
      .get("api/data_sources")
      .then(setSources)
      .catch(() => {});
  }, []);

  const onSaved = useCallback((id, saved) => {
    setTables((current) =>
      current.map((table) =>
        table.id === id
          ? { ...table, description: saved.description, description_source: saved.description_source }
          : table
      )
    );
  }, []);

  const missing = useMemo(() => tables.filter((table) => !table.description).length, [tables]);
  const harvesting = useHarvest(load);

  const columns = [
    {
      title: "Table",
      dataIndex: "name",
      width: 260,
      render: (name, row) => (
        <div>
          <div className="catalog-name">{name}</div>
          <div className="catalog-muted">{row.column_count} columns</div>
        </div>
      ),
    },
    {
      title: "Used by",
      dataIndex: "usage_count",
      width: 110,
      align: "right",
      // The ranking signal, and worth showing rather than only sorting by:
      // it is the answer to "is this worth my time to describe".
      render: (count) => (count ? `${count} queries` : <span className="catalog-muted">—</span>),
    },
    {
      title: "What it is for",
      dataIndex: "description",
      render: (_, row) => <DescriptionCell table={row} onSaved={onSaved} />,
    },
  ];

  return (
    <React.Fragment>
      <div className="p-15 catalog-page" data-test="AdminCatalog">
        <div className="catalog-header">
          <h3>
            Catalog <HelpTrigger type="MCP_CATALOG" />
          </h3>
          <p className="catalog-muted">
            What the MCP tools know about your warehouse. Structure and usage are harvested; what a table is{" "}
            <em>for</em> is the part only a person can write, and{" "}
            <HelpTrigger type="MCP_SEMANTIC" showTooltip={false} renderAsLink>
              kept in git
            </HelpTrigger>{" "}
            if you would rather review it as a pull request &mdash; download the YAML here, or write it straight into a
            checkout with <code>manage ai export</code>.
          </p>
        </div>

        <div className="catalog-controls">
          <Select
            allowClear
            className="catalog-source"
            placeholder="Every data source"
            value={sourceId}
            onChange={setSourceId}
            options={sources.map((source) => ({ value: source.id, label: source.name }))}
          />
          <span className="catalog-toggle">
            <Switch
              size="small"
              checked={undescribed}
              onChange={setUndescribed}
              aria-label="Show only tables with no description"
            />{" "}
            Only ones still missing a description
          </span>
          <Button size="small" onClick={load} loading={loading}>
            Refresh
          </Button>
          <HarvestButton harvesting={harvesting} sourceId={sourceId} />
          {/*
            A plain link rather than a fetch: the browser handles the file,
            the session cookie authenticates it, and nothing has to hold the
            zip in memory to hand it straight back. Absolute, like every
            /api/admin/ path in the admin pages: those routes are registered
            at the root only, not per organization. (The data source list
            this page loads is per organization, so that one is relative.)

            `download` is load-bearing, not decoration. The app puts a click
            handler on the whole body and turns any anchor into a client-side
            route -- so without it the router swallowed this click, pushed
            /<org>/api/catalog/export, and drew its own "page cannot be
            found" over a download that had in fact already succeeded.
            handleNavigationIntent skips anchors carrying it.
          */}
          <a
            download
            className="catalog-download"
            href={`/api/catalog/export${sourceId ? `?data_source_id=${sourceId}` : ""}`}
          >
            <Button size="small">Download YAML</Button>
          </a>
        </div>

        <Tabs defaultActiveKey="tables" className="catalog-tabs">
          <Tabs.TabPane tab="Tables" key="tables">
            {!loading && tables.length === 0 && (
              <Alert
                type="info"
                showIcon
                message={harvesting.inFlight ? "Harvesting" : "Nothing harvested yet"}
                description={
                  harvesting.inFlight
                    ? "The tables appear here as soon as it finishes."
                    : "The catalog fills on a schedule. Harvest now to fill it straight away."
                }
                action={
                  !harvesting.inFlight && (
                    <Button
                      size="small"
                      type="primary"
                      loading={harvesting.busy}
                      onClick={() => harvesting.harvest({ only: "unharvested" })}
                    >
                      Harvest now
                    </Button>
                  )
                }
              />
            )}

            {tables.length > 0 && missing > 0 && !undescribed && (
              <p className="catalog-muted catalog-count">
                {missing} of these {tables.length} have no description.
              </p>
            )}

            <Table
              className="catalog-table"
              dataSource={tables}
              columns={columns}
              rowKey="id"
              size="small"
              loading={loading}
              pagination={{ pageSize: 20, showSizeChanger: false }}
            />
          </Tabs.TabPane>
          <Tabs.TabPane tab="Measures" key="measures">
            <Measures sourceId={sourceId} />
          </Tabs.TabPane>
          <Tabs.TabPane tab="Data sources" key="sources">
            <Sources harvesting={harvesting} />
          </Tabs.TabPane>
        </Tabs>
      </div>
    </React.Fragment>
  );
}
