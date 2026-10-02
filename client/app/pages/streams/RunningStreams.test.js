import React from "react";
import { mount } from "enzyme";

import RunningStreams from "./RunningStreams";
import { axios } from "@/services/axios";

/*
  The page exists to make a limit arguable.

  "All five slots are in use" is only actionable if you can see what is using
  them and who to ask, so the numbers and the names are the content; the table
  is secondary.
*/
function stream(overrides) {
  return {
    id: 1,
    topic: "orders",
    table: "orders",
    data_source_name: "Kafka",
    state: "running",
    watchers: 3,
    started_by: "Ada",
    pinned: false,
    sampled: false,
    sample_rate: 1,
    describes: "last 5 minutes · 12k events",
    last_flush_at: "2026-10-02T12:00:00Z",
    last_error: null,
    ...overrides,
  };
}

async function render(payload) {
  jest.spyOn(axios, "get").mockResolvedValue(payload);
  const wrapper = mount(<RunningStreams />);
  await Promise.resolve();
  wrapper.update();
  return wrapper;
}

const slots = { used: 2, limit: 5, per_user: 2, minutes: 30 };

describe("the Running streams page", () => {
  afterEach(() => {
    jest.restoreAllMocks();
  });

  test("it says how many slots are used and how many there are", async () => {
    const wrapper = await render({ streams: [stream()], slots });

    expect(wrapper.text()).toContain("2 of 5");
  });

  test("and who started each one, because that is who to ask", async () => {
    const wrapper = await render({ streams: [stream()], slots });

    expect(wrapper.text()).toContain("Ada started it");
    expect(wrapper.text()).toContain("3");
  });

  test("a sampled stream says what share is kept", async () => {
    // A count from a sampled stream is an estimate, and that has to be on the
    // page rather than in the documentation.
    const wrapper = await render({ streams: [stream({ sampled: true, sample_rate: 10 })], slots });

    expect(wrapper.text()).toContain("1 in 10");
  });

  test("nothing running says so rather than showing an empty table", async () => {
    const wrapper = await render({ streams: [], slots });

    expect(wrapper.text()).toContain("Nothing is consuming");
  });

  test("a paused stream is distinguished from a consuming one", async () => {
    const wrapper = await render({ streams: [stream({ state: "paused" })], slots });

    expect(wrapper.text()).toContain("paused");
  });

  test("no limit reads as no limit rather than as zero", async () => {
    const wrapper = await render({ streams: [], slots: { used: 0, limit: 0, per_user: 0, minutes: 30 } });

    expect(wrapper.text()).toContain("0 of ∞");
  });

  test("a page that will not load says so", async () => {
    jest.spyOn(axios, "get").mockRejectedValue(new Error("no"));
    const wrapper = mount(<RunningStreams />);
    await Promise.resolve();
    await Promise.resolve();
    wrapper.update();

    expect(wrapper.text()).toContain("Could not load");
  });
});
