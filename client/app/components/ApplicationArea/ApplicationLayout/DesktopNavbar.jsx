import React from "react";
import cx from "classnames";
import PropTypes from "prop-types";
import { first, includes } from "lodash";
import Dropdown from "antd/lib/dropdown";
import Menu from "antd/lib/menu";
import Link from "@/components/Link";
import PlainButton from "@/components/PlainButton";
import HelpTrigger from "@/components/HelpTrigger";
import CreateDashboardDialog from "@/components/dashboards/CreateDashboardDialog";
import { useCurrentRoute } from "@/components/ApplicationArea/Router";
import { Auth, clientConfig, currentUser } from "@/services/auth";
import { axios } from "@/services/axios";
import settingsMenu from "@/services/settingsMenu";
import logoUrl from "@/assets/images/sqldesk_icon.svg";

import PlusOutlinedIcon from "@ant-design/icons/PlusOutlined";
import QuestionCircleOutlinedIcon from "@ant-design/icons/QuestionCircleOutlined";
import SettingOutlinedIcon from "@ant-design/icons/SettingOutlined";

import VersionInfo from "./VersionInfo";

import "./DesktopNavbar.less";

function NavLink({ href, active, children, ...rest }) {
  return (
    <Link href={href} className={cx("desktop-navbar-link", { "desktop-navbar-link-active": active })} {...rest}>
      {children}
    </Link>
  );
}

NavLink.propTypes = {
  href: PropTypes.string.isRequired,
  active: PropTypes.bool,
  children: PropTypes.node,
};

NavLink.defaultProps = { active: false, children: null };

function useNavbarActiveState() {
  const currentRoute = useCurrentRoute();

  return React.useMemo(
    () => ({
      dashboards: includes(
        [
          "Dashboards.List",
          "Dashboards.Favorites",
          "Dashboards.My",
          "Dashboards.Folder",
          "Dashboards.Folders",
          "Dashboards.ViewOrEdit",
          "Dashboards.LegacyViewOrEdit",
        ],
        currentRoute.id
      ),
      queries: includes(
        [
          "Queries.List",
          "Queries.Favorites",
          "Queries.Archived",
          "Queries.My",
          "Queries.View",
          "Queries.New",
          "Queries.Edit",
        ],
        currentRoute.id
      ),
      dataSources: includes(["DataSources.List"], currentRoute.id),
      alerts: includes(["Alerts.List", "Alerts.New", "Alerts.View", "Alerts.Edit"], currentRoute.id),
      catalog: currentRoute.id === "Catalog",
      streams: includes(["Streams.Topics", "Streams.Query", "Streams.Running"], currentRoute.id),
      admin: includes(
        ["Admin.Overview", "Admin.MCP", "Admin.SystemStatus", "Admin.Jobs", "Admin.OutdatedQueries"],
        currentRoute.id
      ),
    }),
    [currentRoute.id]
  );
}

/*
  The folders, for the Dashboards menu.

  Fetched once when the navbar mounts rather than on every open: the list is
  short, it changes rarely, and a dropdown that waits for a request before it
  can draw is a dropdown that feels broken. A failure leaves it empty, which
  degrades to exactly the menu there was before folders existed.
*/
function useDashboardFolders() {
  const [folders, setFolders] = React.useState([]);

  React.useEffect(() => {
    let live = true;
    axios
      .get("api/dashboard_folders")
      .then((found) => live && setFolders(found || []))
      .catch(() => {});
    return () => {
      live = false;
    };
  }, []);

  return folders;
}

