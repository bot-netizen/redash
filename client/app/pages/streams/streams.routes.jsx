import React from "react";

import routeWithUserSession from "@/components/ApplicationArea/routeWithUserSession";
import routes from "@/services/routes";

/*
  Streams is its own place, not a kind of query.

  A topic's window exists only while somebody is watching it, so a saved query
  over one would run against whatever happened to be in it -- which is why the
  query editor does not offer Kafka clusters at all and these three pages
  exist instead: one to choose which topics can be queried, one to watch one,
  and one to see what is running and what is left.
*/
const ManageTopics = React.lazy(() => import(/* webpackChunkName: "streams" */ "./ManageTopics"));
const StreamQuery = React.lazy(() => import(/* webpackChunkName: "streams" */ "./StreamQuery"));
const RunningStreams = React.lazy(() => import(/* webpackChunkName: "streams" */ "./RunningStreams"));

routes.register(
  "Streams.Topics",
  routeWithUserSession({
    path: "/streams/topics",
    title: "Manage topics",
    render: (pageProps) => <ManageTopics {...pageProps} />,
  })
);

routes.register(
  "Streams.Query",
  routeWithUserSession({
    path: "/streams/query",
    title: "Query a stream",
    render: (pageProps) => <StreamQuery {...pageProps} />,
  })
);

routes.register(
  "Streams.Running",
  routeWithUserSession({
    path: "/streams/running",
    title: "Running streams",
    render: (pageProps) => <RunningStreams {...pageProps} />,
  })
);
