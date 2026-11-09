import React, { useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import { useGraphStore } from '../stores/graph';

const Legend: React.FC = () => {
  const { t } = useTranslation();
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
      background: 'var(--surface-panel)',
      border: '1px solid var(--border-color)',
      borderRadius: 12,
      padding: '12px 16px',
      boxShadow: 'var(--elev-3, var(--shadow-md))',
      maxWidth: 250,
      maxHeight: 300,
      overflowY: 'auto'
    }}>
      <div style={{
        fontSize: 12,
        fontWeight: 600,
        color: 'var(--text-secondary)',
        marginBottom: 8,
        textTransform: 'uppercase',
        letterSpacing: '0.5px'
      }}>
        {t('graphPanel.legend.title', '图例')}
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
              border: '1px solid var(--border-color-hover)'
            }} />
            <span style={{
              fontSize: 13,
              color: 'var(--text-primary)',
              fontWeight: 500,
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
