/**
 * Copyright (c) 2025 Bytedance Ltd. and/or its affiliates
 * SPDX-License-Identifier: MIT
 */

import { FC, useContext, useEffect, useRef, useState, useCallback } from 'react';
import { useTranslation } from 'react-i18next';

import classnames from 'classnames';
import { useClientContext, useService } from '@flowgram.ai/free-layout-editor';
import { Button, Notification, Select, Input, Typography } from '@douyinfe/semi-ui';
import { IconPlay, IconSend } from '@douyinfe/semi-icons';

import { WorkflowRuntimeService } from '../../../plugins/runtime-plugin/runtime-service';
import { SidebarContext } from '../../../context';
import { IconCancel } from '../../../assets/icon-cancel';
import { IPCAPI } from '../../../../../services/ipc/api';
import { isWebPlatform } from '../../../../../config/platform';
import { webAuthSession } from '../../../../../services/auth/webAuthSession';
import { useUserStore } from '../../../../../stores/userStore';
import { useSheetsStore } from '../../../stores/sheets-store';
import { useSkillInfoStore } from '../../../stores/skill-info-store';
import { useRunningNodeStore } from '../../../stores/running-node-store';
import { useRuntimeStateStore } from '../../../stores/runtime-state-store';

import styles from './index.module.less';

interface TestRunSidePanelProps {
  visible: boolean;
  onCancel: () => void;
}

const CHANNEL_LABELS: Record<string, string> = {
  whatsapp_baileys: 'WhatsApp (Baileys)',
  whatsapp:         'WhatsApp (Cloud API)',
  telegram:         'Telegram',
  slack:            'Slack',
  discord:          'Discord',
  dingtalk:         'DingTalk',
  messenger:        'Messenger',
  twitter:          'Twitter / X',
  webchat:          'Web Chat',
};

