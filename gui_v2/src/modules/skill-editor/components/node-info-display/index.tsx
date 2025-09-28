import React, { useEffect, useState } from 'react';
import { useClientContext } from '@flowgram.ai/free-layout-editor';
import { TransformData, WorkflowNodeEntity } from '@flowgram.ai/free-layout-editor';

const style: React.CSSProperties = {
  position: 'absolute',
  bottom: 10,
  right: 10,
  zIndex: 1000,
  background: 'rgba(255,255,255,0.9)',
  border: '1px solid #eee',
  borderRadius: 4,
  padding: '4px 12px',
  fontSize: 14,
  color: '#333',
  pointerEvents: 'none',
  minWidth: 120,
};

export const NodeInfoDisplay: React.FC = () => {
  const { selection } = useClientContext();
  const [coords, setCoords] = useState<{ x: number; y: number } | null>(null);

  useEffect(() => {
    function updateCoords() {
      if (
        selection.selection.length === 1 &&
        selection.selection[0] instanceof WorkflowNodeEntity
      ) {
        const node = selection.selection[0] as WorkflowNodeEntity;
        const transform = node.getData(TransformData);
        if (transform && transform.bounds) {
          setCoords({ x: transform.bounds.x, y: transform.bounds.y });
        } else {
          setCoords(null);
        }
      } else {
        setCoords(null);
      }
    }
    updateCoords();
    const dispose = selection.onSelectionChanged(updateCoords);
    return () => dispose.dispose();
  }, [selection]);

  return (
    <div style={{ position: 'relative', zIndex: 100 }}>
      {coords && (
        <div style={style}>
          <span>Position: X = {coords.x}, Y = {coords.y}</span>
        </div>
      )}
    </div>
  );
}; 