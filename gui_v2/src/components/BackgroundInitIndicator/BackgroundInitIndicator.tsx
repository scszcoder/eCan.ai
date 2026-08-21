import React from 'react';
import { Tooltip } from 'antd';
import { LoadingOutlined } from '@ant-design/icons';
import { useSystemStatus } from '../../hooks/useInitializationProgress';
import './BackgroundInitIndicator.css';

interface BackgroundInitIndicatorProps {
  className?: string;
}

const BackgroundInitIndicator: React.FC<BackgroundInitIndicatorProps> = ({ className }) => {
  const { message, isReady } = useSystemStatus(true);

  // Don't show when ready
  if (isReady) {
    return null;
  }

  return (
    <div className={`background-init-indicator ${className || ''}`}>
      <Tooltip title={message}>
        <div className="init-badge">
          <LoadingOutlined className="init-icon" spin />
          <span className="init-text">{message}</span>
        </div>
      </Tooltip>
    </div>
  );
};

export default BackgroundInitIndicator;
