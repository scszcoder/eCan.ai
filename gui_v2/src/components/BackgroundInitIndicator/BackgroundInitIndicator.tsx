import React from 'react';
import { Tooltip } from 'antd';
import { LoadingOutlined } from '@ant-design/icons';
import { useSystemStatus } from '../../hooks/useInitializationProgress';
import { isWebPlatform } from '../../config/platform';
import './BackgroundInitIndicator.css';

interface BackgroundInitIndicatorProps {
  className?: string;
}

const BackgroundInitIndicator: React.FC<BackgroundInitIndicatorProps> = ({ className }) => {
  const isWeb = isWebPlatform();
  const { message, isReady } = useSystemStatus(!isWeb);

  // Initialization progress is provided by the desktop IPC backend only.
  if (isWeb || isReady) {
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
