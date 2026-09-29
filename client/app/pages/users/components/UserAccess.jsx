import React, { useEffect, useState } from "react";
import PropTypes from "prop-types";
import Tag from "antd/lib/tag";
import { axios } from "@/services/axios";

/*
  What this person may do, and where it comes from.

  Read-only on purpose. Access is a property of the groups somebody is in, so
  a control here would be a second place to change it and a second place to
  disagree with the Groups page. What this does instead is name the group
  that grants each thing, so whoever is looking knows where to go.
*/
export default function UserAccess({ user }) {
  const [access, setAccess] = useState(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    let current = true;
    axios
      .get(`api/users/${user.id}/access`)
      .then((data) => current && setAccess(data))
      .catch(() => current && setFailed(true));
    return () => {
      current = false;
    };
  }, [user.id]);

  if (failed || !access) {
    return null;
  }

  return (
    <div data-test="UserAccess">
      <h5 className="m-t-20">Access</h5>
      <p className="text-muted" style={{ fontSize: 12 }}>
        {access.is_admin
          ? "Administrators can do everything this install offers."
          : "Set by the groups this person is in. To change it, change their groups."}
      </p>

      <dl className="profile__dl">
        {access.features.map((feature) => (
          <React.Fragment key={feature.name}>
            <dt>{feature.label}:</dt>
            <dd>
              {feature.granted ? (
                <span>
                  <Tag color="green">Yes</Tag>
                  <span className="text-muted" style={{ fontSize: 12 }}>
                    {feature.granted_by.join(", ")}
                  </span>
                </span>
              ) : (
                <Tag>No</Tag>
              )}
            </dd>
          </React.Fragment>
        ))}
      </dl>

      <h5 className="m-t-20">Data sources</h5>
      {access.data_sources.length === 0 ? (
        <p className="text-muted" style={{ fontSize: 12 }}>
          None. Without a data source this person can open dashboards but cannot run anything.
        </p>
      ) : (
        <dl className="profile__dl">
          {access.data_sources.map((source) => (
            <React.Fragment key={source.name}>
              <dt>{source.name}:</dt>
              <dd>{source.access}</dd>
            </React.Fragment>
          ))}
        </dl>
      )}
    </div>
  );
}

UserAccess.propTypes = {
  user: PropTypes.shape({ id: PropTypes.number }).isRequired,
};
