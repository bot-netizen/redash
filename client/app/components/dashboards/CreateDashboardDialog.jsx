import { trim } from "lodash";
import React, { useState } from "react";
import PropTypes from "prop-types";
import Modal from "antd/lib/modal";
import Input from "antd/lib/input";
import Radio from "antd/lib/radio";
import DynamicComponent from "@/components/DynamicComponent";
import { wrap as wrapDialog, DialogPropType } from "@/components/DialogWrapper";
import navigateTo from "@/components/ApplicationArea/navigateTo";
import recordEvent from "@/services/recordEvent";
import { policy } from "@/services/policy";
import { currentUser } from "@/services/auth";
import { Dashboard } from "@/services/dashboard";

import "./CreateDashboardDialog.less";

/*
  Which kind of dashboard, asked once and never again.

  A dashboard shows streams or saved queries, never both: it has a single
  refresh interval, and a stream wants two seconds where a warehouse query
  wants thirty or more. That used to be settled by whichever panel arrived
  first, which meant the question was answered by accident and the refusal
  could only reach the *second* panel -- after somebody had built half a board.

  Asked here instead. It also decides which list the dashboard appears in from
  the moment it exists, rather than after its first widget: the two lists are
  halves of one set now, and a dashboard that changed kind later would move
  between them under its author.

  Only shown when it is a real question. Somebody who may not stream has one
  answer available, and a dialog that offers one choice is a dialog asking for
  a click it already knows the answer to.
*/
function CreateDashboardDialog({ dialog, kind }) {
  const canStream = currentUser.can("use_streams");
  const [name, setName] = useState("");
  // The half somebody opened this from, when they opened it from a list. From
  // the Create menu there is no half to inherit, so it starts ordinary.
  const [chosenKind, setChosenKind] = useState(kind === "streaming" && canStream ? "streaming" : "saved");
  const [isValid, setIsValid] = useState(false);
  const [saveInProgress, setSaveInProgress] = useState(false);
  const isCreateDashboardEnabled = policy.isCreateDashboardEnabled();

  function handleNameChange(event) {
    const value = trim(event.target.value);
    setName(value);
    setIsValid(value !== "");
  }

  function save() {
    if (name !== "") {
      setSaveInProgress(true);

      Dashboard.save({ name, kind: chosenKind }).then((data) => {
        dialog.close();
        navigateTo(`${data.url}?edit`);
      });
      recordEvent("create", "dashboard");
    }
  }

  return (
    <Modal
      {...dialog.props}
      {...(isCreateDashboardEnabled ? {} : { footer: null })}
      title="New Dashboard"
      okText="Save"
      cancelText="Close"
      okButtonProps={{
        disabled: !isValid || saveInProgress,
        loading: saveInProgress,
        "data-test": "DashboardSaveButton",
      }}
      cancelButtonProps={{
        disabled: saveInProgress,
      }}
      onOk={save}
      closable={!saveInProgress}
      maskClosable={!saveInProgress}
      wrapProps={{
        "data-test": "CreateDashboardDialog",
      }}
    >
      <DynamicComponent name="CreateDashboardDialogExtra" disabled={!isCreateDashboardEnabled}>
        <Input
          defaultValue={name}
          onChange={handleNameChange}
          onPressEnter={save}
          placeholder="Dashboard Name"
          aria-label="Dashboard name"
          disabled={saveInProgress}
          autoFocus
        />
      </DynamicComponent>
      {canStream && (
        <div className="create-dashboard-kind" data-test="DashboardKind">
          <Radio.Group
            value={chosenKind}
            onChange={(event) => setChosenKind(event.target.value)}
            disabled={saveInProgress}
          >
            <Radio value="saved">Saved queries</Radio>
            <Radio value="streaming">Streaming queries</Radio>
          </Radio.Group>
          <p className="create-dashboard-kind-note">
            {chosenKind === "streaming"
              ? "Panels come from streaming queries, and it may refresh every few seconds. It pauses when nobody is watching."
              : "Panels come from saved queries. A dashboard cannot mix the two, because it has one refresh interval."}
          </p>
        </div>
      )}
    </Modal>
  );
}

CreateDashboardDialog.propTypes = {
  dialog: DialogPropType.isRequired,
  //: The half of the list this was opened from, if it was opened from one.
  kind: PropTypes.string,
};

CreateDashboardDialog.defaultProps = { kind: null };

export default wrapDialog(CreateDashboardDialog);
