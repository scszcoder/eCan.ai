/**
 * InstallLocalDialog — install a plugin from a local zip or directory.
 *
 * Two paths:
 *   1. "Browse…" → IPCAPI.showOpenDialog → pick a .zip; falls back to a
 *      manual path input if dialog is unavailable (web mode).
 *   2. Manual path input — user types/pastes an absolute path to either
 *      a .zip or a bundle directory.
 *
 * On confirm: calls plugin.install_local; toast on success/error;
 * caller is responsible for refreshing the plugin list after onInstalled.
 */

import React, { useCallback, useState } from 'react';
import { Modal, Input, Button, Space, Typography, App as AntApp } from 'antd';
import { FolderOpenOutlined } from '@ant-design/icons';
import { useTranslation } from 'react-i18next';
import { IPCAPI } from '@/services/ipc/api';
import { installLocalPlugin } from '@/services/api/pluginApi';

const { Text } = Typography;

export interface InstallLocalDialogProps {
  open: boolean;
  onClose: () => void;
  onInstalled?: (info: { name: string; version: string }) => void;
}

export const InstallLocalDialog: React.FC<InstallLocalDialogProps> = ({
  open,
  onClose,
  onInstalled,
}) => {
  const { t } = useTranslation();
  const { message } = AntApp.useApp();
  const [path, setPath] = useState('');
  const [submitting, setSubmitting] = useState(false);

  const handleBrowse = useCallback(async () => {
    try {
      const ipc = IPCAPI.getInstance();
      const resp = await ipc.showOpenDialog([
        { name: 'Plugin zip', extensions: ['zip'] },
        { name: 'All files', extensions: ['*'] },
      ]);
      if (resp.success && resp.data && !(resp.data as any).cancelled) {
        const picked = (resp.data as any).filePaths?.[0] || (resp.data as any).filePath;
        if (picked) setPath(String(picked));
      }
    } catch (e) {
      message.warning(t('plugins.install.browseUnavailable', 'File browser is not available; please paste an absolute path.'));
    }
  }, [message, t]);

  const handleInstall = useCallback(async () => {
    const trimmed = path.trim();
    if (!trimmed) {
      message.warning(t('plugins.install.pathRequired', 'Please choose a zip file or directory.'));
      return;
    }
    setSubmitting(true);
    try {
      const resp = await installLocalPlugin(trimmed);
      if (resp.success && resp.data) {
        message.success(
          t('plugins.install.success', 'Installed {{name}} v{{version}}', {
            name: resp.data.name,
            version: resp.data.version,
          })
        );
        onInstalled?.({ name: resp.data.name, version: resp.data.version });
        setPath('');
        onClose();
      } else {
        const errMsg = (resp.error?.message || resp.error?.code || 'Unknown error') as string;
        message.error(
          t('plugins.install.failed', 'Install failed: {{msg}}', { msg: errMsg })
        );
      }
    } catch (e: any) {
      message.error(
        t('plugins.install.failed', 'Install failed: {{msg}}', { msg: String(e?.message || e) })
      );
    } finally {
      setSubmitting(false);
    }
  }, [path, message, onClose, onInstalled, t]);

  return (
    <Modal
      open={open}
      onCancel={() => {
        if (!submitting) onClose();
      }}
      title={t('plugins.install.title', 'Install Plugin')}
      footer={[
        <Button key="cancel" onClick={onClose} disabled={submitting}>
          {t('common.cancel', 'Cancel')}
        </Button>,
        <Button key="install" type="primary" onClick={handleInstall} loading={submitting}>
          {t('plugins.install.action', 'Install')}
        </Button>,
      ]}
      destroyOnClose
    >
      <Space direction="vertical" style={{ width: '100%' }} size={12}>
        <Text type="secondary">
          {t(
            'plugins.install.hint',
            'Pick a plugin zip file, or paste an absolute path to a zip OR a bundle directory containing hook.yaml.'
          )}
        </Text>
        <Space.Compact style={{ width: '100%' }}>
          <Input
            placeholder={t('plugins.install.placeholder', 'C:\\path\\to\\bundle.zip OR /abs/path/to/bundle_dir')}
            value={path}
            onChange={(e) => setPath(e.target.value)}
            disabled={submitting}
          />
          <Button icon={<FolderOpenOutlined />} onClick={handleBrowse} disabled={submitting}>
            {t('plugins.install.browse', 'Browse…')}
          </Button>
        </Space.Compact>
      </Space>
    </Modal>
  );
};

export default InstallLocalDialog;
