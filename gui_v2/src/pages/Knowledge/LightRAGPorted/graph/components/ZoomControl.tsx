import React, { useCallback } from 'react';
import { useTranslation } from 'react-i18next';
import { useCamera, useSigma } from '@react-sigma/core';
import { Button, Tooltip } from 'antd';
import { ZoomIn, ZoomOut, Maximize2, RotateCw, RotateCcw } from 'lucide-react';

const ZoomControl: React.FC = () => {
  const { t } = useTranslation();
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

  const handleRotate = useCallback(() => {
    if (!sigma) return;
    const camera = sigma.getCamera();
    const currentAngle = camera.angle;
    const newAngle = currentAngle + Math.PI / 8;
    camera.animate({ angle: newAngle }, { duration: 200 });
  }, [sigma]);

  const handleRotateCounterClockwise = useCallback(() => {
    if (!sigma) return;
    const camera = sigma.getCamera();
    const currentAngle = camera.angle;
    const newAngle = currentAngle - Math.PI / 8;
    camera.animate({ angle: newAngle }, { duration: 200 });
  }, [sigma]);

  return (
    <>
      <Tooltip title={t('graphPanel.sideBar.zoomControl.rotateClockwise', '顺时针旋转')} placement="right">
        <Button
          type="text"
          icon={<RotateCw size={18} style={{ color: '#ffffff' }} />}
          onClick={handleRotate}
          style={{ width: 36, height: 36, color: '#ffffff' }}
        />
      </Tooltip>
      <Tooltip title={t('graphPanel.sideBar.zoomControl.rotateCounterClockwise', '逆时针旋转')} placement="right">
        <Button
          type="text"
          icon={<RotateCcw size={18} style={{ color: '#ffffff' }} />}
          onClick={handleRotateCounterClockwise}
          style={{ width: 36, height: 36, color: '#ffffff' }}
        />
      </Tooltip>
      <Tooltip title={t('graphPanel.sideBar.zoomControl.reset', '重置视图')} placement="right">
        <Button
          type="text"
          icon={<Maximize2 size={18} style={{ color: '#ffffff' }} />}
          onClick={onReset}
          style={{ width: 36, height: 36, color: '#ffffff' }}
        />
      </Tooltip>
      <Tooltip title={t('graphPanel.sideBar.zoomControl.zoomIn', '放大')} placement="right">
        <Button
          type="text"
          icon={<ZoomIn size={18} style={{ color: '#ffffff' }} />}
          onClick={() => zoomIn()}
          style={{ width: 36, height: 36, color: '#ffffff' }}
        />
      </Tooltip>
      <Tooltip title={t('graphPanel.sideBar.zoomControl.zoomOut', '缩小')} placement="right">
        <Button
          type="text"
          icon={<ZoomOut size={18} style={{ color: '#ffffff' }} />}
          onClick={() => zoomOut()}
          style={{ width: 36, height: 36, color: '#ffffff' }}
        />
      </Tooltip>
    </>
  );
};

export default ZoomControl;
