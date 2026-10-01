import React, { useCallback, useEffect, useState } from "react";
import Alert from "antd/lib/alert";
import Button from "antd/lib/button";
import Progress from "antd/lib/progress";
import Table from "antd/lib/table";
import Tag from "antd/lib/tag";

import Layout from "@/components/admin/Layout";
import TimeAgo from "@/components/TimeAgo";
import Tooltip from "@/components/Tooltip";
import { axios } from "@/services/axios";
import notification from "@/services/notification";
import recordEvent from "@/services/recordEvent";

import "./storage.less";

/*
  What SQLDesk is holding, and what happens to it when.

  None of this was visible anywhere. On 28 September the development disk
  reached 100% and took Postgres down with it, and the only way to find out why
  was to look at the filesystem -- which is exactly the position a product that
  stores files for people should not put anybody in.

  Two sections, because the policies are genuinely different and showing them
  as one number is how somebody ends up afraid to delete a cached result. A
  query result belongs to the warehouse and losing it costs a re-query. An
  uploaded file is the only copy there is.
*/

function readable(bytes) {
  if (!bytes) {
    return "0 bytes";
  }
  const units = [
    ["GB", 1024 ** 3],
    ["MB", 1024 ** 2],
    ["KB", 1024],
  ];
  for (const [unit, size] of units) {
    if (bytes >= size) {
      const value = bytes / size;
      return `${value < 10 ? value.toFixed(1) : Math.round(value)} ${unit}`;
    }
  }
  return `${bytes} bytes`;
}

function UploadsHeader({ uploads }) {
  const used = uploads.quota_bytes ? Math.round((uploads.bytes / uploads.quota_bytes) * 100) : null;
  return (
    <div className="storage-summary">
      <div>
        <h3 className="m-t-0">Uploaded files</h3>
        <p className="storage-muted">
          {uploads.files} {uploads.files === 1 ? "file" : "files"}, {readable(uploads.bytes)}
          {uploads.quota_bytes ? ` of ${readable(uploads.quota_bytes)}` : " — no limit set"}.{" "}
          {/* The policy, in words, because a countdown with no stated rule reads as arbitrary. */}
          {uploads.lifetime_days > 0 ? (
            <span>
              Each expires {uploads.lifetime_days} days after it is uploaded, and its uploader is mailed the day before
              with a button that keeps it.
            </span>
          ) : (
            <span>Nothing expires on this install.</span>
          )}
        </p>
      </div>
      {used !== null && (
        <div className="storage-gauge">
          {/* A bar, because "about to run out" should be visible without reading a number. */}
          <Progress
            type="dashboard"
            width={110}
            percent={Math.min(100, used)}
            status={used >= 90 ? "exception" : "normal"}
            format={() => `${used}%`}
          />
        </div>
      )}
    </div>
  );
}

