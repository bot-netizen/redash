import React from "react";
import PropTypes from "prop-types";
import cx from "classnames";
import Tooltip from "@/components/Tooltip";
import { formatDateTime } from "@/lib/utils";

import "./LiveBadge.less";

export const LIVE_INTERVAL_LABELS = {
  2: "every 2 seconds",
  5: "every 5 seconds",
  10: "every 10 seconds",
  20: "every 20 seconds",
  30: "every 30 seconds",
  60: "every minute",
  120: "every 2 minutes",
  300: "every 5 minutes",
};

/*
  Which of those a dashboard may be set to.

  A streaming board is offered seconds: nothing on it touches a warehouse, and
  a window measured in minutes redrawn every half-minute is a chart somebody is
  reading late. An ordinary one keeps its half-minutes, because every refresh
  there is a query against somebody's warehouse.

  Nothing beyond two minutes for a stream: one nobody has looked at for two
  minutes has paused anyway.
*/
export const STREAM_INTERVALS = [2, 5, 10, 20, 30, 60, 120];
export const SAVED_INTERVALS = [30, 60, 120, 300];

export function intervalsFor(dashboard) {
  return dashboard && dashboard.is_streaming ? STREAM_INTERVALS : SAVED_INTERVALS;
}

/**
 * "● Live · every 30 seconds", or "Paused by Iqbal". The dot pulses while
 * live, and stays still for anyone who prefers reduced motion.
 */
export default function LiveBadge({ live }) {
  if (!live) {
    return null;
  }
  const paused = !!live.paused;
  const who = paused && live.paused_by && live.paused_by.name;
  const detail = paused ? (who ? `by ${who}` : "") : LIVE_INTERVAL_LABELS[live.interval] || "";
  const badge = (
    <span className={cx("live-badge", { "live-badge-paused": paused })} data-test="LiveBadge" role="status">
      <span className="live-badge-dot" aria-hidden="true" />
      <span className="live-badge-state">{paused ? "Paused" : "Live"}</span>
      {detail && <span className="live-badge-detail">{detail}</span>}
    </span>
  );
  return paused && live.paused_at ? (
    <Tooltip title={`Paused ${formatDateTime(live.paused_at)}`}>{badge}</Tooltip>
  ) : (
    badge
  );
}

LiveBadge.propTypes = {
  live: PropTypes.shape({
    interval: PropTypes.number,
    paused: PropTypes.bool,
    paused_by: PropTypes.shape({ name: PropTypes.string }),
    paused_at: PropTypes.string,
  }),
};

LiveBadge.defaultProps = {
  live: null,
};
