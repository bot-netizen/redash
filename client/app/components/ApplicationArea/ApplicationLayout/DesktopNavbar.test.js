import React from "react";
import { mount } from "enzyme";
import { act } from "react-dom/test-utils";
import Dropdown from "antd/lib/dropdown";

/*
  The top row is the one piece of UI everybody sees on every page, and three of
  its decisions are not obvious from reading it:

  - what order the places appear in, which is a product decision rather than
    the order the code happens to be written in;
  - who sees each one, which is a permission and not an admin flag -- Catalog
    and Manage Topics are handed to a group by an administrator, and the whole
    point is that the people doing the work are not administrators;
  - that everything which opens a menu looks like it opens a menu.
*/

const mockPermissions = new Set();
const mockFeatures = new Set();

jest.mock("@/services/auth", () => ({
  Auth: { logout: jest.fn() },
  clientConfig: { mcpEnabled: true },
  currentUser: {
    profile_image_url: "",
    hasPermission: (name) => mockPermissions.has(name),
    can: (name) => mockFeatures.has(name),
  },
}));

jest.mock("@/services/axios", () => ({ axios: { get: () => Promise.resolve([]) } }));
jest.mock("@/components/dashboards/CreateDashboardDialog", () => ({ showModal: jest.fn() }));
jest.mock("@/components/ApplicationArea/Router", () => ({
  useCurrentRoute: () => ({ id: "Queries.List" }),
  stripBase: (path) => path,
}));

// eslint-disable-next-line import/first
import DesktopNavbar from "./DesktopNavbar";
// eslint-disable-next-line import/first
import "@/pages/settings.menu";

async function render() {
  let wrapper;
  await act(async () => {
    wrapper = mount(<DesktopNavbar />);
  });
  wrapper.update();
  return wrapper;
}

function places(wrapper) {
  return wrapper
    .find(".desktop-navbar-links")
    .find(".desktop-navbar-link")
    .hostNodes()
    .map((node) => node.text().trim());
}

// antd only renders a dropdown's overlay into the document once it is opened,
// so the menus are read from the element the Dropdown was handed.
function menu(wrapper, which) {
  const dropdown = wrapper
    .findWhere((node) => node.type() === Dropdown && node.find(`[data-test="${which}"]`).exists())
    .first();
  expect(dropdown.exists()).toBe(true);
  return mount(dropdown.prop("overlay"));
}

function linksIn(wrapper, which) {
  return menu(wrapper, which)
    .find("a")
    .map((a) => a.prop("href"));
}

describe("DesktopNavbar", () => {
  beforeEach(() => {
    mockPermissions.clear();
    mockFeatures.clear();
  });

  test("puts the places in the order they were asked for", async () => {
    ["list_dashboards", "view_query", "list_alerts", "super_admin", "admin"].forEach((p) => mockPermissions.add(p));
    ["use_streams", "manage_streams", "manage_catalog"].forEach((f) => mockFeatures.add(f));

    expect(places(await render())).toEqual([
      "Dashboards",
      "Queries",
      "Kafka Streams",
      "Catalog",
      "Alerts",
      "Settings",
      "Admin",
    ]);
  });

  // It consumes Kafka and nothing else, and a menu called "Streams" invites
  // somebody to look for a Kinesis that is not there.
  test("says which kind of stream it means", async () => {
    mockFeatures.add("use_streams");

    expect(places(await render())).toContain("Kafka Streams");
  });

  test("everything that opens a menu carries the same chevron", async () => {
    ["list_dashboards", "view_query", "super_admin", "admin"].forEach((p) => mockPermissions.add(p));
    mockFeatures.add("use_streams");
    const wrapper = await render();

    ["DashboardsMenuButton", "StreamsMenuButton", "SettingsMenuButton", "AdminMenuButton"].forEach((which) => {
      const button = wrapper.find(`[data-test="${which}"]`).hostNodes();
      expect(button.exists()).toBe(true);
      expect(button.find("i.desktop-navbar-caret").exists()).toBe(true);
    });
  });

  // Queries goes somewhere; it must not look like it opens a menu.
  test("and a link that goes somewhere does not", async () => {
    mockPermissions.add("view_query");
    const wrapper = await render();

    expect(wrapper.find('a[href="queries"]').find("i.desktop-navbar-caret").exists()).toBe(false);
  });

  test("Settings is a named place rather than a gear", async () => {
    mockPermissions.add("admin");
    const wrapper = await render();

    expect(places(wrapper)).toContain("Settings");
    expect(wrapper.find('[data-test="SettingsLink"]').exists()).toBe(false);
  });

  // The whole point of the feature mockPermissions: neither is for everybody, and
  // neither is only for administrators.
  test("Catalog belongs to whoever was granted it, not to admins", async () => {
    mockFeatures.add("manage_catalog");

    expect(places(await render())).toContain("Catalog");
  });

  test("and somebody without it does not see it", async () => {
    mockPermissions.add("admin");
    mockPermissions.add("super_admin");

    expect(places(await render())).not.toContain("Catalog");
  });

  test("Manage Topics is for whoever may manage them", async () => {
    mockFeatures.add("use_streams");
    mockFeatures.add("manage_streams");

    expect(linksIn(await render(), "StreamsMenuButton")).toEqual([
      "streams/query",
      "dashboards/streaming",
      "streams/running",
      "streams/topics",
    ]);
  });

  test("and somebody who may only watch streams does not get it", async () => {
    mockFeatures.add("use_streams");

    expect(linksIn(await render(), "StreamsMenuButton")).toEqual([
      "streams/query",
      "dashboards/streaming",
      "streams/running",
    ]);
  });

  test("the Admin menu reaches every admin page", async () => {
    mockPermissions.add("super_admin");
    const wrapper = await render();
    const adminMenu = menu(wrapper, "AdminMenuButton");

    expect(adminMenu.find("a").map((a) => a.prop("href"))).toEqual([
      "admin/overview",
      "admin/status",
      "admin/queries/jobs",
      "admin/storage",
      "admin/queries/running",
      "admin/streams",
      "admin/queries/outdated",
      "admin/mcp",
    ]);
    // Storage and Streaming Queries had routes and pages for days with no way
    // to reach either, because this menu was written out by hand.
    expect(adminMenu.text()).toContain("Storage Status");
    expect(adminMenu.text()).toContain("Streaming Queries");
  });

  // Eight entries describing themselves in three lines each is a menu taller
  // than the window. The descriptions belong on the pages.
  test("and does not repeat what each page says about itself", async () => {
    mockPermissions.add("super_admin");
    const adminMenu = menu(await render(), "AdminMenuButton");

    expect(adminMenu.text()).not.toContain("Where the headroom is going");
    adminMenu.find("a").forEach((link) => expect(link.text().split(" ").length).toBeLessThanOrEqual(3));
  });

  test("the Settings menu shows only the tabs this person may open", async () => {
    mockPermissions.add("create_query");
    const asUser = linksIn(await render(), "SettingsMenuButton");

    mockPermissions.add("admin");
    mockPermissions.add("list_users");
    const asAdmin = linksIn(await render(), "SettingsMenuButton");

    expect(asUser).toEqual(["query_snippets", "users/me"]);
    expect(asAdmin).toEqual([
      "data_sources",
      "users",
      "groups",
      "destinations",
      "query_snippets",
      "settings/general",
      "users/me",
    ]);
  });
});
