import React from "react";
import routeWithUserSession from "@/components/ApplicationArea/routeWithUserSession";
import routes from "@/services/routes";

/*
  The query editor's routes, without the query editor.

  This module is imported at startup so the paths are known; the page itself
  -- and Ace, which is the largest single thing the application bundles --
  is fetched when somebody opens it. The Suspense boundary that covers the
  wait is in Router.
*/
const QuerySourcePage = React.lazy(() => import(/* webpackChunkName: "query-editor" */ "./QuerySource"));

routes.register(
  "Queries.New",
  routeWithUserSession({
    path: "/queries/new",
    render: (pageProps) => <QuerySourcePage {...pageProps} />,
    bodyClass: "fixed-layout",
  })
);
routes.register(
  "Queries.Edit",
  routeWithUserSession({
    path: "/queries/:queryId/source",
    render: (pageProps) => <QuerySourcePage {...pageProps} />,
    bodyClass: "fixed-layout",
  })
);
