import React from "react";
import { mount } from "enzyme";

import StreamQuery from "./StreamQuery";
import { axios } from "@/services/axios";

/*
  The button says Start streaming, not Execute.

  The two are not the same act: executing runs something once, and starting a
  stream takes a slot away from everybody else for as long as the tab is open.
  A button that did not say so would be one people press without meaning to --
  which is the whole reason this page is not the query editor.
*/
const CLUSTER = { id: 7, name: "Kafka", streams_only: true };

async function settle(wrapper, times = 4) {
  for (let index = 0; index < times; index += 1) {
    // eslint-disable-next-line no-await-in-loop
    await new Promise((resolve) => setTimeout(resolve, 0));
    wrapper.update();
  }
}

function gets(schema) {
  return (url) => {
    if (url === "api/data_sources") {
      return Promise.resolve([CLUSTER]);
    }
    if (url === "api/data_sources/7") {
      return Promise.resolve({ id: 7, schema });
    }
    if (url === "api/data_sources/7/topics") {
      return Promise.resolve({ topics: [{ name: "orders", enabled: true, stream_id: 3 }] });
    }
    return Promise.resolve({ streams: [], slots: {} });
  };
}

async function render(schema = [{ name: "orders", columns: ["id"] }]) {
  jest.spyOn(axios, "get").mockImplementation(gets(schema));
  const wrapper = mount(<StreamQuery />);
  await settle(wrapper);
  return wrapper;
}

const STARTED = {
  id: 3,
  observed_rate: 42.5,
  describes: "last 5 minutes · 12k events",
  watchers: 1,
  sampled: false,
  sample_rate: 1,
};

describe("the stream query page", () => {
  afterEach(() => {
    jest.restoreAllMocks();
  });

  test("it offers Start streaming rather than Execute", async () => {
    const wrapper = await render();

    expect(wrapper.find('[data-test="StartStreaming"]').length).toBeGreaterThan(0);
    expect(wrapper.text()).toContain("Start streaming");
    expect(wrapper.text()).not.toContain("Execute");
  });

  test("the starter query names the topic, so pressing start shows something", async () => {
    const wrapper = await render();

    expect(wrapper.find('textarea[data-test="StreamSql"]').prop("value")).toContain("from orders");
  });

  test("a cluster with no topics enabled says who enables them", async () => {
    const wrapper = await render([]);

    expect(wrapper.text()).toContain("No topics are enabled");
  });

  test("starting it shows the rate and what the window holds", async () => {
    const wrapper = await render();
    jest.spyOn(axios, "post").mockResolvedValue(STARTED);

    wrapper.find('[data-test="StartStreaming"]').first().simulate("click");
    await settle(wrapper);

    expect(wrapper.text()).toContain("42.5");
    expect(wrapper.text()).toContain("last 5 minutes");
    expect(wrapper.find('[data-test="StopStreaming"]').length).toBeGreaterThan(0);
  });

  test("and says when other people are watching the same topic", async () => {
    // Because stopping it is then not only your decision.
    const wrapper = await render();
    jest.spyOn(axios, "post").mockResolvedValue({ ...STARTED, watchers: 4 });

    wrapper.find('[data-test="StartStreaming"]').first().simulate("click");
    await settle(wrapper);

    expect(wrapper.text()).toContain("4 people watching");
  });

  test("a refused slot is explained rather than leaving a dead button", async () => {
    const wrapper = await render();
    jest.spyOn(axios, "post").mockRejectedValue({ message: "All 5 streaming slots are in use." });

    wrapper.find('[data-test="StartStreaming"]').first().simulate("click");
    await settle(wrapper);

    expect(wrapper.text()).toContain("All 5 streaming slots are in use.");
    expect(wrapper.find('[data-test="StopStreaming"]').length).toBe(0);
  });

  test("a sampled stream says so while it runs", async () => {
    const wrapper = await render();
    jest.spyOn(axios, "post").mockResolvedValue({ ...STARTED, sampled: true, sample_rate: 20 });

    wrapper.find('[data-test="StartStreaming"]').first().simulate("click");
    await settle(wrapper);

    expect(wrapper.text()).toContain("1 in 20 kept");
  });

  test("leaving the page lets go of the stream rather than waiting to time out", async () => {
    // A tab that goes away without saying so is timed out in 45 seconds;
    // saying so frees the slot at once, which matters when slots are scarce.
    const wrapper = await render();
    const post = jest.spyOn(axios, "post").mockResolvedValue(STARTED);
    const remove = jest.spyOn(axios, "delete").mockResolvedValue({});

    wrapper.find('[data-test="StartStreaming"]').first().simulate("click");
    await settle(wrapper);
    wrapper.unmount();

    expect(post).toHaveBeenCalled();
    expect(remove).toHaveBeenCalledWith("api/streams/3/watch");
  });
});
