import React from "react";
import { mount } from "enzyme";
import Tooltip from "@/components/Tooltip";
import VisualizationDescription from "./VisualizationDescription";

/*
  What is worth pinning: nothing is drawn when there is nothing to say (a
  panel's header is crowded enough), the words are on the panel rather than
  behind a hover, and the hover is there only when the words are cut.
*/

describe("a visualization's description", () => {
  afterEach(() => jest.restoreAllMocks());

  test("is not drawn at all when there is none", () => {
    expect(mount(<VisualizationDescription />).find(".visualization-description")).toHaveLength(0);
    expect(mount(<VisualizationDescription description="" />).find(".visualization-description")).toHaveLength(0);
  });

  test("nor when it is only whitespace", () => {
    expect(mount(<VisualizationDescription description="   " />).find(".visualization-description")).toHaveLength(0);
  });

  test("is on the panel as text, not behind a hover", () => {
    const wrapper = mount(<VisualizationDescription description="Weeks since the account opened." />);

    expect(wrapper.find(".visualization-description").text()).toBe("Weeks since the account opened.");
    expect(wrapper.find(Tooltip).prop("title")).toBeNull();
  });

  test("offers the whole of it on hover when two lines cut it", () => {
    jest.spyOn(HTMLElement.prototype, "scrollHeight", "get").mockReturnValue(60);
    jest.spyOn(HTMLElement.prototype, "clientHeight", "get").mockReturnValue(38);

    const wrapper = mount(<VisualizationDescription description="A long account of what this counts." />);
    wrapper.update();

    expect(wrapper.find(Tooltip).prop("title")).toBe("A long account of what this counts.");
  });

  test("is trimmed, so a stray newline is not a description", () => {
    const wrapper = mount(<VisualizationDescription description="  Counts, not sums.  " />);
    expect(wrapper.find(".visualization-description").text()).toBe("Counts, not sums.");
  });
});
