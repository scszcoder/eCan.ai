import React, { useCallback, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useSigma, useCamera } from '@react-sigma/core';
import { useGraphStore } from '../stores/graph';
import { Search } from 'lucide-react';
import { theme } from 'antd';
import { useTheme } from '@/contexts/ThemeContext';

const SearchControls: React.FC = () => {
  const { t } = useTranslation();
  const { token } = theme.useToken();
  const { theme: currentTheme } = useTheme();
  const isDark = currentTheme === 'dark' || (currentTheme === 'system' && window.matchMedia('(prefers-color-scheme: dark)').matches);
  
  const sigma = useSigma();
  const { goto } = useCamera({ duration: 400 });
  const graph = useMemo(() => sigma.getGraph(), [sigma]);
  const [labelQuery, setLabelQuery] = useState('');
  const [nodeQuery, setNodeQuery] = useState('');

  const inputWrap: React.CSSProperties = {
    display: 'flex',
    alignItems: 'center',
    gap: 8,
    background: '#ffffff',
    border: `1px solid rgba(0, 0, 0, 0.08)`,
    borderRadius: 12,
    padding: '10px 16px',
    height: 44,
    boxShadow: '0 2px 8px rgba(0, 0, 0, 0.08), 0 1px 2px rgba(0, 0, 0, 0.05)',
    transition: 'all 0.2s ease',
  };

  const inputStyle: React.CSSProperties = {
    border: 'none',
    outline: 'none',
    background: 'transparent',
    color: '#000000',
    width: 200,
    fontSize: 14,
    fontWeight: 500,
  };

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
    <div style={{ display: 'flex', gap: 10 }}>
      <form 
        onSubmit={onSearchLabels} 
        style={inputWrap}
        onFocus={(e) => {
          e.currentTarget.style.borderColor = token.colorPrimary;
          e.currentTarget.style.boxShadow = `0 2px 12px ${token.colorPrimary}30, 0 1px 4px ${token.colorPrimary}20`;
        }}
        onBlur={(e) => {
          e.currentTarget.style.borderColor = 'rgba(0, 0, 0, 0.08)';
          e.currentTarget.style.boxShadow = '0 2px 8px rgba(0, 0, 0, 0.08), 0 1px 2px rgba(0, 0, 0, 0.05)';
        }}
      >
        <Search size={18} color={token.colorPrimary} strokeWidth={2.5} />
        <input
          style={inputStyle}
          placeholder={t('pages.knowledge.graph.searchLabels')}
          value={labelQuery}
          onChange={(e) => setLabelQuery(e.target.value)}
        />
      </form>
      <form 
        onSubmit={onSearchNode} 
        style={inputWrap}
        onFocus={(e) => {
          e.currentTarget.style.borderColor = token.colorPrimary;
          e.currentTarget.style.boxShadow = `0 2px 12px ${token.colorPrimary}30, 0 1px 4px ${token.colorPrimary}20`;
        }}
        onBlur={(e) => {
          e.currentTarget.style.borderColor = 'rgba(0, 0, 0, 0.08)';
          e.currentTarget.style.boxShadow = '0 2px 8px rgba(0, 0, 0, 0.08), 0 1px 2px rgba(0, 0, 0, 0.05)';
        }}
      >
        <Search size={18} color={token.colorPrimary} strokeWidth={2.5} />
        <input
          style={inputStyle}
          placeholder={t('pages.knowledge.graph.searchNode')}
          value={nodeQuery}
          onChange={(e) => setNodeQuery(e.target.value)}
        />
      </form>
    </div>
  );
};

export default SearchControls;
