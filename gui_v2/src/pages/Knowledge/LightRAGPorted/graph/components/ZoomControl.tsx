import React, { useCallback } from 'react';
import { useCamera, useSigma } from '@react-sigma/core';

const btn: React.CSSProperties = { padding: '4px 8px', border: '1px solid #d9d9d9', borderRadius: 6, background: '#fff', color: '#111', cursor: 'pointer', fontSize: 12 };

const ZoomControl: React.FC = () => {
  const { zoomIn, zoomOut, reset } = useCamera({ duration: 200, factor: 1.5 });
  const sigma = useSigma();

  const onReset = useCallback(() => {
    try {
      // @ts-ignore
      sigma.setCustomBBox?.(null);
      sigma.refresh();
      reset();
    } catch {
      reset();
    }
  }, [sigma, reset]);

  return (
    <div style={{ display: 'flex', gap: 6, color: '#111' }}>
      <button style={btn} onClick={() => zoomIn()}>Zoom In</button>
      <button style={btn} onClick={() => zoomOut()}>Zoom Out</button>
      <button style={btn} onClick={onReset}>Reset</button>
    </div>
  );
};

export default ZoomControl;
