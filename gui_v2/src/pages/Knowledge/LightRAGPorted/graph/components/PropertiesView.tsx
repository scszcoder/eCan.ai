import React, { useMemo } from 'react';
import { theme } from 'antd';
import { useGraphStore } from '../stores/graph';

const PropertiesView: React.FC = () => {
  const { token } = theme.useToken();
  
  const boxStyle: React.CSSProperties = {
    background: token.colorBgElevated,
    border: `1px solid ${token.colorBorder}`,
    borderRadius: 8,
    padding: 8,
    fontSize: 12,
    maxWidth: 280,
    color: token.colorText,
  };

  const rowStyle: React.CSSProperties = { display: 'flex', gap: 6, alignItems: 'baseline' };
  const nameStyle: React.CSSProperties = { color: token.colorTextSecondary, whiteSpace: 'nowrap' };
  const selectedNode = useGraphStore(s => s.selectedNode);
  const focusedNode = useGraphStore(s => s.focusedNode);
  const selectedEdge = useGraphStore(s => s.selectedEdge);
  const focusedEdge = useGraphStore(s => s.focusedEdge);
  const sigmaGraph = useGraphStore(s => s.sigmaGraph);

  const current = useMemo(() => {
    if (!sigmaGraph) return null;
    const nodeId = focusedNode || selectedNode;
    if (nodeId && sigmaGraph.hasNode(nodeId)) {
      const label = sigmaGraph.getNodeAttribute(nodeId, 'label');
      const size = sigmaGraph.getNodeAttribute(nodeId, 'size');
      return { type: 'node' as const, id: nodeId, label, size };
    }
    const edgeId = focusedEdge || selectedEdge;
    if (edgeId && sigmaGraph.hasEdge(edgeId)) {
      const [source, target] = sigmaGraph.extremities(edgeId);
      const size = sigmaGraph.getEdgeAttribute(edgeId, 'size');
      const label = sigmaGraph.getEdgeAttribute(edgeId, 'label');
      return { type: 'edge' as const, id: edgeId, source, target, size, label };
    }
    return null;
  }, [sigmaGraph, selectedNode, focusedNode, selectedEdge, focusedEdge]);

  if (!current) return null;

  return (
    <div style={boxStyle}>
      {current.type === 'node' ? (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
          <div style={rowStyle}><span style={nameStyle}>Type</span><span>Node</span></div>
          <div style={rowStyle}><span style={nameStyle}>ID</span><span>{current.id}</span></div>
          {current.label && <div style={rowStyle}><span style={nameStyle}>Label</span><span>{String(current.label)}</span></div>}
          <div style={rowStyle}><span style={nameStyle}>Size</span><span>{String(current.size)}</span></div>
        </div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
          <div style={rowStyle}><span style={nameStyle}>Type</span><span>Edge</span></div>
          <div style={rowStyle}><span style={nameStyle}>ID</span><span>{current.id}</span></div>
          <div style={rowStyle}><span style={nameStyle}>Source</span><span>{current.source}</span></div>
          <div style={rowStyle}><span style={nameStyle}>Target</span><span>{current.target}</span></div>
          {current.label && <div style={rowStyle}><span style={nameStyle}>Label</span><span>{String(current.label)}</span></div>}
          <div style={rowStyle}><span style={nameStyle}>Size</span><span>{String(current.size)}</span></div>
        </div>
      )}
    </div>
  );
};

export default PropertiesView;
