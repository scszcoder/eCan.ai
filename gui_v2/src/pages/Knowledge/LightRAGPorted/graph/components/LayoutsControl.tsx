import React, { useCallback } from 'react';
import { useTranslation } from 'react-i18next';
import { useSigma } from '@react-sigma/core';
import { animateNodes } from 'sigma/utils';
import { useLayoutCircular } from '@react-sigma/layout-circular';
import { useLayoutRandom } from '@react-sigma/layout-random';
import { useLayoutNoverlap } from '@react-sigma/layout-noverlap';
import { useLayoutForceAtlas2 } from '@react-sigma/layout-forceatlas2';
import { theme } from 'antd';
import { useTheme } from '@/contexts/ThemeContext';

const LayoutsControl: React.FC = () => {
  const { t } = useTranslation();
  const { token } = theme.useToken();
  const { theme: currentTheme } = useTheme();
  const isDark = currentTheme === 'dark' || (currentTheme === 'system' && window.matchMedia('(prefers-color-scheme: dark)').matches);
  
  const btnStyle: React.CSSProperties = { 
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
  const groupStyle: React.CSSProperties = { display: 'flex', gap: 8 };
  
  const hoverBg = `${token.colorPrimary}1a`;
  const hoverBorder = `${token.colorPrimary}40`;
  
  const sigma = useSigma();
  const circular = useLayoutCircular();
  const random = useLayoutRandom();
  const noverlap = useLayoutNoverlap({ settings: { margin: 5, expansion: 1.1, gridSize: 1, ratio: 1, speed: 3 } });
  const fa2 = useLayoutForceAtlas2({ iterations: 200 });

  const run = useCallback((which: 'circular'|'random'|'noverlap'|'fa2') => {
    const graph = sigma.getGraph();
    if (!graph || graph.order === 0) return;
    const layout = which==='circular' ? circular : which==='random' ? random : which==='noverlap' ? noverlap : fa2;
    const pos = layout.positions();
    animateNodes(graph as any, pos as any, { duration: 400 });
  }, [sigma, circular, random, noverlap, fa2]);

  const handleMouseEnter = (e: React.MouseEvent<HTMLButtonElement>) => {
    e.currentTarget.style.background = hoverBg;
    e.currentTarget.style.borderColor = hoverBorder;
  };

  const handleMouseLeave = (e: React.MouseEvent<HTMLButtonElement>) => {
    e.currentTarget.style.background = token.colorBgContainer;
    e.currentTarget.style.borderColor = token.colorBorder;
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
      <div style={groupStyle}>
        <button 
          style={btnStyle} 
          onClick={() => run('circular')}
          onMouseEnter={handleMouseEnter}
          onMouseLeave={handleMouseLeave}
        >
          {t('pages.knowledge.graph.circularLayout')}
        </button>
        <button 
          style={btnStyle} 
          onClick={() => run('random')}
          onMouseEnter={handleMouseEnter}
          onMouseLeave={handleMouseLeave}
        >
          {t('pages.knowledge.graph.randomLayout')}
        </button>
      </div>
      <div style={groupStyle}>
        <button 
          style={btnStyle} 
          onClick={() => run('noverlap')}
          onMouseEnter={handleMouseEnter}
          onMouseLeave={handleMouseLeave}
        >
          {t('pages.knowledge.graph.noverlapLayout')}
        </button>
        <button 
          style={btnStyle} 
          onClick={() => run('fa2')}
          onMouseEnter={handleMouseEnter}
          onMouseLeave={handleMouseLeave}
        >
          {t('pages.knowledge.graph.forceAtlas2Layout')}
        </button>
      </div>
    </div>
  );
};

export default LayoutsControl;
