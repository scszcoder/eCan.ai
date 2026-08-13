/**
 * PluginsSummaryCard — small cross-link card on the Browser Use settings tab.
 *
 * Shows enabled browser-automation plugins as tags + a button that routes
 * to the full Plugins page.
 */

import React, { useEffect, useState } from 'react';
import { Card, Tag, Button, Space, Typography } from 'antd';
import { AppstoreOutlined } from '@ant-design/icons';
import { useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { listPlugins } from '@/services/api/pluginApi';
import type { PluginEntry } from '@/services/api/pluginApi';

const { Text } = Typography;

export const PluginsSummaryCard: React.FC = () => {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [items, setItems] = useState<PluginEntry[]>([]);

  useEffect(() => {
    let cancelled = false;
    listPlugins('all').then((resp) => {
      if (!cancelled && resp.success && resp.data) {
        setItems(resp.data.items);
      }
    });
    return () => {
      cancelled = true;
    };
  }, []);

  const enabled = items.filter((e) => e.enabled);

  return (
    <Card
      size="small"
      style={{ marginBottom: 12 }}
      title={
        <Space size={6}>
          <AppstoreOutlined />
          <Text strong>{t('plugins.settingsCard.title', 'Browser Automation Plugins')}</Text>
        </Space>
      }
      extra={
        <Button type="link" size="small" onClick={() => navigate('/plugins')}>
          {t('plugins.settingsCard.managePlugins', 'Manage Plugins…')}
        </Button>
      }
    >
      <Space wrap>
        <Text type="secondary">{t('plugins.settingsCard.enabledLabel', 'Enabled')}:</Text>
        {enabled.length === 0 ? (
          <Text type="secondary">
            {t('plugins.settingsCard.noneEnabled', 'No plugins enabled.')}
          </Text>
        ) : (
          enabled.map((e) => (
            <Tag key={e.name} color={e.install_source === 'builtin' ? 'default' : 'blue'}>
              {e.name}
            </Tag>
          ))
        )}
      </Space>
    </Card>
  );
};

export default PluginsSummaryCard;
