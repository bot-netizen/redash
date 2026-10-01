import React, { useCallback, useEffect, useState } from "react";
import PropTypes from "prop-types";
import Button from "antd/lib/button";
import Popconfirm from "antd/lib/popconfirm";

import TimeAgo from "@/components/TimeAgo";
import { axios } from "@/services/axios";
import { currentUser } from "@/services/auth";
import notification from "@/services/notification";

/*
  The MCP clients this person has connected, and a way to disconnect them.

  The reason this section exists at all: an API key is the same secret forever
  and nothing in the product can tell you where it has been pasted. A token
  can. So the list is not a nicety -- it is the difference between "somebody
  may have a credential of mine somewhere" and "this client, connected on that
  date, last used an hour ago, and I can stop it now."

  Only shown when there is something to show. An empty "Connected apps" heading
  on every profile in an install that does not use MCP is furniture.
*/
export default function ConnectedApps({ user }) {
  const [tokens, setTokens] = useState([]);
  const [loading, setLoading] = useState(true);

  // Somebody else's profile cannot list their connections: the endpoint
  // answers for whoever is signed in, by design, so asking here would show an
  // admin their own clients under another person's name.
  const isSelf = currentUser.id === user.id;

  useEffect(() => {
    if (!isSelf) {
      setLoading(false);
      return undefined;
    }
    let live = true;
    axios
      .get("/api/oauth/tokens")
      .then((data) => live && setTokens(data.tokens))
      // Silent: a profile page that cannot list connections should still show
      // the rest of the profile.
      .catch(() => {})
      .finally(() => live && setLoading(false));
    return () => {
      live = false;
    };
  }, [isSelf]);

  const disconnect = useCallback((token) => {
    axios
      .delete(`/api/oauth/tokens/${token.id}`)
      .then(() => {
        setTokens((current) => current.filter((item) => item.id !== token.id));
        notification.success(`${token.client_name} can no longer reach your data.`);
      })
      .catch(() => notification.error("Could not disconnect that."));
  }, []);

  if (loading || !isSelf || tokens.length === 0) {
    return null;
  }

  return (
    <React.Fragment>
      <hr />
      <h5>Connected apps</h5>
      <p className="text-muted">
        Apps you have signed in to with your SQLDesk account. Each can read what you can read, and nothing else.
        Disconnecting takes effect immediately.
      </p>
      <ul className="list-unstyled connected-apps">
        {tokens.map((token) => (
          <li key={token.id} className="connected-app">
            <div>
              {/* The app's own claim about its name, as on the consent page. */}
              <strong>{token.client_name}</strong>
              <div className="text-muted">
                connected <TimeAgo date={token.connected_at} />
                {token.last_used_at ? (
                  <span>
                    , last used <TimeAgo date={token.last_used_at} />
                  </span>
                ) : (
                  // A connection that has never been used is the one most
                  // worth removing, so it says so rather than showing nothing.
                  <span>, never used</span>
                )}
              </div>
            </div>
            <Popconfirm
              title={`Disconnect ${token.client_name}? It will stop working at once.`}
              okText="Disconnect"
              onConfirm={() => disconnect(token)}
            >
              <Button size="small" danger>
                Disconnect
              </Button>
            </Popconfirm>
          </li>
        ))}
      </ul>
    </React.Fragment>
  );
}

ConnectedApps.propTypes = {
  user: PropTypes.shape({ id: PropTypes.number }).isRequired,
};
