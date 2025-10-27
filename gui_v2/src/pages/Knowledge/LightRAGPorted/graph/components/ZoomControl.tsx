import React, { useCallback } from 'react';
import { useTranslation } from 'react-i18next';
import { useCamera, useSigma } from '@react-sigma/core';
import { theme } from 'antd';
import { useTheme } from '@/contexts/ThemeContext';

const ZoomControl: React.FC = () => {
  const { t } = useTranslation();
  const { token } = theme.useToken();
  const { theme: currentTheme } = useTheme();
  const isDark = currentTheme === 'dark' || (currentTheme === 'system' && window.matchMedia('(prefers-color-scheme: dark)').matches);
  
  const btn: React.CSSProperties = { 
    padding: '6px 12px', 
    border: `1px solid ${token.colorBorder}`, 
    borderRadius: 8, 
    background: token.colorBgContainer, 
    color: token.colorText, 
    cursor: 'pointer', 
    fontSize: 13,
    fontWeight: 500,
    boxShadow: isDark ? '0 2px 6px rgba(0, 0, 0, 0.2)' : '0 2px 6px rgba(0, 0, 0, 0.08)',
    transition: 'all 0.2s',
  };
  
  const hoverBg = `${token.colorPrimary}1a`;
  const hoverBorder = `${token.colorPrimary}40`;
  
  const { zoomIn, zoomOut, reset } = useCamera({ duration: 200, factor: 1.5 });
  const sigma = useSigma();

  const onReset = useCallback(() => {
    try {
      // @ts-ignore
      sigma.setCustomBBox?.(null);
      sigma.refresh();
      reset();
    } catch {
      reset();
    }
  }, [sigma, reset]);

  return (
    <div style={{ display: 'flex', gap: 8 }}>
      <button 
        style={btn} 
        onClick={() => zoomIn()}
        onMouseEnter={(e) => {
          e.currentTarget.style.background = hoverBg;
          e.currentTarget.style.borderColor = hoverBorder;
        }}
        onMouseLeave={(e) => {
          e.currentTarget.style.background = token.colorBgContainer;
          e.currentTarget.style.borderColor = token.colorBorder;
        }}
      >
        {t('pages.knowledge.graph.zoomIn')}
      </button>
      <button 
        style={btn} 
        onClick={() => zoomOut()}
        onMouseEnter={(e) => {
          e.currentTarget.style.background = hoverBg;
          e.currentTarget.style.borderColor = hoverBorder;
        }}
        onMouseLeave={(e) => {
          e.currentTarget.style.background = token.colorBgContainer;
          e.currentTarget.style.borderColor = token.colorBorder;
        }}
      >
        {t('pages.knowledge.graph.zoomOut')}
      </button>
      <button 
        style={btn} 
        onClick={onReset}
        onMouseEnter={(e) => {
          e.currentTarget.style.background = hoverBg;
          e.currentTarget.style.borderColor = hoverBorder;
        }}
        onMouseLeave={(e) => {
          e.currentTarget.style.background = token.colorBgContainer;
          e.currentTarget.style.borderColor = token.colorBorder;
        }}
      >
        {t('common.reset')}
      </button>
    </div>
  );
};

export default ZoomControl;
