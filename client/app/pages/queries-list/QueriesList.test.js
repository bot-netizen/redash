const mockPermissions = new Set(["view_query", "create_query"]);

jest.mock("@/services/auth", () => ({
  // `services/axios` reads the api key on every request.
  Auth: { getApiKey: () => null, isAuthenticated: () => true },
  clientConfig: { multiByteSearchEnabled: false, pageSizeOptions: [25, 50, 100] },
  currentUser: {
    id: 1,
    name: "Iqbal",
    profile_image_url: "",
    hasPermission: (name) => mockPermissions.has(name),
    can: () => false,
  },
}));

// The session wrapper is not what is under test, and it would hold the page
// behind a loading state. Passing the route through leaves the chain this test
// is about: route -> props -> request.
// The tag chips and the favourites column reach for the network on mount;
// jsdom answers with an XHR error that fails the test before the page has
// finished rendering.
jest.mock("@/services/axios", () => ({
  axios: {
    get: () => Promise.resolve([]),
    post: () => Promise.resolve({}),
    delete: () => Promise.resolve({}),
    interceptors: { request: { use: () => {} }, response: { use: () => {} } },
  },
}));

jest.mock("@/components/ApplicationArea/routeWithUserSession", () => ({
  __esModule: true,
  default: (route) => route,
}));

jest.mock("@/components/queries/useDataSourceNames", () => ({
  __esModule: true,
  default: () => ({ 7: "Cluster" }),
}));

// eslint-disable-next-line import/first
import { mount } from "enzyme";
// eslint-disable-next-line import/first
import { Query } from "@/services/query";
// eslint-disable-next-line import/first
import routes from "@/services/routes";

// Importing the page is what registers its routes, and the routes are what
// decide the props -- which half, and which view. Driving the page through
// them tests the wiring somebody actually changed rather than a hand-written
// set of props that could agree with nothing.
// eslint-disable-next-line import/first
import { viewsFor } from "./QueriesList";

function routeFor(id) {
  const route = routes.items.find((item) => item.id === id);
  expect(route).toBeDefined();
  return route;
}

/*
  The two halves of the queries list.

  The rule being held here is that nothing is in both: `?kind=` has to ride on
  every request the page makes, and the four views have to stay inside the half
  somebody is looking at. The first version of this filtered the unfiltered
  list and left Mine and Favorites showing both kinds, so which half you saw
  depended on which tab you had clicked -- the kind of fault that looks like
  the data is wrong rather than the page.
*/
async function settle(wrapper, times = 3) {
  for (let index = 0; index < times; index += 1) {
    // eslint-disable-next-line no-await-in-loop
    await new Promise((resolve) => setTimeout(resolve, 0));
    wrapper.update();
  }
}

const EMPTY = { results: [], count: 0, page: 1, page_size: 25 };

async function render(routeId) {
  const wrapper = mount(routeFor(routeId).render({}));
  await settle(wrapper);
  return wrapper;
}

describe("the queries list", () => {
  beforeEach(() => {
    jest.spyOn(Query, "query").mockResolvedValue(EMPTY);
    jest.spyOn(Query, "myQueries").mockResolvedValue(EMPTY);
    jest.spyOn(Query, "favorites").mockResolvedValue(EMPTY);
    jest.spyOn(Query, "archive").mockResolvedValue(EMPTY);
  });

  afterEach(() => {
    jest.restoreAllMocks();
  });

  test("the ordinary half asks for the saved queries", async () => {
    await render("Queries.List");

    expect(Query.query).toHaveBeenCalledWith(expect.objectContaining({ kind: "saved" }));
  });

  test("and the streaming half asks for the other kind", async () => {
    await render("Queries.Streaming");

    expect(Query.query).toHaveBeenCalledWith(expect.objectContaining({ kind: "streaming" }));
  });

  // The three that are not the plain list each go to their own endpoint, so
  // each had to be told separately.
  test.each([
    ["Queries.StreamingMy", () => Query.myQueries],
    ["Queries.StreamingFavorites", () => Query.favorites],
    ["Queries.StreamingArchived", () => Query.archive],
  ])("%s carries the kind as well", async (routeId, resource) => {
    await render(routeId);

    expect(resource()).toHaveBeenCalledWith(expect.objectContaining({ kind: "streaming" }));
  });

  /*
    The four views, inside whichever half you are in.

    Tested on the function that makes them rather than on the rendered tabs:
    one rule generates all eight paths, and a test that typed them out again
    by hand would be checking its own arithmetic. What matters is that no path
    from one half can be reached from the other.
  */
  test("the views stay inside the half you are looking at", () => {
    expect(viewsFor("streaming").map((view) => view.href)).toEqual([
      "queries/streaming",
      "queries/streaming/favorites",
      "queries/streaming/my",
      "queries/streaming/archive",
    ]);
  });

  test("and in the ordinary half they are the paths they always were", () => {
    expect(viewsFor("saved").map((view) => view.href)).toEqual([
      "queries",
      "queries/favorites",
      "queries/my",
      "queries/archive",
    ]);
  });

  // A folder page, or anything else that names no half, must not silently
  // become the streaming one.
  test("and anything that is neither gets the ordinary paths", () => {
    expect(viewsFor(undefined).map((view) => view.href)).toEqual(viewsFor("saved").map((view) => view.href));
  });

  test("both halves offer the same four views", () => {
    expect(viewsFor("streaming").map((view) => view.title)).toEqual(viewsFor("saved").map((view) => view.title));
  });
});