export const TestRunSidePanel: FC<TestRunSidePanelProps> = ({ visible }) => {
  const { t } = useTranslation('skillEditor');
  try { useService(WorkflowRuntimeService); } catch {}
  const { document } = useClientContext();
  useContext(SidebarContext);
  const ipcApi = IPCAPI.getInstance();
  const username = useUserStore((state) => state.username);
  const skillInfo = useSkillInfoStore((state) => state.skillInfo);
  const breakpoints = useSkillInfoStore((state) => state.breakpoints);
  const runInCloud = useSkillInfoStore((state) => state.runInCloud);
  const hybridCloudMode = useSkillInfoStore((state) => state.hybridCloudMode);
  const localHelperSkillId = useSkillInfoStore((state) => state.localHelperSkillId);
  const localHelperMachine = useSkillInfoStore((state) => state.localHelperMachine);
  const setRunningNodeId = useRunningNodeStore((state) => state.setRunningNodeId);

  const [values] = useState<Record<string, unknown>>({});
  const [isRunning, setRunning] = useState(false);
  const [, setErrors] = useState<string[] | undefined>(undefined);

  // ── Channel test state ────────────────────────────────────────────────────
  interface ChannelInfo {
    id: string;
    label: string;
    enabled: boolean;
    status: string;
  }
  interface TestMessage {
    channel_id: string;
    chat_id: string;
    sender_name: string;
    text: string;
    timestamp: number;
    message_id: string;
    direction: 'in' | 'out';
  }

  const [channels, setChannels] = useState<ChannelInfo[]>([]);
  const [selectedChannel, setSelectedChannel] = useState<string>('');
  const [channelRecipient, setChannelRecipient] = useState('');
  const [channelText, setChannelText] = useState('');
  const [channelSending, setChannelSending] = useState(false);
  const [channelMessages, setChannelMessages] = useState<TestMessage[]>([]);
  const sinceTs = useRef<number>(Date.now() / 1000);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const msgBoxRef = useRef<HTMLDivElement>(null);

  // Load channel list
  useEffect(() => {
    if (!visible) return;
    ipcApi.getChannels().then((resp: any) => {
      if (resp?.success && resp.data?.channels) {
        const list: ChannelInfo[] = Object.entries(resp.data.channels).map(([id, entry]: any) => ({
          id,
          label: CHANNEL_LABELS[id] || id,
          enabled: entry.config?.enabled === true,
          status: entry.status || 'stopped',
        }));
        setChannels(list);
      }
    }).catch(() => {});
  }, [visible]);

  // Poll for inbound messages while panel is open
  useEffect(() => {
    if (!visible) { stopPoll(); return; }
    startPoll();
    return () => stopPoll();
  }, [visible, selectedChannel]);

  const startPoll = () => {
    if (pollRef.current) return;
    pollRef.current = setInterval(async () => {
      try {
        const resp: any = await ipcApi.getChannelTestMessages(
          selectedChannel || undefined,
          sinceTs.current,
        );
        if (resp?.success && resp.data?.messages?.length) {
          const incoming: TestMessage[] = resp.data.messages.map((m: any) => ({
            ...m,
            direction: 'in' as const,
          }));
          setChannelMessages((prev) => [...prev, ...incoming]);
          sinceTs.current = Math.max(...incoming.map((m: any) => m.received_at ?? m.timestamp)) + 0.001;
        }
      } catch {}
    }, 2000);
  };

  const stopPoll = () => {
    if (pollRef.current) { clearInterval(pollRef.current); pollRef.current = null; }
  };

  // Auto-scroll message box
  useEffect(() => {
    if (msgBoxRef.current) msgBoxRef.current.scrollTop = msgBoxRef.current.scrollHeight;
  }, [channelMessages]);

  const onSendChannelMessage = useCallback(async () => {
    if (!selectedChannel || !channelRecipient.trim() || !channelText.trim()) return;
    setChannelSending(true);
    const outMsg: TestMessage = {
      channel_id: selectedChannel,
      chat_id: channelRecipient,
      sender_name: 'Me',
      text: channelText,
      timestamp: Date.now() / 1000,
      message_id: String(Math.random()),
      direction: 'out',
    };
    setChannelMessages((prev) => [...prev, outMsg]);
    try {
      const resp: any = await ipcApi.sendChannelMessage(selectedChannel, channelRecipient, channelText);
      if (!resp?.success) {
        Notification.error({ title: 'Send failed', content: resp?.error?.message || 'Unknown error' });
        setChannelMessages((prev) => prev.filter((m) => m.message_id !== outMsg.message_id));
      } else {
        setChannelText('');
      }
    } catch (e: any) {
      Notification.error({ title: 'Send failed', content: String(e?.message || e) });
    } finally {
      setChannelSending(false);
    }
  }, [selectedChannel, channelRecipient, channelText]);

  const onTestRun = useCallback(() => {
    if (isRunning) {
      // TODO: Implement backend cancel
      setRunning(false);
      setRunningNodeId(null); // Clear indicator on cancel
      try { useRuntimeStateStore.getState().clearAll(); } catch {}
      return;
    }

    // 1. Set the initial state
    setErrors(undefined);
    setRunning(true);
    // Clear all runtime states so badges from previous runs are removed
    try { useRuntimeStateStore.getState().clearAll(); } catch {}
    const startNode = document.toJSON().nodes.find((node: any) => node.id === 'start');
    if (startNode) {
      setRunningNodeId(startNode.id);
    }

    // 2. Use setTimeout to allow the UI to update before proceeding
    setTimeout(async () => {
      if (!username || !skillInfo) {
        Notification.error({ title: t('testrun.cannotRun'), content: t('testrun.missingInfo') });
        setRunning(false);
        setRunningNodeId(null);
        return;
      }

      const diagram = document.toJSON();

      // Create a deep copy to avoid mutating the original diagram state
      const diagramWithBreakpoints = JSON.parse(JSON.stringify(diagram));

      // Inject breakpoint info
      diagramWithBreakpoints.nodes.forEach((node: any) => {
        if (breakpoints.includes(node.id)) {
          if (!node.data) {
            node.data = {};
          }
          node.data.break_point = true;
        }
      });

      // Compose bundle.sheets from sheets-store so backend receives all sheets
      const allSheets = useSheetsStore.getState().getAllSheets();
      const mainSheet = allSheets.sheets.find((s) => s.id === allSheets.mainSheetId) || allSheets.sheets[0];
      const composedDiagram = {
        ...(diagramWithBreakpoints || {}),
        // Ensure workFlow points to main sheet document if available
        ...(mainSheet && mainSheet.document ? { workFlow: mainSheet.document } : {}),
        bundle: {
          sheets: allSheets.sheets.map((s) => ({ name: s.name || s.id, document: s.document || {} })),
        },
      } as any;

      // Build meta_data for cloud runs
      // dev_mode=true enables fixed client_id/run_id for skill editor testing
      // passive_client_id format: {username}_{machine_name} with fallback to SCHOME
      const machineName = localHelperMachine || 'SCHOME';
      const passiveClientId = `${username}_${machineName}`;
      const webJwt = isWebPlatform() ? webAuthSession.getAccessToken() : null;
      const metaData = runInCloud ? {
        dev_mode: true,  // Skill editor always runs in dev mode
        run_in_cloud: true,
        client_id: passiveClientId,
        passive_client_id: passiveClientId,
        run_id: '0123456789',
        hybrid_cloud_mode: hybridCloudMode,
        local_helper_skill_id: localHelperSkillId,
        local_helper_machine: machineName,
        ...(webJwt ? { jwt: webJwt } : {}),
      } : null;

      const skillPayload = {
        ...skillInfo,
        diagram: composedDiagram,
        testInputs: values,
      };

      // Debug logs to verify bundle presence on FE side
      try {
        const sheetNames = (allSheets.sheets || []).map((s) => `${s.id}:${s.name}`);
        // eslint-disable-next-line no-console
        console.debug('[RunSkill][FE] sheets in store:', sheetNames);
        // eslint-disable-next-line no-console
        console.debug('[RunSkill][FE] composedDiagram.workFlow nodes:', (composedDiagram?.workFlow?.nodes || []).length, 'edges:', (composedDiagram?.workFlow?.edges || []).length);
        // eslint-disable-next-line no-console
        console.debug('[RunSkill][FE] composedDiagram.bundle.sheet_count:', (composedDiagram?.bundle?.sheets || []).length);
      } catch {}

      // Send the skill payload to the backend (pass metaData as separate argument)
      const response = await ipcApi.runSkill(username, skillPayload, metaData);

      if (!response.success) {
        setRunning(false);
        setRunningNodeId(null);
        Notification.error({
          title: t('testrun.backendRunFailed'),
          content: response.error?.message || t('testrun.unknownError'),
        });
        setErrors([response.error?.message || t('testrun.unknownError')]);
      }
    }, 0);
  }, [document, isRunning, username, skillInfo, breakpoints, runInCloud, hybridCloudMode, localHelperSkillId, localHelperMachine, setRunningNodeId, values]);

  // Removed input form UI per request: only keep a minimal Start/Cancel button

  const renderButton = (
    <Button
      onClick={onTestRun}
      icon={isRunning ? <IconCancel /> : <IconPlay size="small" />}
      className={classnames(styles.button, {
        [styles.running]: isRunning,
        [styles.default]: !isRunning,
      })}
    >
      {isRunning ? t('testrun.cancel') : t('testrun.testRun')}
    </Button>
  );

  // Minimal floating popup so it doesn't block the canvas
  if (!visible) return null;

  return (
    <div
      style={{
        position: 'fixed',
        right: 16,
        bottom: 16,
        zIndex: 1000,
        background: 'var(--semi-color-bg-1)',
        border: '1px solid var(--semi-color-border)',
        borderRadius: 8,
        boxShadow: '0 2px 8px rgba(0,0,0,0.15)',
        padding: 10,
        display: 'flex',
        flexDirection: 'column',
        gap: 8,
        minWidth: 320,
        maxWidth: 420,
      }}
    >
      {/* Row 1: Test Run + Test Channel buttons + channel selector */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 6, flexWrap: 'wrap' }}>
        {renderButton}

        <Button
          icon={<IconSend size="small" />}
          size="small"
          theme="light"
          disabled={!selectedChannel || channelSending}
          loading={channelSending}
          onClick={onSendChannelMessage}
          style={{ flexShrink: 0 }}
        >
          Test Channel
        </Button>

        <Select
          size="small"
          placeholder="Select channel…"
          value={selectedChannel || undefined}
          onChange={(v) => setSelectedChannel(v as string)}
          style={{ flex: 1, minWidth: 130 }}
          showClear
        >
          {channels.map((ch) => (
            <Select.Option
              key={ch.id}
              value={ch.id}
              disabled={!ch.enabled}
            >
              <span style={{ color: ch.enabled ? undefined : 'var(--semi-color-text-3)' }}>
                {ch.label}
                {!ch.enabled && ' (disabled)'}
              </span>
            </Select.Option>
          ))}
        </Select>
      </div>

      {/* Row 2: Recipient + message input (only when a channel is selected) */}
      {selectedChannel && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
          <Input
            size="small"
            placeholder="Recipient (phone / JID / chat ID)"
            value={channelRecipient}
            onChange={setChannelRecipient}
          />
          <Input
            size="small"
            placeholder="Message to send…"
            value={channelText}
            onChange={setChannelText}
            onEnterPress={onSendChannelMessage}
          />
        </div>
      )}

      {/* Row 3: Test Output — inbound/outbound messages */}
      {(channelMessages.length > 0 || selectedChannel) && (
        <div>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 4 }}>
            <Typography.Text size="small" strong>Test Output</Typography.Text>
            {channelMessages.length > 0 && (
              <Typography.Text
                size="small"
                link
                onClick={() => setChannelMessages([])}
                style={{ cursor: 'pointer', fontSize: 11 }}
              >
                Clear
              </Typography.Text>
            )}
          </div>
          <div
            ref={msgBoxRef}
            style={{
              maxHeight: 200,
              overflowY: 'auto',
              background: 'var(--semi-color-fill-0)',
              borderRadius: 6,
              padding: '6px 8px',
              fontSize: 12,
              display: 'flex',
              flexDirection: 'column',
              gap: 4,
            }}
          >
            {channelMessages.length === 0 ? (
              <Typography.Text type="tertiary" size="small">
                Waiting for messages…
              </Typography.Text>
            ) : (
              channelMessages.map((msg) => (
                <div
                  key={msg.message_id}
                  style={{
                    alignSelf: msg.direction === 'out' ? 'flex-end' : 'flex-start',
                    maxWidth: '85%',
                    background: msg.direction === 'out'
                      ? 'var(--semi-color-primary-light-default)'
                      : 'var(--semi-color-bg-2)',
                    borderRadius: 6,
                    padding: '4px 8px',
                  }}
                >
                  <div style={{ color: 'var(--semi-color-text-2)', fontSize: 10, marginBottom: 2 }}>
                    {msg.direction === 'out' ? 'You' : (msg.sender_name || msg.chat_id)}
                    {' · '}
                    {new Date(msg.timestamp * 1000).toLocaleTimeString()}
                  </div>
                  <div>{msg.text}</div>
                </div>
              ))
            )}
          </div>
        </div>
      )}
    </div>
  );
};
