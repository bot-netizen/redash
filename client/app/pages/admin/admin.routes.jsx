import React from "react";
import routeWithUserSession from "@/components/ApplicationArea/routeWithUserSession";
import routes from "@/services/routes";

/*
  The admin routes, without the admin pages.

  Imported at startup so the paths are known; the pages arrive when somebody
  opens one. Six pages nobody visits in an ordinary day, and everybody was
  downloading all of them before drawing anything.

  One chunk, because somebody looking at system status is usually about to
  look at the queue as well.

  The Suspense boundary that covers the wait is in Router.
*/
const Overview = React.lazy(() => import(/* webpackChunkName: "admin" */ "./overview/Overview"));
const Jobs = React.lazy(() => import(/* webpackChunkName: "admin" */ "./Jobs"));
const OutdatedQueries = React.lazy(() => import(/* webpackChunkName: "admin" */ "./OutdatedQueries"));
const SystemStatus = React.lazy(() => import(/* webpackChunkName: "admin" */ "./SystemStatus"));
const Catalog = React.lazy(() => import(/* webpackChunkName: "admin" */ "./Catalog"));
const McpHome = React.lazy(() => import(/* webpackChunkName: "admin" */ "../mcp/McpHome"));

routes.register(
  "Admin.Overview",
  routeWithUserSession({
    path: "/admin/overview",
    title: "Admin Overview",
    render: (pageProps) => <Overview {...pageProps} />,
  })
);
routes.register(
  "Admin.Jobs",
  routeWithUserSession({
    path: "/admin/queries/jobs",
    title: "RQ Status",
    render: (pageProps) => <Jobs {...pageProps} />,
  })
);
routes.register(
  "Admin.OutdatedQueries",
  routeWithUserSession({
    path: "/admin/queries/outdated",
    title: "Outdated Queries",
    render: (pageProps) => <OutdatedQueries {...pageProps} currentPage="outdated_queries" />,
  })
);
routes.register(
  "Admin.SystemStatus",
  routeWithUserSession({
    path: "/admin/status",
    title: "System Status",
    render: (pageProps) => <SystemStatus {...pageProps} />,
  })
);
routes.register(
  "Admin.MCP",
  routeWithUserSession({
    path: "/admin/mcp",
    title: "MCP",
    render: (pageProps) => <McpHome {...pageProps} />,
  })
);
routes.register(
  "Catalog",
  routeWithUserSession({
    path: "/catalog",
    title: "Catalog",
    render: (pageProps) => <Catalog {...pageProps} />,
  })
);
