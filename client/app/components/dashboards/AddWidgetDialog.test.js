jest.mock("@/services/auth", () => ({
  Auth: { getApiKey: () => null, isAuthenticated: () => true },
  clientConfig: {},
  currentUser: { id: 1, name: "Iqbal", profile_image_url: "", hasPermission: () => true, can: () => false },
}));

jest.mock("@/services/axios", () => ({
  axios: {
    get: () => Promise.resolve([]),
    post: () => Promise.resolve({}),
    interceptors: { request: { use: () => {} }, response: { use: () => {} } },
  },
}));

// eslint-disable-next-line import/first
import React from "react";
// eslint-disable-next-line import/first
import { mount } from "enzyme";
// eslint-disable-next-line import/first
import QuerySelector from "@/components/QuerySelector";
// eslint-disable-next-line import/first
import AddWidgetDialog from "./AddWidgetDialog";

/*
  The dialog asks for the half the dashboard can hold.

  Which half is not a detail: a dashboard shows streams or saved queries and
  never both, and the server refuses the mixture. Asking for the wrong half
  would offer somebody exactly the queries that cannot go on the board they
  are looking at -- and would look, from the inside, like the dashboard having
  no queries to choose from.
*/
function kindOffered(dashboard) {
  const Dialog = AddWidgetDialog.Component;
  const dialog = {
    props: { visible: true, okButtonProps: {}, onCancel: () => {}, afterClose: () => {} },
    close: jest.fn(),
    dismiss: jest.fn(),
  };
  const wrapper = mount(<Dialog dialog={dialog} dashboard={dashboard} />);
  return wrapper.find(QuerySelector).prop("kind");
}

describe("the add widget dialog", () => {
  // Enough of a dashboard for the dialog: it reads the existing parameters to
  // offer mappings.
  const board = (streaming) => ({
    id: 1,
    is_streaming: streaming,
    widgets: [],
    getParametersDefs: () => [],
  });

  test("offers saved queries to an ordinary dashboard", () => {
    expect(kindOffered(board(false))).toBe("saved");
  });

  test("and streaming queries to a streaming one", () => {
    expect(kindOffered(board(true))).toBe("streaming");
  });
});
