import React, { useCallback, useEffect, useState } from "react";
import PropTypes from "prop-types";
import Alert from "antd/lib/alert";
import Button from "antd/lib/button";
import Table from "antd/lib/table";
import Tag from "antd/lib/tag";
import Tooltip from "@/components/Tooltip";

import HelpTrigger from "@/components/HelpTrigger";
import TimeAgo from "@/components/TimeAgo";
import { axios } from "@/services/axios";
import notification from "@/services/notification";
import { currentUser, clientConfig } from "@/services/auth";
import Layout from "@/components/admin/Layout";

import "./mcp.less";

/*
  Admin -> MCP: who is connected, and what they have been asking for.

  The audit is the whole of it. A tool server that answers questions about
  somebody's warehouse, to a client nobody can see, is a thing an
  administrator has to be able to look at.

  How to *connect* is not here. It is the same paragraph for everybody, it is
  on everyone's own My MCP page already, and an administrator reading an audit
  is not in the middle of setting a client up. It was on both pages and the
  copy on this one said nothing the other did not.
*/

const OUTCOME = {
  ok: { colour: null, label: "ok" },
  error: { colour: "red", label: "error" },
  refused: { colour: "orange", label: "refused" },
};

function ActivePanel({ active, minutes }) {
  if (!active.length) {
    return (
      <div className="mcp-panel">
        <h3>Nobody connected</h3>
        <p className="mcp-muted">No MCP session has been active in the last {minutes} minutes.</p>
      </div>
    );
  }
  return (
    <div className="mcp-panel">
      <h3>
        Active sessions{" "}
        {/* Not a socket: this transport is one POST per call, so "connected"
            can only honestly mean "seen recently". */}
        <Tooltip
          title={`A session seen in the last ${minutes} minutes. The transport holds no connection open, so this means recently active rather than attached.`}
        >
          <span className="mcp-muted" style={{ fontWeight: 400, fontSize: 13 }}>
            — seen in the last {minutes} minutes
          </span>
        </Tooltip>
      </h3>
      <dl className="mcp-facts">
        {active.map((session) => (
          <React.Fragment key={session.session_id}>
            <dt>{session.user || "unknown"}</dt>
            <dd>
              {session.client || "unnamed client"} · {session.calls} call{session.calls === 1 ? "" : "s"} ·{" "}
              <TimeAgo date={session.last_seen} />
            </dd>
          </React.Fragment>
        ))}
      </dl>
    </div>
  );
}

ActivePanel.propTypes = {
  active: PropTypes.arrayOf(PropTypes.object).isRequired, // eslint-disable-line react/forbid-prop-types
  minutes: PropTypes.number.isRequired,
};

const COLUMNS = [
  {
    title: "When",
    dataIndex: "at",
    width: 130,
    render: (at) => <TimeAgo date={at} />,
  },
  { title: "User", dataIndex: "user", width: 150, render: (user) => user || <em>unauthenticated</em> },
  { title: "Method", dataIndex: "method", width: 120 },
  { title: "Tool", dataIndex: "tool", width: 140, render: (tool) => tool || "" },
  {
    title: "Outcome",
    dataIndex: "outcome",
    width: 100,
    render: (outcome) => {
      const it = OUTCOME[outcome] || OUTCOME.ok;
      return it.colour ? <Tag color={it.colour}>{it.label}</Tag> : <span className="mcp-outcome-ok">{it.label}</span>;
    },
  },
  { title: "Took", dataIndex: "duration_ms", width: 80, render: (ms) => (ms === null ? "" : `${ms} ms`) },
  { title: "From", dataIndex: "remote_addr", width: 130 },
  { title: "Detail", dataIndex: "detail", render: (detail) => <span className="mcp-detail">{detail}</span> },
];

