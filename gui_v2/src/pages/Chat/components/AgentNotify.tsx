import React from 'react';
import { Card, Tag, Typography, Space, Divider, Empty, Table, Tooltip, Collapse } from 'antd';
import styled from '@emotion/styled';
import { useNotifications } from '../hooks/useNotifications';

const { Title, Text } = Typography;
const { Panel } = Collapse;

const NotifyContainer = styled.div`
  padding: 32px 40px;
  overflow-y: auto;
  height: 100%;
  width: 100%;
  background: linear-gradient(135deg, #1a1a2e 0%, #16213e 50%, #0f3460 100%);
  position: relative;
`;

const EmptyContainer = styled.div`
  display: flex;
  align-items: center;
  justify-content: center;
  height: 100%;
  width: 100%;
  position: relative;
  z-index: 1;
`;

const NotificationCard = styled(Card)`
  margin-bottom: 40px;
  border-radius: 20px;
  border: none;
  background: rgba(255, 255, 255, 0.13);
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.18), 0 4px 16px rgba(0, 0, 0, 0.10);
  position: relative;
  overflow: hidden;
`;

const SectionTitle = styled.div`
  font-size: 16px;
  font-weight: 600;
  color: #a0aec0;
  margin-bottom: 10px;
  margin-top: 18px;
  letter-spacing: 0.5px;
`;

