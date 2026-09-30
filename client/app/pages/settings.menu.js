import settingsMenu from "@/services/settingsMenu";

/*
  The tabs across the top of the settings screen, and the Settings link in the
  navbar, which is the first of them the current user may see.

  Here rather than in the pages, because the pages are fetched only when
  somebody opens one (see `settings.routes.jsx`) and this has to be known
  before that: the navbar draws the link on every page. When these lived in the
  page modules -- a `settingsMenu.add` that ran as a side effect of
  `wrapSettingsTab` at import time -- making the pages lazy emptied the menu
  and took the navbar link with it, with nothing failing to say so.

  `order` is the order they appear in. `permission` decides who sees each one;
  an item with none is for everybody.
*/
settingsMenu.add("DataSources.List", {
  permission: "admin",
  title: "Data Sources",
  path: "data_sources",
  order: 1,
});

settingsMenu.add("Users.List", {
  permission: "list_users",
  title: "Users",
  path: "users",
  // `/users/me` is the Account tab, which is a different entry below.
  isActive: (path) => path.startsWith("/users") && path !== "/users/me",
  order: 2,
});

settingsMenu.add("Groups.List", {
  permission: "list_users",
  title: "Groups",
  path: "groups",
  order: 3,
});

settingsMenu.add("AlertDestinations.List", {
  permission: "admin",
  title: "Alert Destinations",
  path: "destinations",
  order: 4,
});

settingsMenu.add("QuerySnippets.List", {
  permission: "create_query",
  title: "Query Snippets",
  path: "query_snippets",
  order: 5,
});

settingsMenu.add("Settings.Organization", {
  permission: "admin",
  title: "General",
  path: "settings/general",
  order: 6,
});

settingsMenu.add("Users.Account", {
  title: "Account",
  path: "users/me",
  order: 7,
});
