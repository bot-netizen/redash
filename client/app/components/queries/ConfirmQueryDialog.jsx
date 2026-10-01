import React, { useState } from "react";
import PropTypes from "prop-types";
import Modal from "antd/lib/modal";
import Input from "antd/lib/input";
import { wrap as wrapDialog, DialogPropType } from "@/components/DialogWrapper";

/*
  What a curator is asked when they confirm a query.

  Two fields, both optional, and the question is the one that matters: a
  query's name drifts towards the technical ("daily_active_v3") while the
  question is what somebody would type. An AI client searching the catalog
  matches on both, so writing it down is how the query gets found at all.

  The note is for the condition that is true of the SQL and nowhere written
  in it -- "excludes internal orders" -- which is exactly the knowledge that
  makes a saved query worth more than a schema.
*/
function ConfirmQueryDialog({ dialog, query, verification }) {
  const [question, setQuestion] = useState((verification && verification.question) || "");
  const [note, setNote] = useState((verification && verification.note) || "");

  return (
    <Modal
      {...dialog.props}
      title="Confirm this as the right answer"
      okText="Confirm"
      onOk={() => dialog.close({ question, note })}
    >
      <p className="text-muted">
        You are saying you have read <strong>{query.name}</strong> and it answers its question correctly. AI clients are
        told to prefer it, unchanged, over SQL of their own. If anyone edits the query, the confirmation stops counting
        until somebody reads it again.
      </p>
      <label htmlFor="confirm-query-question">The question it answers</label>
      <Input
        id="confirm-query-question"
        value={question}
        placeholder="What did each region take last month?"
        onChange={(event) => setQuestion(event.target.value)}
      />
      <label className="m-t-15" htmlFor="confirm-query-note">
        Anything someone reading it should know
      </label>
      <Input.TextArea
        id="confirm-query-note"
        rows={2}
        value={note}
        placeholder="Excludes internal orders. Amounts are before refunds."
        onChange={(event) => setNote(event.target.value)}
      />
    </Modal>
  );
}

ConfirmQueryDialog.propTypes = {
  dialog: DialogPropType.isRequired,
  query: PropTypes.shape({ name: PropTypes.string }).isRequired,
  verification: PropTypes.shape({ question: PropTypes.string, note: PropTypes.string }),
};

ConfirmQueryDialog.defaultProps = { verification: null };

export default wrapDialog(ConfirmQueryDialog);
