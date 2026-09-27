import React, { useEffect, useRef, useState } from "react";
import PropTypes from "prop-types";
import cx from "classnames";
import { trim } from "lodash";
import Tooltip from "@/components/Tooltip";
import resizeObserver from "@/services/resizeObserver";

import "./VisualizationDescription.less";

/*
  What a visualization is of, under its name on a dashboard panel.

  Written for the chart -- which weeks, which column is counted, "completed
  orders only, refunds excluded" -- so it is the description a panel should
  carry. The query's own description is written mostly for MCP and is not
  shown here.

  A line of text rather than the "i" mark it used to be. A mark hides the
  words from anyone not hovering, which is everyone on a phone, on a wall
  screen, and in an exported picture or PDF.

  Two lines at most, because the point of a panel is its chart. Longer text
  is clamped only visually: the rest is on hover when it is cut, and all of
  it stays in the document for a screen reader.
*/
export default function VisualizationDescription({ description, className }) {
  const text = trim(description || "");
  const ref = useRef(null);
  const [clipped, setClipped] = useState(false);

  useEffect(() => {
    const element = ref.current;
    if (!element) {
      return undefined;
    }
    const measure = () => setClipped(element.scrollHeight > element.clientHeight + 1);
    measure();
    // Resizing a panel in edit mode can cut the text or stop cutting it. The
    // application's one shared watcher, like the charts beside it.
    return resizeObserver(element, measure);
  }, [text]);

  if (!text) {
    return null;
  }

  return (
    <Tooltip placement="topLeft" title={clipped ? text : null}>
      <div ref={ref} className={cx("visualization-description", className)} data-test="VisualizationDescription">
        {text}
      </div>
    </Tooltip>
  );
}

VisualizationDescription.propTypes = {
  description: PropTypes.string,
  className: PropTypes.string,
};

VisualizationDescription.defaultProps = {
  description: "",
  className: null,
};
