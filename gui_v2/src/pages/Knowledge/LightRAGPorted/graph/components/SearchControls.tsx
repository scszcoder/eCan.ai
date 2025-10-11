import React, { useCallback, useMemo, useState } from 'react';
import { useSigma, useCamera } from '@react-sigma/core';
import { useGraphStore } from '../stores/graph';
import { Search } from 'lucide-react';

const inputWrap: React.CSSProperties = {
  display: 'flex',
  alignItems: 'center',
  gap: 6,
  background: 'rgba(255,255,255,0.85)',
  border: '1px solid #d9d9d9',
  borderRadius: 8,
  padding: '4px 8px',
  height: 32,
};

const inputStyle: React.CSSProperties = {
  border: 'none',
  outline: 'none',
  background: 'transparent',
  color: '#111',
  width: 200,
  fontSize: 12,
};

const SearchControls: React.FC = () => {
  const sigma = useSigma();
  const { goto } = useCamera({ duration: 400 });
  const graph = useMemo(() => sigma.getGraph(), [sigma]);
  const [labelQuery, setLabelQuery] = useState('');
  const [nodeQuery, setNodeQuery] = useState('');

  const selectAndZoom = useCallback((nodeId: string) => {
    if (!graph.hasNode(nodeId)) return false;
    useGraphStore.getState().setSelectedNode(nodeId, true);
    const dd = sigma.getNodeDisplayData(nodeId);
    if (dd) goto({ x: dd.x, y: dd.y, ratio: 0.5 });
    return true;
  }, [graph, sigma, goto]);

  const onSearchLabels = useCallback((e: React.FormEvent) => {
    e.preventDefault();
    const q = labelQuery.trim().toLowerCase();
    if (!q) return;
    let found: string | null = null;
    graph.forEachNode((n, attrs) => {
      if (found) return;
      const label = String(attrs.label || '');
      const labelsFromData = label.split(',').map(s => s.trim().toLowerCase());
      if (labelsFromData.some(l => l.includes(q))) found = n;
    });
    if (found) selectAndZoom(found);
  }, [graph, labelQuery, selectAndZoom]);

  const onSearchNode = useCallback((e: React.FormEvent) => {
    e.preventDefault();
    const q = nodeQuery.trim().toLowerCase();
    if (!q) return;
    let found: string | null = null;
    if (graph.hasNode(q)) found = q; // exact id
    if (!found) {
      graph.forEachNode((n, attrs) => {
        if (found) return;
        const label = String(attrs.label || '').toLowerCase();
        if (n.toLowerCase().includes(q) || label.includes(q)) found = n;
      });
    }
    if (found) selectAndZoom(found);
  }, [graph, nodeQuery, selectAndZoom]);

  return (
    <div style={{ display: 'flex', gap: 8 }}>
      <form onSubmit={onSearchLabels} style={inputWrap}>
        <Search size={16} color="#111" />
        <input
          style={inputStyle}
          placeholder="Search labels"
          value={labelQuery}
          onChange={(e) => setLabelQuery(e.target.value)}
        />
      </form>
      <form onSubmit={onSearchNode} style={inputWrap}>
        <Search size={16} color="#111" />
        <input
          style={inputStyle}
          placeholder="Search node"
          value={nodeQuery}
          onChange={(e) => setNodeQuery(e.target.value)}
        />
      </form>
    </div>
  );
};

export default SearchControls;