function FilesTable({ files, onChanged }) {
  const keep = useCallback(
    (file, keeping) => {
      const url = `api/data_sources/${file.data_source_id}/uploads/${file.id}/keep`;
      const request = keeping ? axios.post(url) : axios.delete(url);
      request
        .then(() => {
          notification.success(
            keeping ? `${file.filename} will not expire.` : `${file.filename} is back on the clock.`
          );
          onChanged();
        })
        .catch((error) => {
          const message =
            error && error.response && error.response.data && error.response.data.message
              ? error.response.data.message
              : "Could not save that.";
          notification.error(message);
        });
    },
    [onChanged]
  );

  const columns = [
    {
      title: "File",
      dataIndex: "filename",
      render: (filename, row) => (
        <span>
          <strong>{row.display_name || filename}</strong>
          <div className="storage-muted">
            queried as <code>{row.view_name}</code>
            {row.unloaded && (
              <Tooltip title="Not registered with DuckDB at the moment, because nothing has queried it for a few days. The file is untouched and the next query that names it brings it back.">
                <Tag className="m-l-5">unloaded</Tag>
              </Tooltip>
            )}
          </div>
        </span>
      ),
    },
    { title: "Size", dataIndex: "size", width: 100, align: "right", render: (size) => readable(size) },
    {
      title: "Last queried",
      dataIndex: "last_queried_at",
      width: 150,
      // The one column that says which files are worth removing, and the one
      // nothing in the product showed before.
      render: (at) => (at ? <TimeAgo date={at} /> : <span className="storage-muted">never</span>),
    },
    {
      title: "Expires",
      dataIndex: "expires_at",
      width: 230,
      align: "right",
      render: (expiresAt, row) =>
        row.kept ? (
          <span className="storage-review">
            <Tooltip title={row.kept_by ? `Kept by ${row.kept_by}.` : "Kept."}>
              <Tag color="green">kept</Tag>
            </Tooltip>
            <Button size="small" onClick={() => keep(row, false)}>
              Let it expire
            </Button>
          </span>
        ) : (
          <span className="storage-review">
            <Tag color={row.expires_in_days <= 1 ? "red" : null}>
              {row.expires_in_days === 0
                ? "today"
                : `in ${row.expires_in_days} ${row.expires_in_days === 1 ? "day" : "days"}`}
            </Tag>
            <Button size="small" onClick={() => keep(row, true)}>
              Keep
            </Button>
          </span>
        ),
    },
  ];

  return <Table dataSource={files} columns={columns} rowKey="id" size="small" pagination={{ pageSize: 10 }} />;
}

export default function Storage() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const load = useCallback(() => {
    setLoading(true);
    axios
      .get("api/admin/storage")
      .then((response) => {
        setData(response);
        setError(null);
      })
      .catch(() => setError("Could not read what is stored."))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    recordEvent("view", "page", "admin/storage");
    load();
  }, [load]);

  const uploads = data && data.uploads;
  const nearlyFull = uploads && uploads.quota_bytes && uploads.bytes / uploads.quota_bytes >= 0.9;

  return (
    <Layout activeTab="storage">
      <div className="p-15 storage-page">
        {error && <Alert type="error" showIcon message={error} className="m-b-15" />}

        {nearlyFull && (
          <Alert
            className="m-b-15"
            type="warning"
            showIcon
            message="The uploads are nearly at their limit"
            description="New uploads will be refused once they would take it past. Removing files nothing has queried is almost always the answer; the Last queried column says which those are."
          />
        )}

        {uploads && <UploadsHeader uploads={uploads} />}

        {uploads &&
          uploads.by_data_source.map((source) => (
            <div key={source.data_source_id} className="storage-source">
              <h4>
                {source.data_source_name}{" "}
                <span className="storage-muted">
                  — {source.files} {source.files === 1 ? "file" : "files"}, {readable(source.bytes)}
                </span>
              </h4>
              <FilesTable files={source.uploads} onChanged={load} />
            </div>
          ))}

        {uploads && uploads.files === 0 && <div className="storage-empty">Nothing has been uploaded.</div>}

        {data && (
          <div className="storage-source">
            <h3>Query results</h3>
            <p className="storage-muted">
              {/* Said explicitly, because the whole point of the split is that
                  these can go and the uploads cannot. */}
              Answers borrowed from your warehouses. Losing one costs a re-query, so unused results are deleted after
              seven days without anybody being asked.
            </p>
            <Table
              dataSource={data.results.map(([name, bytes]) => ({ name, bytes }))}
              columns={[
                { title: "", dataIndex: "name" },
                { title: "Size", dataIndex: "bytes", width: 120, align: "right", render: (b) => readable(b) },
              ]}
              rowKey="name"
              size="small"
              pagination={false}
            />
          </div>
        )}

        <div className="m-t-15">
          <Button size="small" onClick={load} loading={loading}>
            Refresh
          </Button>
        </div>
      </div>
    </Layout>
  );
}
