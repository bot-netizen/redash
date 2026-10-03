import React from "react";
import Spin from "antd/lib/spin";
import Spinner from "@/components/Spinner";

// Every antd <Spin> in the app, in one place. The indicator itself says
// nothing to a screen reader; the live region around it does.
Spin.setDefaultIndicator(
  <span role="status" aria-live="polite" aria-relevant="additions removals">
    <Spinner />
    <span className="sr-only">Loading...</span>
  </span>
);
