import React, { useState, useCallback } from 'react';
import { useTranslation } from 'react-i18next';
import { 
  Button, 
  Table, 
  Tag, 
  Space, 
  Tooltip, 
  App, 
  Empty,
  Badge,
  Select,
  Typography
} from 'antd';
import { 
  ReloadOutlined, 
  GlobalOutlined, 
  ApiOutlined
} from '@ant-design/icons';
import type { ColumnsType } from 'antd/es/table';
import { get_ipc_api } from '@/services/ipc_api';

const { Text, Link } = Typography;

interface RyoAISDevice {
  name: string;
  device_uuid: string;
  short_uuid: string;
  hostname: string;
  addresses: string[];
  port: number;
  url: string;
  environment: string;
  version: string;
  api_types: string[];
  description: string;
  properties: Record<string, string>;
  discovered_at: number;
}

interface RyoaisManagementProps {
  username?: string;
  devices?: RyoAISDevice[];
  onDevicesChange?: (devices: RyoAISDevice[]) => void;
}

const RyoaisManagement: React.FC<RyoaisManagementProps> = ({ 
  username, 
  devices: externalDevices = [],
  onDevicesChange 
}) => {
  const { t } = useTranslation();
  const { message } = App.useApp();
  const [loading, setLoading] = useState(false);
  const [scanTimeout, setScanTimeout] = useState(5);
  
  // Use external devices if provided, otherwise use local state
  const devices = externalDevices;

  // Scan for devices
  const handleScan = useCallback(async () => {
    try {
      setLoading(true);
      console.log('[RyoAIS] Starting device scan...');

      const response = await get_ipc_api().executeRequest<{
        devices: RyoAISDevice[];
        count: number;
        scan_duration: number;
      }>('ryoais.scanDevices', {
        timeout: scanTimeout,
        environment: 'production'
      });

      if (response && response.success && response.data) {
        const discoveredDevices = response.data.devices || [];
        
        // Update parent component's state if callback provided
        if (onDevicesChange) {
          onDevicesChange(discoveredDevices);
        }
        
        if (discoveredDevices.length > 0) {
          message.success(t('pages.settings.ryoais.scan_success', { count: discoveredDevices.length }));
        } else {
          message.info(t('pages.settings.ryoais.no_devices_found'));
        }
        
        console.log('[RyoAIS] Scan complete:', discoveredDevices);
      } else {
        console.error('[RyoAIS] Scan failed:', response);
        message.error(t('pages.settings.ryoais.scan_failed'));
      }
    } catch (error) {
      console.error('[RyoAIS] Error scanning devices:', error);
      message.error(t('pages.settings.ryoais.scan_error'));
    } finally {
      setLoading(false);
    }
  }, [scanTimeout, message, t, onDevicesChange]);

  // Open device URL in browser
  const handleOpenDevice = useCallback((url: string) => {
    try {
      window.open(url, '_blank', 'noopener,noreferrer');
      message.success(t('pages.settings.ryoais.opened_device'));
    } catch (error) {
      console.error('[RyoAIS] Error opening device URL:', error);
      message.error(t('pages.settings.ryoais.open_error'));
    }
  }, [message, t]);

  // Get device info
  const handleGetInfo = useCallback(async (url: string) => {
    try {
      console.log('[RyoAIS] Fetching device info:', url);
      
      const response = await get_ipc_api().executeRequest<{
        device_info: any;
        url: string;
      }>('ryoais.getDeviceInfo', { url });

      if (response && response.success && response.data) {
        const info = response.data.device_info;
        
        // Show device info in a message
        const infoText = `
Device: ${info.hostname || 'Unknown'}
UUID: ${info.device_uuid || 'Unknown'}
Environment: ${info.environment || 'Unknown'}
Version: ${info.api_version || 'Unknown'}
APIs: ${info.supported_apis?.join(', ') || 'Unknown'}
        `.trim();
        
        message.info({
          content: (
            <pre style={{ margin: 0, whiteSpace: 'pre-wrap', fontSize: '12px' }}>
              {infoText}
            </pre>
          ),
          duration: 5
        });
      } else {
        message.error(t('pages.settings.ryoais.info_failed'));
      }
    } catch (error) {
      console.error('[RyoAIS] Error getting device info:', error);
      message.error(t('pages.settings.ryoais.info_error'));
    }
  }, [message, t]);

  // No auto-scan - user must click the scan button manually
  // This prevents unnecessary scans when switching tabs

  // Table columns
  const columns: ColumnsType<RyoAISDevice> = [
    {
      title: t('pages.settings.ryoais.column_device'),
      dataIndex: 'hostname',
      key: 'hostname',
      width: 200,
      render: (hostname: string, record: RyoAISDevice) => (
        <Space direction="vertical" size={0}>
          <Text strong>{hostname}</Text>
          <Text type="secondary" style={{ fontSize: '12px' }}>
            {record.short_uuid}
          </Text>
        </Space>
      ),
    },
    {
      title: t('pages.settings.ryoais.column_address'),
      dataIndex: 'url',
      key: 'url',
      width: 250,
      render: (url: string, record: RyoAISDevice) => (
        <Space direction="vertical" size={0}>
          <Link onClick={() => handleOpenDevice(url)} style={{ fontSize: '13px' }}>
            {url}
          </Link>
          <Text type="secondary" style={{ fontSize: '11px' }}>
            {record.addresses[0]} : {record.port}
          </Text>
        </Space>
      ),
    },
    {
      title: t('pages.settings.ryoais.column_environment'),
      dataIndex: 'environment',
      key: 'environment',
      width: 120,
      render: (environment: string) => {
        const colorMap: Record<string, string> = {
          production: 'green',
          development: 'blue',
          testing: 'orange',
          unknown: 'default'
        };
        return (
          <Tag color={colorMap[environment] || 'default'}>
            {environment.toUpperCase()}
          </Tag>
        );
      },
    },
    {
      title: t('pages.settings.ryoais.column_version'),
      dataIndex: 'version',
      key: 'version',
      width: 100,
      render: (version: string) => (
        <Text style={{ fontSize: '12px' }}>{version}</Text>
      ),
    },
    {
      title: t('pages.settings.ryoais.column_apis'),
      dataIndex: 'api_types',
      key: 'api_types',
      width: 150,
      render: (apiTypes: string[]) => (
        <Space size={4} wrap>
          {apiTypes.map((api) => (
            <Tag key={api} style={{ fontSize: '11px', margin: 0 }}>
              {api}
            </Tag>
          ))}
        </Space>
      ),
    },
    {
      title: t('pages.settings.ryoais.column_status'),
      key: 'status',
      width: 100,
      render: () => (
        <Badge status="success" text={t('pages.settings.ryoais.status_online')} />
      ),
    },
    {
      title: t('pages.settings.ryoais.column_actions'),
      key: 'actions',
      width: 180,
      render: (_: any, record: RyoAISDevice) => (
        <Space size="small">
          <Tooltip title={t('pages.settings.ryoais.action_open')}>
            <Button
              type="link"
              size="small"
              icon={<GlobalOutlined />}
              onClick={() => handleOpenDevice(record.url)}
            />
          </Tooltip>
          <Tooltip title={t('pages.settings.ryoais.action_info')}>
            <Button
              type="link"
              size="small"
              icon={<ApiOutlined />}
              onClick={() => handleGetInfo(record.url)}
            />
          </Tooltip>
        </Space>
      ),
    },
  ];

  return (
    <div style={{ height: '100%', display: 'flex', flexDirection: 'column', padding: '16px' }}>
      {/* Header with controls */}
      <Space size="middle" wrap style={{ marginBottom: '16px' }}>
        <Button
          type="primary"
          icon={<ReloadOutlined />}
          onClick={handleScan}
          loading={loading}
        >
          {t('pages.settings.ryoais.scan_button')}
        </Button>

        <Select
          value={scanTimeout}
          onChange={setScanTimeout}
          style={{ width: 80 }}
          options={[
            { label: '3s', value: 3 },
            { label: '5s', value: 5 },
            { label: '10s', value: 10 },
            { label: '15s', value: 15 },
          ]}
        />

        <Text type="secondary">
          {t('pages.settings.ryoais.devices_found', { count: devices.length })}
        </Text>
      </Space>

      {/* Device table */}
      <div style={{ flex: 1, overflow: 'auto' }}>
        <Table
          columns={columns}
          dataSource={devices}
          rowKey="device_uuid"
          loading={loading}
          pagination={{
            pageSize: 10,
            showSizeChanger: true,
            showTotal: (total) => t('pages.settings.ryoais.total_devices', { total }),
          }}
          locale={{
            emptyText: (
              <Empty
                image={Empty.PRESENTED_IMAGE_SIMPLE}
                description={
                  <Space direction="vertical" size="small">
                    <Text type="secondary">
                      {t('pages.settings.ryoais.no_devices')}
                    </Text>
                    <Text type="secondary" style={{ fontSize: '12px' }}>
                      {t('pages.settings.ryoais.scan_hint')}
                    </Text>
                  </Space>
                }
              />
            ),
          }}
        />
      </div>
    </div>
  );
};

export default RyoaisManagement;
