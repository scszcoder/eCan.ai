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
      background: 'rgba(45, 55, 72, 0.95)',
      border: '2px solid rgba(255, 255, 255, 0.2)',
      borderRadius: 12,
      padding: '12px 16px',
      boxShadow: '0 4px 12px rgba(0, 0, 0, 0.3)',
      backdropFilter: 'blur(12px)',
      maxWidth: 250,
      maxHeight: 300,
      overflowY: 'auto'
    }}>
      <div style={{
        fontSize: 12,
        fontWeight: 600,
        color: 'rgba(255, 255, 255, 0.9)',
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
              border: '1px solid rgba(255, 255, 255, 0.3)',
              boxShadow: '0 0 4px rgba(255, 255, 255, 0.2)'
            }} />
            <span style={{
              fontSize: 13,
              color: '#ffffff',
              fontWeight: 500,
              overflow: 'hidden',
              textOverflow: 'ellipsis',
              whiteSpace: 'nowrap',
              textShadow: '0 1px 2px rgba(0, 0, 0, 0.5)'
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
