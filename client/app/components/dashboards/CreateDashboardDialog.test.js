import React from "react";
import { mount } from "enzyme";

const mockFeatures = new Set();

jest.mock("@/services/auth", () => ({
  Auth: { getApiKey: () => null, isAuthenticated: () => true },
  clientConfig: {},
  currentUser: { can: (name) => mockFeatures.has(name) },
}));

jest.mock("@/services/policy", () => ({ policy: { isCreateDashboardEnabled: () => true } }));
jest.mock("@/components/ApplicationArea/navigateTo", () => ({ __esModule: true, default: jest.fn() }));
jest.mock("@/services/recordEvent", () => ({ __esModule: true, default: jest.fn() }));

// eslint-disable-next-line import/first
import { Dashboard } from "@/services/dashboard";
// eslint-disable-next-line import/first
import CreateDashboardDialog from "./CreateDashboardDialog";

/*
  A dashboard's kind is declared when it is made.

  It used to be decided by whichever panel arrived first, which had two costs:
  the question was answered by accident, and the refusal to mix could only ever
  reach the *second* panel -- after somebody had built half a board on the
  strength of the first. It also meant a dashboard with no widgets yet looked
  ordinary, so a new streaming one appeared in the ordinary list and moved out
  of it later, under its author.
*/
function render(props = {}) {
  // The dialog is normally opened through `showModal`; mounting the wrapped
  // component directly needs the dialog object it would be handed.
  const Dialog = CreateDashboardDialog.Component;
  const dialog = {
    props: { visible: true, onCancel: () => {}, afterClose: () => {} },
    close: jest.fn(),
    dismiss: jest.fn(),
  };
  return mount(<Dialog dialog={dialog} {...props} />);
}

function type(wrapper, name) {
  wrapper
    .find("input")
    .first()
    .simulate("change", { target: { value: name } });
  wrapper.update();
}

function save(wrapper) {
  wrapper.find('button[data-test="DashboardSaveButton"]').simulate("click");
}

describe("the new dashboard dialog", () => {
  beforeEach(() => {
    mockFeatures.clear();
    jest.spyOn(Dashboard, "save").mockResolvedValue({ url: "dashboards/1" });
  });

  afterEach(() => {
    jest.restoreAllMocks();
  });

  test("makes an ordinary dashboard by default", () => {
    mockFeatures.add("use_streams");
    const wrapper = render();

    type(wrapper, "Board");
    save(wrapper);

    expect(Dashboard.save).toHaveBeenCalledWith({ name: "Board", kind: "saved" });
  });

  test("and a streaming one when that is where you started from", () => {
    // Opened from the streaming half of the list: the half somebody is looking
    // at is the answer they would give, so it is not asked for again.
    mockFeatures.add("use_streams");
    const wrapper = render({ kind: "streaming" });

    type(wrapper, "Board");
    save(wrapper);

    expect(Dashboard.save).toHaveBeenCalledWith({ name: "Board", kind: "streaming" });
  });

  test("the choice is not offered to somebody who may not stream", () => {
    const wrapper = render();

    expect(wrapper.find('[data-test="DashboardKind"]').exists()).toBe(false);
  });

  // Nor honoured. A link or a stale tab could carry the prop; the dialog is
  // not the thing enforcing the permission -- the server is -- but it must not
  // offer to send a request that is going to be refused.
  test("and is not honoured for them either", () => {
    const wrapper = render({ kind: "streaming" });

    type(wrapper, "Board");
    save(wrapper);

    expect(Dashboard.save).toHaveBeenCalledWith({ name: "Board", kind: "saved" });
  });

  test("the choice is offered to somebody who may", () => {
    mockFeatures.add("use_streams");
    const wrapper = render();

    expect(wrapper.find('[data-test="DashboardKind"]').exists()).toBe(true);
    expect(wrapper.text()).toContain("one refresh interval");
  });
});
