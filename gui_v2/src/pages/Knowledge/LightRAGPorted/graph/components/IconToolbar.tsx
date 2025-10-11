import React, { useCallback } from 'react';
import { RefreshCw, Circle, Shuffle, Focus, ZoomIn, ZoomOut } from 'lucide-react';
import { useSigma, useCamera } from '@react-sigma/core';
import { useLayoutCircular } from '@react-sigma/layout-circular';
import { useLayoutRandom } from '@react-sigma/layout-random';
import { useLayoutNoverlap } from '@react-sigma/layout-noverlap';
import { useLayoutForceAtlas2 } from '@react-sigma/layout-forceatlas2';
import { animateNodes } from 'sigma/utils';

const barStyle: React.CSSProperties = {
  display: 'flex',
  flexDirection: 'column',
  gap: 8,
  background: 'rgba(255,255,255,0.85)',
  border: '1px solid #d9d9d9',
  borderRadius: 10,
  padding: 8,
  color: '#111',
};

const iconBtn: React.CSSProperties = {
  width: 36,
  height: 36,
  display: 'grid',
  placeItems: 'center',
  background: '#fff',
  border: '1px solid #d9d9d9',
  borderRadius: 8,
  cursor: 'pointer',
};

const IconToolbar: React.FC = () => {
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

  return (
    <div style={barStyle}>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
        <button style={iconBtn} title="Circular" onClick={() => runLayout('circular')}>
          <Circle size={18} color="#111" />
        </button>
        <button style={iconBtn} title="Random" onClick={() => runLayout('random')}>
          <Shuffle size={18} color="#111" />
        </button>
        <button style={iconBtn} title="Noverlap" onClick={() => runLayout('noverlap')}>
          <Focus size={18} color="#111" />
        </button>
        <button style={iconBtn} title="Force Atlas2" onClick={() => runLayout('fa2')}>
          <RefreshCw size={18} color="#111" />
        </button>
      </div>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
        <button style={iconBtn} title="Zoom In" onClick={() => zoomIn()}>
          <ZoomIn size={18} color="#111" />
        </button>
        <button style={iconBtn} title="Zoom Out" onClick={() => zoomOut()}>
          <ZoomOut size={18} color="#111" />
        </button>
      </div>
    </div>
  );
};

export default IconToolbar;
