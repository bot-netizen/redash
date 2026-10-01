import React from "react";
import { mount } from "enzyme";

import Streams from "./Streams";
import { axios } from "@/services/axios";

/*
  What the Streams page says about a stream that is not producing anything.

  This is the whole reason the page exists. An empty chart on a dashboard says
  nothing about why: nobody has looked at the stream lately, the consumer
  stopped with an error, or the topic genuinely has nothing on it. Only one of
  those is somebody's problem, and showing all three as "0 events" sends people
  to the broker for a paused consumer.
*/
function stream(overrides) {
  return {
    id: 1,
    data_source_id: 7,
    data_source_name: "Orders topic",
    topic: "orders",
    active: true,
    pinned: false,
    quiet: null,
    rows: 1000,
    malformed: 0,
    observed_rate: 12.5,
    window_seconds: 600,
    sample_rate: 1,
    sampled: false,
    describes: "last 10 minutes · 1.0k events",
    schema_state: "inferred",
    columns: 4,
    has_rollup: false,
    last_flush_at: "2026-10-01T12:00:00Z",
    ...overrides,
  };
}

async function render(streams) {
  jest.spyOn(axios, "get").mockResolvedValue({ streams });
  const wrapper = mount(<Streams />);
  // Let the load settle.
  await Promise.resolve();
  wrapper.update();
  return wrapper;
}

describe("the Streams page", () => {
  afterEach(() => {
    jest.restoreAllMocks();
  });

  test("a consuming stream says so and when it last flushed", async () => {
    const wrapper = await render([stream()]);

    expect(wrapper.text()).toContain("consuming");
    expect(wrapper.text()).toContain("last 10 minutes · 1.0k events");
  });

  test("a paused one says it is paused, not that it is broken", async () => {
    const wrapper = await render([
      stream({ active: false, quiet: "Paused: nothing has used this stream in 15 minutes." }),
    ]);

    expect(wrapper.text()).toContain("paused");
    expect(wrapper.text()).not.toContain("not working");
    // And the reason, because "paused" alone does not say it comes back.
    expect(wrapper.text()).toContain("nothing has used this stream");
  });

  test("and a broken one is distinguished from a paused one", async () => {
    const wrapper = await render([stream({ quiet: "The broker refused the credentials." })]);

    expect(wrapper.text()).toContain("not working");
    expect(wrapper.text()).toContain("The broker refused the credentials.");
  });

  test("a stream nobody has used yet is not called broken either", async () => {
    const wrapper = await render([
      stream({ active: false, quiet: "Nothing has used this stream yet, so nothing is being consumed." }),
    ]);

    expect(wrapper.text()).toContain("paused");
    expect(wrapper.text()).not.toContain("not working");
  });

  test("sampling is shown as a figure rather than left implicit", async () => {
    // A count from a sampled stream is an estimate, and a chart that did not
    // say so would be inventing nineteen events out of twenty.
    const wrapper = await render([stream({ sampled: true, sample_rate: 20 })]);

    expect(wrapper.text()).toContain("1-in-20");
  });

  test("malformed messages are shown but do not look like a failure", async () => {
    const wrapper = await render([stream({ malformed: 12 })]);

    expect(wrapper.text()).toContain("12 malformed");
    expect(wrapper.text()).toContain("consuming");
  });

  test("a frozen schema is distinguished from an inferred one", async () => {
    const wrapper = await render([stream({ schema_state: "frozen" })]);

    expect(wrapper.text()).toContain("schema frozen");
  });

  test("with no streams it says what one is for rather than showing an empty table", async () => {
    const wrapper = await render([]);

    expect(wrapper.text()).toContain("No streams yet");
    expect(wrapper.text()).toContain("land the topic in your warehouse");
  });
});
