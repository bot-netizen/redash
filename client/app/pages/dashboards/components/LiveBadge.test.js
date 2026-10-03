import React from "react";
import { mount } from "enzyme";
import LiveBadge from "./LiveBadge";

describe("LiveBadge", () => {
  test("nothing for an ordinary dashboard", () => {
    expect(mount(<LiveBadge live={null} />).html()).toBeNull();
  });

  test("live, with how often", () => {
    const text = mount(<LiveBadge live={{ interval: 120, paused: false }} />).text();
    expect(text).toContain("Live");
    expect(text).toContain("every 2 minutes");
  });

  test("paused, and by whom", () => {
    const wrapper = mount(
      <LiveBadge
        live={{ interval: 30, paused: true, paused_by: { name: "Iqbal" }, paused_at: "2026-09-18T10:00:00" }}
      />
    );
    expect(wrapper.text()).toContain("Paused");
    expect(wrapper.text()).toContain("by Iqbal");
    expect(wrapper.find(".live-badge-paused")).toHaveLength(1);
  });
});

/*
  "Live" is a state, not a kind.

  It says a dashboard is refreshing on the server right now, and it says that
  about ordinary dashboards too -- `SAVED_INTERVALS` is the set they are
  offered. So the word cannot also mean "fed by a stream": a dashboard wearing
  this badge may be an ordinary one on a thirty-second cycle. What a dashboard
  *is* is said by the chip beside its name, and the two are deliberately
  different words.

  This is the test that fails if somebody renames either of them into the
  other.
*/
describe("Live is about refreshing, not about streams", () => {
  test("an ordinary dashboard can be live", () => {
    const text = mount(<LiveBadge live={{ interval: 30, paused: false }} />).text();

    expect(text).toContain("Live");
    expect(text).toContain("every 30 seconds");
  });

  test("and the badge never claims a stream", () => {
    const text = mount(<LiveBadge live={{ interval: 2, paused: false }} />).text();

    expect(text).not.toMatch(/stream/i);
  });
});
