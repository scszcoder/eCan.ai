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
  Typography,
  Descriptions,
  Card,
  Row,
  Col,
  Divider,
  Alert
} from 'antd';
import { 
  ReloadOutlined, 
  GlobalOutlined, 
  ApiOutlined,
  InfoCircleOutlined,
  CheckCircleOutlined,
  CloseCircleOutlined,
  ClockCircleOutlined,
  CodeOutlined,
  DatabaseOutlined,
  CloudServerOutlined
} from '@ant-design/icons';
import type { ColumnsType } from 'antd/es/table';
import { get_ipc_api } from '@/services/ipc_api';

const { Text, Link } = Typography;

interface ServiceStatus {
  status: 'running' | 'stopped' | 'error';
  port?: number;
}

interface RyoAISDevice {
  // mDNS TXT record fields - 设备标识
  sn: string;                    // 序列号 (16位)
  uuid: string;                  // 设备 UUID (12位MAC)
  mac: string;                   // MAC地址
  hostname: string;              // 主机名
  model: string;                 // 设备型号 (RYOAIS16NE)
  name: string;                  // 友好设备名称 (RyoAIS Gateway)
  
  // mDNS TXT record fields - 版本信息
  version: string;               // 软件版本
  build_time: string;            // 构建时间
  git_commit: string;            // Git 提交哈希
  
  // mDNS TXT record fields - 服务信息
  environment: string;           // 运行环境 (production/development)
  api_types: string | string[]; // 支持的 API 类型 (可能是字符串或数组)
  api_version: string;           // API 版本
  services: string | string[];   // 提供的服务 (可能是字符串或数组)
  
  // mDNS TXT record fields - 系统信息
  platform: string;              // 操作系统平台
  python_version: string;        // Python 版本
  
  // mDNS TXT record fields - 网络信息
  ip: string;                    // IP 地址
  port: string;                  // 服务端口
  url: string;                   // 完整访问 URL
  
  // mDNS TXT record fields - 描述
  description: string;           // 描述信息
  
  // mDNS Discovery metadata
  service_name?: string;
  service_type?: string;
  instance_name?: string;
  
  // Computed/derived fields
  short_uuid?: string;           // 短 UUID (从 uuid 派生)
  api_types_array?: string[];    // API 类型数组 (从 api_types 解析)
  services_array?: string[];     // 服务数组 (从 services 解析)
  services_status?: {            // 服务状态详情 (可选，来自额外API调用)
    llm?: ServiceStatus;
    embedding?: ServiceStatus;
    rerank?: ServiceStatus;
    rag?: ServiceStatus;
    ocr?: ServiceStatus;
  };
  
  // Legacy fields for backward compatibility
  local_ip?: string;
  device_uuid?: string;
  serial_number?: string;
  discovery_method?: string;
  supported_apis?: string[];
  addresses?: string[];
  properties?: Record<string, string>;
  discovered_at?: number;
}

interface RyoaisManagementProps {
  username?: string;
  devices?: RyoAISDevice[];
  onDevicesChange?: (devices: RyoAISDevice[]) => void;
}

