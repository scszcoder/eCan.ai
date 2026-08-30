import React, { useState } from 'react';
import { Select, Button, Input, Tooltip, Segmented, Space, Modal } from 'antd';
import { ReloadOutlined, DeleteOutlined, PlusOutlined, FolderOutlined } from '@ant-design/icons';
import type { GlobalToken } from 'antd/es/theme/interface';
import type { TFunction } from 'i18next';

interface Workspace {
  name: string;
  path: string;
  is_valid: boolean;
  created_at: number;
}

interface WorkspaceSelectorProps {
  workspaces: Workspace[];
  currentWorkspace: string;
  loading: boolean;
  onSwitch: (workspaceName: string) => Promise<void>;
  onCreate: (workspaceName: string) => Promise<void>;
  onDelete: (workspaceName: string) => void;
  onRefresh: () => void;
  token: GlobalToken;
  t: TFunction;
}

const WorkspaceSelector: React.FC<WorkspaceSelectorProps> = ({
  workspaces,
  currentWorkspace,
  loading,
  onSwitch,
  onCreate,
  onDelete,
  onRefresh,
  token,
  t
}) => {
  const [mode, setMode] = useState<'switch' | 'create'>('switch');
  const [newWorkspaceName, setNewWorkspaceName] = useState('');
  const [creating, setCreating] = useState(false);
  const CONTROL_HEIGHT = 34;
  const ICON_BUTTON_WIDTH = 34;

  const handleCreate = async () => {
    const trimmedName = newWorkspaceName.trim();
    if (!trimmedName) {
      Modal.warning({
        title: t('pages.knowledge.settings.workspace.error'),
        content: t('pages.knowledge.settings.workspace.nameRequired'),
      });
      return;
    }

    // Check if workspace already exists
    if (workspaces.some(ws => ws.name === trimmedName)) {
      Modal.warning({
        title: t('pages.knowledge.settings.workspace.error'),
        content: t('pages.knowledge.settings.workspace.alreadyExists', { name: trimmedName }),
      });
      return;
    }

    try {
      setCreating(true);
      await onCreate(trimmedName);
      setNewWorkspaceName('');
      setMode('switch');
    } finally {
      setCreating(false);
    }
  };

  const handleSwitch = async (workspaceName: string) => {
    if (workspaceName === currentWorkspace) {
      return;
    }
    await onSwitch(workspaceName);
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
      {/* Mode Selector */}
      <Segmented
        value={mode}
        onChange={(value) => setMode(value as 'switch' | 'create')}
        options={[
          {
            label: (
              <Space>
                <FolderOutlined />
                {t('pages.knowledge.settings.workspace.switchMode')}
              </Space>
            ),
            value: 'switch',
          },
          {
            label: (
              <Space>
                <PlusOutlined />
                {t('pages.knowledge.settings.workspace.createMode')}
              </Space>
            ),
            value: 'create',
          },
        ]}
        block
        size="middle"
        style={{ minHeight: CONTROL_HEIGHT, padding: 3, borderRadius: 10, background: token.colorFillTertiary }}
      />

      {/* Switch Mode */}
      {mode === 'switch' && (
        <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
          <Select
            value={currentWorkspace}
            onChange={handleSwitch}
            style={{ flex: 1 }}
            size="middle"
            loading={loading}
            showSearch
            allowClear={false}
            placeholder={t('pages.knowledge.settings.workspace.selectPlaceholder')}
            popupMatchSelectWidth
            styles={{ popup: { root: { borderRadius: 10, padding: 4 } } }}
            options={workspaces.map(ws => ({
              label: (
                <Space>
                  <FolderOutlined style={{ color: ws.is_valid ? token.colorPrimary : token.colorTextTertiary }} />
                  <span style={{ fontWeight: ws.name === currentWorkspace ? 600 : 400 }}>{ws.name}</span>
                  {!ws.is_valid && (
                    <span style={{ fontSize: 11, color: token.colorTextTertiary }}>
                      ({t('pages.knowledge.settings.workspace.empty')})
                    </span>
                  )}
                </Space>
              ),
              value: ws.name,
            }))}
          />
          <Tooltip title={t('pages.knowledge.settings.workspace.refresh')}>
            <Button
              icon={<ReloadOutlined />}
              onClick={onRefresh}
              loading={loading}
              size="middle"
              style={{
                height: CONTROL_HEIGHT,
                minWidth: ICON_BUTTON_WIDTH,
                borderRadius: 9,
                display: 'inline-flex',
                alignItems: 'center',
                justifyContent: 'center'
              }}
            />
          </Tooltip>
          {currentWorkspace && (
            <Tooltip title={t('pages.knowledge.settings.workspace.delete')}>
              <Button
                icon={<DeleteOutlined />}
                onClick={() => onDelete(currentWorkspace)}
                danger
                size="middle"
              style={{
                  height: CONTROL_HEIGHT,
                  minWidth: ICON_BUTTON_WIDTH,
                  borderRadius: 9,
                  display: 'inline-flex',
                  alignItems: 'center',
                  justifyContent: 'center'
                }}
              />
            </Tooltip>
          )}
        </div>
      )}

      {/* Create Mode */}
      {mode === 'create' && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
          <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
            <Input
              value={newWorkspaceName}
              onChange={(e) => setNewWorkspaceName(e.target.value)}
              placeholder={t('pages.knowledge.settings.workspace.newPlaceholder')}
              size="middle"
              style={{ flex: 1 }}
              onPressEnter={handleCreate}
              disabled={creating}
              prefix={<FolderOutlined style={{ color: token.colorTextTertiary }} />}
            />
            <Button
              type="primary"
              size="middle"
              onClick={handleCreate}
              loading={creating}
              disabled={!newWorkspaceName.trim()}
              style={{ height: CONTROL_HEIGHT }}
            >
              {t('common.create')}
            </Button>
          </div>
          <div style={{ 
            fontSize: 12, 
            color: token.colorTextSecondary,
            paddingLeft: 4
          }}>
            {t('pages.knowledge.settings.workspace.createHint')}
          </div>
        </div>
      )}
    </div>
  );
};

export default WorkspaceSelector;
