import React, { useMemo } from 'react';
import { theme } from 'antd';
import { useGraphStore } from '../stores/graph';
import { useTheme } from '@/contexts/ThemeContext';

const Legend: React.FC = () => {
  const { token } = theme.useToken();
  const { theme: currentTheme } = useTheme();
  const isDark = currentTheme === 'dark' || (currentTheme === 'system' && window.matchMedia('(prefers-color-scheme: dark)').matches);
  
  const typeColorMap = useGraphStore((s) => s.typeColorMap);

  // 将 Map 转换为数组以便渲染
  const legendItems = useMemo(() => {
    const items: Array<{ type: string; color: string }> = [];
    typeColorMap.forEach((color, type) => {
      items.push({ type, color });
    });
    return items.sort((a, b) => a.type.localeCompare(b.type));
  }, [typeColorMap]);

  if (legendItems.length === 0) {
    return null;
  }

  return (
    <div style={{
      position: 'absolute',
      bottom: 16,
      right: 16,
      background: isDark ? 'rgba(0, 0, 0, 0.75)' : 'rgba(255, 255, 255, 0.95)',
      border: `1px solid ${token.colorBorder}`,
      borderRadius: token.borderRadiusLG,
      padding: '12px 16px',
      boxShadow: token.boxShadowSecondary,
      backdropFilter: 'blur(8px)',
      maxWidth: 250,
      maxHeight: 300,
      overflowY: 'auto'
    }}>
      <div style={{
        fontSize: 12,
        fontWeight: 600,
        color: token.colorTextSecondary,
        marginBottom: 8,
        textTransform: 'uppercase',
        letterSpacing: '0.5px'
      }}>
        图例
      </div>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
        {legendItems.map(({ type, color }) => (
          <div key={type} style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <div style={{
              width: 12,
              height: 12,
              borderRadius: '50%',
              background: color,
              flexShrink: 0,
              border: `1px solid ${isDark ? 'rgba(255,255,255,0.1)' : 'rgba(0,0,0,0.1)'}`
            }} />
            <span style={{
              fontSize: 13,
              color: token.colorText,
              overflow: 'hidden',
              textOverflow: 'ellipsis',
              whiteSpace: 'nowrap'
            }} title={type}>
              {type}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
};

export default Legend;
