import React from "react";
import Menu from "antd/lib/menu";
import PageHeader from "@/components/PageHeader";
import Link from "@/components/Link";
import location from "@/services/location";
import settingsMenu from "@/services/settingsMenu";

/*
  The settings chrome -- the title and the row of tabs -- around a page.

  It used to take the page's own menu entry as well and register it here, as a
  side effect of importing the page. That stopped working the moment the pages
  became lazily loaded, because the navbar needs the menu before any of them
  has been fetched. The entries are in `pages/settings.menu.js` now, and this
  only draws.
*/
function wrapSettingsTab(WrappedComponent) {
  return function SettingsTab(props) {
    const activeItem = settingsMenu.getActiveItem(location.path);
    return (
      <div className="settings-screen">
        <div className="container">
          <PageHeader title="Settings" />
          <div className="bg-white tiled">
            <Menu selectedKeys={[activeItem && activeItem.title]} selectable={false} mode="horizontal">
              {settingsMenu.getAvailableItems().map((item) => (
                <Menu.Item key={item.title}>
                  <Link href={item.path} data-test="SettingsScreenItem">
                    {item.title}
                  </Link>
                </Menu.Item>
              ))}
            </Menu>
            <div className="p-15">
              <div>
                <WrappedComponent {...props} />
              </div>
            </div>
          </div>
        </div>
      </div>
    );
  };
}

export default wrapSettingsTab;
