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

  // 解析名称和计数
  const parseNameAndCount = useCallback((displayName: string) => {
    // 匹配形如 "Name (count)" 的格式
    const match = displayName.match(/^(.+?)\s*\((\d+)\)$/);
    if (match) {
      return {
        name: match[1].trim(),
        count: match[2]
      };
    }
    return {
      name: displayName,
      count: null
    };
  }, []);

  const { name: doorName, count } = parseNameAndCount(name);

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
      <div className="org-door-label">
        <div className="org-door-label-name">{doorName}</div>
        {count && (
          <div className="org-door-label-count">({count})</div>
        )}
      </div>
    </div>
  );
};

export default React.memo(OrgDoor);
