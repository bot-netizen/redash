import React, { useCallback, useEffect, useState } from "react";
import Alert from "antd/lib/alert";
import Button from "antd/lib/button";
import Input from "antd/lib/input";
import Modal from "antd/lib/modal";
import Switch from "antd/lib/switch";
import Tag from "antd/lib/tag";
import Tooltip from "antd/lib/tooltip";

import Link from "@/components/Link";
import { axios } from "@/services/axios";
import { currentUser } from "@/services/auth";
import notification from "@/services/notification";
import recordEvent from "@/services/recordEvent";

import "./dashboard-folders.less";

/*
  What sets of dashboards exist, and what each one is for.

  The meaning is the content of this page. A folder called "Business KPIs" with
  nothing said about it is a label; one that says what belongs in it is
  something somebody can hold a dashboard up against. So the description is
  asked for when a folder is made and shown wherever the folder is.

  A locked folder is one only administrators change. Said here in the same
  breath as its meaning, because the two together are the statement: this is
  what these are, and these have been through review.
*/

function FolderDialog({ open, folder, onClose, onSaved }) {
  const [name, setName] = useState("");
  const [meaning, setMeaning] = useState("");
  const [locked, setLocked] = useState(false);
  const [inMenu, setInMenu] = useState(false);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    setName((folder && folder.name) || "");
    setMeaning((folder && folder.meaning) || "");
    setLocked(!!(folder && folder.locked));
    setInMenu(!!(folder && folder.in_menu));
  }, [folder, open]);

  const save = useCallback(() => {
    setSaving(true);
    const url = folder ? `api/dashboard_folders/${folder.id}` : "api/dashboard_folders";
    axios
      .post(url, { name, meaning, locked, in_menu: inMenu })
      .then(() => {
        notification.success(folder ? "Folder updated." : `${name} created.`);
        onSaved();
        onClose();
      })
      .catch((error) => notification.error("Could not save that", (error && error.message) || ""))
      .finally(() => setSaving(false));
  }, [folder, name, meaning, locked, inMenu, onClose, onSaved]);

  return (
    <Modal
      visible={open}
      title={folder ? "Edit folder" : "New folder"}
      okText="Save"
      confirmLoading={saving}
      onOk={save}
      onCancel={onClose}
      okButtonProps={{ disabled: !name.trim(), "data-test": "SaveFolder" }}
    >
      <label htmlFor="folder-name">Name</label>
      <Input id="folder-name" value={name} onChange={(event) => setName(event.target.value)} />

      <label htmlFor="folder-meaning" className="m-t-15">
        What belongs in it
      </label>
      <Input.TextArea
        id="folder-meaning"
        rows={3}
        value={meaning}
        onChange={(event) => setMeaning(event.target.value)}
        placeholder="Numbers the board reads every month."
      />
      <p className="folders-muted">
        Written once and shown wherever the folder is, so &ldquo;does this belong here&rdquo; has an answer.
      </p>

      <div className="m-t-15">
        <Switch checked={inMenu} onChange={setInMenu} data-test="FolderInMenu" />{" "}
        <strong className="m-l-5">Show it in the Dashboards menu</strong>
        <p className="folders-muted">
          For the few people open every day. The rest live here, and a menu of thirty folders is one nobody reads.
        </p>
      </div>

      <div className="m-t-15">
        <Switch checked={locked} onChange={setLocked} data-test="LockFolder" />{" "}
        <strong className="m-l-5">Only administrators may change what is in it</strong>
        <p className="folders-muted">
          Dashboards in a locked folder cannot be edited, renamed, archived or have a widget added by anybody else —
          including whoever made them. Everybody can still read them.
        </p>
      </div>
    </Modal>
  );
}

function DashboardFolders() {
  const [folders, setFolders] = useState(null);
  const [failed, setFailed] = useState(false);
  const [editing, setEditing] = useState(undefined);
  const admin = currentUser.isAdmin;

  const load = useCallback(() => {
    axios
      .get("api/dashboard_folders")
      .then(setFolders)
      .catch(() => setFailed(true));
  }, []);

  useEffect(() => {
    recordEvent("view", "page", "dashboards/folders");
    load();
  }, [load]);

  const remove = useCallback(
    (folder) => {
      axios
        .delete(`api/dashboard_folders/${folder.id}`)
        .then(() => {
          notification.success(`${folder.name} removed.`);
          load();
        })
        .catch((error) => notification.error("Could not remove that folder", (error && error.message) || ""));
    },
    [load]
  );

  return (
    <div className="container folders-page" data-test="DashboardFolders">
      <div className="folders-header">
        <div className="folders-header-text">
          <h2>Dashboard folders</h2>
          <p className="folders-muted">
            Sets of dashboards with a stated meaning. A locked folder is one only administrators change.
          </p>
        </div>
        {admin && (
          <Button type="primary" onClick={() => setEditing(null)} data-test="NewFolder">
            New folder
          </Button>
        )}
      </div>

      {failed && <Alert type="warning" showIcon message="Could not load the folders." />}

      {folders && folders.length === 0 && (
        <p className="folders-muted">
          No folders yet.{" "}
          {admin ? "Make one to group dashboards that belong together." : "An administrator makes them."}
        </p>
      )}

      <div className="folders-list">
        {(folders || []).map((folder) => (
          <div className="folders-folder" key={folder.id} data-test="Folder">
            <div className="folders-folder-main">
              <h3>
                <Link href={`dashboards/folder/${folder.id}`}>{folder.name}</Link>
                {folder.locked && (
                  <Tooltip title="Only administrators may change what is in this folder, or the dashboards in it.">
                    <Tag color="blue" className="m-l-10">
                      administrators only
                    </Tag>
                  </Tooltip>
                )}
                {folder.in_menu && (
                  <Tooltip title="Shown in the Dashboards menu, so people reach it without coming here first.">
                    <Tag className="m-l-5">in the menu</Tag>
                  </Tooltip>
                )}
              </h3>
              <p className={folder.meaning ? "" : "folders-muted"}>
                {folder.meaning || "Nothing written about what belongs in it."}
              </p>
              <p className="folders-muted">
                {folder.dashboards} dashboard{folder.dashboards === 1 ? "" : "s"}
                {folder.created_by && <span> &middot; made by {folder.created_by}</span>}
              </p>
            </div>
            {admin && (
              <div>
                <Button size="small" onClick={() => setEditing(folder)}>
                  Edit
                </Button>
                <Button size="small" danger className="m-l-5" onClick={() => remove(folder)}>
                  Remove
                </Button>
              </div>
            )}
          </div>
        ))}
      </div>

      <FolderDialog
        open={editing !== undefined}
        folder={editing}
        onClose={() => setEditing(undefined)}
        onSaved={load}
      />
    </div>
  );
}

export default DashboardFolders;
