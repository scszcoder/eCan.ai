import React, { useCallback } from 'react';
import { useTranslation } from 'react-i18next';
import { RefreshCw, Circle, Shuffle, Focus, ZoomIn, ZoomOut } from 'lucide-react';
import { useSigma, useCamera } from '@react-sigma/core';
import { useLayoutCircular } from '@react-sigma/layout-circular';
import { useLayoutRandom } from '@react-sigma/layout-random';
import { useLayoutNoverlap } from '@react-sigma/layout-noverlap';
import { useLayoutForceAtlas2 } from '@react-sigma/layout-forceatlas2';
import { animateNodes } from 'sigma/utils';
import { theme } from 'antd';
import { useTheme } from '@/contexts/ThemeContext';

const IconToolbar: React.FC = () => {
  const { t } = useTranslation();
  const { token } = theme.useToken();
  const { theme: currentTheme } = useTheme();
  const isDark = currentTheme === 'dark' || (currentTheme === 'system' && window.matchMedia('(prefers-color-scheme: dark)').matches);
  
  const barStyle: React.CSSProperties = {
    display: 'flex',
    flexDirection: 'column',
    gap: 8,
    background: '#ffffff',
    border: `1px solid rgba(0, 0, 0, 0.08)`,
    borderRadius: 12,
    padding: 8,
    boxShadow: '0 2px 8px rgba(0, 0, 0, 0.08), 0 1px 2px rgba(0, 0, 0, 0.05)',
  };

  const iconBtn: React.CSSProperties = {
    width: 36,
    height: 36,
    display: 'grid',
    placeItems: 'center',
    background: 'transparent',
    border: 'none',
    borderRadius: 8,
    cursor: 'pointer',
    transition: 'all 0.2s',
  };
  
  const sigma = useSigma();
  const circular = useLayoutCircular();
  const random = useLayoutRandom();
  const noverlap = useLayoutNoverlap({ settings: { margin: 5, expansion: 1.1, gridSize: 1, ratio: 1, speed: 3 } });
  const fa2 = useLayoutForceAtlas2({ iterations: 200 });
  const { zoomIn, zoomOut } = useCamera({ duration: 200, factor: 1.5 });

  const runLayout = useCallback((which: 'circular'|'random'|'noverlap'|'fa2') => {
    const graph = sigma.getGraph();
    if (!graph || graph.order === 0) return;
    const layout = which==='circular' ? circular : which==='random' ? random : which==='noverlap' ? noverlap : fa2;
    const pos = layout.positions();
    animateNodes(graph as any, pos as any, { duration: 400 });
  }, [sigma, circular, random, noverlap, fa2]);

  const hoverBg = `${token.colorPrimary}1a`;

  return (
    <div style={barStyle}>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
        <button 
          style={iconBtn} 
          title={t('pages.knowledge.graph.circularLayout')}
          onClick={() => runLayout('circular')}
          onMouseEnter={(e) => e.currentTarget.style.background = hoverBg}
          onMouseLeave={(e) => e.currentTarget.style.background = 'transparent'}
        >
          <Circle size={20} color={token.colorPrimary} strokeWidth={2.5} />
        </button>
        <button 
          style={iconBtn} 
          title={t('pages.knowledge.graph.randomLayout')}
          onClick={() => runLayout('random')}
          onMouseEnter={(e) => e.currentTarget.style.background = hoverBg}
          onMouseLeave={(e) => e.currentTarget.style.background = 'transparent'}
        >
          <Shuffle size={20} color={token.colorPrimary} strokeWidth={2.5} />
        </button>
        <button 
          style={iconBtn} 
          title={t('pages.knowledge.graph.noverlapLayout')}
          onClick={() => runLayout('noverlap')}
          onMouseEnter={(e) => e.currentTarget.style.background = hoverBg}
          onMouseLeave={(e) => e.currentTarget.style.background = 'transparent'}
        >
          <Focus size={20} color={token.colorPrimary} strokeWidth={2.5} />
        </button>
        <button 
          style={iconBtn} 
          title={t('pages.knowledge.graph.forceAtlas2Layout')}
          onClick={() => runLayout('fa2')}
          onMouseEnter={(e) => e.currentTarget.style.background = hoverBg}
          onMouseLeave={(e) => e.currentTarget.style.background = 'transparent'}
        >
          <RefreshCw size={20} color={token.colorPrimary} strokeWidth={2.5} />
        </button>
      </div>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 4, marginTop: 4, paddingTop: 8, borderTop: `1px solid ${token.colorBorderSecondary}` }}>
        <button 
          style={iconBtn} 
          title={t('pages.knowledge.graph.zoomIn')}
          onClick={() => zoomIn()}
          onMouseEnter={(e) => e.currentTarget.style.background = hoverBg}
          onMouseLeave={(e) => e.currentTarget.style.background = 'transparent'}
        >
          <ZoomIn size={20} color={token.colorSuccess} strokeWidth={2.5} />
        </button>
        <button 
          style={iconBtn} 
          title={t('pages.knowledge.graph.zoomOut')}
          onClick={() => zoomOut()}
          onMouseEnter={(e) => e.currentTarget.style.background = hoverBg}
          onMouseLeave={(e) => e.currentTarget.style.background = 'transparent'}
        >
          <ZoomOut size={20} color={token.colorError} strokeWidth={2.5} />
        </button>
      </div>
    </div>
  );
};

export default IconToolbar;
