import React, { useCallback, useEffect, useState } from "react";
import PropTypes from "prop-types";
import Alert from "antd/lib/alert";
import Button from "antd/lib/button";
import Table from "antd/lib/table";
import Tag from "antd/lib/tag";

import HelpTrigger from "@/components/HelpTrigger";
import InputWithCopy from "@/components/InputWithCopy";
import Link from "@/components/Link";
import TimeAgo from "@/components/TimeAgo";
import { axios } from "@/services/axios";
import { clientConfig } from "@/services/auth";
import recordEvent from "@/services/recordEvent";

import "./mcp.less";

/*
  My MCP: how to connect a client, and what mine has been doing.

  Not the admin audit with a filter on it. The audit names every user, every
  question and every address, and that is the whole point of it; this names
  nobody else and carries no question, no SQL and no arguments — only which
  tool was called, when, whether it worked and how long it took. The endpoint
  behind it cannot be asked about another user at all, which is a stronger
  statement than a page that merely does not ask.

  Before a first call it shows only how to connect: a table of nothing, under a
  heading about activity, reads as something being broken.
*/

const OUTCOME = {
  ok: { colour: null, label: "ok" },
  error: { colour: "red", label: "error" },
  refused: { colour: "orange", label: "refused" },
  ignored: { colour: null, label: "acknowledged" },
};

function HowToConnect({ origin }) {
  return (
    <div className="mcp-panel">
      <h3>
        Connecting your client <HelpTrigger type="MCP_CONNECT" />
      </h3>
      {clientConfig.mcpOAuthEnabled ? (
        <React.Fragment>
          <p className="mcp-muted">
            Add the endpoint and your client will open a browser. You sign in the way you always do, and it gets a token
            that expires and that you can disconnect from your profile — nothing to paste, and nothing living in a
            config file.
          </p>
          <InputWithCopy value={`claude mcp add --transport http sqldesk ${origin}/mcp`} />
          <p className="mcp-muted m-t-15">
            A script or a headless setup should use an API key instead, from <Link href="users/me">your profile</Link>:
          </p>
        </React.Fragment>
      ) : (
        <p className="mcp-muted">
          Authenticated with your API key, from <Link href="users/me">your profile</Link>. Every call runs as you and
          sees only the data sources you can see.
        </p>
      )}
      <InputWithCopy
        value={`claude mcp add --transport http sqldesk ${origin}/mcp --header "Authorization: Bearer <your API key>"`}
      />
      <p className="mcp-muted m-t-15">
        <HelpTrigger type="MCP_TOOLS" showTooltip={false} renderAsLink>
          What the tools do
        </HelpTrigger>{" "}
        &middot;{" "}
        <HelpTrigger type="MCP" showTooltip={false} renderAsLink>
          The whole guide
        </HelpTrigger>
      </p>
    </div>
  );
}

const COLUMNS = [
  {
    title: "When",
    dataIndex: "at",
    width: 150,
    render: (at) => <TimeAgo date={at} />,
  },
  { title: "Tool", dataIndex: "tool", render: (tool, row) => tool || row.method },
  {
    title: "Outcome",
    dataIndex: "outcome",
    width: 120,
    render: (outcome) => {
      const it = OUTCOME[outcome] || OUTCOME.ok;
      return it.colour ? <Tag color={it.colour}>{it.label}</Tag> : <span className="mcp-outcome-ok">{it.label}</span>;
    },
  },
  {
    title: "Took",
    dataIndex: "duration_ms",
    width: 100,
    align: "right",
    render: (ms) => (ms === null || ms === undefined ? "" : `${ms} ms`),
  },
];

export default function MyMcp({ onError }) {
  const [mine, setMine] = useState(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(() => {
    setLoading(true);
    axios
      .get("api/mcp/mine")
      .then(setMine)
      .catch(onError)
      .finally(() => setLoading(false));
  }, [onError]);

  useEffect(() => {
    recordEvent("view", "page", "mcp/mine");
    load();
  }, [load]);

  const origin = window.location.origin;

  return (
    <div className="container mcp-page" data-test="MyMcp">
      <div className="mcp-header">
        <h2>My MCP</h2>
        <p className="mcp-muted">How to point an AI client at SQLDesk, and what yours has been doing.</p>
      </div>

      {!clientConfig.mcpEnabled && (
        <Alert
          className="m-b-15"
          type="warning"
          showIcon
          message="MCP is off"
          description="An administrator turns it on. Until then the endpoint answers 404."
        />
      )}

      <HowToConnect origin={origin} />

      {/* Before a first call: nothing about activity at all. A table of
          nothing under a heading about activity reads as something broken. */}
      {mine && mine.ever_connected && (
        <React.Fragment>
          <h3 className="mcp-section-title">
            Your client{" "}
            {mine.connected ? (
              <Tag color="green">connected</Tag>
            ) : (
              <Tag>
                last seen <TimeAgo date={mine.last_call_at} />
              </Tag>
            )}{" "}
            <Button size="small" onClick={load} loading={loading} data-test="MyMcpRefresh">
              Refresh
            </Button>
          </h3>
          {mine.clients.length > 0 && <p className="mcp-muted">{mine.clients.join(", ")}</p>}
          <p className="mcp-muted">
            Your own calls only, and never the questions or the SQL in them. The organisation-wide audit, with those
            details, is for administrators.
          </p>
          <Table
            className="mcp-audit-table"
            dataSource={mine.calls}
            columns={COLUMNS}
            rowKey={(row) => `${row.at}-${row.tool || row.method}`}
            size="small"
            pagination={false}
          />
        </React.Fragment>
      )}
    </div>
  );
}

MyMcp.propTypes = { onError: PropTypes.func };
MyMcp.defaultProps = { onError: () => {} };
