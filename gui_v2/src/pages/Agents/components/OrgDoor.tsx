import React, { useState, useCallback } from 'react';
import { useTranslation } from 'react-i18next';
import doorClosedImg from '@/assets/icons1_door_256.png';
import doorOpenImg from '@/assets/icons3_door_256.png';
import './OrgDoor.css';

interface OrgDoorProps {
  name: string;
}

const OrgDoor: React.FC<OrgDoorProps> = ({ name }) => {
  const [hovered, setHovered] = useState(false);
  const { t } = useTranslation();

  const handleMouseEnter = useCallback(() => {
    setHovered(true);
  }, []);

  const handleMouseLeave = useCallback(() => {
    setHovered(false);
  }, []);

  return (
    <div
      className={`org-door custom-door${hovered ? ' opening' : ''}`}
      style={{ position: 'static', zIndex: 2 }}
      onMouseEnter={handleMouseEnter}
      onMouseLeave={handleMouseLeave}
    >
      <div className="org-door-img-container">
        <img
          src={hovered ? doorOpenImg : doorClosedImg}
          alt={t('common.door') || 'door'}
          className="org-door-img"
        />
      </div>
      <div className="org-door-label">{name}</div>
    </div>
  );
};

export default React.memo(OrgDoor);
