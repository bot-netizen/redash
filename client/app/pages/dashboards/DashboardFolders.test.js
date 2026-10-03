import React from "react";
import { mount } from "enzyme";

import DashboardFolders from "./DashboardFolders";
import { axios } from "@/services/axios";
import { currentUser } from "@/services/auth";

/*
  The meaning is the content of this page.

  A folder called "Business KPIs" with nothing said about it is a label; one
  that says what belongs in it is something somebody can hold a dashboard up
  against. And "administrators only" has to be visible beside it, because the
  two together are the statement: this is what these are, and these have been
  through review.
*/
async function settle(wrapper, times = 3) {
  for (let index = 0; index < times; index += 1) {
    // eslint-disable-next-line no-await-in-loop
    await new Promise((resolve) => setTimeout(resolve, 0));
    wrapper.update();
  }
}

const KPIS = {
  id: 1,
  name: "Business KPIs",
  meaning: "Numbers the board reads every month.",
  locked: true,
  created_by: "Iqbal",
  dashboards: 4,
};

async function render(folders, admin = false) {
  currentUser.isAdmin = admin;
  jest.spyOn(axios, "get").mockResolvedValue(folders);
  const wrapper = mount(<DashboardFolders />);
  await settle(wrapper);
  return wrapper;
}

describe("the dashboard folders page", () => {
  afterEach(() => {
    jest.restoreAllMocks();
    currentUser.isAdmin = false;
  });

  test("it shows what each folder means, not only its name", async () => {
    const wrapper = await render([KPIS]);

    expect(wrapper.text()).toContain("Business KPIs");
    expect(wrapper.text()).toContain("Numbers the board reads every month.");
  });

  test("a locked folder says who may change it", async () => {
    const wrapper = await render([KPIS]);

    expect(wrapper.text()).toContain("administrators only");
  });

  test("and an unlocked one does not", async () => {
    const wrapper = await render([{ ...KPIS, locked: false }]);

    expect(wrapper.text()).not.toContain("administrators only");
  });

  test("a folder with nothing written about it says so rather than looking finished", async () => {
    const wrapper = await render([{ ...KPIS, meaning: null }]);

    expect(wrapper.text()).toContain("Nothing written about what belongs in it");
  });

  test("it counts what is in each", async () => {
    const wrapper = await render([KPIS]);

    expect(wrapper.text()).toContain("4 dashboards");
  });

  test("one dashboard is not pluralised", async () => {
    const wrapper = await render([{ ...KPIS, dashboards: 1 }]);

    expect(wrapper.text()).toContain("1 dashboard");
    expect(wrapper.text()).not.toContain("1 dashboards");
  });

  test("an administrator is offered the controls", async () => {
    const wrapper = await render([KPIS], true);

    expect(wrapper.find('[data-test="NewFolder"]').length).toBeGreaterThan(0);
    expect(wrapper.text()).toContain("Remove");
  });

  test("and nobody else is", async () => {
    const wrapper = await render([KPIS], false);

    expect(wrapper.find('[data-test="NewFolder"]').length).toBe(0);
    expect(wrapper.text()).not.toContain("Remove");
  });

  test("with no folders at all it says who makes them", async () => {
    const wrapper = await render([], false);

    expect(wrapper.text()).toContain("An administrator makes them");
  });
});

describe("which folders reach the Dashboards menu", () => {
  afterEach(() => {
    jest.restoreAllMocks();
    currentUser.isAdmin = false;
  });

  test("one chosen for the menu says so", async () => {
    // An install ends up with more folders than fit in a dropdown, so the page
    // has to show which few were picked.
    const wrapper = await render([{ ...KPIS, in_menu: true }]);

    expect(wrapper.text()).toContain("in the menu");
  });

  test("and one that was not does not", async () => {
    const wrapper = await render([{ ...KPIS, in_menu: false }]);

    expect(wrapper.text()).not.toContain("in the menu");
  });

  test("the dialog offers the choice", async () => {
    const wrapper = await render([KPIS], true);

    wrapper.find('[data-test="NewFolder"]').first().simulate("click");
    await settle(wrapper);

    // Through the tree rather than `wrapper.text()`: antd renders a Modal into
    // a portal, which enzyme walks but does not fold into the page's text.
    expect(wrapper.find('[data-test="FolderInMenu"]').length).toBeGreaterThan(0);
    expect(
      wrapper.findWhere((node) => node.type() === "strong" && /Show it in the Dashboards menu/.test(node.text())).length
    ).toBeGreaterThan(0);
  });
});
