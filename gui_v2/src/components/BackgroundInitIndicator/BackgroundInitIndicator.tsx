import React, { useState, useEffect } from 'react';
import { Badge, Tooltip, Button } from 'antd';
import { LoadingOutlined, CheckCircleOutlined, SettingOutlined } from '@ant-design/icons';
import { useTranslation } from 'react-i18next';
import { useInitializationProgress } from '../../hooks/useInitializationProgress';
import LoadingProgress from '../LoadingProgress/LoadingProgress';
import './BackgroundInitIndicator.css';

interface BackgroundInitIndicatorProps {
  className?: string;
}

const BackgroundInitIndicator: React.FC<BackgroundInitIndicatorProps> = ({ className }) => {
  const { t } = useTranslation();
  const { progress, isLoading } = useInitializationProgress(true);
  const [showDetails, setShowDetails] = useState(false);

  // Auto-hide after initialization is complete
  useEffect(() => {
    if (progress?.fully_ready) {
      const timer = setTimeout(() => {
        setShowDetails(false);
      }, 3000); // Hide after 3 seconds when fully ready
      return () => clearTimeout(timer);
    }
  }, [progress?.fully_ready]);

  // Don't show if no progress data or if UI is not ready yet
  if (!progress || !progress.ui_ready) {
    return null;
  }

  // Don't show if fully ready and details are not shown
  if (progress.fully_ready && !showDetails) {
    return null;
  }

  const getStatusIcon = () => {
    if (progress.fully_ready) {
      return <CheckCircleOutlined className="status-icon success" />;
    }
    return <LoadingOutlined className="status-icon loading" spin />;
  };

  const getStatusText = () => {
    if (progress.fully_ready) {
      return t('init.allReady');
    }
    if (progress.async_init_complete) {
      return t('init.finalizing');
    }
    if (progress.critical_services_ready) {
      return t('init.loadingServices');
    }
    return t('init.initializing');
  };

  const getProgressPercent = () => {
    if (progress.fully_ready) return 100;
    if (progress.async_init_complete) return 90;
    if (progress.critical_services_ready) return 70;
    if (progress.ui_ready) return 50;
    return 20;
  };

  return (
    <>
      <div className={`background-init-indicator ${className || ''}`}>
        <Tooltip 
          title={getStatusText()}
          placement="bottomRight"
        >
          <Badge 
            count={progress.fully_ready ? 0 : ''}
            dot={!progress.fully_ready}
            status={progress.fully_ready ? 'success' : 'processing'}
          >
            <Button
              type="text"
              size="small"
              icon={getStatusIcon()}
              onClick={() => setShowDetails(!showDetails)}
              className="indicator-button"
            >
              {getStatusText()}
            </Button>
          </Badge>
        </Tooltip>
      </div>

      {/* Show detailed progress when clicked */}
      <LoadingProgress
        visible={showDetails}
        progress={progress}
        mode="compact"
        title={getStatusText()}
        onComplete={() => setShowDetails(false)}
      />
    </>
  );
};

export default BackgroundInitIndicator;
