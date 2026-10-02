import React from "react";
import { mount } from "enzyme";

import MyMcp from "./MyMcp";
import { axios } from "@/services/axios";
import { clientConfig } from "@/services/auth";

/*
  What My MCP shows its own user.

  Two things it must get right, and neither is cosmetic.

  The first is that before a first call it says nothing about activity. A table
  of nothing under a heading about activity reads as something being broken,
  and the person looking at it has just been told to connect a client.

  The second is that this page is not the admin audit with a filter on it. The
  audit names every user, every question and every address, which is the point
  of it; this one carries only which tool was called and how it went. A test
  that the question is absent is a test that one is never added back casually.
*/
const CALL = {
  at: "2026-10-01T12:00:00Z",
  tool: "run_query",
  method: "tools/call",
  outcome: "ok",
  duration_ms: 42,
};

function mine(overrides) {
  return {
    ever_connected: true,
    connected: true,
    last_call_at: "2026-10-01T12:00:00Z",
    clients: ["claude-code 1.2.3"],
    calls: [CALL],
    ...overrides,
  };
}

async function render(payload) {
  jest.spyOn(axios, "get").mockResolvedValue(payload);
  const wrapper = mount(<MyMcp />);
  // Let the load settle.
  await Promise.resolve();
  wrapper.update();
  return wrapper;
}

describe("the My MCP page", () => {
  beforeEach(() => {
    clientConfig.mcpEnabled = true;
    clientConfig.mcpOAuthEnabled = false;
  });

  afterEach(() => {
    jest.restoreAllMocks();
  });

  test("before a first call it offers the command and says nothing about activity", async () => {
    const wrapper = await render(mine({ ever_connected: false, connected: false, calls: [], clients: [] }));

    expect(wrapper.text()).toContain("Connecting your client");
    expect(wrapper.text()).not.toContain("Your client");
  });

  test("once connected it says so, and lists the call", async () => {
    const wrapper = await render(mine());

    expect(wrapper.text()).toContain("connected");
    expect(wrapper.text()).toContain("run_query");
    expect(wrapper.text()).toContain("42 ms");
  });

  test("a client that has stopped calling is last seen rather than connected", async () => {
    const wrapper = await render(mine({ connected: false }));

    expect(wrapper.text()).toContain("last seen");
  });

  test("a refused call is marked as refused rather than as an error", async () => {
    // They are different things to the person reading this: an error is
    // something broken, a refusal is a limit an administrator set.
    const wrapper = await render(mine({ calls: [{ ...CALL, outcome: "refused" }] }));

    expect(wrapper.text()).toContain("refused");
    expect(wrapper.text()).not.toContain("error");
  });

  test("it shows no question, no SQL and no address even when handed them", async () => {
    // The endpoint does not send these -- it cannot be asked for them at all.
    // They are put in the payload here so that the test fails if a column for
    // one is ever added, rather than only if the endpoint changes.
    const wrapper = await render(
      mine({
        calls: [
          {
            ...CALL,
            detail: "which customers churned last quarter",
            sql: "select * from customers",
            remote_addr: "203.0.113.7",
          },
        ],
      })
    );
    const shown = wrapper.text();

    ["churned", "select *", "203.0.113.7"].forEach((leak) => {
      expect(shown).not.toContain(leak);
    });
  });

  test("with OAuth on, the command to copy needs no key pasted into it", async () => {
    clientConfig.mcpOAuthEnabled = true;
    const wrapper = await render(mine());
    const values = wrapper.find("input").map((input) => input.prop("value"));

    expect(values.some((value) => value && !value.includes("Authorization"))).toBe(true);
  });

  test("when MCP is off it says so rather than showing a dead endpoint", async () => {
    clientConfig.mcpEnabled = false;
    const wrapper = await render(mine({ ever_connected: false, calls: [], clients: [] }));

    expect(wrapper.text()).toContain("MCP is off");
  });
});
