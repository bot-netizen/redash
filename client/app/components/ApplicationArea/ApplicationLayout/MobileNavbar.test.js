import React from "react";
import { mount } from "enzyme";
import Dropdown from "antd/lib/dropdown";

/*
  The phone menu holds the same places as the desktop bar, flattened: no
  submenu inside a dropdown, because that is a target nobody hits, and no
  three-line descriptions, because they would make it longer than the screen.

  What is worth a test is that it holds the same places at all. It is a second
  hand-written list of the same navigation, which is exactly the shape that had
  already left Storage and Streams unreachable from the desktop one.
*/
const mockPermissions = new Set();
const mockFeatures = new Set();

jest.mock("@/services/auth", () => ({
  Auth: { logout: jest.fn() },
  clientConfig: { mcpEnabled: true },
  currentUser: {
    hasPermission: (name) => mockPermissions.has(name),
    can: (name) => mockFeatures.has(name),
  },
}));

// eslint-disable-next-line import/first
import MobileNavbar from "./MobileNavbar";
// eslint-disable-next-line import/first
import "@/pages/settings.menu";

function links() {
  const wrapper = mount(<MobileNavbar />);
  const overlay = mount(wrapper.find(Dropdown).first().prop("overlay"));
  return overlay.find("a").map((a) => a.prop("href"));
}

// antd renames a Menu's classes when it is rendered as a dropdown overlay
// (`ant-menu-*` becomes `ant-dropdown-menu-*`), and this mounts the Menu
// directly, so match either.
function headings() {
  const wrapper = mount(<MobileNavbar />);
  const overlay = mount(wrapper.find(Dropdown).first().prop("overlay"));
  return overlay
    .findWhere((node) => /(^| )ant-(dropdown-)?menu-item-group-title( |$)/.test(node.prop("className") || ""))
    .hostNodes()
    .map((node) => node.text().trim());
}

describe("MobileNavbar", () => {
  beforeEach(() => {
    mockPermissions.clear();
    mockFeatures.clear();
  });

  test("reaches the same places as the desktop bar", () => {
    ["list_dashboards", "view_query", "list_alerts", "super_admin", "admin", "list_users"].forEach((p) =>
      mockPermissions.add(p)
    );
    ["use_streams", "manage_streams", "manage_catalog"].forEach((f) => mockFeatures.add(f));
    const hrefs = links();

    ["dashboards", "queries", "alerts", "catalog"].forEach((href) => expect(hrefs).toContain(href));
    ["queries/streaming", "dashboards/streaming"].forEach((href) => expect(hrefs).toContain(href));
    ["admin/overview", "admin/storage", "admin/queries/running", "admin/streams"].forEach((href) =>
      expect(hrefs).toContain(href)
    );
    ["data_sources", "data_sources/streaming", "groups", "users/me"].forEach((href) => expect(hrefs).toContain(href));
  });

  test("groups the long lists so the shape survives flattening", () => {
    mockPermissions.add("super_admin");
    mockFeatures.add("use_streams");

    // No Streams group any more: the two streaming entries are the second half
    // of lists whose first half is directly above them, so they read in place.
    // A heading over two items on a phone is a line of chrome for nothing.
    expect(headings()).toEqual(["Settings", "Admin"]);
  });

  test("shows an ordinary user neither Admin nor the topics they may not manage", () => {
    mockPermissions.add("view_query");
    mockFeatures.add("use_streams");
    const hrefs = links();

    expect(hrefs).toContain("queries/streaming");
    expect(hrefs).not.toContain("data_sources/streaming");
    expect(hrefs).not.toContain("admin/overview");
    expect(headings()).toEqual(["Settings"]);
  });

  // The same rule as the desktop bar: nothing in the navigation is named after
  // the broker underneath it.
  test("and names nothing after the broker", () => {
    ["list_dashboards", "view_query", "super_admin", "admin", "list_users"].forEach((p) => mockPermissions.add(p));
    ["use_streams", "manage_streams"].forEach((f) => mockFeatures.add(f));

    const overlay = mount(
      mount(<MobileNavbar />)
        .find(Dropdown)
        .first()
        .prop("overlay")
    );

    expect(overlay.text()).not.toMatch(/kafka/i);
  });
});
