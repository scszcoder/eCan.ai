/**
 * PluginDetailPanel — right pane: tabbed view of the selected plugin.
 *
 * Tabs: Description / Config / Permissions / Hooks.
 * Actions: Uninstall (with dependents check), Enable/Disable mirror.
 *
 * Phase 2: config form renders the schema but Save is a no-op placeholder
 * (Phase 3 wires plugin.set_config). We surface that clearly in the UI.
 */

import React, { useEffect, useState } from 'react';
import {
  Tabs,
  Typography,
  Space,
  Tag,
  Button,
  Descriptions,
  List,
  Empty,
  Popconfirm,
  Alert,
  Modal,
  App as AntApp,
} from 'antd';
import { DeleteOutlined } from '@ant-design/icons';
import { useTranslation } from 'react-i18next';
import styled from '@emotion/styled';
import type { PluginEntry, PluginDependent } from '@/services/api/pluginApi';
import { pluginDependents, uninstallPlugin } from '@/services/api/pluginApi';
import PluginAutoForm, { JsonSchema } from '@/modules/plugin-bridge/schema-form/PluginAutoForm';
import PluginIframeHost from '@/modules/plugin-bridge/PluginIframeHost';

const { Text, Title, Paragraph } = Typography;

const DetailContainer = styled.div`
  display: flex;
  flex-direction: column;
  height: 100%;
  overflow: hidden;
`;

const Header = styled.div`
  padding: 16px 24px;
  border-bottom: 1px solid var(--ant-color-border-secondary);
  flex-shrink: 0;
`;

const Body = styled.div`
  flex: 1;
  overflow: hidden;
  display: flex;
  flex-direction: column;

  .ant-tabs {
    height: 100%;
  }
  .ant-tabs-content-holder {
    overflow-y: auto;
    padding: 16px 24px;
  }
`;

export interface PluginDetailPanelProps {
  entry: PluginEntry | null;
  onMutated: () => void;
}

export const PluginDetailPanel: React.FC<PluginDetailPanelProps> = ({ entry, onMutated }) => {
  const { t } = useTranslation();
  const { message } = AntApp.useApp();
  const [configDraft, setConfigDraft] = useState<Record<string, unknown>>({});

  // Reset draft whenever selected entry changes.
  useEffect(() => {
    setConfigDraft({ ...(entry?.manifest_summary?.config_defaults || {}) });
  }, [entry?.name]);

  if (!entry) {
    return (
      <DetailContainer>
        <Empty
          image={Empty.PRESENTED_IMAGE_SIMPLE}
          description={t('plugins.detail.noSelection', 'Select a plugin to see details.')}
          style={{ marginTop: 96 }}
        />
      </DetailContainer>
    );
  }

  const isBuiltin = entry.install_source === 'builtin';
  const schema = entry.manifest_summary?.config_schema as JsonSchema | null | undefined;
  // Phase 3: if the plugin declares a config_panel GUI slot, we render
  // the plugin's own iframe instead of the schema-driven auto-form.
  const gui = (entry.manifest_summary as any)?.gui as
    | { slots?: { config_panel?: any } }
    | undefined;
  const hasConfigPanelSlot = !!gui?.slots?.config_panel;

  const handleUninstall = async (force: boolean) => {
    try {
      const resp = await uninstallPlugin(entry.name, { force });
      if (resp.success) {
        message.success(
          t('plugins.detail.uninstallSuccess', 'Uninstalled {{name}}', { name: entry.name })
        );
        onMutated();
      } else {
        const code = resp.error?.code;
        if (code === 'DEPENDENTS_BLOCKED') {
          // Fetch dependents to show in a confirm dialog.
          const depResp = await pluginDependents(entry.name);
          const deps = depResp.success ? depResp.data?.dependents || [] : [];
          showDependentsModal(deps, () => handleUninstall(true));
        } else {
          message.error(resp.error?.message || 'Uninstall failed');
        }
      }
    } catch (e: any) {
      message.error(String(e?.message || e));
    }
  };

  const showDependentsModal = (deps: PluginDependent[], onForce: () => void) => {
    Modal.confirm({
      title: t('plugins.detail.dependentsTitle', '{{name}} is in use', { name: entry.name }),
      content: (
        <Space direction="vertical" style={{ width: '100%' }}>
          <Text>
            {t(
              'plugins.detail.dependentsBody',
              'This plugin is referenced by {{n}} skill node(s):',
              { n: deps.length }
            )}
          </Text>
          <List
            size="small"
            dataSource={deps}
            renderItem={(d) => (
              <List.Item>
                <Text strong>{d.skill_name}</Text>
                <Text type="secondary">→ node {d.node_name || d.node_id}</Text>
              </List.Item>
            )}
          />
          <Alert
            type="warning"
            showIcon
            message={t(
              'plugins.detail.dependentsForceHint',
              'Uninstalling now will leave those nodes referencing a missing plugin. Skills will still load but the plugin will be skipped at runtime.'
            )}
          />
        </Space>
      ),
      okText: t('plugins.detail.uninstallAnyway', 'Uninstall anyway'),
      okButtonProps: { danger: true },
      cancelText: t('common.cancel', 'Cancel'),
      onOk: onForce,
    });
  };

  return (
    <DetailContainer>
      <Header>
        <Space direction="vertical" size={8} style={{ width: '100%' }}>
          <Space style={{ width: '100%', justifyContent: 'space-between' }} align="start">
            <Space direction="vertical" size={2}>
              <Title level={4} style={{ margin: 0 }}>
                {entry.name}
              </Title>
              <Space size={6}>
                <Text type="secondary">v{entry.version}</Text>
                <Tag>{entry.install_source}</Tag>
                {entry.enabled ? (
                  <Tag color="green">{t('plugins.detail.enabled', 'Enabled')}</Tag>
                ) : (
                  <Tag>{t('plugins.detail.disabled', 'Disabled')}</Tag>
                )}
                {entry.signature_status !== 'n/a' ? (
                  <Tag>{entry.signature_status}</Tag>
                ) : null}
              </Space>
            </Space>
            <Popconfirm
              title={t('plugins.detail.uninstallConfirm', 'Uninstall {{name}}?', { name: entry.name })}
              okText={t('common.confirm', 'Confirm')}
              cancelText={t('common.cancel', 'Cancel')}
              onConfirm={() => handleUninstall(false)}
              disabled={isBuiltin}
            >
              <Button danger icon={<DeleteOutlined />} disabled={isBuiltin}>
                {t('plugins.detail.uninstall', 'Uninstall')}
              </Button>
            </Popconfirm>
          </Space>
          {isBuiltin ? (
            <Alert
              type="info"
              showIcon
              message={t(
                'plugins.detail.builtinNotice',
                'This is a built-in plugin shipped with the app and cannot be uninstalled or disabled from here.'
              )}
            />
          ) : null}
        </Space>
      </Header>
      <Body>
        <Tabs
          defaultActiveKey="description"
          items={[
            {
              key: 'description',
              label: t('plugins.detail.tabDescription', 'Description'),
              children: (
                <Descriptions column={1} bordered size="small">
                  <Descriptions.Item label={t('plugins.detail.author', 'Author')}>
                    {entry.manifest_summary?.author || '—'}
                  </Descriptions.Item>
                  <Descriptions.Item label={t('plugins.detail.kind', 'Kind')}>
                    {entry.kind}
                  </Descriptions.Item>
                  <Descriptions.Item label={t('plugins.detail.installPath', 'Install path')}>
                    <Text code copyable={{ text: entry.install_path }} style={{ fontSize: 12 }}>
                      {entry.install_path || '—'}
                    </Text>
                  </Descriptions.Item>
                  <Descriptions.Item label={t('plugins.detail.description', 'Description')}>
                    <Paragraph style={{ margin: 0 }}>
                      {entry.manifest_summary?.description || '—'}
                    </Paragraph>
                  </Descriptions.Item>
                </Descriptions>
              ),
            },
            {
              key: 'config',
              label: t('plugins.detail.tabConfig', 'Config'),
              children: hasConfigPanelSlot ? (
                <PluginIframeHost bundle={entry.name} slot="config_panel" scope="global" />
              ) : (
                <Space direction="vertical" style={{ width: '100%' }} size={12}>
                  <Alert
                    type="info"
                    showIcon
                    message={t(
                      'plugins.detail.configReadOnlyPhase2',
                      'Editing global config is read-only in this preview. Per-node config can be set from the skill editor.'
                    )}
                  />
                  <PluginAutoForm
                    schema={schema as JsonSchema | null | undefined}
                    value={configDraft}
                    onChange={setConfigDraft}
                    disabled
                  />
                </Space>
              ),
            },
            {
              key: 'permissions',
              label: t('plugins.detail.tabPermissions', 'Permissions'),
              children: (
                <PermissionsView hooks={entry.manifest_summary?.hooks || []} />
              ),
            },
            {
              key: 'hooks',
              label: t('plugins.detail.tabHooks', 'Hooks'),
              children: (
                <HooksView hooks={entry.manifest_summary?.hooks || []} />
              ),
            },
          ]}
        />
      </Body>
    </DetailContainer>
  );
};

