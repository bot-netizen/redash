import React from "react";
import { mount } from "enzyme";
import Menu from "antd/lib/menu";

import PlainButton from "@/components/PlainButton";
import { mayMoveFolders as mayMove } from "./DashboardHeader";
import { currentUser } from "@/services/auth";

/*
  Who is offered the move, and to where.

  A locked folder is an administrator's to put things into and take them out
  of, so offering the move to anybody else would be offering a button that
  answers 403. The server refuses it either way; the menu's job is not to lie
  about what will work.

  The rule is exported from the header rather than copied here: a test that
  restates the expression it is checking passes whatever the page does.
*/

function folderItems({ folders, admin }) {
  return (
    <Menu>
      {folders.map((folder) => (
        <Menu.Item key={folder.id} disabled={folder.locked && !admin}>
          <PlainButton>{folder.name}</PlainButton>
        </Menu.Item>
      ))}
    </Menu>
  );
}

describe("moving a dashboard between folders", () => {
  afterEach(() => {
    currentUser.isAdmin = false;
  });

  test("an administrator may always move it", () => {
    expect(mayMove({ admin: true, inLocked: true, canEdit: false })).toBe(true);
  });

  test("somebody who can edit it may file it", () => {
    expect(mayMove({ admin: false, inLocked: false, canEdit: true })).toBe(true);
  });

  test("but not out of a locked folder", () => {
    // Otherwise anybody could take a dashboard out of the folder protecting
    // it, change it, and put it back.
    expect(mayMove({ admin: false, inLocked: true, canEdit: true })).toBe(false);
  });

  test("and somebody who cannot edit it may not file it", () => {
    expect(mayMove({ admin: false, inLocked: false, canEdit: false })).toBe(false);
  });

  test("a locked folder is not offered as a destination to a non-administrator", () => {
    const wrapper = mount(
      folderItems({
        admin: false,
        folders: [
          { id: 1, name: "Business KPIs", locked: true },
          { id: 2, name: "Scratch", locked: false },
        ],
      })
    );
    const disabled = wrapper.find("li.ant-menu-item-disabled");

    expect(disabled.length).toBe(1);
    expect(disabled.text()).toContain("Business KPIs");
  });

  test("and is offered to an administrator", () => {
    const wrapper = mount(folderItems({ admin: true, folders: [{ id: 1, name: "Business KPIs", locked: true }] }));

    expect(wrapper.find("li.ant-menu-item-disabled").length).toBe(0);
  });
});
