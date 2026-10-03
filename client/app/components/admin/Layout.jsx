import React from "react";
import PropTypes from "prop-types";
import Menu from "antd/lib/menu";
import PageHeader from "@/components/PageHeader";
import Link from "@/components/Link";
import { adminTab, adminTabs } from "@/pages/admin/adminTabs";

import "./layout.less";

export default function Layout({ activeTab, children }) {
  const tabs = adminTabs();
  const current = adminTab(activeTab);

  return (
    <div className="admin-page-layout">
      <div className="container">
        <PageHeader title="Admin" />
        <div className="bg-white tiled">
          <Menu selectedKeys={[activeTab]} selectable={false} mode="horizontal">
            {tabs.map((tab) => (
              <Menu.Item key={tab.key}>
                <Link href={tab.path}>{tab.title}</Link>
              </Menu.Item>
            ))}
          </Menu>
          {/*
            What this page is, before the numbers on it. Someone opens this
            section when something is wrong, which is the worst moment to be
            working out which of seven pages holds the figure they are after.
          */}
          {current && <p className="admin-tab-description">{current.description}</p>}
          {children}
        </div>
      </div>
    </div>
  );
}

Layout.propTypes = {
  activeTab: PropTypes.string,
  children: PropTypes.node,
};

Layout.defaultProps = {
  activeTab: "overview",
  children: null,
};
