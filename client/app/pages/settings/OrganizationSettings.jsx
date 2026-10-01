import React from "react";
import PropTypes from "prop-types";

import Button from "antd/lib/button";
import Form from "antd/lib/form";
import Skeleton from "antd/lib/skeleton";
import wrapSettingsTab from "@/components/SettingsWrapper";

import { getHorizontalFormProps, getHorizontalFormItemWithoutLabelProps } from "@/styles/formStyle";

import useOrganizationSettings from "./hooks/useOrganizationSettings";
import GeneralSettings from "./components/GeneralSettings";
import AuthSettings from "./components/AuthSettings";
import SlackSettings from "./components/SlackSettings";

function OrganizationSettings({ onError }) {
  const { settings, currentValues, isLoading, isSaving, handleSubmit, handleChange } = useOrganizationSettings(onError);
  return (
    <div className="row" data-test="OrganizationSettings">
      <div className="m-r-20 m-l-20">
        <Form {...getHorizontalFormProps()} onFinish={handleSubmit}>
          <GeneralSettings loading={isLoading} settings={settings} values={currentValues} onChange={handleChange} />
          <AuthSettings loading={isLoading} settings={settings} values={currentValues} onChange={handleChange} />
          <Form.Item {...getHorizontalFormItemWithoutLabelProps()}>
            {isLoading ? (
              <Skeleton.Button active />
            ) : (
              <Button type="primary" htmlType="submit" loading={isSaving} data-test="OrganizationSettingsSaveButton">
                Save
              </Button>
            )}
          </Form.Item>
        </Form>
        {/*
          Outside the form on purpose. Everything above is a preference saved
          together; a Slack token is checked against Slack before it is stored,
          so it has its own button and its own answer.
        */}
        <SlackSettings />
      </div>
    </div>
  );
}

OrganizationSettings.propTypes = {
  onError: PropTypes.func,
};

OrganizationSettings.defaultProps = {
  onError: () => {},
};

const OrganizationSettingsPage = wrapSettingsTab(OrganizationSettings);

export default OrganizationSettingsPage;
