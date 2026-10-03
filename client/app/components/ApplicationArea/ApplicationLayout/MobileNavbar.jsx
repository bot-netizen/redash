import React from "react";
import PropTypes from "prop-types";
import Button from "antd/lib/button";
import MenuOutlinedIcon from "@ant-design/icons/MenuOutlined";
import Dropdown from "antd/lib/dropdown";
import Menu from "antd/lib/menu";
import Link from "@/components/Link";
import { Auth, currentUser } from "@/services/auth";
import settingsMenu from "@/services/settingsMenu";
import { adminTabs } from "@/pages/admin/adminTabs";
import logoUrl from "@/assets/images/sqldesk_icon.svg";

import "./MobileNavbar.less";

/*
  The same places as the desktop bar, flattened into one list.

  No descriptions and no nesting: a submenu inside a dropdown on a phone is a
  target nobody hits, and a three-line hint under every entry would make this
  longer than the screen. Group headings carry the shape instead.
*/
export default function MobileNavbar({ getPopupContainer }) {
  const settingsTabs = settingsMenu.getAvailableItems();
  const canUseStreams = currentUser.can("use_streams") || currentUser.can("manage_streams");

  return (
    <div className="mobile-navbar">
      <div className="mobile-navbar-logo">
        <Link href="./">
          <img src={logoUrl} alt="SQLDesk" />
        </Link>
      </div>
      <div>
        <Dropdown
          overlayStyle={{ minWidth: 200 }}
          trigger={["click"]}
          getPopupContainer={getPopupContainer} // so the overlay menu stays with the fixed header when page scrolls
          overlay={
            <Menu mode="vertical" theme="dark" selectable={false} className="mobile-navbar-menu">
              {currentUser.hasPermission("list_dashboards") && (
                <Menu.Item key="dashboards">
                  <Link href="dashboards">Dashboards</Link>
                </Menu.Item>
              )}
              {currentUser.hasPermission("view_query") && (
                <Menu.Item key="queries">
                  <Link href="queries">Queries</Link>
                </Menu.Item>
              )}
              {canUseStreams && (
                <Menu.ItemGroup key="streams" title="Kafka Streams">
                  <Menu.Item key="streams-query">
                    <Link href="streams/query">Streaming Query</Link>
                  </Menu.Item>
                  <Menu.Item key="streams-dashboards">
                    <Link href="dashboards/streaming">Streaming Dashboards</Link>
                  </Menu.Item>
                  <Menu.Item key="streams-running">
                    <Link href="streams/running">Running Streams</Link>
                  </Menu.Item>
                  {currentUser.can("manage_streams") && (
                    <Menu.Item key="streams-topics">
                      <Link href="streams/topics">Manage Topics</Link>
                    </Menu.Item>
                  )}
                </Menu.ItemGroup>
              )}
              {currentUser.can("manage_catalog") && (
                <Menu.Item key="catalog">
                  <Link href="catalog">Catalog</Link>
                </Menu.Item>
              )}
              {currentUser.hasPermission("list_alerts") && (
                <Menu.Item key="alerts">
                  <Link href="alerts">Alerts</Link>
                </Menu.Item>
              )}
              {settingsTabs.length > 0 && (
                <Menu.ItemGroup key="settings" title="Settings">
                  {settingsTabs.map((tab) => (
                    <Menu.Item key={`settings-${tab.id || tab.path}`}>
                      <Link href={tab.path}>{tab.title}</Link>
                    </Menu.Item>
                  ))}
                </Menu.ItemGroup>
              )}
              {currentUser.hasPermission("super_admin") && (
                <Menu.ItemGroup key="admin" title="Admin">
                  {adminTabs().map((tab) => (
                    <Menu.Item key={`admin-${tab.key}`}>
                      <Link href={tab.path}>{tab.title}</Link>
                    </Menu.Item>
                  ))}
                </Menu.ItemGroup>
              )}
              <Menu.Divider />
              {/* How to point a client at SQLDesk, and what yours has been
                  doing -- every user's business, not only an
                  administrator's. */}
              {currentUser.can("use_mcp") && (
                <Menu.Item key="mcp">
                  <Link href="mcp/mine">My MCP</Link>
                </Menu.Item>
              )}
              <Menu.Item key="help">
                {/* eslint-disable-next-line react/jsx-no-target-blank */}
                <Link href="https://bot-netizen.github.io/sqldesk" target="_blank" rel="noopener">
                  Help
                </Link>
              </Menu.Item>
              <Menu.Item key="logout" onClick={() => Auth.logout()}>
                Log out
              </Menu.Item>
            </Menu>
          }
        >
          <Button className="mobile-navbar-toggle-button" ghost>
            <MenuOutlinedIcon />
          </Button>
        </Dropdown>
      </div>
    </div>
  );
}

MobileNavbar.propTypes = {
  getPopupContainer: PropTypes.func,
};

MobileNavbar.defaultProps = {
  getPopupContainer: null,
};