const RyoaisManagement: React.FC<RyoaisManagementProps> = ({ 
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

  // Render service status badge
  const renderServiceStatus = (status?: 'running' | 'stopped' | 'error') => {
    if (!status) return <Badge status="default" text={t('common.unknown')} />;
    
    const statusMap = {
      running: { status: 'success' as const, icon: <CheckCircleOutlined />, text: t('pages.settings.ryoais.service_running') },
      stopped: { status: 'default' as const, icon: <CloseCircleOutlined />, text: t('pages.settings.ryoais.service_stopped') },
      error: { status: 'error' as const, icon: <CloseCircleOutlined />, text: t('pages.settings.ryoais.service_error') }
    };
    
    const config = statusMap[status];
    return (
      <Space size={4}>
        {config.icon}
        <Badge status={config.status} text={config.text} />
      </Space>
    );
  };

  // Expanded row render
  const expandedRowRender = (record: RyoAISDevice) => {
    return (
      <Card size="small" style={{ margin: '8px 0' }}>
        <Row gutter={[16, 16]}>
          {/* Device Information */}
          <Col span={12}>
            <Descriptions
              title={<Space><InfoCircleOutlined />{t('pages.settings.ryoais.device_info')}</Space>}
              column={1}
              size="small"
              bordered
            >
              <Descriptions.Item label={t('pages.settings.ryoais.device_name')}>
                <Text strong>{record.name || t('common.unknown')}</Text>
              </Descriptions.Item>
              <Descriptions.Item label={t('pages.settings.ryoais.serial_number')}>
                <Text code style={{ fontSize: '11px' }}>{record.sn || t('common.unknown')}</Text>
              </Descriptions.Item>
              <Descriptions.Item label={t('pages.settings.ryoais.uuid')}>
                <Text code style={{ fontSize: '11px' }}>{record.uuid || t('common.unknown')}</Text>
              </Descriptions.Item>
              <Descriptions.Item label={t('pages.settings.ryoais.mac_address')}>
                <Text code style={{ fontSize: '11px' }}>{record.mac || t('common.unknown')}</Text>
              </Descriptions.Item>
              <Descriptions.Item label={t('pages.settings.ryoais.model')}>
                <Tag color="purple">{record.model || t('common.unknown')}</Tag>
              </Descriptions.Item>
              <Descriptions.Item label={t('pages.settings.ryoais.platform')}>
                <Tag color="cyan">{record.platform || t('common.unknown')}</Tag>
              </Descriptions.Item>
              <Descriptions.Item label={t('pages.settings.ryoais.python_version')}>
                {record.python_version || t('common.unknown')}
              </Descriptions.Item>
            </Descriptions>
          </Col>

          {/* Version & Build Information */}
          <Col span={12}>
            <Descriptions
              title={<Space><CodeOutlined />{t('pages.settings.ryoais.version_info')}</Space>}
              column={1}
              size="small"
              bordered
            >
              <Descriptions.Item label={t('pages.settings.ryoais.software_version')}>
                <Tag color="geekblue">v{record.version || '0.0.0'}</Tag>
              </Descriptions.Item>
              <Descriptions.Item label={t('pages.settings.ryoais.api_version')}>
                <Tag color="blue">v{record.api_version || '0.0.0'}</Tag>
              </Descriptions.Item>
              <Descriptions.Item label={t('pages.settings.ryoais.build_time')}>
                {record.build_time && record.build_time !== 'unknown' ? new Date(record.build_time).toLocaleString() : (record.build_time || t('common.unknown'))}
              </Descriptions.Item>
              <Descriptions.Item label={t('pages.settings.ryoais.git_commit')}>
                {record.git_commit && record.git_commit !== 'unknown' ? (
                  <Text code style={{ fontSize: '11px' }}>{record.git_commit.substring(0, 8)}</Text>
                ) : (record.git_commit || t('common.unknown'))}
              </Descriptions.Item>
              <Descriptions.Item label={t('pages.settings.ryoais.api_types')}>
                <Space size={4} wrap>
                  {(() => {
                    let apiTypes: string[] = [];
                    if (record.api_types_array) {
                      apiTypes = record.api_types_array;
                    } else if (Array.isArray(record.api_types)) {
                      apiTypes = record.api_types;
                    } else if (typeof record.api_types === 'string') {
                      apiTypes = record.api_types.split(',');
                    }
                    return apiTypes.map((api: string) => (
                      <Tag key={api} color="blue" style={{ fontSize: '10px' }}>
                        {api.trim().toUpperCase()}
                      </Tag>
                    ));
                  })()}
                </Space>
              </Descriptions.Item>
              <Descriptions.Item label={t('pages.settings.ryoais.services_list')}>
                <Space size={4} wrap>
                  {(() => {
                    let servicesList: string[] = [];
                    if (record.services_array) {
                      servicesList = record.services_array;
                    } else if (Array.isArray(record.services)) {
                      servicesList = record.services;
                    } else if (typeof record.services === 'string') {
                      servicesList = record.services.split(',');
                    }
                    return servicesList.map((service: string) => (
                      <Tag key={service} color="green" style={{ fontSize: '10px' }}>
                        {service.trim().toUpperCase()}
                      </Tag>
                    ));
                  })()}
                </Space>
              </Descriptions.Item>
              <Descriptions.Item label={t('common.description')}>
                <Text type="secondary" style={{ fontSize: '12px' }}>{record.description}</Text>
              </Descriptions.Item>
            </Descriptions>
          </Col>

          {/* Services Status */}
          {record.services_status && (
            <Col span={24}>
              <Divider orientation="left" style={{ margin: '12px 0' }}>
                <Space><DatabaseOutlined />{t('pages.settings.ryoais.services_status')}</Space>
              </Divider>
              <Row gutter={[16, 8]}>
                {Object.entries(record.services_status).map(([serviceName, serviceInfo]) => (
                  <Col span={8} key={serviceName}>
                    <Card size="small" style={{ textAlign: 'center' }}>
                      <Space direction="vertical" size={4}>
                        <Text strong style={{ textTransform: 'uppercase' }}>{serviceName}</Text>
                        {renderServiceStatus(serviceInfo?.status)}
                        {serviceInfo?.port && (
                          <Text type="secondary" style={{ fontSize: '11px' }}>
                            {t('pages.settings.ryoais.port')}: {serviceInfo.port}
                          </Text>
                        )}
                      </Space>
                    </Card>
                  </Col>
                ))}
              </Row>
            </Col>
          )}

        </Row>
      </Card>
    );
  };

  // Table columns
  const columns: ColumnsType<RyoAISDevice> = [
    {
      title: t('pages.settings.ryoais.column_device'),
      dataIndex: 'hostname',
      key: 'hostname',
      width: 220,
      render: (hostname: string, record: RyoAISDevice) => (
        <Space direction="vertical" size={2}>
          <Space size={4}>
            <CloudServerOutlined style={{ color: '#1890ff' }} />
            <Text strong>{hostname}</Text>
          </Space>
          <Text type="secondary" style={{ fontSize: '11px' }}>
            {t('pages.settings.ryoais.serial_number')}: {record.sn || 'N/A'}
          </Text>
          {record.model && record.model !== 'unknown' && (
            <Tag color="purple" style={{ fontSize: '10px', margin: 0 }}>
              {record.model}
            </Tag>
          )}
        </Space>
      ),
    },
    {
      title: t('pages.settings.ryoais.column_address'),
      key: 'address',
      width: 240,
      render: (_: any, record: RyoAISDevice) => {
        const displayUrl = record.url || (record.ip && record.port ? `http://${record.ip}:${record.port}` : 'N/A');
        return (
          <Space direction="vertical" size={2}>
            {displayUrl !== 'N/A' ? (
              <Link onClick={() => handleOpenDevice(displayUrl)} style={{ fontSize: '12px' }}>
                <GlobalOutlined /> {displayUrl}
              </Link>
            ) : (
              <Text type="secondary" style={{ fontSize: '12px' }}>N/A</Text>
            )}
            <Text type="secondary" style={{ fontSize: '11px' }}>
              {t('pages.settings.ryoais.ip_address')}: {record.ip || 'N/A'}
            </Text>
            <Text type="secondary" style={{ fontSize: '11px' }}>
              {t('pages.settings.ryoais.port')}: {record.port || 'N/A'}
            </Text>
          </Space>
        );
      },
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
      width: 120,
      render: (version: string, record: RyoAISDevice) => (
        <Space direction="vertical" size={2}>
          <Tag color="geekblue" style={{ fontSize: '11px' }}>
            v{version}
          </Tag>
          <Text type="secondary" style={{ fontSize: '10px' }}>
            {record.environment?.toUpperCase()}
          </Text>
        </Space>
      ),
    },
    {
      title: t('pages.settings.ryoais.column_services'),
      key: 'services',
      width: 180,
      render: (_: any, record: RyoAISDevice) => {
        // Parse services from TXT record - handle both string and array
        let servicesArray: string[] = [];
        if (record.services_array) {
          servicesArray = record.services_array;
        } else if (Array.isArray(record.services)) {
          servicesArray = record.services;
        } else if (typeof record.services === 'string') {
          servicesArray = record.services.split(',').map(s => s.trim());
        }
        const servicesStatus = record.services_status;
        
        if (servicesStatus && Object.keys(servicesStatus).length > 0) {
          const runningCount = Object.values(servicesStatus).filter(
            (s) => s?.status === 'running'
          ).length;
          return (
            <Space direction="vertical" size={2}>
              <Badge
                count={runningCount}
                showZero
                style={{ backgroundColor: '#52c41a' }}
              >
                <Tag icon={<DatabaseOutlined />}>
                  {servicesArray.length} {t('pages.settings.ryoais.services')}
                </Tag>
              </Badge>
              <Text type="secondary" style={{ fontSize: '10px' }}>
                {servicesArray.map(s => s.toUpperCase()).join(', ')}
              </Text>
            </Space>
          );
        }
        
        // Fallback: show services list from TXT record
        return (
          <Space size={4} wrap>
            {servicesArray.slice(0, 3).map((service: string) => (
              <Tag key={service} color="green" style={{ fontSize: '10px', margin: 0 }}>
                {service.toUpperCase()}
              </Tag>
            ))}
            {servicesArray.length > 3 && (
              <Text type="secondary" style={{ fontSize: '10px' }}>+{servicesArray.length - 3}</Text>
            )}
          </Space>
        );
      },
    },
    {
      title: t('pages.settings.ryoais.column_status'),
      key: 'status',
      width: 120,
      render: (_: any, record: RyoAISDevice) => {
        // Determine overall status based on services_status
        let overallStatus: 'success' | 'warning' | 'error' = 'success';
        let statusText = t('pages.settings.ryoais.status_online');
        
        if (record.services_status) {
          const statuses = Object.values(record.services_status).map(s => s?.status);
          if (statuses.some(s => s === 'error')) {
            overallStatus = 'error';
            statusText = t('pages.settings.ryoais.status_error');
          } else if (statuses.some(s => s === 'stopped')) {
            overallStatus = 'warning';
            statusText = t('pages.settings.ryoais.status_partial');
          }
        }
        
        return (
          <Space direction="vertical" size={2}>
            <Badge status={overallStatus} text={statusText} />
            {record.environment && (
              <Tag 
                color={record.environment === 'production' ? 'green' : 'blue'}
                style={{ fontSize: '10px', margin: 0 }}
              >
                {record.environment.toUpperCase()}
              </Tag>
            )}
          </Space>
        );
      },
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
              onClick={() => handleOpenDevice(record.url || `http://${record.ip}:${record.port}`)}
              disabled={!record.url && !record.ip}
            />
          </Tooltip>
          <Tooltip title={t('pages.settings.ryoais.action_info')}>
            <Button
              type="link"
              size="small"
              icon={<ApiOutlined />}
              onClick={() => handleGetInfo(record.url || `http://${record.ip}:${record.port}`)}
              disabled={!record.url && !record.ip}
            />
          </Tooltip>
        </Space>
      ),
    },
  ];

  return (
    <div style={{ height: '100%', display: 'flex', flexDirection: 'column', padding: '16px' }}>
      {/* Info Alert */}
      <Alert
        message={t('pages.settings.ryoais.about_title')}
        description={t('pages.settings.ryoais.about_description')}
        type="info"
        icon={<InfoCircleOutlined />}
        showIcon
        closable
        style={{ marginBottom: '16px' }}
      />

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

        <Space>
          <ClockCircleOutlined />
          <Text type="secondary">
            {t('pages.settings.ryoais.scan_timeout')}: {scanTimeout}s
          </Text>
        </Space>

        <Divider type="vertical" />

        <Text type="secondary" strong>
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
          expandable={{
            expandedRowRender,
            expandIcon: ({ expanded, onExpand, record }) => (
              <Tooltip title={expanded ? t('common.close') : t('pages.settings.ryoais.view_details')}>
                <Button
                  type="text"
                  size="small"
                  icon={<InfoCircleOutlined />}
                  onClick={(e) => onExpand(record, e)}
                  style={{ color: expanded ? '#1890ff' : undefined }}
                />
              </Tooltip>
            ),
          }}
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
