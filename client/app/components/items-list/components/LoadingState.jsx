import React from "react";
import PropTypes from "prop-types";
import Spinner from "@/components/Spinner";

// Default "loading" message for list pages.
//
// It used to go through BigMessage, which can only draw a font icon; the
// spinner is drawn rather than typed, so the two lines live here instead.
export default function LoadingState({ className }) {
  return (
    <div className="text-center">
      <div
        className={`big-message p-15 text-center ${className}`}
        role="status"
        aria-live="assertive"
        aria-relevant="additions removals"
      >
        <Spinner size="large" />
        <div className="m-t-15">Loading...</div>
      </div>
    </div>
  );
}

LoadingState.propTypes = {
  className: PropTypes.string,
};

LoadingState.defaultProps = {
  className: "tiled bg-white",
};
