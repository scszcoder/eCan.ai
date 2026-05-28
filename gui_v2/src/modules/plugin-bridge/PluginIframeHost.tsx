/**
 * PluginIframeHost — mounts a sandboxed iframe + BridgeHost for one
 * plugin GUI slot.
 *
 * Phase 3 scope: config_panel (global scope) and status_widget.
 * node_config requires per-node scope wiring on the skill-editor side
 * and is supported by the component but called by skill-editor code,
 * not by Plugins page.
 */

import React, { useEffect, useRef, useState } from 'react';
import { Alert, App as AntApp, Spin } from 'antd';
import styled from '@emotion/styled';
import { useTranslation } from 'react-i18next';
import { ipcApi } from '@/services/ipc/api';
import { BridgeHost } from './bridge-host';
import type { BridgeMethod, BridgeHostContext } from './bridge-protocol';
import { DEFAULT_BRIDGE_METHODS } from './bridge-protocol';

const IframeBox = styled.div<{ $h: number }>`
  width: 100%;
  border: 1px solid var(--ant-color-border-secondary);
  border-radius: 4px;
  overflow: hidden;
  height: ${({ $h }) => $h}px;
  transition: height 200ms ease;

  iframe {
    width: 100%;
    height: 100%;
    border: 0;
    display: block;
  }
`;

export interface PluginIframeHostProps {
  bundle: string;
  slot: 'config_panel' | 'node_config' | 'status_widget';
  scope?: 'global' | 'node';
  nodeRef?: { skill_id: string; node_id: string };
  /** Theme passed to iframe context; default reads from document attr. */
  theme?: 'light' | 'dark';
  locale?: string;
  /** Override initial height; iframe can later request resize. */
  initialHeight?: number;
}

interface SlotInfo {
  url: string;
  expectedOrigin: string;
  initialHeight: number;
  allowedMethods: BridgeMethod[];
  toolsUi: string[];
  hostApiVersion: number;
}

async function loadSlotInfo(
  bundle: string,
  slot: string,
  fallbackHeight: number
): Promise<SlotInfo | null> {
  const resp = await ipcApi.executeRequest<{
    url: string | null;
    port: number;
    slots: string[];
    slot_config: { entrypoint: string; height?: number } | null;
  }>('plugin.get_gui_url', { bundle, slot });

  if (!resp.success || !resp.data || !resp.data.url) {
    return null;
  }

  // Fetch the bundle's gui block to get permissions allowlist + tools_ui.
  // (Phase 3: we read from PluginEntry; manifest_summary doesn't include gui
  // permissions yet, so use defaults until plugin.get exposes them.)
  let allowedMethods: BridgeMethod[] = DEFAULT_BRIDGE_METHODS;
  let toolsUi: string[] = [];
  let hostApiVersion = 1;

  const detail = await ipcApi.executeRequest<{ item: any }>('plugin.get', { bundle });
  if (detail.success && detail.data?.item) {
    const gui = detail.data.item?.manifest_summary?.gui as any;
    if (gui && typeof gui === 'object') {
      const perms = gui.permissions || {};
      if (Array.isArray(perms.bridge_methods) && perms.bridge_methods.length > 0) {
        allowedMethods = perms.bridge_methods as BridgeMethod[];
      }
      if (Array.isArray(perms.tools_ui)) {
        toolsUi = perms.tools_ui as string[];
      }
      if (typeof gui.host_api_version === 'number') {
        hostApiVersion = gui.host_api_version;
      }
    }
  }

  const url = new URL(resp.data.url);
  return {
    url: resp.data.url,
    expectedOrigin: `${url.protocol}//${url.host}`,
    initialHeight: resp.data.slot_config?.height || fallbackHeight,
    allowedMethods,
    toolsUi,
    hostApiVersion,
  };
}

export const PluginIframeHost: React.FC<PluginIframeHostProps> = ({
  bundle,
  slot,
  scope = 'global',
  nodeRef,
  theme,
  locale,
  initialHeight = 480,
}) => {
  const { t, i18n } = useTranslation();
  const { message } = AntApp.useApp();
  const iframeRef = useRef<HTMLIFrameElement>(null);
  const hostRef = useRef<BridgeHost | null>(null);
  const [info, setInfo] = useState<SlotInfo | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [height, setHeight] = useState(initialHeight);

  // Resolve slot URL on bundle/slot change.
  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    setInfo(null);
    loadSlotInfo(bundle, slot, initialHeight)
      .then((next) => {
        if (cancelled) return;
        if (!next) {
          setError(t('plugins.iframe.notDeclared', 'This plugin does not declare a {{slot}} GUI slot.', { slot }));
          return;
        }
        setInfo(next);
        setHeight(next.initialHeight);
      })
      .catch((e) => {
        if (!cancelled) setError(String(e?.message || e));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [bundle, slot, initialHeight, t]);

  // Mount/unmount BridgeHost as iframe + info come/go.
  useEffect(() => {
    if (!info || !iframeRef.current) return;
    const detectedTheme: 'dark' | 'light' = theme || (
      document.documentElement.getAttribute('data-theme') === 'dark' ? 'dark' : 'light'
    );
    const detectedLocale = locale || i18n.language || 'en';
    const host = new BridgeHost(iframeRef.current, {
      bundle,
      scope,
      nodeRef,
      allowedMethods: info.allowedMethods,
      toolsUi: info.toolsUi,
      expectedOrigin: info.expectedOrigin,
      onResize: (h) => setHeight(h),
      onNotify: ({ type, msg }) => {
        const m: any = message;
        if (m && typeof m[type] === 'function') m[type](msg);
      },
      getContext: () => ({
        theme: detectedTheme,
        locale: detectedLocale,
        host_api_version: info.hostApiVersion,
      } as Pick<BridgeHostContext, 'theme' | 'locale' | 'agent_id' | 'host_api_version'>),
    });
    hostRef.current = host;
    return () => {
      host.dispose();
      hostRef.current = null;
    };
  }, [info, bundle, scope, nodeRef, theme, locale, i18n.language, message]);

  if (loading) {
    return <Spin />;
  }
  if (error) {
    return <Alert type="info" showIcon message={error} />;
  }
  if (!info) {
    return null;
  }
  return (
    <IframeBox $h={height}>
      <iframe
        ref={iframeRef}
        src={info.url}
        sandbox="allow-scripts"
        title={`${bundle} / ${slot}`}
      />
    </IframeBox>
  );
};

export default PluginIframeHost;
