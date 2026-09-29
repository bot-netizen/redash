import React, { useState, useEffect } from "react";
import PropTypes from "prop-types";
import Button from "antd/lib/button";
import Divider from "antd/lib/divider";
import Checkbox from "antd/lib/checkbox";

import * as Sidebar from "@/components/items-list/components/Sidebar";
import { ControllerType } from "@/components/items-list/ItemsList";
import DeleteGroupButton from "./DeleteGroupButton";

import { currentUser, clientConfig } from "@/services/auth";
import Group from "@/services/group";
import notification from "@/services/notification";

/*
  One checkbox per feature this install offers, drawn from the list the
  server sends in `grantableFeatures`.

  The list is deliberately not kept here. A feature is added in
  sqldesk/features.py and appears on this page with its own label and its own
  sentence; a page carrying its own copy of the names is a page that drifts
  from the server the first time somebody adds one.
*/
function FeatureToggle({ group, feature }) {
  const [granted, setGranted] = useState(false);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    setGranted((group.permissions || []).includes(feature.name));
  }, [group, feature.name]);

  const toggle = (event) => {
    const next = event.target.checked;
    setSaving(true);
    Group.setPermissions(group, { [feature.name]: next })
      .then((updated) => {
        setGranted((updated.permissions || []).includes(feature.name));
        notification.success(
          next
            ? `Members can now: ${feature.label.toLowerCase()}.`
            : `Members can no longer: ${feature.label.toLowerCase()}.`
        );
      })
      .catch(() => notification.error("Could not change the permission."))
      .finally(() => setSaving(false));
  };

  return (
    <div className="m-b-10">
      <Checkbox checked={granted} disabled={saving} onChange={toggle} data-test={`GroupFeature-${feature.name}`}>
        {feature.label}
      </Checkbox>
      <div className="text-muted" style={{ fontSize: 12, lineHeight: 1.4, marginLeft: 24 }}>
        {feature.description}
      </div>
    </div>
  );
}

FeatureToggle.propTypes = {
  group: PropTypes.object.isRequired, // eslint-disable-line react/forbid-prop-types
  feature: PropTypes.shape({ name: PropTypes.string, label: PropTypes.string, description: PropTypes.string })
    .isRequired,
};

export default function DetailsPageSidebar({
  controller,
  group,
  items,
  canAddMembers,
  onAddMembersClick,
  canAddDataSources,
  onAddDataSourcesClick,
  onGroupDeleted,
}) {
  const canRemove = group && currentUser.isAdmin && group.type !== "builtin";
  // The admin group has every feature already, so there is nothing to grant it.
  const features =
    group && currentUser.isAdmin && !(group.permissions || []).includes("admin")
      ? clientConfig.grantableFeatures || []
      : [];

  return (
    <React.Fragment>
      <Sidebar.Menu items={items} selected={controller.params.currentPage} />
      {canAddMembers && (
        <Button className="w-100 m-t-5" type="primary" onClick={onAddMembersClick}>
          <i className="fa fa-plus m-r-5" aria-hidden="true" />
          Add Members
        </Button>
      )}
      {canAddDataSources && (
        <Button className="w-100 m-t-5" type="primary" onClick={onAddDataSourcesClick}>
          <i className="fa fa-plus m-r-5" aria-hidden="true" />
          Add Data Sources
        </Button>
      )}
      {features.length > 0 && (
        <React.Fragment>
          <Divider dashed className="m-t-10 m-b-10" />
          {features.map((feature) => (
            <FeatureToggle key={feature.name} group={group} feature={feature} />
          ))}
        </React.Fragment>
      )}
      {canRemove && (
        <React.Fragment>
          <Divider dashed className="m-t-10 m-b-10" />
          <DeleteGroupButton className="w-100" group={group} onClick={onGroupDeleted}>
            Delete Group
          </DeleteGroupButton>
        </React.Fragment>
      )}
    </React.Fragment>
  );
}

DetailsPageSidebar.propTypes = {
  controller: ControllerType.isRequired,
  group: PropTypes.object, // eslint-disable-line react/forbid-prop-types
  items: PropTypes.array.isRequired, // eslint-disable-line react/forbid-prop-types

  canAddMembers: PropTypes.bool,
  onAddMembersClick: PropTypes.func,

  canAddDataSources: PropTypes.bool,
  onAddDataSourcesClick: PropTypes.func,

  onGroupDeleted: PropTypes.func,
};

DetailsPageSidebar.defaultProps = {
  group: null,

  canAddMembers: false,
  onAddMembersClick: null,

  canAddDataSources: false,
  onAddDataSourcesClick: null,

  onGroupDeleted: null,
};
