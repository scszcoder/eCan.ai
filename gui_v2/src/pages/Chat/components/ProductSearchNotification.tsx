import React from 'react';
import { Card, Tag, Typography, Space, Divider, Table, Tooltip, Modal } from 'antd';
import styled from '@emotion/styled';
import { useTranslation } from 'react-i18next';
import { TableOutlined, UnorderedListOutlined } from '@ant-design/icons';
import { Button } from 'antd';

const { Title } = Typography;


// 注入LinkClickListen器的 hook
const useLinkClickHandler = () => {
  React.useEffect(() => {
    // 注入 JavaScript 来确保LinkClickAble to被正确捕获
    const script = `
      document.addEventListener('click', function(e) {
        // 忽略下拉MenuRelated toClickEvent
        if (e.target.closest('.ant-dropdown') ||
            e.target.closest('.user-profile-dropdown') ||
            e.target.closest('.ant-dropdown-menu')) {
          return;
        }

        if (e.target.tagName === 'A' && e.target.href) {
          var url = e.target.href;
          if (url.startsWith('http://') || url.startsWith('https://')) {
            console.log('External link clicked:', url);
            // 不阻止Default行为，让 Qt WebEngine Process
          }
        }
      });
      //console.log('Link click handler injected');
    `;
    
    // DelayExecute，确保 DOM 已经Load
    setTimeout(() => {
      try {
        const scriptElement = document.createElement('script');
        scriptElement.textContent = script;
        document.head.appendChild(scriptElement);
        //console.log('Link click handler script injected');
      } catch (error) {
        console.error('Failed to inject link click handler:', error);
      }
    }, 1000);
  }, []);
};

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
  font-size: 18px;
  font-weight: 600;
  color: #a0aec0;
  margin-bottom: 10px;
  margin-top: 18px;
  letter-spacing: 0.5px;
