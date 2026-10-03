import runStreamQuery from "./stream-query";
import { axios } from "@/services/axios";

/*
  A stream query answers with a `QueryResult`, which is what makes every
  visualization, the results table and the download buttons work unchanged. The
  only thing that differs is where the rows came from, and nothing above this
  needs to know -- which is the whole reason the stream editor can be the query
  editor rather than a second page that reimplements charts.
*/
describe("runStreamQuery", () => {
  afterEach(() => {
    jest.restoreAllMocks();
  });

  test("it asks the cluster's own endpoint, not the job queue", async () => {
    // The ordinary path enqueues a job for a worker. This reads a local file
    // and returns in milliseconds, and runs every couple of seconds.
    const post = jest.spyOn(axios, "post").mockResolvedValue({ columns: [], rows: [] });

    runStreamQuery(7, "select 1");
    await Promise.resolve();

    expect(post).toHaveBeenCalledWith("api/data_sources/7/stream_query", { query: "select 1" });
  });

  test("the rows arrive as a result the charts already understand", async () => {
    jest.spyOn(axios, "post").mockResolvedValue({
      columns: [{ name: "region", type: "string" }],
      rows: [{ region: "east" }],
    });

    const result = runStreamQuery(7, "select region from orders");
    const resolved = await result.toPromise();

    expect(resolved.getData()).toEqual([{ region: "east" }]);
    expect(resolved.getColumnNames()).toEqual(["region"]);
  });

  test("it carries no result id, because nothing was stored", async () => {
    // The window is what a consumer saw while somebody was watching; an id
    // would imply a row in Postgres that there is deliberately not.
    jest.spyOn(axios, "post").mockResolvedValue({ columns: [], rows: [] });

    const result = runStreamQuery(7, "select 1");
    await result.toPromise();

    expect(result.getId()).toBeNull();
  });

  test("a refusal arrives as a failure the page can show", async () => {
    jest.spyOn(axios, "post").mockRejectedValue({
      response: { data: { message: "All 5 streaming slots are in use." } },
    });

    const result = runStreamQuery(7, "select 1");
    // The page attaches this; a test that does not gets an unhandled
    // rejection rather than the assertion it came for.
    await result.toPromise().catch(() => {});

    expect(result.getError()).toBe("All 5 streaming slots are in use.");
  });

  test("and so does one with no message at all", async () => {
    jest.spyOn(axios, "post").mockRejectedValue({});

    const result = runStreamQuery(7, "select 1");
    await result.toPromise().catch(() => {});

    expect(result.getError()).toContain("did not run");
  });
});