const HooksView: React.FC<{ hooks: Array<{ name: string; stage: string; runtime: string; tier: number; priority: number }> }> = ({ hooks }) => {
  const { t } = useTranslation();
  if (!hooks.length) {
    return <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={t('plugins.detail.noHooks', 'No hooks declared')} />;
  }
  return (
    <List
      dataSource={hooks}
      renderItem={(h) => (
        <List.Item>
          <Space direction="vertical" size={2}>
            <Space size={6}>
              <Text strong>{h.name}</Text>
              <Tag>{h.stage}</Tag>
              <Tag>{h.runtime}</Tag>
              <Tag>tier {h.tier}</Tag>
              <Tag>priority {h.priority}</Tag>
            </Space>
          </Space>
        </List.Item>
      )}
    />
  );
};

const PermissionsView: React.FC<{ hooks: Array<{ name: string; stage: string; runtime: string; tier: number; priority: number }> }> = ({ hooks }) => {
  const { t } = useTranslation();
  // Phase 2: permissions are per-hook in the manifest; the summary doesn't
  // include them yet (would inflate the IPC payload). We surface stages so
  // users can see the surface area without round-tripping.
  if (!hooks.length) {
    return <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={t('plugins.detail.noPermissions', 'No permission data')} />;
  }
  const stages = Array.from(new Set(hooks.map((h) => h.stage)));
  return (
    <Descriptions column={1} bordered size="small">
      <Descriptions.Item label={t('plugins.detail.stagesObserved', 'Stages observed')}>
        <Space wrap>
          {stages.map((s) => (
            <Tag key={s}>{s}</Tag>
          ))}
        </Space>
      </Descriptions.Item>
      <Descriptions.Item label={t('plugins.detail.tools', 'Tools used')}>
        <Text type="secondary" style={{ fontSize: 12 }}>
          {t('plugins.detail.toolsHint', 'Detailed tool/network permissions live in hook.yaml. Phase 3 of the plugin UI will surface them here.')}
        </Text>
      </Descriptions.Item>
    </Descriptions>
  );
};

export default PluginDetailPanel;
