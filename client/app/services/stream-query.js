import { get } from "lodash";

import QueryResult from "@/services/query-result";
import { axios } from "@/services/axios";

/*
  Running a query against a cluster's windows.

  Deliberately not the ordinary path. That one enqueues a job for a worker,
  because a query against a warehouse can take four minutes and holding a web
  worker for that long is how a server stops answering. A stream query reads a
  DuckDB file on local disk and returns in milliseconds, and it runs every
  couple of seconds while somebody watches -- a round trip through Redis and a
  worker per refresh would cost more than the query.

  It still answers with a `QueryResult`, which is what makes every
  visualization, the results table and the download buttons work unchanged: the
  thing that differs is where the rows came from, and nothing above this needs
  to know.

  Nothing is stored. No result row, no job, no id that outlives the page. The
  window is what a consumer saw while somebody was watching, and writing it
  down would be making a copy of the one thing whose point is that it is
  current.
*/

//: RQ's "failed". The results pane reads the job's status to decide whether to
//: show an error, so a failure has to arrive looking like one.
const FAILED = 4;

export default function runStreamQuery(dataSourceId, text) {
  const result = new QueryResult();

  axios
    .post(`api/data_sources/${dataSourceId}/stream_query`, { query: text })
    .then((data) => {
      result.update({
        query_result: {
          // No id, because there is no stored result to have one. Enough of a
          // shape for the results pane, which reads `data` and `retrieved_at`.
          id: null,
          data: { columns: data.columns || [], rows: data.rows || [] },
          retrieved_at: new Date().toISOString(),
          runtime: 0,
        },
      });
    })
    .catch((error) => {
      result.update({
        job: {
          status: FAILED,
          error:
            get(error, "response.data.message") ||
            get(error, "message") ||
            "That query did not run against the stream.",
        },
      });
    });

  return result;
}
