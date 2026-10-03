import QueryResult from "./query-result";
import { Query } from "./query";
import { newestStored, noOlderThan, onPageLoad, runNow, thisResult } from "./freshness";

jest.mock("./query-result", () => {
  const getById = jest.fn(() => ({ source: "cached" }));
  const getByQueryId = jest.fn(() => ({ source: "server" }));
  return { __esModule: true, default: { getById, getByQueryId } };
});

function savedQuery() {
  // What a dashboard hands a widget: a query that knows its latest result.
  return new Query({ id: 1, query: "select 1", latest_query_data_id: 21, options: {} });
}

describe("Query.getQueryResult", () => {
  beforeEach(() => {
    QueryResult.getById.mockClear();
    QueryResult.getByQueryId.mockClear();
  });

  test("a page loading reuses the result the query already knows about", () => {
    const query = savedQuery();
    expect(query.getQueryResult(onPageLoad()).source).toBe("cached");
    expect(QueryResult.getById).toHaveBeenCalledWith(1, 21);
    expect(QueryResult.getByQueryId).not.toHaveBeenCalled();
  });

  test("every other intent is asked of the server, every time", () => {
    // Refresh, live and auto-refresh each used to get the cached result
    // instead, so after the first load nothing ever changed.
    const query = savedQuery();
    query.getQueryResult(onPageLoad());
    [runNow(), newestStored(), noOlderThan(300)].forEach((request) => {
      expect(query.getQueryResult(request).source).toBe("server");
      expect(QueryResult.getByQueryId).toHaveBeenLastCalledWith(1, {}, false, request.maxAge);
    });
    expect(QueryResult.getByQueryId).toHaveBeenCalledTimes(3);
  });

  test("a named result names no age, and still does not take the cached one", () => {
    // `thisResult` and `onPageLoad` both leave `maxAge` undefined. Reading
    // that number alone -- which is what the old code did -- makes a live
    // dashboard show the result it loaded when the page opened, for ever.
    const query = savedQuery();

    expect(query.getQueryResult(thisResult(99)).source).toBe("server");
    expect(QueryResult.getByQueryId).toHaveBeenCalledWith(1, {}, false, undefined);
  });

  test("with no intent given at all, a query assumes a page is loading", () => {
    expect(savedQuery().getQueryResult().source).toBe("cached");
  });
});

/*
  Where a link to a query points.

  A streaming query has one page, not two. Nothing it produces is stored -- the
  window is what a consumer saw while somebody was watching -- so there is no
  saved result for a view page to show, and the editor is the only page it has.

  This used to return `queries/<id>` whatever the query was. A streaming query
  listed among the others therefore linked to a page that would try to run it
  through the warehouse path, and `QuerySource` carried code to bounce the
  browser back out of the mistake after the navigation had already happened.
*/
describe("Query.getUrl", () => {
  const streaming = () => new Query({ id: 7, query: "select * from orders", is_streaming: true, options: {} });
  const saved = () => new Query({ id: 7, query: "select 1", is_streaming: false, options: {} });

  test("an ordinary query has a page to view and a page to edit", () => {
    expect(saved().getUrl()).toBe("queries/7");
    expect(saved().getUrl(true)).toBe("queries/7/source");
  });

  test("a streaming query has only the editor", () => {
    expect(streaming().getUrl()).toBe("streams/query/7");
  });

  test("and asking for its source does not invent a second page", () => {
    // `/streams/query/7/source` is not a route. A list's edit link asks for
    // the source URL of every row it draws, so getting this wrong would make
    // the edit action on a streaming row a dead link.
    expect(streaming().getUrl(true)).toBe("streams/query/7");
  });

  test("a query that says nothing about its kind is treated as an ordinary one", () => {
    // Anything serialized before `is_streaming` existed, and `Query.newQuery()`.
    expect(new Query({ id: 7, query: "select 1", options: {} }).getUrl()).toBe("queries/7");
  });

  test("the hash and the parameters survive either way", () => {
    expect(streaming().getUrl(false, "table")).toBe("streams/query/7#table");
  });
});
