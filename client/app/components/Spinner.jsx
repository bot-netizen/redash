import React from "react";
import cx from "classnames";
import PropTypes from "prop-types";

import "./Spinner.less";

/*
  The one thing that spins while something is happening.

  There were two before this, and both came from an icon font. Font Awesome's
  `fa-spinner fa-pulse` is a ring of unequal dots stepped round in eight jumps
  -- at 14px it reads as a glyph failing to draw rather than as progress -- and
  the dashboard widgets used a Material refresh arrow at five times body size,
  which is a button's icon doing a job it was not drawn for.

  A ring is drawn, not typed. Two pixels of border, the track in the page's own
  border colour and one quarter of it in the action teal, turning once every
  0.7s with no steps. It costs nothing, it cannot fail to load, and it takes
  the theme with it: the colours are the runtime tokens, so a theme switch
  moves the spinner too.

  Sized in `em` by default, so one dropped beside text or inside a button comes
  out the size of that text without being told. `size` is for the cases where
  it is the only thing on the screen.
*/
export default function Spinner({ size, className, ...rest }) {
  return <span className={cx("sqldesk-spinner", `sqldesk-spinner-${size}`, className)} aria-hidden="true" {...rest} />;
}

Spinner.propTypes = {
  /** `inline` follows the surrounding font size; the rest are fixed. */
  size: PropTypes.oneOf(["inline", "small", "medium", "large"]),
  className: PropTypes.string,
};

Spinner.defaultProps = {
  size: "inline",
  className: null,
};
