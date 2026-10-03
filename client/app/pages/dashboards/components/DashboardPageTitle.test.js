jest.mock("@/services/auth", () => ({
  Auth: { getApiKey: () => null, isAuthenticated: () => true },
  clientConfig: {},
  currentUser: { id: 1, name: "Iqbal", profile_image_url: "", hasPermission: () => true, can: () => false },
}));

jest.mock("@/services/axios", () => ({
  axios: {
    get: () => Promise.resolve([]),
    post: () => Promise.resolve({}),
    interceptors: { request: { use: () => {} }, response: { use: () => {} } },
  },
}));

// eslint-disable-next-line import/first
import React from "react";
// eslint-disable-next-line import/first
import { mount } from "enzyme";
// eslint-disable-next-line import/first
import { DashboardPageTitle } from "./DashboardHeader";

/*
  A dashboard says what it is when it opens.

  Asked for explicitly: the kind had to be visible on the page and not only
  true in the database. It matters most for a streaming dashboard whose panels
  are standing still -- which reads as broken unless you can see that it is a
  stream nobody has started, rather than a query that returned nothing.

  The word is "streaming", and the `Live` badge beside it is a different claim:
  that one says whether the dashboard is refreshing right now, which an
  ordinary dashboard can also be. See LiveBadge.test.js.
*/
function render(dashboard) {
  return mount(
    <DashboardPageTitle
      dashboardConfiguration={{
        dashboard: {
          name: "Orders",
          tags: [],
          user: { name: "Iqbal", profile_image_url: "" },
          ...dashboard,
        },
        canEditDashboard: false,
        updateDashboard: () => {},
        editingLayout: false,
      }}
    />
  );
}

describe("the dashboard title", () => {
  test("a streaming dashboard carries a chip saying so", () => {
    const wrapper = render({ is_streaming: true });

    expect(wrapper.find('[data-test="StreamingChip"]').hostNodes().text()).toBe("streaming");
  });

  test("and an ordinary one carries nothing", () => {
    const wrapper = render({ is_streaming: false });

    expect(wrapper.find('[data-test="StreamingChip"]').exists()).toBe(false);
  });

  test("the name is still the name", () => {
    expect(render({ is_streaming: true }).text()).toContain("Orders");
  });
});
