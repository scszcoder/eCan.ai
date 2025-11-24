import React, { useEffect } from 'react';
import { SigmaContainer, useSigma } from '@react-sigma/core';
import '@react-sigma/core/lib/style.css';
import { UndirectedGraph } from 'graphology';
import { useGraphStore } from './stores/graph';
import useLightragGraph from './hooks/useLightragGraph';
import GraphControl from './components/GraphControl';
import PropertiesView from './components/PropertiesView';
import SearchControls from './components/SearchControls';
import IconToolbar from './components/IconToolbar';
import FocusOnNode from './components/FocusOnNode';
import GraphLabels from './components/GraphLabels';
import Legend from './components/Legend';
import { useSettingsStore } from './stores/settings';

const InitGraph: React.FC = () => {
  const sigma = useSigma();

  useEffect(() => {
    // Build a tiny placeholder graph so the viewer renders immediately
    const g = new UndirectedGraph();
    g.addNode('A', { x: 0.3, y: 0.5, size: 8, label: 'A' });
    g.addNode('B', { x: 0.7, y: 0.5, size: 8, label: 'B' });
    g.addEdge('A', 'B', { size: 2 });

    try {
      // Bind to sigma
      // @ts-ignore - setGraph exists on Sigma 3
      if (typeof (sigma as any).setGraph === 'function') {
        (sigma as any).setGraph(g);
      } else {
        (sigma as any).graph = g;
      }
      useGraphStore.getState().setSigmaInstance(sigma as any);
      useGraphStore.getState().setSigmaGraph(g as any);
    } catch (e) {
      // noop
    }
  }, [sigma]);
  return null;
};

const ResizeHandler: React.FC = () => {
  const sigma = useSigma();
  useEffect(() => {
    const onResize = () => {
      try {
        // @ts-ignore
        sigma.refresh?.();
      } catch {}
    };
    // Defer a refresh after mount to catch late layout sizing
    const t = setTimeout(onResize, 0);
    window.addEventListener('resize', onResize);
    return () => {
      clearTimeout(t);
      window.removeEventListener('resize', onResize);
    };
  }, [sigma]);
  return null;
};

const GraphViewer: React.FC = () => {
  // Fetch and populate graph from backend via IPC
  useLightragGraph();
  const showPropertyPanel = useSettingsStore(s => s.showPropertyPanel);
  const showLegend = useSettingsStore(s => s.showLegend);
  const selectedNode = useGraphStore(s => s.selectedNode);
  const moveToSelectedNode = useGraphStore(s => s.moveToSelectedNode);
  
  return (
    <div style={{ position: 'relative', width: '100%', height: '100%', background: '#ffffff' }}>
      <SigmaContainer className="!size-full" style={{ width: '100%', height: '100%', background: '#ffffff' }} settings={{ allowInvalidContainer: true }}>
        <InitGraph />
        <GraphControl />
        <FocusOnNode node={selectedNode} move={moveToSelectedNode} />
        <ResizeHandler />

        {/* Top-left: Graph Labels selector and search controls */}
        <div style={{ position: 'absolute', top: 8, left: 8, display: 'flex', flexDirection: 'column', gap: 8 }}>
          <GraphLabels />
          <SearchControls />
        </div>

        {/* Bottom-left: floating vertical icon toolbar */}
        <div style={{ position: 'absolute', bottom: 8, left: 8 }}>
          <IconToolbar />
        </div>

        {/* Right-top properties panel */}
        {showPropertyPanel && (
          <div style={{ position: 'absolute', top: 8, right: 8 }}>
            <PropertiesView />
          </div>
        )}

        {/* Bottom-right: Legend */}
        {showLegend && <Legend />}
      </SigmaContainer>
    </div>
  );
};

export default GraphViewer;