const SummaryTable: React.FC<{ summary: any }> = ({ summary }) => {
  const firstRow = summary && Object.values(summary)[0] as Record<string, any> | undefined;
  const columns = firstRow ? Object.keys(firstRow) : [];
  return (
    <Card size="small" style={{ borderRadius: 12, background: 'rgba(255,255,255,0.08)', marginTop: 8 }}>
      <SectionTitle>对比摘要</SectionTitle>
      <table style={{ width: '100%', color: '#fff', fontSize: 13, borderCollapse: 'collapse' }}>
        <thead>
          <tr style={{ background: 'rgba(255,255,255,0.10)' }}>
            <th style={{ textAlign: 'left', padding: 8, fontWeight: 600 }}>Product</th>
            {columns.map((k) => (
              <th key={k} style={{ textAlign: 'left', padding: 8, fontWeight: 600 }}>{k}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {(Object.entries(summary) as [string, Record<string, any>][]).map(([product, criterias], idx) => {
            const row = (criterias ?? {}) as Record<string, any>;
            return (
              <tr key={product} style={{ background: idx % 2 === 0 ? 'rgba(255,255,255,0.01)' : 'rgba(255,255,255,0.07)' }}>
                <td style={{ padding: 8 }}>{product}</td>
                {columns.map((col, i) => (
                  <td key={i} style={{ padding: 8 }}>{row[col]}</td>
                ))}
              </tr>
            );
          })}
        </tbody>
      </table>
    </Card>
  );
};

const renderHighlights = (highlights: any[]) => (
  <div style={{ minWidth: 120, background: 'rgba(0, 123, 255, 0.06)', borderRadius: 6, padding: 6 }}>
    <div style={{ fontWeight: 600, color: '#1677ff', marginBottom: 2 }}>亮点</div>
    <Space wrap>
      {highlights?.map((h, idx) => (
        <Tag key={idx} color="blue" style={{ marginBottom: 2 }}>
          <b>{h.label}</b>: {h.value} {h.unit}
        </Tag>
      ))}
    </Space>
  </div>
);

const renderNeededCriterias = (criterias: any[]) => (
  <ol style={{ margin: 0, paddingLeft: 18, background: 'rgba(255, 193, 7, 0.06)', borderRadius: 6 }}>
    {criterias?.map((c, idx) => (
      <li key={idx} style={{ marginBottom: 2 }}>
        <Space size={4}>
          {Object.entries(c).map(([k, v]) => (
            <span key={k}><b>{k}:</b> {v}</span>
          ))}
        </Space>
      </li>
    ))}
  </ol>
);

const renderAppSpecific = (apps: any[]) => (
  <div style={{ minWidth: 120 }}>
    {apps?.map((app, idx) => (
      <div key={idx} style={{ background: 'rgba(120,120,255,0.08)', borderRadius: 6, padding: 6, marginBottom: 4 }}>
        <div style={{ fontWeight: 600, color: '#6f42c1', marginBottom: 2 }}>
          <Tag color="purple" style={{ fontWeight: 600 }}>{app.app}</Tag>
        </div>
        {app.needed_criterias && renderNeededCriterias(app.needed_criterias)}
      </div>
    ))}
  </div>
);

const renderCell = (value: any, key: string) => {
  if (key === 'highlights' && Array.isArray(value)) return renderHighlights(value);
  if (key === 'app_specific' && Array.isArray(value)) return renderAppSpecific(value);
  if (Array.isArray(value)) {
    return (
      <Space wrap>
        {value.map((v, idx) =>
          typeof v === 'object'
            ? <Tooltip key={idx} title={JSON.stringify(v)}><Tag color="geekblue">{idx + 1}</Tag></Tooltip>
            : <Tag key={idx}>{String(v)}</Tag>
        )}
      </Space>
    );
  }
  if (typeof value === 'object' && value !== null) {
    return <Tooltip title={JSON.stringify(value)}><Tag color="orange">对象</Tag></Tooltip>;
  }
  if (typeof value === 'string' && value.startsWith('http')) {
    return <a href={value} target="_blank" rel="noopener noreferrer" style={{ color: '#1890ff' }}>详情</a>;
  }
  return String(value ?? '');
};

const getAllKeys = (items: any[]) => {
  const keys = new Set<string>();
  items.forEach(item => {
    Object.keys(item || {}).forEach(k => keys.add(k));
  });
  // 主字段优先
  const main = ['main_image', 'product_name', 'brand', 'model', 'score', 'url', 'highlights', 'app_specific'];
  const rest = Array.from(keys).filter(k => !main.includes(k));
  return [...main.filter(k => keys.has(k)), ...rest];
};

const ProductTable: React.FC<{ items: any[] }> = ({ items }) => {
  const keys = getAllKeys(items);
  const columns = keys.map(key => ({
    title: String(key),
    dataIndex: key,
    key,
    render: (value: any) => renderCell(value, key),
    width: key === 'main_image' ? 60 : undefined,
    align: key === 'main_image' ? ('center' as const) : undefined,
  }));

  return (
    <Table
      columns={columns}
      dataSource={items.map((item, idx) => ({ ...item, key: idx }))}
      pagination={false}
      scroll={{ x: Math.max(900, keys.length * 120) }}
      bordered
      size="middle"
      style={{ background: 'rgba(255,255,255,0.04)', borderRadius: 12, margin: '16px 0' }}
    />
  );
};

const NotificationRenderer: React.FC<{ notification: any }> = ({ notification }) => {
  if (!notification) return null;
  const {
    title,
    Items = [],
    summary,
    comments,
    statistics,
    behind_the_scene,
    show_feedback_options
  } = notification;

  const safeTitle = typeof title === 'string' ? title : (title ? String(title) : '查询结果');
  const safeStatistics = statistics && typeof statistics === 'object' && !Array.isArray(statistics) ? statistics : undefined;
  const safeComments = Array.isArray(comments) ? comments : [];
  const safeBehindTheScene = typeof behind_the_scene === 'string' ? behind_the_scene : '';
  const safeShowFeedback = !!show_feedback_options;

  return (
    <NotificationCard>
      {/* 标题和统计 */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 8, marginBottom: 8 }}>
        <Title level={4} style={{ color: '#fff', margin: 0 }}>{safeTitle}</Title>
        {safeStatistics && (
          <Space wrap>
            {Object.entries(safeStatistics).map(([k, v]) => (
              <Tag key={k} color="blue" style={{ fontSize: 12 }}>{k}: {String(v)}</Tag>
            ))}
          </Space>
        )}
      </div>
      <Divider style={{ margin: '12px 0', borderColor: 'rgba(255,255,255,0.13)' }} />

      {/* 产品表格分区 */}
      {Array.isArray(Items) && Items.length > 0 && (
        <>
          <SectionTitle>查询结果</SectionTitle>
          <ProductTable items={Items} />
        </>
      )}

      {/* Summary 区域 */}
      {summary && (
        <div style={{ margin: '24px 0 0 0' }}>
          <SummaryTable summary={summary} />
        </div>
      )}

      {/* Comments 区域 */}
      {safeComments.length > 0 && (
        <div style={{ margin: '24px 0 0 0' }}>
          <Card size="small" style={{ borderRadius: 12, background: 'rgba(255,255,255,0.08)' }}>
            <SectionTitle>评论</SectionTitle>
            <ul style={{ margin: 0, padding: '8px 0 0 18px', color: '#fff' }}>
              {safeComments.map((c: any, idx: number) => (
                <li key={idx}>{typeof c === 'string' ? c : JSON.stringify(c)}</li>
              ))}
            </ul>
          </Card>
        </div>
      )}

      {/* Behind the Scene/Feedback */}
      {(safeBehindTheScene || safeShowFeedback) && (
        <div style={{ marginTop: 24, display: 'flex', alignItems: 'center', gap: 32, flexWrap: 'wrap', borderTop: '1px solid rgba(255,255,255,0.10)', paddingTop: 16 }}>
          {safeBehindTheScene && <a href={safeBehindTheScene} target="_blank" rel="noopener noreferrer" style={{ color: '#aaa', fontSize: 13 }}>Behind the Scene</a>}
          {safeShowFeedback && <Tag color="red">Feedback Options Here</Tag>}
        </div>
      )}
    </NotificationCard>
  );
};

interface AgentNotifyProps {
  chatId: string;
}

const AgentNotify: React.FC<AgentNotifyProps> = ({ chatId }) => {
  const { notifications } = useNotifications(chatId);
  const displayNotifications = notifications.filter(n => !!n);

  if (!displayNotifications || displayNotifications.length === 0) {
    return (
      <EmptyContainer>
        <Empty description="No search results" />
      </EmptyContainer>
    );
  }

  return (
    <NotifyContainer>
      {displayNotifications.map((notification, index) => (
        <NotificationRenderer key={notification.id || index} notification={notification} />
      ))}
    </NotifyContainer>
  );
};

export default AgentNotify;