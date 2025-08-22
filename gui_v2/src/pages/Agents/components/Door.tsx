import React, { useState, useCallback } from 'react';
import doorClosedImg from '@/assets/icons1_door_256.png';
import doorOpenImg from '@/assets/icons3_door_256.png';
import './Door.css';
import { useTranslation } from 'react-i18next';

interface DoorProps {
  name: string;
}

const Door: React.FC<DoorProps> = ({ name }) => {
  const [hovered, setHovered] = useState(false);
  const { t } = useTranslation();

  // 使用 useCallback 缓存事件处理函数
  const handleMouseEnter = useCallback(() => {
    setHovered(true);
  }, []);

  const handleMouseLeave = useCallback(() => {
    setHovered(false);
  }, []);

  return (
    <div
      className={`door custom-door${hovered ? ' opening' : ''}`}
      style={{ position: 'static', zIndex: 2 }}
      onMouseEnter={handleMouseEnter}
      onMouseLeave={handleMouseLeave}
    >
      <div className="door-img-container">
        {/* 只显示门图片，不播放动画视频 */}
        <img
          src={hovered ? doorOpenImg : doorClosedImg}
          alt={t('common.door') || 'door'}
          className="door-img-png"
        />
      </div>
      <div className="door-label-below">{name}</div>
    </div>
  );
};

export default React.memo(Door); 