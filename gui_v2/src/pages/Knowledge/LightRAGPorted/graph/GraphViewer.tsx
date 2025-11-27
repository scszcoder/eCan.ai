import React, { useEffect } from 'react';
import { SigmaContainer, useSigma } from '@react-sigma/core';
import '@react-sigma/core/lib/style.css';
import { UndirectedGraph } from 'graphology';
import { useGraphStore } from './stores/graph';
import useLightragGraph from './hooks/useLightragGraph';
import GraphControl from './components/GraphControl';
import PropertiesView from './components/PropertiesView';
import GraphSearch, { OptionItem } from './components/GraphSearch';
import FocusOnNode from './components/FocusOnNode';
import GraphLabels from './components/GraphLabels';
import Legend from './components/Legend';
import { useSettingsStore } from './stores/settings';
import LayoutsControl from './components/LayoutsControl';
import ZoomControl from './components/ZoomControl';
import FullScreenControl from './components/FullScreenControl';
import LegendButton from './components/LegendButton';
import SettingsButton from './components/SettingsButton';
import SettingsDisplay from './components/SettingsDisplay';
import DragNodes from './components/DragNodes';

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
  const showNodeSearchBar = useSettingsStore(s => s.showNodeSearchBar);
  const showLegend = useSettingsStore(s => s.showLegend);
  const selectedNode = useGraphStore(s => s.selectedNode);
  const focusedNode = useGraphStore(s => s.focusedNode);
  const moveToSelectedNode = useGraphStore(s => s.moveToSelectedNode);

  const onSearchFocus = React.useCallback((value: OptionItem | null) => {
    if (value === null) useGraphStore.getState().setFocusedNode(null);
    else if (value.type === 'nodes') useGraphStore.getState().setFocusedNode(value.id);
  }, []);

  const onSearchSelect = React.useCallback((value: OptionItem | null) => {
    if (value === null) {
      useGraphStore.getState().setSelectedNode(null);
    } else if (value.type === 'nodes') {
      useGraphStore.getState().setSelectedNode(value.id, true);
    }
  }, []);

  const autoFocusedNode = React.useMemo(() => focusedNode ?? selectedNode, [focusedNode, selectedNode]);
  const searchInitSelectedNode = React.useMemo(
    (): OptionItem | null => (selectedNode ? { type: 'nodes', id: selectedNode } : null),
    [selectedNode]
  );
  
  // 添加调试日志
  React.useEffect(() => {
    console.log('[GraphViewer] Component mounted');
    console.log('[GraphViewer] Body classes:', document.body.className);
    return () => {
      console.log('[GraphViewer] Component unmounted');
    };
  }, []);

  return (
    <div className="graph-viewer-container" style={{ position: 'relative', width: '100%', height: '100%', background: '#ffffff' }}>
      <style>{`
        /* 全屏模式样式 */
        body.graph-fullscreen-active {
          overflow: hidden !important;
        }
        
        /* 隐藏所有顶部UI元素 */
        body.graph-fullscreen-active .ant-layout-header,
        body.graph-fullscreen-active .ant-layout-sider,
        body.graph-fullscreen-active .ant-breadcrumb,
        body.graph-fullscreen-active nav:not(.graph-viewer-container nav),
        body.graph-fullscreen-active header:not(.graph-viewer-container header),
        body.graph-fullscreen-active [class*="Header"]:not(.graph-viewer-container [class*="Header"]),
        body.graph-fullscreen-active [class*="header"]:not(.graph-viewer-container [class*="header"]),
        body.graph-fullscreen-active [class*="Navigation"]:not(.graph-viewer-container [class*="Navigation"]),
        body.graph-fullscreen-active [class*="navigation"]:not(.graph-viewer-container [class*="navigation"]),
        body.graph-fullscreen-active [class*="TopBar"]:not(.graph-viewer-container [class*="TopBar"]),
        body.graph-fullscreen-active [class*="topbar"]:not(.graph-viewer-container [class*="topbar"]) {
          display: none !important;
          visibility: hidden !important;
          height: 0 !important;
          overflow: hidden !important;
        }
        
        /* 隐藏知识库页面内的Header和Tabs（前两个子元素） */
        body.graph-fullscreen-active [data-ec-scope="lightrag-ported"] > *:nth-child(1),
        body.graph-fullscreen-active [data-ec-scope="lightrag-ported"] > *:nth-child(2),
        body.graph-fullscreen-active [data-ec-scope="lightrag-ported"] > *:nth-child(4) {
          display: none !important;
          visibility: hidden !important;
          height: 0 !important;
        }
        
        /* 确保第三个子元素（GraphTab）可见并充满 */
        body.graph-fullscreen-active [data-ec-scope="lightrag-ported"] > *:nth-child(3) {
          display: flex !important;
          visibility: visible !important;
          height: 100% !important;
          width: 100% !important;
          flex: 1 !important;
          opacity: 1 !important;
        }
        
        /* 确保图谱容器可见并充满 */
        body.graph-fullscreen-active .graph-viewer-container {
          display: block !important;
          visibility: visible !important;
          width: 100% !important;
          height: 100% !important;
          opacity: 1 !important;
        }
        
        /* 确保Sigma容器可见 */
        body.graph-fullscreen-active .graph-viewer-container > *,
        body.graph-fullscreen-active .sigma-container,
        body.graph-fullscreen-active .sigma-container > * {
          display: block !important;
          visibility: visible !important;
          opacity: 1 !important;
        }
        
        /* 强制隐藏Layout的header部分 */
        body.graph-fullscreen-active .ant-layout > .ant-layout-header,
        body.graph-fullscreen-active .ant-layout > header {
          display: none !important;
          visibility: hidden !important;
          height: 0 !important;
        }
        
        /* 激进方案：隐藏body的所有直接子元素，除了包含图谱的元素 */
        body.graph-fullscreen-active > *:not(#root) {
          display: none !important;
        }
        
        /* 隐藏root下的所有直接子元素，除了包含图谱的Layout */
        body.graph-fullscreen-active #root > *:not(.ant-layout) {
          display: none !important;
        }
        
        /* 隐藏Layout下的所有直接子元素，除了content */
        body.graph-fullscreen-active .ant-layout > *:not(.ant-layout-content) {
          display: none !important;
          visibility: hidden !important;
          height: 0 !important;
        }
        
        /* 确保所有父容器不限制大小 */
        body.graph-fullscreen-active,
        body.graph-fullscreen-active #root,
        body.graph-fullscreen-active #root > div,
        body.graph-fullscreen-active .ant-layout,
        body.graph-fullscreen-active .ant-layout-content,
        body.graph-fullscreen-active [data-ec-scope="lightrag-ported"] {
          height: 100vh !important;
          width: 100vw !important;
          padding: 0 !important;
          margin: 0 !important;
          overflow: hidden !important;
        }
        
        /* 图谱容器全屏 - 使用更高优先级 */
        body.graph-fullscreen-active .graph-viewer-container.graph-fullscreen-mode {
          display: block !important;
          visibility: visible !important;
          position: fixed !important;
          top: 0 !important;
          left: 0 !important;
          right: 0 !important;
          bottom: 0 !important;
          width: 100vw !important;
          height: 100vh !important;
          z-index: 99999 !important;
          margin: 0 !important;
          padding: 0 !important;
          background: #ffffff !important;
          opacity: 1 !important;
          border: 5px solid red !important; /* 测试：红色边框 */
        }
        
        /* 测试：给Sigma容器添加绿色边框 */
        body.graph-fullscreen-active .sigma-container {
          border: 5px solid green !important;
          min-height: 100vh !important;
          min-width: 100vw !important;
        }
        
        /* 确保 Sigma 容器也充满 */
        .graph-fullscreen-mode .sigma-container,
        .graph-fullscreen-mode canvas {
          width: 100% !important;
          height: 100% !important;
        }
        
        .graph-search-input input {
          color: #ffffff !important;
          background: transparent !important;
        }
        .graph-search-input input::placeholder {
          color: rgba(255, 255, 255, 0.5) !important;
        }
        .graph-search-input .ant-input {
          color: #ffffff !important;
          background: transparent !important;
        }
        .graph-async-select .ant-select-selector {
          background: rgba(100, 116, 139, 0.5) !important;
          border: 1px solid rgba(255, 255, 255, 0.15) !important;
          color: #ffffff !important;
          height: 40px !important;
          backdrop-filter: blur(12px) !important;
        }
        .graph-async-select .ant-select-selection-search-input {
          height: 38px !important;
        }
        .graph-async-select .ant-select-selection-item {
          color: #ffffff !important;
          line-height: 38px !important;
        }
        .graph-async-select .ant-select-selection-placeholder {
          color: rgba(255, 255, 255, 0.5) !important;
          line-height: 38px !important;
        }
        .lightrag-async-select-dropdown {
          background: rgba(45, 55, 72, 0.95) !important;
        }
        .lightrag-async-select-dropdown .ant-select-item {
          color: #ffffff !important;
        }
        .lightrag-async-select-dropdown .ant-select-item-option-selected {
          background: rgba(255, 255, 255, 0.1) !important;
          position: relative;
        }
        .lightrag-async-select-dropdown .ant-select-item-option-selected::after {
          content: '✓';
          position: absolute;
          right: 12px;
          top: 50%;
          transform: translateY(-50%);
          color: #60a5fa;
          font-weight: bold;
          font-size: 16px;
        }
        .lightrag-async-select-dropdown .ant-select-item-option-active {
          background: rgba(255, 255, 255, 0.05) !important;
        }
        .async-select-search-input input {
          color: #ffffff !important;
          background: transparent !important;
        }
        .async-select-search-input input::placeholder {
          color: rgba(255, 255, 255, 0.5) !important;
        }
        .async-select-search-input .ant-input {
          color: #ffffff !important;
          background: transparent !important;
        }
      `}</style>
      <SigmaContainer className="!size-full" style={{ width: '100%', height: '100%', background: '#ffffff' }} settings={{ allowInvalidContainer: true }}>
        <InitGraph />
        <GraphControl />
        <FocusOnNode node={autoFocusedNode} move={moveToSelectedNode} />
        <DragNodes />
        <ResizeHandler />

        {/* Top-left: Graph Labels and Search */}
        <div style={{ position: 'absolute', top: 8, left: 8, zIndex: 10, display: 'flex', gap: 8, alignItems: 'flex-start' }}>
          <GraphLabels />
          {showNodeSearchBar && (
            <div style={{ minWidth: 200 }}>
              <GraphSearch
                value={searchInitSelectedNode}
                onFocus={onSearchFocus}
                onChange={onSearchSelect}
              />
            </div>
          )}
        </div>

        {/* Bottom-left: Vertical toolbar */}
        <div style={{ 
          position: 'absolute', 
          bottom: 8, 
          left: 8, 
          zIndex: 100,
          display: 'flex',
          flexDirection: 'column',
          gap: 0,
          background: 'rgba(45, 55, 72, 0.95)',
          backdropFilter: 'blur(12px)',
          border: '2px solid rgba(255, 255, 255, 0.1)',
          borderRadius: 12,
          padding: 4,
          boxShadow: '0 4px 12px rgba(0, 0, 0, 0.3)',
          pointerEvents: 'auto'
        }}>
          <LayoutsControl />
          <ZoomControl />
          <FullScreenControl />
          <LegendButton />
          <SettingsButton />
        </div>

        {/* Right-top: Properties panel */}
        {showPropertyPanel && (
          <div style={{ position: 'absolute', top: 8, right: 8, zIndex: 10 }}>
            <PropertiesView />
          </div>
        )}

        {/* Bottom-left: Settings display */}
        <SettingsDisplay />

        {/* Bottom-right: Legend */}
        {showLegend && (
          <div style={{ position: 'absolute', bottom: 8, right: 8, zIndex: 10 }}>
            <Legend />
          </div>
        )}
      </SigmaContainer>
    </div>
  );
};

export default GraphViewer;
