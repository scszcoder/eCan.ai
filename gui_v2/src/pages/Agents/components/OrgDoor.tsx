import React, { useState, useCallback } from 'react';
import { useTranslation } from 'react-i18next';
import { TeamOutlined, FolderOpenOutlined } from '@ant-design/icons';
import doorClosedImg from '@/assets/icons1_door_256.png';
import doorOpenImg from '@/assets/icons3_door_256.png';
import './OrgDoor.css';

interface OrgDoorProps {
  name: string;
  hasChildren?: boolean;
  isActive?: boolean;
}

const OrgDoor: React.FC<OrgDoorProps> = ({ name, hasChildren = false, isActive = false }) => {
  const [hovered, setHovered] = useState(false);
  const [clicked, setClicked] = useState(false);
  const { t } = useTranslation();

  const handleMouseEnter = useCallback(() => {
    setHovered(true);
  }, []);

  const handleMouseLeave = useCallback(() => {
    setHovered(false);
  }, []);

  const handleClick = useCallback(() => {
    setClicked(true);
    setTimeout(() => setClicked(false), 300);
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
      className={`org-door custom-door${hovered ? ' opening' : ''}${clicked ? ' clicked' : ''}${isActive ? ' active' : ''}`}
      style={{ position: 'static', zIndex: 2 }}
      onMouseEnter={handleMouseEnter}
      onMouseLeave={handleMouseLeave}
      onClick={handleClick}
    >
      {/* 悬停光晕效果 */}
      {hovered && <div className="door-glow" />}
      
      {/* 状态指示器 */}
      {isActive && (
        <div className="door-status-indicator">
          <div className="status-dot" />
        </div>
      )}
      
      <div className="org-door-img-container">
        {/* 门图片 */}
        <img
          src={hovered ? doorOpenImg : doorClosedImg}
          alt={t('common.door') || 'door'}
          className="org-door-img"
        />
        
        {/* 门把手细节 */}
        <div className="door-handle" />
        
        {/* 类型图标 */}
        <div className="door-type-icon">
          {hasChildren ? (
            <FolderOpenOutlined style={{ fontSize: 20, color: 'rgba(59, 130, 246, 0.8)' }} />
          ) : (
            <TeamOutlined style={{ fontSize: 20, color: 'rgba(99, 102, 241, 0.8)' }} />
          )}
        </div>
      </div>
      
      <div className="org-door-label">
        <div className="org-door-label-name">{doorName}</div>
        {count && (
          <div className="org-door-label-count">
            <TeamOutlined style={{ fontSize: 12, marginRight: 4 }} />
            {count}
          </div>
        )}
      </div>
    </div>
  );
};

export default React.memo(OrgDoor);