`;

const SummaryTable: React.FC<{ summary: any }> = ({ summary }) => {
  const { t } = useTranslation();
  const firstRow = summary && Object.values(summary)[0] as Record<string, any> | undefined;
  const columns = firstRow ? Object.keys(firstRow) : [];
  const summaryTitle = (() => {
    const label = t('agentnotify.summary');
    return label === 'agentnotify.summary' ? '对比摘要' : label;
  })();
  return (
    <Card size="small" style={{ borderRadius: 12, background: 'rgba(255,255,255,0.08)', marginTop: 8 }}>
      <SectionTitle>{summaryTitle}</SectionTitle>
      <table style={{ width: '100%', color: '#fff', fontSize: 15, borderCollapse: 'collapse' }}>
        <thead>
          <tr style={{ background: 'rgba(255,255,255,0.10)' }}>
            <th style={{ textAlign: 'left', padding: 8, fontWeight: 600, fontSize: '15px' }}>Product</th>
            {columns.map((k) => (
                              <th key={k} style={{ textAlign: 'left', padding: 8, fontWeight: 600, fontSize: '15px' }}>{k}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {(Object.entries(summary) as [string, Record<string, any>][])?.map(([product, criterias], idx) => {
            const row = (criterias ?? {}) as Record<string, any>;
            return (
              <tr key={product} style={{ background: idx % 2 === 0 ? 'rgba(255,255,255,0.01)' : 'rgba(255,255,255,0.07)' }}>
                <td style={{ padding: 8, fontSize: '15px' }}>{product}</td>
                                  {columns.map((col, i) => (
                    <td key={i} style={{ padding: 8, fontSize: '15px' }}>{row[col]}</td>
                  ))}
              </tr>
            );
          })}
        </tbody>
      </table>
    </Card>
  );
};

const getI18nLabel = (t: (s: string) => string, key: string) => {
  const label = t(`agentnotify.${key}`);
  return label === `agentnotify.${key}` ? key : label;
};

const renderHighlights = (highlights: any[], t: (s: string) => string) => (
          <div style={{ minWidth: 140, background: 'rgba(0, 123, 255, 0.06)', borderRadius: 6, padding: 8 }}>
            <div style={{ fontWeight: 600, color: '#1677ff', marginBottom: 2, fontSize: '16px' }}>{t('agentnotify.highlights')}</div>
    <Space wrap>
      {highlights?.map((h, idx) => (
        <Tag key={idx} color="#fff" style={{ marginBottom: 2, fontSize: '14px' }}>
          <b>{h.label}</b>: {h.value} {h.unit}
        </Tag>
      ))}
    </Space>
  </div>
);

const renderNeededCriterias = (criterias: any[], t: (s: string) => string) => (
      <ol style={{ margin: 0, paddingLeft: 18, background: 'rgba(255, 193, 7, 0.06)', borderRadius: 6, padding: '8px 0' }}>
    {criterias?.map((c, idx) => (
              <li key={idx} style={{ marginBottom: 2, fontSize: '14px' }}>
        <Space size={4}>
                      {Object.entries(c).map(([k, v]) => (
              <span key={k} style={{ fontSize: '14px' }}><b>{getI18nLabel(t, k)}:</b> {String(v)}</span>
            ))}
        </Space>
      </li>
    ))}
  </ol>
);

const renderAppSpecific = (apps: any[], t: (s: string) => string) => (
  <div style={{ minWidth: 140 }}>
    {apps?.map((app, idx) => (
      <div
        key={idx}
        style={{
          background: 'rgba(120,120,255,0.06)',
          borderRadius: 6,
          padding: 8,
          marginBottom: 10,
        }}
      >
        <div style={{ fontWeight: 600, color: '#6f42c1', marginBottom: 2, fontSize: '16px' }}>
          <Tag color="purple" style={{ fontWeight: 600, fontSize: 14 }}>{app.app}</Tag>
        </div>
        {Array.isArray(app.needed_criterias) && (
          <Space wrap>
            {app.needed_criterias.map((c: any, i: number) =>
              Object.entries(c).map(([k, v], j) => (
                <Tag key={i + '-' + j} color="#fff" style={{ marginBottom: 2, fontSize: 14 }}>
                  <b>{getI18nLabel(t, k)}:</b> {String(v)}
                </Tag>
              ))
            )}
          </Space>
        )}
      </div>
    ))}
  </div>
);

const renderCell = (value: any, key: string, t: (s: string) => string, onImageClick?: (url: string) => void) => {
  if (key === 'highlights' && Array.isArray(value)) return renderHighlights(value, t);
  if (key === 'app_specific' && Array.isArray(value)) return renderAppSpecific(value, t);
  
  // Handle main_image field - display image with click to enlarge
  if (key === 'main_image' && typeof value === 'string' && value.startsWith('http')) {
    return (
      <div 
        style={{ 
          cursor: 'pointer', 
          display: 'flex', 
          alignItems: 'center', 
          justifyContent: 'center',
          width: '100%',
          height: '100%'
        }}
        onClick={() => onImageClick?.(value)}
      >
        <img 
          src={value} 
          alt="product" 
          style={{ 
            width: 50, 
            height: 50, 
            objectFit: 'contain', 
            borderRadius: 4, 
            background: '#fff',
            border: '1px solid #d9d9d9'
          }} 
        />
      </div>
    );
  }
  
  // Handle url field - make it clickable
  if (key === 'url' && typeof value === 'string' && value.startsWith('http')) {
    return (
      <a 
        href={value} 
        onClick={(e) => {
          e.preventDefault();
          console.log('URL link clicked:', value);
          // 直接调用SystemBrowser
          try {
            const newWindow = window.open(value, '_blank');
            if (!newWindow || newWindow.closed || typeof newWindow.closed === 'undefined') {
              console.warn('window.open failed, trying alternative method');
            }
          } catch (error) {
            console.error('Failed to open link:', error);
          }
        }}
        style={{ color: '#1890ff', textDecoration: 'underline', cursor: 'pointer', fontSize: '14px' }}
      >
        {t('agentnotify.view_details')}
      </a>
    );
  }
  
  if (Array.isArray(value)) {
    return (
      <Space wrap>
        {value.map((v, idx) =>
          typeof v === 'object'
            ? <Tooltip key={idx} title={JSON.stringify(v)}><Tag color="geekblue" style={{ fontSize: '14px' }}>{idx + 1}</Tag></Tooltip>
            : <Tag key={idx} style={{ fontSize: '14px' }}>{String(v)}</Tag>
        )}
      </Space>
    );
  }
  if (typeof value === 'object' && value !== null) {
    return <Tooltip title={JSON.stringify(value)}><Tag color="orange" style={{ fontSize: '14px' }}>{t('agentnotify.object')}</Tag></Tooltip>;
  }
  if (typeof value === 'string' && value.startsWith('http')) {
    return (
      <a 
        href={value} 
        onClick={(e) => {
          e.preventDefault();
          console.log('Generic link clicked:', value);
          // 直接调用SystemBrowser
          try {
            const newWindow = window.open(value, '_blank');
            if (!newWindow || newWindow.closed || typeof newWindow.closed === 'undefined') {
              console.warn('window.open failed, trying alternative method');
            }
          } catch (error) {
            console.error('Failed to open link:', error);
          }
        }}
        style={{ color: '#1890ff', textDecoration: 'underline', cursor: 'pointer', fontSize: '14px' }}
      >
        {t('agentnotify.view_details')}
      </a>
    );
  }
  return String(value ?? '');
};

const getAllKeys = (items: any[]) => {
  const keys = new Set<string>();
  items.forEach(item => {
    Object.keys(item || {}).forEach(k => keys.add(k));
  });
  // 主Field优先
  const main = ['main_image', 'product_name', 'brand', 'model', 'score', 'url', 'highlights', 'app_specific'];
  const rest = Array.from(keys).filter(k => !main.includes(k));
  return [...main.filter(k => keys.has(k)), ...rest];
};

const ProductTable: React.FC<{ items: any[], onImageClick?: (url: string) => void }> = ({ items, onImageClick }) => {
  const { t } = useTranslation();
  const keys = getAllKeys(items);
  const columns = keys.map(key => ({
    title: getI18nLabel(t, key),
    dataIndex: key,
    key,
    render: (value: any) => renderCell(value, key, t, onImageClick),
    width: key === 'main_image' ? 80 : undefined,
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

// 新增 ProductList Component
const ProductList: React.FC<{ items: any[], onImageClick?: (url: string) => void }> = ({ items, onImageClick }) => {
  const { t } = useTranslation();
  if (!Array.isArray(items) || items.length === 0) return null;
  const keys = getAllKeys(items);
  // 主Field
  const mainFields = ['product_name', 'brand', 'model', 'score'];
  // 其他Field
  const otherFields = keys.filter(k => !['main_image', ...mainFields, 'highlights', 'app_specific', 'url'].includes(k));

  return (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 24, margin: '20px 0' }}>
                {items.map((item: any, idx) => (
                  <Card
            key={idx}
            size="small"
            style={{ borderRadius: 16, background: 'rgba(255,255,255,0.10)', color: '#fff', boxShadow: '0 2px 8px rgba(0,0,0,0.10)' }}
            styles={{ body: { padding: 24 } }}
          >
                      <div style={{ display: 'flex', gap: 28, alignItems: 'flex-start' }}>
                          {/* Left主图 */}
              {item.main_image && (
                <div style={{ minWidth: 100, maxWidth: 140, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                <div 
                  style={{ 
                    cursor: 'pointer',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center'
                  }}
                  onClick={() => onImageClick?.(item.main_image)}
                >
                  <img 
                    src={item.main_image} 
                    alt={item.product_name || 'product'} 
                    style={{ 
                      width: 90, 
                      height: 90, 
                      objectFit: 'contain', 
                      borderRadius: 10, 
                      background: '#fff',
                      border: '1px solid #d9d9d9'
                    }} 
                  />
                </div>
              </div>
            )}
            {/* RightContent */}
            <div style={{ flex: 1, minWidth: 0 }}>
              {/* 主Field */}
              <div style={{ display: 'flex', alignItems: 'center', gap: 16, flexWrap: 'wrap', marginBottom: 8 }}>
                <span style={{ fontWeight: 700, fontSize: 20, color: '#fff' }}>{item.product_name}</span>
                {item.brand && <Tag color="blue" style={{ fontWeight: 500, fontSize: '14px' }}>{item.brand}</Tag>}
                {item.model && <Tag color="geekblue" style={{ fontWeight: 500, fontSize: '14px' }}>{item.model}</Tag>}
                {item.score !== undefined && <Tag color="gold" style={{ fontWeight: 600, fontSize: '14px' }}>{t('agentnotify.score')}: {item.score}</Tag>}
              </div>
              {/* 其他Field */}
              {otherFields.length > 0 && (
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: 12, marginBottom: 10 }}>
                  {otherFields.map((key) => (
                    item[key] !== undefined && item[key] !== null && item[key] !== '' && (
                      <div key={key} style={{ minWidth: 120 }}>
                        <span style={{ color: '#a0aec0', fontWeight: 500, fontSize: '14px' }}>{getI18nLabel(t, key)}: </span>
                        {renderCell(item[key], key, t, onImageClick)}
                      </div>
                    )
                  ))}
                </div>
              )}
              {/* 高亮/Tag/应用特定/DetailsLink */}
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: 16, alignItems: 'center', marginTop: 10 }}>
                {item.highlights && renderHighlights(item.highlights, t)}
                {item.app_specific && renderAppSpecific(item.app_specific, t)}
                {item.url && typeof item.url === 'string' && item.url.startsWith('http') && (
                  <a 
                    href={item.url} 
                    onClick={(e) => {
                      e.preventDefault();
                      console.log('List view link clicked:', item.url);
                      // 直接调用SystemBrowser
                      try {
                        const newWindow = window.open(item.url, '_blank');
                        if (!newWindow || newWindow.closed || typeof newWindow.closed === 'undefined') {
                          console.warn('window.open failed, trying alternative method');
                        }
                      } catch (error) {
                        console.error('Failed to open link:', error);
                      }
                    }}
                    style={{ color: '#1890ff', fontWeight: 500, marginLeft: 8, textDecoration: 'underline', cursor: 'pointer', fontSize: '15px' }}
                  >
                    {t('agentnotify.view_details')}
                  </a>
                )}
              </div>
            </div>
          </div>
        </Card>
      ))}
    </div>
  );
};

const ProductSearchNotification: React.FC<{ content: any }> = ({ content }) => {
  const { t } = useTranslation();
  const [viewMode, setViewMode] = React.useState<'table' | 'list'>('table');
  const [imageModalVisible, setImageModalVisible] = React.useState(false);
  const [selectedImageUrl, setSelectedImageUrl] = React.useState('');
  
  // 使用LinkClickProcess器
  useLinkClickHandler();
  
  if (!content) return null;
  // 只Process业务Content部分，不解构 isRead、time、uid
  const {
    title,
    Items = [],
    summary,
    comments,
    statistics,
    behind_the_scene,
    show_feedback_options
  } = content;

  const safeTitle = typeof title === 'string' ? title : (title ? String(title) : t('agentnotify.result'));
  const safeStatistics = statistics && typeof statistics === 'object' && !Array.isArray(statistics) ? statistics : undefined;
  const safeComments = Array.isArray(comments) ? comments : [];
  const safeBehindTheScene = typeof behind_the_scene === 'string' ? behind_the_scene : '';
  const safeShowFeedback = !!show_feedback_options;

  const handleImageClick = (imageUrl: string) => {
    setSelectedImageUrl(imageUrl);
    setImageModalVisible(true);
  };

  return (
    <>
      <NotificationCard>
        {/* 标题和Toggle视图Button */}
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 8, marginBottom: 4 }}>
          <Title level={4} style={{ color: '#fff', margin: 0, fontSize: '22px' }}>{safeTitle}</Title>
          {Array.isArray(Items) && Items.length > 0 && (
            <Button
              icon={viewMode === 'table' ? <TableOutlined /> : <UnorderedListOutlined />}
              onClick={() => setViewMode(viewMode === 'table' ? 'list' : 'table')}
              size="small"
              title={viewMode === 'table' ? t('agentnotify.table_view') : t('agentnotify.list_view')}
            />
          )}
        </div>
        {/* 统计Information独立一行 */}
        {safeStatistics && (
          <div style={{ marginBottom: 12 }}>
            <Space wrap>
              {Object.entries(safeStatistics).map(([k, v]) => (
                <Tag key={k} color="blue" style={{ fontSize: 14 }}>{getI18nLabel(t, k)}: {String(v)}</Tag>
              ))}
            </Space>
          </div>
        )}
        <Divider style={{ margin: '16px 0', borderColor: 'rgba(255,255,255,0.13)' }} />

        {/* 产品Table/List分区 */}
        {Array.isArray(Items) && Items.length > 0 && (
          <>
            <SectionTitle>{t('agentnotify.result')}</SectionTitle>
            {viewMode === 'table' ? 
              <ProductTable items={Items} onImageClick={handleImageClick} /> : 
              <ProductList items={Items} onImageClick={handleImageClick} />
            }
          </>
        )}

        {/* Summary 区域 */}
        {summary && (
          <div style={{ margin: '28px 0 0 0' }}>
            <SummaryTable summary={summary} />
          </div>
        )}

        {/* Comments 区域 */}
        {safeComments.length > 0 && (
          <div style={{ margin: '28px 0 0 0' }}>
            <Card size="small" style={{ borderRadius: 12, background: 'rgba(255,255,255,0.08)' }}>
              <SectionTitle>{t('agentnotify.comments')}</SectionTitle>
              <ul style={{ margin: 0, padding: '8px 0 0 18px', color: '#fff', fontSize: '15px' }}>
                {safeComments.map((c: any, idx: number) => (
                  <li key={idx} style={{ fontSize: '15px' }}>{typeof c === 'string' ? c : JSON.stringify(c)}</li>
                ))}
              </ul>
            </Card>
          </div>
        )}

        {/* Behind the Scene/Feedback */}
        {(safeBehindTheScene || safeShowFeedback) && (
          <div style={{ marginTop: 24, display: 'flex', alignItems: 'center', gap: 32, flexWrap: 'wrap', borderTop: '1px solid rgba(255,255,255,0.10)', paddingTop: 18 }}>
            {safeBehindTheScene && <a href={safeBehindTheScene} onClick={(e) => { e.preventDefault(); console.log('Behind the scene link clicked:', safeBehindTheScene); try { window.open(safeBehindTheScene, '_blank'); } catch (error) { console.error('Failed to open link:', error); } }} style={{ color: '#aaa', fontSize: 15, cursor: 'pointer' }}>{t('agentnotify.behind_the_scene')}</a>}
                          {safeShowFeedback && <Tag color="red" style={{ fontSize: '14px' }}>{t('agentnotify.feedback')}</Tag>}
            {/* TestLink */}
            <a href="https://www.google.com" onClick={(e) => { e.preventDefault(); console.log('Test link clicked: https://www.google.com'); try { window.open('https://www.google.com', '_blank'); } catch (error) { console.error('Failed to open link:', error); } }} style={{ color: '#1890ff', fontSize: 15, cursor: 'pointer' }}>Test Link (Google)</a>
          </div>
        )}
      </NotificationCard>

      {/* Image Modal */}
      <Modal
        title={t('agentnotify.product_image')}
        open={imageModalVisible}
        onCancel={() => setImageModalVisible(false)}
        footer={null}
        width={800}
        centered
      >
        <div style={{ textAlign: 'center' }}>
          <img 
            src={selectedImageUrl} 
            alt="product" 
            style={{ 
              maxWidth: '100%', 
              maxHeight: '600px', 
              objectFit: 'contain' 
            }} 
          />
        </div>
      </Modal>
    </>
  );
};

export default ProductSearchNotification; 