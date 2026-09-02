import React from 'react';
import { useTranslation } from 'react-i18next';
import { Select, Switch, Button, Input, Row, Col, Tooltip, Divider, Tabs, theme } from 'antd';
import { ReloadOutlined, SaveOutlined } from '@ant-design/icons';
import { FormInstance } from 'antd/es/form';
import styled from '@emotion/styled';
import { StyledFormItem } from '@/components/Common/StyledForm';

const StyledRefreshButton = styled(Button)`
  &,
  &:hover,
  &:focus,
  &:active {
    border-color: transparent !important;
    background: transparent !important;
    box-shadow: none !important;
  }
`;

const StyledSaveButton = styled(Button)`
  color: var(--ant-color-primary) !important;
  font-weight: 500;

  &,
  &:hover,
  &:focus,
  &:active {
    border-color: transparent !important;
    background: transparent !important;
    box-shadow: none !important;
  }
`;

interface GeneralTabContentProps {
  form: FormInstance;
  loading: boolean;
  handleReload: () => void;
  handleNetworkApiEngineChange: (value: string) => void;
  handleOpenUrl: (url: string) => void;
}

export const GeneralTabContent: React.FC<GeneralTabContentProps> = ({
  form,
  loading,
  handleReload,
  handleNetworkApiEngineChange,
  handleOpenUrl,
}) => {
  const { t } = useTranslation();
  const { token } = theme.useToken();

  return (
    <div style={{ 
      height: '100%',
      display: 'flex',
      flexDirection: 'column',
      padding: '0 16px 16px'
    }}>
      <div style={{
        background: token.colorBgContainer,
        borderRadius: 12,
        border: `1px solid ${token.colorBorder}`,
        boxShadow: token.boxShadowTertiary,
        display: 'flex',
        flexDirection: 'column',
        flex: 1,
        minHeight: 0,
        marginTop: 12
      }} className="general-settings-card">
        <Tabs
          type="line"
          size="small"
          className="general-settings-tabs"
          destroyOnHidden={false}
          tabBarExtraContent={(
            <div style={{ display: 'flex', gap: 8, marginRight: 8 }}>
              <StyledSaveButton
                type="text"
                icon={<SaveOutlined />} 
                onClick={() => form.submit()} 
                loading={loading}
                size="small"
              >
                {t('common.save')}
              </StyledSaveButton>
              <Tooltip title={t('common.reload')}>
                <StyledRefreshButton
                  type="text"
                  icon={<ReloadOutlined />}
                  onClick={handleReload}
                  loading={loading}
                  size="small"
                />
              </Tooltip>
            </div>
          )}
          items={[
            {
              key: 'basic',
              label: t('pages.settings.basic_settings'),
              children: (
                <div style={{ height: '100%', overflowY: 'auto', overflowX: 'hidden' }}>
                  <div className="general-settings-panel" style={{ padding: '12px 18px' }}>
                  <Divider orientation="left" style={{ margin: '8px 0 16px 0', fontSize: '14px', fontWeight: 600 }}>
                    {t('pages.settings.basic_mode_settings')}
                  </Divider>
                  <Row gutter={[16, 4]}>
                    <Col span={12}>
                      <StyledFormItem
                        name="debug_mode"
                        label={t('pages.settings.debug_mode')}
                        valuePropName="checked"
                        style={{ marginBottom: '8px' }}
                      >
                        <Switch size="small" />
                      </StyledFormItem>
                    </Col>
                    <Col span={12}>
                      <StyledFormItem
                        name="schedule_mode"
                        label={t('pages.settings.schedule_mode')}
                        style={{ marginBottom: '8px' }}
                      >
                        <Select size="small">
                          <Select.Option value="auto">{t('common.auto')}</Select.Option>
                          <Select.Option value="manual">{t('common.manual')}</Select.Option>
                          <Select.Option value="test">{t('common.test')}</Select.Option>
                        </Select>
                      </StyledFormItem>
                    </Col>
                  </Row>

                  <Divider orientation="left" style={{ margin: '24px 0 16px 0', fontSize: '14px', fontWeight: 600 }}>
                    {t('pages.settings.hardware_settings')}
                  </Divider>
                  <Row gutter={[16, 4]}>
                    <Col span={8}>
                      <StyledFormItem
                        name="default_wifi"
                        label={t('pages.settings.default_wifi')}
                        style={{ marginBottom: '8px' }}
                      >
                        <Input size="small" placeholder="Enter default WiFi" />
                      </StyledFormItem>
                    </Col>
                    <Col span={8}>
                      <StyledFormItem
                        name="default_printer"
                        label={t('pages.settings.default_printer')}
                        style={{ marginBottom: '8px' }}
                      >
                        <Input size="small" placeholder="Enter default printer" />
                      </StyledFormItem>
                    </Col>
                    <Col span={8}>
                      <StyledFormItem
                        name="display_resolution"
                        label={t('pages.settings.display_resolution')}
                        style={{ marginBottom: '8px' }}
                      >
                        <Select size="small">
                          <Select.Option value="D1920X1080">{t('pages.settings.resolution_1920x1080')}</Select.Option>
                          <Select.Option value="D2560X1440">{t('pages.settings.resolution_2560x1440')}</Select.Option>
                          <Select.Option value="D3840X2160">{t('pages.settings.resolution_3840x2160')}</Select.Option>
                        </Select>
                      </StyledFormItem>
                    </Col>
                  </Row>
                </div>
                </div>
              ),
            },
            {
              key: 'network',
              label: t('pages.settings.network_settings'),
              children: (
                <div style={{ height: '100%', overflowY: 'auto', overflowX: 'hidden' }}>
                  <div className="general-settings-panel" style={{ padding: '12px 18px' }}>
                  <Divider orientation="left" style={{ margin: '8px 0 16px 0', fontSize: '14px', fontWeight: 600 }}>
                    {t('pages.settings.engine_port_settings')}
                  </Divider>
                  <Row gutter={[16, 4]}>
                    <Col span={8}>
                      <StyledFormItem
                        name="network_api_engine"
                        label={t('pages.settings.network_api_engine')}
                        style={{ marginBottom: '8px' }}
                        tooltip={t('pages.settings.network_api_engine_tooltip')}
                      >
                        <Select 
                          size="small"
                          onChange={handleNetworkApiEngineChange}
                        >
                          <Select.Option value="lan">LAN</Select.Option>
                          <Select.Option value="wan">WAN</Select.Option>
                        </Select>
                      </StyledFormItem>
                    </Col>
                    <Col span={8}>
                      <StyledFormItem
                        name="schedule_engine"
                        label={t('pages.settings.schedule_engine')}
                        style={{ marginBottom: '8px' }}
                      >
                        <Select size="small">
                          <Select.Option value="lan">LAN</Select.Option>
                          <Select.Option value="wan">WAN</Select.Option>
                        </Select>
                      </StyledFormItem>
                    </Col>
                    <Col span={8}>
                      <StyledFormItem
                        name="local_server_port"
                        label={t('pages.settings.local_server_port')}
                        style={{ marginBottom: '8px' }}
                      >
                        <Input size="small" placeholder="Enter local server port" />
                      </StyledFormItem>
                    </Col>
                  </Row>

                  <Divider orientation="left" style={{ margin: '24px 0 16px 0', fontSize: '14px', fontWeight: 600 }}>
                    {t('pages.settings.database_settings')}
                  </Divider>
                  <Row gutter={[16, 4]}>
                    <Col span={8}>
                      <StyledFormItem
                        name="db_host"
                        label={t('pages.settings.db_host')}
                        style={{ marginBottom: '8px' }}
                      >
                        <Input size="small" placeholder="Enter database host" />
                      </StyledFormItem>
                    </Col>
                    <Col span={8}>
                      <StyledFormItem
                        name="db_port"
                        label={t('pages.settings.db_port')}
                        style={{ marginBottom: '8px' }}
                      >
                        <Input size="small" placeholder="Enter database port" />
                      </StyledFormItem>
                    </Col>
                    <Col span={8}>
                      <StyledFormItem
                        name="db_name"
                        label={t('pages.settings.db_name')}
                        style={{ marginBottom: '8px' }}
                      >
                        <Input size="small" placeholder="Enter database name" />
                      </StyledFormItem>
                    </Col>
                  </Row>
                  <Row gutter={[16, 4]}>
                    <Col span={8}>
                      <StyledFormItem
                        name="db_user"
                        label={t('pages.settings.db_user')}
                        style={{ marginBottom: '8px' }}
                      >
                        <Input size="small" placeholder="Enter database user" />
                      </StyledFormItem>
                    </Col>
                    <Col span={8}>
                      <StyledFormItem
                        name="db_password"
                        label={t('pages.settings.db_password')}
                        style={{ marginBottom: '8px' }}
                      >
                        <Input.Password size="small" placeholder="Enter database password" />
                      </StyledFormItem>
                    </Col>
                    <Col span={8}>
                      <StyledFormItem
                        name="db_pool_size"
                        label={t('pages.settings.db_pool_size')}
                        style={{ marginBottom: '8px' }}
                      >
                        <Input size="small" placeholder="Enter pool size" />
                      </StyledFormItem>
                    </Col>
                  </Row>
                </div>
                </div>
              ),
            },
            {
              key: 'api',
              label: t('pages.settings.api_paths'),
              children: (
                <div style={{ height: '100%', overflowY: 'auto', overflowX: 'hidden' }}>
                  <div className="general-settings-panel" style={{ padding: '12px 18px' }}>
                  <Divider orientation="left" style={{ margin: '8px 0 16px 0', fontSize: '14px', fontWeight: 600 }}>
                    OCR API
                  </Divider>
                  <Row gutter={[16, 4]}>
                    <Col span={12}>
                      <StyledFormItem
                        name="ocr_api_endpoint"
                        label={t('pages.settings.ocr_api_endpoint')}
                        style={{ marginBottom: '8px' }}
                        tooltip={t('pages.settings.ocr_api_endpoint_tooltip')}
                      >
                        <Input 
                          size="small" 
                          placeholder={form.getFieldValue('network_api_engine') === 'lan' 
                            ? 'http://52.204.81.197:8848/graphql/reqScreenTxtRead' 
                            : 'Enter WAN OCR endpoint'
                          }
                        />
                      </StyledFormItem>
                    </Col>
                    <Col span={12}>
                      <StyledFormItem
                        name="ocr_api_key"
                        label={t('pages.settings.ocr_api_key')}
                        style={{ marginBottom: '8px' }}
                      >
                        <Input.Password size="small" placeholder="Enter OCR API key" />
                      </StyledFormItem>
                    </Col>
                  </Row>

                  <Divider orientation="left" style={{ margin: '24px 0 16px 0', fontSize: '14px', fontWeight: 600 }}>
                    WAN API
                  </Divider>
                  <Row gutter={[16, 4]}>
                    <Col span={24}>
                      <StyledFormItem
                        name="wan_api_endpoint"
                        label={t('pages.settings.wan_api_endpoint')}
                        style={{ marginBottom: '8px' }}
                        tooltip={
                          <span>
                            {t('pages.settings.wan_api_endpoint_tooltip')}
                            <Button 
                              type="link" 
                              size="small" 
                              onClick={() => handleOpenUrl('https://www.ecan.ai')}
                              style={{ padding: 0, marginLeft: 4 }}
                            >
                              www.ecan.ai
                            </Button>
                          </span>
                        }
                      >
                        <Input size="small" placeholder="https://www.ecan.ai/graphql" />
                      </StyledFormItem>
                    </Col>
                  </Row>

                  <Divider orientation="left" style={{ margin: '24px 0 16px 0', fontSize: '14px', fontWeight: 600 }}>
                    LAN API
                  </Divider>
                  <Row gutter={[16, 4]}>
                    <Col span={24}>
                      <StyledFormItem
                        name="lan_api_endpoint"
                        label={t('pages.settings.lan_api_endpoint')}
                        style={{ marginBottom: '8px' }}
                        tooltip={
                          <span>
                            {t('pages.settings.lan_api_endpoint_tooltip')}
                            <Button
                              type="link"
                              size="small"
                              onClick={() => handleOpenUrl('http://192.168.1.100:8848')}
                              style={{ padding: 0, marginLeft: 4 }}
                            >
                              http://192.168.1.100:8848
                            </Button>
                          </span>
                        }
                      >
                        <Input size="small" placeholder="http://192.168.1.100:8848/graphql" />
                      </StyledFormItem>
                    </Col>
                  </Row>

                  <Divider orientation="left" style={{ margin: '24px 0 16px 0', fontSize: '14px', fontWeight: 600 }}>
                    Cloud LLM Proxy
                  </Divider>
                  <Row gutter={[16, 4]}>
                    <Col span={8}>
                      <StyledFormItem
                        name="use_lambda_proxy"
                        label="Use Cloud LLM Proxy"
                        valuePropName="checked"
                        style={{ marginBottom: '8px' }}
                        tooltip="Route LLM and embedding calls through a managed cloud proxy instead of using local API keys"
                      >
                        <Switch size="small" />
                      </StyledFormItem>
                    </Col>
                    <Col span={16}>
                      <StyledFormItem
                        name="lambda_proxy_endpoint"
                        label="Proxy Endpoint"
                        style={{ marginBottom: '8px' }}
                        tooltip="Lambda Function URL for the cloud LLM proxy"
                      >
                        <Input size="small" placeholder="https://xxxxxxxxxx.lambda-url.us-east-1.on.aws" />
                      </StyledFormItem>
                    </Col>
                  </Row>
                </div>
                </div>
              ),
            },
            {
              key: 'paths',
              label: t('pages.settings.path_settings'),
              children: (
                <div style={{ height: '100%', overflowY: 'auto', overflowX: 'hidden' }}>
                  <div className="general-settings-panel" style={{ padding: '12px 18px' }}>
                  <Divider orientation="left" style={{ margin: '8px 0 16px 0', fontSize: '14px', fontWeight: 600 }}>
                    {t('pages.settings.path_settings')}
                  </Divider>
                  <Row gutter={[16, 4]}>
                    <Col span={12}>
                      <StyledFormItem
                        name="browser_use_file_system_path"
                        label={t('pages.settings.browser_use_file_system_path')}
                        style={{ marginBottom: '8px' }}
                      >
                        <Input size="small" placeholder="Enter browser file system path" />
                      </StyledFormItem>
                    </Col>
                    <Col span={12}>
                      <StyledFormItem
                        name="build_dom_tree_script_path"
                        label={t('pages.settings.build_dom_tree_script_path')}
                        style={{ marginBottom: '8px' }}
                      >
                        <Input size="small" placeholder="Enter DOM tree script path" />
                      </StyledFormItem>
                    </Col>
                  </Row>
                  <Row gutter={[16, 4]}>
                    <Col span={12}>
                      <StyledFormItem
                        name="skill_code_dir"
                        label={t('pages.settings.skill_code_dir')}
                        style={{ marginBottom: '8px' }}
                      >
                        <Input size="small" placeholder="Enter skill code directory" />
                      </StyledFormItem>
                    </Col>
                    <Col span={12}>
                      <StyledFormItem
                        name="skill_resource_dir"
                        label={t('pages.settings.skill_resource_dir')}
                        style={{ marginBottom: '8px' }}
                      >
                        <Input size="small" placeholder="Enter skill resource directory" />
                      </StyledFormItem>
                    </Col>
                  </Row>

                  <Divider orientation="left" style={{ margin: '24px 0 16px 0', fontSize: '14px', fontWeight: 600 }}>
                    {t('pages.settings.file_tracking_settings')}
                  </Divider>
                  <Row gutter={[16, 4]}>
                    <Col span={12}>
                      <StyledFormItem
                        name="enable_file_tracking"
                        label={t('pages.settings.enable_file_tracking')}
                        valuePropName="checked"
                        style={{ marginBottom: '8px' }}
                      >
                        <Switch size="small" />
                      </StyledFormItem>
                    </Col>
                    <Col span={12}>
                      <StyledFormItem
                        name="file_tracking_interval"
                        label={t('pages.settings.file_tracking_interval')}
                        style={{ marginBottom: '8px' }}
                      >
                        <Input size="small" placeholder="Enter interval (seconds)" />
                      </StyledFormItem>
                    </Col>
                  </Row>

                  <Divider orientation="left" style={{ margin: '24px 0 16px 0', fontSize: '14px', fontWeight: 600 }}>
                    {t('pages.settings.advanced_settings')}
                  </Divider>
                  <Row gutter={[16, 4]}>
                    <Col span={12}>
                      <StyledFormItem
                        name="max_concurrent_tasks"
                        label={t('pages.settings.max_concurrent_tasks')}
                        style={{ marginBottom: '8px' }}
                      >
                        <Input size="small" placeholder="Enter max concurrent tasks" />
                      </StyledFormItem>
                    </Col>
                    <Col span={12}>
                      <StyledFormItem
                        name="task_timeout"
                        label={t('pages.settings.task_timeout')}
                        style={{ marginBottom: '8px' }}
                      >
                        <Input size="small" placeholder="Enter timeout (seconds)" />
                      </StyledFormItem>
                    </Col>
                  </Row>
                  <Row gutter={[16, 4]}>
                    <Col span={24}>
                      <StyledFormItem
                        name="log_level"
                        label={t('pages.settings.log_level')}
                        style={{ marginBottom: '8px' }}
                      >
                        <Select size="small">
                          <Select.Option value="DEBUG">DEBUG</Select.Option>
                          <Select.Option value="INFO">INFO</Select.Option>
                          <Select.Option value="WARNING">WARNING</Select.Option>
                          <Select.Option value="ERROR">ERROR</Select.Option>
                        </Select>
                      </StyledFormItem>
                    </Col>
                  </Row>
                </div>
                </div>
              ),
            },
          ]}
        />
      </div>

      {/* Scoped styles for general-settings-tabs */}
      <style>{`
        .general-settings-tabs {
          height: 100%;
          display: flex;
          flex-direction: column;
        }
        .general-settings-tabs .ant-tabs-nav {
          margin: 0 !important;
          padding: 0 20px !important;
          flex-shrink: 0;
        }
        .general-settings-tabs .ant-tabs-content-holder {
          flex: 1;
          min-height: 0;
          overflow: hidden;
        }
        .general-settings-tabs .ant-tabs-content {
          height: 100%;
        }
        .general-settings-tabs .ant-tabs-tabpane {
          height: 100%;
          padding: 0;
        }
        .general-settings-tabs .ant-tabs-nav-wrap {
          flex-shrink: 0;
        }
      `}</style>
    </div>
  );
};
