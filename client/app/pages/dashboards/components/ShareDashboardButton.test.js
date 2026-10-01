import React from "react";
import { mount } from "enzyme";

import { currentUser, clientConfig } from "@/services/auth";
import ShareDashboardButton from "./ShareDashboardButton";

/*
  What the Share menu offers, and to whom.

  Three conditions decide whether "Send to Slack" is there, and each of them
  can be true while the feature is still unusable: the permission, a connected
  workspace, and a dashboard that has been published. Offering the item without
  all three means a dialog whose only content is an error.
*/
function menuText({ permission = true, slack = true, draft = false } = {}) {
  currentUser.can = (feature) => (feature === "send_dashboards" ? permission : false);
  clientConfig.slackConfigured = slack;

  const wrapper = mount(
    <ShareDashboardButton
      dashboard={{ id: 1, name: "Revenue", is_draft: draft, user: { name: "Iqbal" } }}
      getExportTarget={() => null}
    />
  );
  // The menu is in a dropdown overlay, which antd renders on open.
  wrapper.find('[data-test="ShareDashboardButton"]').first().simulate("click");
  return wrapper.find('[data-test="ShareDashboardMenu"]').first().text();
}

describe("the Share menu", () => {
  const can = currentUser.can;
  const configured = clientConfig.slackConfigured;

  afterEach(() => {
    currentUser.can = can;
    clientConfig.slackConfigured = configured;
  });

  test("offers Slack when the permission and a workspace are both there", () => {
    expect(menuText()).toContain("Send to Slack");
  });

  test("not without the permission", () => {
    // Which is also absent where no renderer is configured: the server does
    // not grant `send_dashboards` without one.
    expect(menuText({ permission: false })).not.toContain("Send to Slack");
  });

  test("not without a connected workspace", () => {
    expect(menuText({ slack: false })).not.toContain("Send to Slack");
  });

  test("and not for a draft nobody has published", () => {
    // Sending a draft to a channel sends people a link they cannot open.
    expect(menuText({ draft: true })).not.toContain("Send to Slack");
  });

  test("the file exports are always there", () => {
    // They run in the browser and need nothing configured, so losing them to
    // a Slack condition would be a real regression.
    const text = menuText({ permission: false, slack: false });
    expect(text).toContain("Export as PDF");
    expect(text).toContain("Export as image");
  });
});