/*
  Every connected client in the organisation, and a way to end any of them.

  The administrator's half of "Connected apps". It exists for the question an
  API key cannot answer: when somebody leaves, or a laptop goes missing, which
  clients are holding a credential for this install and whose. Revoked rows
  stay, because "did that client have access last Tuesday" is a question that
  gets asked after the fact.
*/
function ConnectionsPanel() {
  const [tokens, setTokens] = useState(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(() => {
    setLoading(true);
    axios
      .get("api/admin/oauth/tokens")
      .then((data) => setTokens(data.tokens))
      .catch(() => setTokens([]))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const revoke = useCallback((token) => {
    axios
      .delete(`api/admin/oauth/tokens/${token.id}`)
      .then(() => {
        setTokens((current) =>
          current.map((item) => (item.id === token.id ? { ...item, revoked_at: new Date().toISOString() } : item))
        );
        notification.success(`${token.client_name} can no longer reach ${token.user_name}'s data.`);
      })
      .catch(() => notification.error("Could not revoke that."));
  }, []);

  if (loading || !tokens || tokens.length === 0) {
    return null;
  }

  const columns = [
    {
      title: "App",
      dataIndex: "client_name",
      // The app's own claim about its name, as on the consent page.
      render: (name) => <strong>{name}</strong>,
    },
    { title: "As", dataIndex: "user_name", width: 180 },
    {
      title: "Connected",
      dataIndex: "connected_at",
      width: 150,
      render: (at) => <TimeAgo date={at} />,
    },
    {
      title: "Last used",
      dataIndex: "last_used_at",
      width: 150,
      // The never-used ones are the ones worth removing, so they say so.
      render: (at) => (at ? <TimeAgo date={at} /> : <span className="mcp-muted">never</span>),
    },
    {
      title: "",
      dataIndex: "revoked_at",
      width: 120,
      align: "right",
      render: (revokedAt, row) =>
        revokedAt ? (
          <Tooltip title="Kept so you can see it had access, and when that ended.">
            <Tag>revoked</Tag>
          </Tooltip>
        ) : (
          <Button size="small" danger onClick={() => revoke(row)}>
            Revoke
          </Button>
        ),
    },
  ];

  return (
    <React.Fragment>
      <h3 className="mcp-section-title">
        Connected apps{" "}
        <Button size="small" onClick={load} loading={loading}>
          Refresh
        </Button>
      </h3>
      <p className="mcp-muted">
        Clients holding a token for this organisation. Revoking one stops it immediately; the person has to connect it
        again. Disabling an account revokes everything it holds.
      </p>
      <Table dataSource={tokens} columns={columns} rowKey="id" size="small" pagination={{ pageSize: 10 }} />
    </React.Fragment>
  );
}

export default function McpHome({ onError }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const isAdmin = currentUser.hasPermission("super_admin");

  const load = useCallback(() => {
    setLoading(true);
    axios
      .get("api/mcp/audit")
      .then(setData)
      .catch(onError)
      .finally(() => setLoading(false));
  }, [onError]);

  useEffect(() => {
    if (isAdmin) {
      load();
    } else {
      setLoading(false);
    }
  }, [isAdmin, load]);

  return (
    <Layout activeTab="mcp">
      <div className="mcp-page" data-test="McpHome">
        {!clientConfig.mcpEnabled && (
          <Alert
            className="m-b-15"
            type="warning"
            showIcon
            message="MCP is off"
            description="Set SQLDESK_FEATURE_AI=true on the server. Until then the endpoint answers 404."
          />
        )}

        {!isAdmin && (
          <Alert
            type="info"
            showIcon
            message="The audit is for administrators"
            description="It names every user, every question and every address, so it is not shown here."
          />
        )}

        {isAdmin && data && <ActivePanel active={data.active} minutes={data.active_minutes} />}

        {isAdmin && clientConfig.mcpOAuthEnabled && <ConnectionsPanel />}

        {isAdmin && (
          <React.Fragment>
            <h3 className="mcp-section-title">
              Audit <HelpTrigger type="MCP_AUDIT" />{" "}
              <Button size="small" onClick={load} loading={loading} data-test="McpAuditRefresh">
                Refresh
              </Button>
            </h3>
            {data && data.events.length === 0 ? (
              <div className="mcp-empty">Nothing yet. Connect a client and its calls will appear here.</div>
            ) : (
              <Table
                className="mcp-audit-table"
                dataSource={data ? data.events : []}
                columns={COLUMNS}
                rowKey="id"
                size="small"
                loading={loading}
                pagination={{ pageSize: 25, showSizeChanger: false }}
                data-test="McpAuditTable"
              />
            )}
          </React.Fragment>
        )}
      </div>
    </Layout>
  );
}

McpHome.propTypes = { onError: PropTypes.func };
McpHome.defaultProps = { onError: () => {} };
