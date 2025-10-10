import React, { useCallback } from 'react';
import { useSigma } from '@react-sigma/core';
import { animateNodes } from 'sigma/utils';
import { useLayoutCircular } from '@react-sigma/layout-circular';
import { useLayoutRandom } from '@react-sigma/layout-random';
import { useLayoutNoverlap } from '@react-sigma/layout-noverlap';
import { useLayoutForceAtlas2 } from '@react-sigma/layout-forceatlas2';

const btnStyle: React.CSSProperties = { padding: '4px 8px', border: '1px solid #d9d9d9', borderRadius: 6, background: '#fff', color: '#111', cursor: 'pointer', fontSize: 12 };
const groupStyle: React.CSSProperties = { display: 'flex', gap: 6 };

const LayoutsControl: React.FC = () => {
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

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
      <div style={groupStyle}>
        <button style={btnStyle} onClick={() => run('circular')}>Circular</button>
        <button style={btnStyle} onClick={() => run('random')}>Random</button>
      </div>
      <div style={groupStyle}>
        <button style={btnStyle} onClick={() => run('noverlap')}>Noverlap</button>
        <button style={btnStyle} onClick={() => run('fa2')}>Force Atlas2</button>
      </div>
    </div>
  );
};

export default LayoutsControl;
