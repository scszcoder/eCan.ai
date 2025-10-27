import React from 'react';
import { theme } from 'antd';
import { useTranslation } from 'react-i18next';
import GraphViewer from './graph/GraphViewer';
import { useTheme } from '@/contexts/ThemeContext';
import { ApartmentOutlined } from '@ant-design/icons';

const GraphTab: React.FC = () => {
  const { t } = useTranslation();
  const { token } = theme.useToken();
  const { theme: currentTheme } = useTheme();
  const isDark = currentTheme === 'dark' || (currentTheme === 'system' && window.matchMedia('(prefers-color-scheme: dark)').matches);

  return (
    <div style={{ 
      padding: '24px', 
      height: '100%', 
      display: 'flex', 
      flexDirection: 'column', 
      gap: 20,
      background: token.colorBgLayout
    }} data-ec-scope="lightrag-ported">
      {/* Header */}
      <div style={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        padding: '16px 0',
        marginBottom: 8
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <div style={{ 
            width: 36, 
            height: 36, 
            borderRadius: 8, 
            background: `linear-gradient(135deg, ${token.colorPrimary} 0%, ${token.colorPrimaryHover} 100%)`,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center'
          }}>
            <ApartmentOutlined style={{ fontSize: 18, color: '#ffffff' }} />
          </div>
          <div>
            <h3 style={{ margin: 0, fontSize: 18, fontWeight: 600, color: token.colorText, lineHeight: 1.2 }}>
              {t('pages.knowledge.graph.title')}
            </h3>
            <p style={{ margin: '4px 0 0 0', fontSize: 13, color: token.colorTextSecondary }}>
              {t('pages.knowledge.graph.subtitle')}
            </p>
          </div>
        </div>
      </div>

      {/* Graph Viewer */}
      <div style={{ 
        flex: 1,
        minHeight: 0,
        border: `2px solid ${token.colorBorder}`, 
        borderRadius: 16, 
        overflow: 'hidden',
        background: token.colorBgContainer,
        boxShadow: isDark ? '0 6px 24px rgba(0, 0, 0, 0.2)' : '0 6px 24px rgba(0, 0, 0, 0.08)'
      }}>
        <GraphViewer />
      </div>
    </div>
  );
};

export default GraphTab;
