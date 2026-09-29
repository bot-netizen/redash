import React, { Suspense } from "react";

/*
  The editor arrives when a form actually has one.

  `AceEditorInput` pulls in Ace, which is the largest single dependency the
  application has -- close to a megabyte. It is used by the handful of data
  source settings whose field type is `ace`, and was reaching everybody who
  opened a dashboard, because this module is imported eagerly through the
  dynamic form's field table.
*/
const AceEditorInput = React.lazy(() => import(/* webpackChunkName: "ace-editor" */ "@/components/AceEditorInput"));

export default function AceEditorField({ form, field, ...otherProps }) {
  return (
    <Suspense fallback={<div className="ace-editor-input" style={{ height: 100 }} />}>
      <AceEditorInput {...otherProps} />
    </Suspense>
  );
}
