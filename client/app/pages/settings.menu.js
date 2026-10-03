import settingsMenu from "@/services/settingsMenu";
import { currentUser } from "@/services/auth";

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
  // `/data_sources/streaming` is the tab below, and this prefix would claim it
  // -- `getActiveItem` takes the first entry that matches and this one is
  // first. The same exception Users makes for `/users/me`.
  isActive: (path) => path.startsWith("/data_sources") && !path.startsWith("/data_sources/streaming"),
  order: 1,
});

/*
  Beside Data Sources, because that is what it configures.

  A Kafka cluster is a data source like any other and is added on the page
  next to this one; this is where its topics are turned into tables somebody
  can query, and where each one's row budget and events-per-second ceiling are
  set. Both pages say which is which, because two tabs with "Data Sources" in
  their names is otherwise an invitation to add a cluster on the wrong one.

  `isAvailable` rather than `permission`: `manage_streams` is a feature an
  administrator grants to a group, and `currentUser.can` is what knows both
  whether this install offers streams at all and whether this person was
  granted them. The `permission` field only understands `hasPermission`, which
  would show the tab on an install that ships with streams switched off.
*/
settingsMenu.add("Streams.Topics", {
  title: "Streaming Data Sources",
  path: "data_sources/streaming",
  order: 1.5,
  isAvailable: () => currentUser.can("manage_streams"),
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
