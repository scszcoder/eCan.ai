/**
 * Plugins page — installed browser-automation hook bundles.
 *
 * Phase 2 layout: left list + right detail (DetailLayout pattern used by
 * Agents/Prompts). Catalog and Updates tabs are designed for but hidden
 * until Phase 3 wires the catalog client.
 */

import React, { useCallback, useEffect, useState } from 'react';
import { Alert, App as AntApp, Layout, Spin } from 'antd';
import styled from '@emotion/styled';
import { useTranslation } from 'react-i18next';
import type { PluginEntry } from '@/services/api/pluginApi';
import { listPlugins, getAutoloadStatus } from '@/services/api/pluginApi';
import PluginListPanel from './components/PluginListPanel';
import PluginDetailPanel from './components/PluginDetailPanel';
import InstallLocalDialog from './components/InstallLocalDialog';

const PageLayout = styled(Layout)`
  height: 100%;
  background: var(--ant-color-bg-container);
`;

const SidePanel = styled.div`
  width: 360px;
  min-width: 280px;
  max-width: 480px;
  border-right: 1px solid var(--ant-color-border-secondary);
  background: var(--ant-color-bg-container);
  display: flex;
  flex-direction: column;
  overflow: hidden;
`;

const MainPanel = styled.div`
  flex: 1;
  background: var(--ant-color-bg-container);
  display: flex;
  flex-direction: column;
  overflow: hidden;
`;

const ErrorBanner = styled.div`
  padding: 12px 24px;
  border-bottom: 1px solid var(--ant-color-border-secondary);
`;

export const Plugins: React.FC = () => {
  const { t } = useTranslation();
  const { message } = AntApp.useApp();

  const [items, setItems] = useState<PluginEntry[]>([]);
  const [loading, setLoading] = useState(false);
  const [selectedName, setSelectedName] = useState<string | null>(null);
  const [installOpen, setInstallOpen] = useState(false);
  const [autoloadErrors, setAutoloadErrors] = useState<
    Array<{ bundle: string; message: string }>
  >([]);

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const resp = await listPlugins('all');
      if (resp.success && resp.data) {
        setItems(resp.data.items);
        // Keep selection if still present; otherwise select first item.
        setSelectedName((current) => {
          if (current && resp.data!.items.some((e) => e.name === current)) return current;
          return resp.data!.items[0]?.name ?? null;
        });
      } else {
        message.error(resp.error?.message || 'Failed to load plugins');
      }
    } catch (e: any) {
      message.error(String(e?.message || e));
    } finally {
      setLoading(false);
    }
  }, [message]);

  const refreshAutoload = useCallback(async () => {
    try {
      const resp = await getAutoloadStatus();
      if (resp.success && resp.data) {
        setAutoloadErrors(
          (resp.data.errors || []).map((e) => ({ bundle: e.bundle, message: e.message }))
        );
      }
    } catch {
      // best-effort; don't surface to user
    }
  }, []);

  useEffect(() => {
    refresh();
    refreshAutoload();
  }, [refresh, refreshAutoload]);

  const selected = items.find((e) => e.name === selectedName) || null;

  return (
    <PageLayout>
      {autoloadErrors.length > 0 ? (
        <ErrorBanner>
          <Alert
            type="warning"
            showIcon
            message={t(
              'plugins.autoloadErrorsTitle',
              '{{n}} plugin(s) failed to warm-load at startup',
              { n: autoloadErrors.length }
            )}
            description={autoloadErrors
              .map((e) => `${e.bundle}: ${e.message}`)
              .join('\n')}
            closable
            onClose={() => setAutoloadErrors([])}
          />
        </ErrorBanner>
      ) : null}
      <Layout style={{ flex: 1, height: '100%', minHeight: 0 }}>
        <SidePanel>
          <Spin spinning={loading} style={{ height: '100%' }}>
            <PluginListPanel
              items={items}
              loading={loading}
              selectedName={selectedName}
              onSelect={setSelectedName}
              onInstallClick={() => setInstallOpen(true)}
              onMutated={refresh}
            />
          </Spin>
        </SidePanel>
        <MainPanel>
          <PluginDetailPanel entry={selected} onMutated={refresh} />
        </MainPanel>
      </Layout>
      <InstallLocalDialog
        open={installOpen}
        onClose={() => setInstallOpen(false)}
        onInstalled={() => refresh()}
      />
    </PageLayout>
  );
};

export default Plugins;
