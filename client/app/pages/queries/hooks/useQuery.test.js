import React from "react";
import { mount } from "enzyme";

import useQuery from "./useQuery";

/*
  Whether the editor thinks there is something unsaved.

  `isDirty` is the editor's SQL measured against a baseline, and the baseline
  used to move only when somebody saved. Restoring a version is the first thing
  that changes the SQL from outside the editor: it has already been written, so
  an editor that called it unsaved would warn on the way out about losing text
  the server is already holding.
*/
function Probe({ query }) {
  const state = useQuery(query);
  return (
    <div>
      <span className="dirty">{String(state.isDirty)}</span>
      <button className="edit" onClick={() => state.setQuery({ ...state.query, query: "select 2" })} />
      <button className="edit-again" onClick={() => state.setQuery({ ...state.query, query: "select 3" })} />
      <button className="restore" onClick={() => state.markSaved({ ...state.query, query: "select 2" })} />
    </div>
  );
}

const query = () => ({ id: 1, query: "select 1", options: { apply_auto_limit: true } });

describe("useQuery", () => {
  const dirty = (wrapper) => wrapper.find(".dirty").text();

  test("a fresh query is not dirty", () => {
    expect(dirty(mount(<Probe query={query()} />))).toBe("false");
  });

  test("editing the SQL makes it dirty", () => {
    const wrapper = mount(<Probe query={query()} />);

    wrapper.find(".edit").simulate("click");

    expect(dirty(wrapper)).toBe("true");
  });

  test("but a change the server already holds does not", () => {
    const wrapper = mount(<Probe query={query()} />);

    wrapper.find(".restore").simulate("click");

    expect(dirty(wrapper)).toBe("false");
  });

  test("the baseline moves with it, so the next edit is dirty again", () => {
    const wrapper = mount(<Probe query={query()} />);

    wrapper.find(".restore").simulate("click");
    wrapper.find(".edit-again").simulate("click");

    expect(dirty(wrapper)).toBe("true");
  });

  test("and typing the restored text back is not dirty", () => {
    // The baseline is the restored version, not whatever the page opened with.
    const wrapper = mount(<Probe query={query()} />);

    wrapper.find(".restore").simulate("click");
    wrapper.find(".edit-again").simulate("click");
    wrapper.find(".edit").simulate("click");

    expect(dirty(wrapper)).toBe("false");
  });
});
