import React, { memo } from 'react';
import { useTranslation } from 'react-i18next';
import './LoadingProgress.css';

interface LoadingProgressProps {
  visible: boolean;
  message?: string;
  progress?: number; // 0-100
}

const LoadingProgress: React.FC<LoadingProgressProps> = ({
  visible,
  message,
  progress
}) => {
  const { t } = useTranslation();
  const displayMessage = message || t('system.initializing', '加载中...');

  if (!visible) return null;

  return (
    <div className="loading-overlay">
      <div className="loading-content">
        <div className="loading-spinner">
          <div className="spinner-ring" />
          <div className="spinner-ring" />
          <div className="spinner-ring" />
        </div>
        <p className="loading-message">{displayMessage}</p>
        {progress !== undefined && (
          <div className="loading-bar-container">
            <div className="loading-bar" style={{ width: `${progress}%` }} />
          </div>
        )}
      </div>
    </div>
  );
};

export default memo(LoadingProgress);