export default function DesktopNavbar() {
  const firstSettingsTab = first(settingsMenu.getAvailableItems());
  const activeState = useNavbarActiveState();
  const folders = useDashboardFolders();

  const canCreateQuery = currentUser.hasPermission("create_query");
  const canCreateDashboard = currentUser.hasPermission("create_dashboard");
  const canCreateAlert = currentUser.hasPermission("list_alerts");
  const canCreate = canCreateQuery || canCreateDashboard || canCreateAlert;

  const createMenu = (
    <Menu className="desktop-navbar-dropdown-menu">
      {canCreateQuery && (
        <Menu.Item key="new-query">
          <Link href="queries/new" data-test="CreateQueryMenuItem">
            New Query
          </Link>
        </Menu.Item>
      )}
      {canCreateDashboard && (
        <Menu.Item key="new-dashboard">
          <PlainButton data-test="CreateDashboardMenuItem" onClick={() => CreateDashboardDialog.showModal()}>
            New Dashboard
          </PlainButton>
        </Menu.Item>
      )}
      {canCreateAlert && (
        <Menu.Item key="new-alert">
          <Link data-test="CreateAlertMenuItem" href="alerts/new">
            New Alert
          </Link>
        </Menu.Item>
      )}
    </Menu>
  );

  // Everything an admin does, in one place. These pages existed already and
  // were reachable only through the profile menu, filed next to "Log out" --
  // which is not where anyone looks when the instance is slow.
  const adminMenu = (
    <Menu className="desktop-navbar-dropdown-menu">
      <Menu.Item key="admin-overview">
        <Link href="admin/overview">Overview</Link>
      </Menu.Item>
      {/*
        MCP lives here rather than in the top row: it is an audit of who
        connected and what they asked for, which is a thing an administrator
        checks, not a place anyone goes between queries.
      */}
      {clientConfig.mcpEnabled && (
        <Menu.Item key="admin-mcp">
          <Link href="admin/mcp">MCP</Link>
        </Menu.Item>
      )}
      <Menu.Item key="admin-status">
        <Link href="admin/status">System Status</Link>
      </Menu.Item>
      <Menu.Item key="admin-jobs">
        <Link href="admin/queries/jobs">RQ Status</Link>
      </Menu.Item>
      <Menu.Item key="admin-outdated">
        <Link href="admin/queries/outdated">Outdated Queries</Link>
      </Menu.Item>
    </Menu>
  );

  /*
    Dashboards opens on all of them, as it always has. The folders are under
    it, each a set with a stated meaning -- which is only useful if people can
    get to them without knowing they exist, hence here rather than only on a
    page of their own.
  */
  const dashboardsMenu = (
    <Menu className="desktop-navbar-dropdown-menu">
      <Menu.Item key="dashboards-all">
        <Link href="dashboards">All dashboards</Link>
      </Menu.Item>
      <Menu.Item key="dashboards-favorites">
        <Link href="dashboards/favorites">Favorites</Link>
      </Menu.Item>
      <Menu.Item key="dashboards-my">
        <Link href="dashboards/my">Mine</Link>
      </Menu.Item>
      {folders.length > 0 && <Menu.Divider />}
      {folders.map((folder) => (
        <Menu.Item key={`folder-${folder.id}`}>
          <Link href={`dashboards/folder/${folder.id}`}>{folder.name}</Link>
        </Menu.Item>
      ))}
      <Menu.Divider />
      <Menu.Item key="dashboards-folders">
        <Link href="dashboards/folders">Browse folders…</Link>
      </Menu.Item>
    </Menu>
  );

  // Streams is a place of its own rather than a kind of query. A topic's
  // window exists only while somebody is watching it, so a saved query over
  // one would run against whatever happened to be there -- which is why the
  // editor does not offer clusters at all and these pages exist instead.
  const streamsMenu = (
    <Menu className="desktop-navbar-dropdown-menu">
      <Menu.Item key="streams-query">
        <Link href="streams/query">Query a stream</Link>
      </Menu.Item>
      <Menu.Item key="streams-running">
        <Link href="streams/running">Running streams</Link>
      </Menu.Item>
      {currentUser.can("manage_streams") && (
        <Menu.Item key="streams-topics">
          <Link href="streams/topics">Manage topics</Link>
        </Menu.Item>
      )}
    </Menu>
  );

  const profileMenu = (
    <Menu className="desktop-navbar-dropdown-menu">
      <Menu.Item key="profile">
        <Link href="users/me">Profile</Link>
      </Menu.Item>
      {/*
        Everybody who may connect a client, not administrators: the page says
        how to point one at SQLDesk and what yours has been doing. Reachable
        only from the Admin menu, nobody without super_admin could find it at
        all -- which was the state before this.

        System Status used to be here. It is in the Admin menu now, and a
        profile menu is not where somebody looks for the queue depth.
      */}
      {currentUser.can("use_mcp") && (
        <Menu.Item key="mcp">
          <Link href="mcp/mine">My MCP</Link>
        </Menu.Item>
      )}
      <Menu.Divider />
      <Menu.Item key="logout">
        <PlainButton data-test="LogOutButton" onClick={() => Auth.logout()}>
          Log out
        </PlainButton>
      </Menu.Item>
      <Menu.Divider />
      <Menu.Item key="version" role="presentation" disabled className="version-info">
        <VersionInfo />
      </Menu.Item>
    </Menu>
  );

  return (
    <nav className="desktop-navbar" aria-label="Main">
      <Link href="./" className="desktop-navbar-brand" aria-label="SQLDesk home">
        <img src={logoUrl} alt="" />
        <span className="desktop-navbar-wordmark">SQLDesk</span>
      </Link>

      <div className="desktop-navbar-links">
        {currentUser.hasPermission("list_dashboards") && (
          <Dropdown overlay={dashboardsMenu} trigger={["click"]} placement="bottomLeft">
            <PlainButton
              className={cx("desktop-navbar-link", { "desktop-navbar-link-active": activeState.dashboards })}
              data-test="DashboardsMenuButton"
            >
              Dashboards
              <i className="fa fa-angle-down m-l-5" aria-hidden="true" />
            </PlainButton>
          </Dropdown>
        )}
        {currentUser.hasPermission("view_query") && (
          <NavLink href="queries" active={activeState.queries}>
            Queries
          </NavLink>
        )}
        {currentUser.hasPermission("list_alerts") && (
          <NavLink href="alerts" active={activeState.alerts}>
            Alerts
          </NavLink>
        )}
        {/*
          Beside the others rather than under Admin: describing a table is
          the work of whoever knows what it is for, and an administrator
          hands that out per group.
        */}
        {currentUser.can("manage_catalog") && (
          <NavLink href="catalog" active={activeState.catalog}>
            Catalog
          </NavLink>
        )}
        {/*
          Shown to anyone who may watch one, and to anyone who may set topics
          up. Watching somebody else's running stream needs neither, but
          somebody with no streams permission at all has nothing to do here.
        */}
        {(currentUser.can("use_streams") || currentUser.can("manage_streams")) && (
          <Dropdown overlay={streamsMenu} trigger={["click"]} placement="bottomLeft">
            <PlainButton
              className={cx("desktop-navbar-link", { "desktop-navbar-link-active": activeState.streams })}
              data-test="StreamsMenuButton"
            >
              Streams
              <i className="fa fa-angle-down m-l-5" aria-hidden="true" />
            </PlainButton>
          </Dropdown>
        )}
        {currentUser.hasPermission("super_admin") && (
          <Dropdown overlay={adminMenu} trigger={["click"]} placement="bottomLeft">
            <PlainButton
              className={cx("desktop-navbar-link", { "desktop-navbar-link-active": activeState.admin })}
              data-test="AdminMenuButton"
            >
              Admin
            </PlainButton>
          </Dropdown>
        )}
      </div>

      <div className="desktop-navbar-spacer" />

      {canCreate && (
        <Dropdown overlay={createMenu} trigger={["click"]} placement="bottomRight">
          <PlainButton className="desktop-navbar-create-button" data-test="CreateButton">
            <PlusOutlinedIcon aria-hidden="true" />
            <span>Create</span>
          </PlainButton>
        </Dropdown>
      )}

      <HelpTrigger showTooltip={false} type="HOME" tabIndex={0} className="desktop-navbar-icon-link">
        <QuestionCircleOutlinedIcon aria-hidden="true" />
        <span className="sr-only">Help</span>
      </HelpTrigger>

      {firstSettingsTab && (
        <Link
          href={firstSettingsTab.path}
          data-test="SettingsLink"
          className={cx("desktop-navbar-icon-link", { "desktop-navbar-link-active": activeState.dataSources })}
        >
          <SettingOutlinedIcon aria-hidden="true" />
          <span className="sr-only">Settings</span>
        </Link>
      )}

      <Dropdown overlay={profileMenu} trigger={["click"]} placement="bottomRight">
        <PlainButton className="desktop-navbar-profile-button" data-test="ProfileDropdown" aria-label="Account menu">
          <img className="profile__image_thumb" src={currentUser.profile_image_url} alt="" />
        </PlainButton>
      </Dropdown>
    </nav>
  );
}
