import settingsMenu from "@/services/settingsMenu";
import { currentUser } from "@/services/auth";

/*
  The settings tabs exist before any settings page has been fetched.

  The navbar draws a Settings link on every page, pointing at the first tab the
  current user may see, and the settings screen draws the row of tabs. Both
  read this menu. The entries used to be registered as a side effect of
  importing the page modules, which stopped being true the moment those pages
  became lazily loaded: the menu was empty, the navbar link vanished, and
  nothing failed -- until somebody looked at the application.

  So: import what the application imports at startup, and nothing else.
*/
describe("the settings menu at startup", () => {
  beforeAll(() => {
    currentUser.permissions = ["admin", "list_users", "create_query"];
    require("@/pages/index");
  });

  test("has every tab, in order, without a page having been opened", () => {
    expect(settingsMenu.getAvailableItems().map((item) => [item.title, item.path])).toEqual([
      ["Data Sources", "data_sources"],
      ["Users", "users"],
      ["Groups", "groups"],
      ["Alert Destinations", "destinations"],
      ["Query Snippets", "query_snippets"],
      ["General", "settings/general"],
      ["Account", "users/me"],
    ]);
  });

  test("shows somebody without the permissions only their own account", () => {
    currentUser.permissions = ["view_query"];

    expect(settingsMenu.getAvailableItems().map((item) => item.title)).toEqual(["Account"]);

    currentUser.permissions = ["admin", "list_users", "create_query"];
  });

  test("knows which tab a path belongs to", () => {
    expect(settingsMenu.getActiveItem("/data_sources/3").title).toBe("Data Sources");
    expect(settingsMenu.getActiveItem("/users/4").title).toBe("Users");
    // The one special case: the account page is its own tab, not the user list.
    expect(settingsMenu.getActiveItem("/users/me").title).toBe("Account");
  });
});
