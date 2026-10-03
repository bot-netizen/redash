import React from "react";
import { mount } from "enzyme";

import StreamStatus from "./StreamStatus";
import { axios } from "@/services/axios";

/*
  What the strip beside the button has to say.

  The numbers that tell somebody whether to believe the answer -- the rate, how
  much history the window holds, whether it is sampled -- live nowhere else on
  this page. And "nothing has arrived yet" is a state, not a fault: a quiet
  topic looks like that for its first seconds and a topic nobody produces to
  looks like it all day, so painting it red sends people to the broker to find
  a problem that is not there.
*/
const STREAM = {
  id: 1,
  topic: "orders",
  table: "orders",
  data_source_id: 7,
  state: "running",
  observed_rate: 42.5,
  describes: "last 5 minutes · 12k events",
  sampled: false,
  sample_rate: 1,
  watchers: 1,
};

async function render(streams, props = {}) {
  jest.spyOn(axios, "get").mockResolvedValue({ streams });
  const wrapper = mount(
    <StreamStatus dataSource={{ id: 7 }} query={{ query: "select * from orders" }} streaming {...props} />
  );
  for (let index = 0; index < 3; index += 1) {
    // eslint-disable-next-line no-await-in-loop
    await new Promise((resolve) => setTimeout(resolve, 0));
    wrapper.update();
  }
  return wrapper;
}

describe("the stream status strip", () => {
  afterEach(() => {
    jest.restoreAllMocks();
  });

  test("it shows the rate and what the window holds", async () => {
    const wrapper = await render([STREAM]);

    expect(wrapper.find('[data-test="StreamRate"]').first().text()).toBe("42.5 /s");
    expect(wrapper.text()).toContain("last 5 minutes");
  });

  test("before anything is started it says it is not streaming", async () => {
    const wrapper = await render([]);

    expect(wrapper.text()).toContain("not streaming");
  });

  /*
    The bug this exists for: Stop ended the polling and left whatever the
    server last said on screen, so the strip went on claiming "consuming"
    against a stream the person had just stopped.

    Two things in the component stop that, and only one of them is observable
    here. Clearing what was fetched is covered by the restart test below. The
    render-time gate on `streaming` covers the frame between the switch
    flipping and the effect running -- real in a browser, and invisible in
    jsdom, where effects have already flushed by the time a test can look.
    It stays because that frame is exactly what somebody sees when they press
    Stop, not because a test demands it.
  */
  test("and says so the moment streaming is switched off, whatever the server last said", async () => {
    const wrapper = await render([STREAM]);
    expect(wrapper.text()).toContain("consuming");

    wrapper.setProps({ streaming: false });
    wrapper.update();

    expect(wrapper.text()).not.toContain("consuming");
    expect(wrapper.text()).toContain("not streaming");
  });

  // Restarting must not flash the previous run's numbers while the first
  // request is still in the air.
  test("and forgets what it knew, so starting again does not show the old run", async () => {
    const wrapper = await render([STREAM]);
    wrapper.setProps({ streaming: false });
    wrapper.update();

    // Streaming again, with the server not answering yet.
    axios.get.mockReturnValue(new Promise(() => {}));
    wrapper.setProps({ streaming: true });
    wrapper.update();

    expect(wrapper.text()).not.toContain("consuming");
    expect(wrapper.text()).not.toContain("last 5 minutes");
  });

  // Seventeen digits of false precision pushed everything after it off the
  // end of the strip, and nobody decides anything on the sixteenth decimal
  // place of a number that changes every two seconds.
  test("a rate is rounded to something a person can read", async () => {
    const wrapper = await render([{ ...STREAM, observed_rate: 0.8166666666666667 }]);

    expect(wrapper.find('[data-test="StreamRate"]').first().text()).toBe("0.82 /s");
  });

  test("and a big one loses its decimals rather than its digits", async () => {
    const wrapper = await render([{ ...STREAM, observed_rate: 1483.27 }]);

    expect(wrapper.find('[data-test="StreamRate"]').first().text()).toBe("1483 /s");
  });

  test("it says how long it has been running", async () => {
    // So a stream drawing nothing is distinguishable from one that just
    // started drawing nothing.
    const wrapper = await render([STREAM], { startedAt: Date.now() - 125000 });

    expect(wrapper.find('[data-test="StreamElapsed"]').first().text()).toContain("2m");
  });

  test("a sampled stream says what share is kept", async () => {
    const wrapper = await render([{ ...STREAM, sampled: true, sample_rate: 10 }]);

    expect(wrapper.text()).toContain("1 in 10");
  });

  test("other watchers are named, because stopping is then not only your call", async () => {
    const wrapper = await render([{ ...STREAM, watchers: 4 }]);

    expect(wrapper.text()).toContain("4 watching");
  });

  test("waiting for the first event is said calmly, not as an error", async () => {
    const wrapper = await render([STREAM], {
      note: "Consuming, but nothing has arrived on the topic yet.",
    });

    expect(wrapper.find('[data-test="StreamWaiting"]').length).toBeGreaterThan(0);
    expect(wrapper.find('[data-test="StreamError"]').length).toBe(0);
  });

  test("and a real failure is not", async () => {
    const wrapper = await render([STREAM], { error: "syntax error at or near FROM" });

    expect(wrapper.find('[data-test="StreamError"]').first().text()).toContain("syntax error");
  });

  test("a note wins over an error, because waiting is the kinder reading", async () => {
    // The server sends a note only when every topic named is consuming and
    // simply has nothing yet; that is never also a fault.
    const wrapper = await render([STREAM], { note: "Consuming, but nothing has arrived yet.", error: "x" });

    expect(wrapper.find('[data-test="StreamError"]').length).toBe(0);
  });

  test("a topic the query does not name is not reported", async () => {
    const wrapper = await render([{ ...STREAM, topic: "payments", table: "payments" }]);

    expect(wrapper.text()).toContain("not streaming");
  });
});
