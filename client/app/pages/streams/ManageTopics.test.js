import React from "react";
import { mount } from "enzyme";

import ManageTopics from "./ManageTopics";
import { axios } from "@/services/axios";

/*
  Enabling a topic is the access decision on a Kafka cluster, so the page's job
  is to make somebody look before they make it. The three numbers that cannot
  be guessed from a topic's name are what the messages contain, how fast they
  arrive, and what that buys -- and the two warnings are the ones that turn
  into a bad afternoon if nobody reads them.
*/
const CLUSTER = { id: 7, name: "Kafka", streams_only: true };
const WAREHOUSE = { id: 8, name: "Warehouse", streams_only: false };

function listing(topics) {
  return (url) => {
    if (url === "api/data_sources") {
      return Promise.resolve([CLUSTER, WAREHOUSE]);
    }
    return Promise.resolve({ topics });
  };
}

/*
  The page loads in two steps -- the clusters, then that cluster's topics --
  and each is a promise plus a render, so one flush is not enough to see the
  second. Several small ones rather than a timer: the test should not be slower
  than the thing it is testing.
*/
async function settle(wrapper, times = 4) {
  for (let index = 0; index < times; index += 1) {
    // A macrotask rather than a microtask: `.then().finally()` chains and the
    // renders between them do not all drain on one flush of the microtask
    // queue, and a test that half-loads the page asserts on half a page.
    // eslint-disable-next-line no-await-in-loop
    await new Promise((resolve) => setTimeout(resolve, 0));
    wrapper.update();
  }
}

async function render(topics) {
  jest.spyOn(axios, "get").mockImplementation(listing(topics));
  const wrapper = mount(<ManageTopics />);
  await settle(wrapper);
  return wrapper;
}

const analysis = {
  topic: "orders",
  read: 500,
  malformed: 0,
  columns: [{ name: "id", type: "integer" }],
  events_per_second: 12.5,
  window_seconds: 600,
  row_budget: 5000000,
  ceiling: 5000,
  sampled: false,
  sample_rate: 1,
};

describe("the Manage topics page", () => {
  afterEach(() => {
    jest.restoreAllMocks();
  });

  test("it lists the cluster's topics and marks the enabled ones", async () => {
    const wrapper = await render([
      { name: "orders", partitions: 3, enabled: true, columns: 4 },
      { name: "payments", partitions: 1, enabled: false, columns: 0 },
    ]);

    expect(wrapper.text()).toContain("orders");
    expect(wrapper.text()).toContain("payments");
    expect(wrapper.text()).toContain("enabled");
  });

  test("only Kafka clusters are offered, not every data source", async () => {
    const wrapper = await render([]);

    expect(wrapper.text()).not.toContain("Warehouse");
  });

  test("with no clusters at all it says who adds one", async () => {
    jest.spyOn(axios, "get").mockResolvedValue([WAREHOUSE]);
    const wrapper = mount(<ManageTopics />);
    await settle(wrapper);

    expect(wrapper.text()).toContain("No Kafka clusters yet");
  });

  test("analysing one shows what is in it and what that buys", async () => {
    const wrapper = await render([{ name: "orders", partitions: 1, enabled: false, columns: 0 }]);
    jest.spyOn(axios, "post").mockResolvedValue(analysis);

    wrapper.find('[data-test="AnalyseTopic"]').first().simulate("click");
    await settle(wrapper);

    const shown = wrapper.text();
    expect(shown).toContain("500");
    expect(shown).toContain("12.5");
    expect(shown).toContain("10 minutes");
    expect(shown).toContain("id");
  });

  test("messages that could not be parsed are a warning, not a footnote", async () => {
    // A schema inferred from a tenth of the messages is a trap.
    const wrapper = await render([{ name: "orders", partitions: 1, enabled: false, columns: 0 }]);
    jest.spyOn(axios, "post").mockResolvedValue({ ...analysis, malformed: 120 });

    wrapper.find('[data-test="AnalyseTopic"]').first().simulate("click");
    await settle(wrapper);

    expect(wrapper.text()).toContain("120 of 500 messages could not be read");
  });

  test("and so is a topic that would be sampled", async () => {
    const wrapper = await render([{ name: "orders", partitions: 1, enabled: false, columns: 0 }]);
    jest.spyOn(axios, "post").mockResolvedValue({ ...analysis, sampled: true, sample_rate: 8 });

    wrapper.find('[data-test="AnalyseTopic"]').first().simulate("click");
    await settle(wrapper);

    expect(wrapper.text()).toContain("1 event in 8 would be kept");
  });

  test("the schema lists every column, one per line, and the one SQLDesk adds", async () => {
    // A row of tags wrapped into an unreadable block past about eight fields,
    // and a topic with forty is ordinary.
    const wrapper = await render([{ name: "orders", partitions: 1, enabled: false, columns: 0 }]);
    const many = Array.from({ length: 24 }, (unused, index) => ({ name: `field_${index}`, type: "string" }));
    jest.spyOn(axios, "post").mockResolvedValue({ ...analysis, columns: many });

    wrapper.find('[data-test="AnalyseTopic"]').first().simulate("click");
    await settle(wrapper);

    const schema = wrapper.find('[data-test="TopicSchema"]').first();
    expect(schema.find(".streams-schema-row").length).toBe(25);
    expect(schema.text()).toContain("field_23");
    expect(schema.text()).toContain("_received_at");
  });

  test("a reading says when it was taken and offers to take another", async () => {
    // Without the time on it the figure reads as something precomputed, and
    // nobody thinks to take it again after the topic has changed.
    const wrapper = await render([{ name: "orders", partitions: 1, enabled: false, columns: 0 }]);
    const post = jest.spyOn(axios, "post").mockResolvedValue(analysis);

    wrapper.find('[data-test="AnalyseTopic"]').first().simulate("click");
    await settle(wrapper);
    expect(wrapper.text()).toContain("measured");

    wrapper.find('[data-test="AnalyseAgain"]').first().simulate("click");
    await settle(wrapper);

    expect(post).toHaveBeenCalledTimes(2);
  });

  test("an already-enabled topic is not offered the button that enables it", async () => {
    const wrapper = await render([{ name: "orders", partitions: 1, enabled: true, columns: 4 }]);
    jest.spyOn(axios, "post").mockResolvedValue(analysis);

    wrapper.find('[data-test="AnalyseTopic"]').first().simulate("click");
    await settle(wrapper);

    expect(wrapper.find('[data-test="EnableTopic"]').length).toBe(0);
  });

  test("sampling is explained whether or not it is happening", async () => {
    const wrapper = await render([{ name: "orders", partitions: 1, enabled: false, columns: 0 }]);
    jest.spyOn(axios, "post").mockResolvedValue(analysis);

    wrapper.find('[data-test="AnalyseTopic"]').first().simulate("click");
    await settle(wrapper);

    expect(wrapper.text()).toContain("Everything is kept");
    expect(wrapper.text()).toContain("5,000");
  });

  test("a cluster that will not answer says so instead of showing nothing", async () => {
    jest.spyOn(axios, "get").mockImplementation((url) => {
      if (url === "api/data_sources") {
        return Promise.resolve([CLUSTER]);
      }
      return Promise.reject({ message: "no route to host" });
    });
    const wrapper = mount(<ManageTopics />);
    await settle(wrapper);

    expect(wrapper.text()).toContain("no route to host");
  });
});
