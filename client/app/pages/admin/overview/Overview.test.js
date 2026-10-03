import React from "react";
import { mount } from "enzyme";
import { act } from "react-dom/test-utils";

/*
  The overview answers "where is the headroom going". What is running now is a
  page of its own, because it is read while somebody is waiting and refreshes
  four times as often -- and a summary of it here was a second answer to a
  question one page should own.
*/
jest.mock("@/services/auth", () => ({ clientConfig: { mcpEnabled: false }, currentUser: {} }));
jest.mock("@/services/recordEvent", () => jest.fn());

const mockGet = jest.fn();
jest.mock("@/services/axios", () => ({ axios: { get: (...args) => mockGet(...args) } }));

// eslint-disable-next-line import/first
import Overview from "./Overview";

const OVERVIEW = {
  running: [{ job_id: "a", query_name: "Nightly roll-up", elapsed: 42 }],
  queues: { queries: { queued: 0, started: 0 } },
  workers: { total: 2, busy: 0 },
  limits: {
    postgres: { used: 3, max: 100, used_here: 1 },
    redis: { app: { used_memory: 1000, max_memory: 0 }, rq: { used_memory: 1000, max_memory: 0 } },
  },
  storage: { database: 1000, query_results: 500, events: 100 },
  activity: { window_minutes: 60, executions: 0, cache_hit_ratio: 0, top_users: [] },
};

async function render() {
  mockGet.mockResolvedValue(OVERVIEW);
  let wrapper;
  await act(async () => {
    wrapper = mount(<Overview />);
  });
  wrapper.update();
  return wrapper;
}

describe("admin Overview", () => {
  function panels(wrapper) {
    return wrapper
      .find(".admin-panel-head h2")
      .hostNodes()
      .map((h) => h.text().trim());
  }

  test("shows where the headroom is going, and nothing else", async () => {
    const wrapper = await render();

    expect(panels(wrapper)).toEqual(["Headroom", "Who is asking (last 60 minutes)", "Storage"]);
    expect(wrapper.text()).toContain("Postgres connections");
  });

  test("does not answer what is running, which has its own page", async () => {
    const wrapper = await render();

    expect(panels(wrapper)).not.toContain("Running now");
    expect(wrapper.text()).not.toContain("Nightly roll-up");
  });
});
