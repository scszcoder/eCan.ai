import React, { useState, useEffect, useMemo, memo } from 'react';
import { Progress, Typography, Card, Spin } from 'antd';
import { CheckCircleOutlined, LoadingOutlined } from '@ant-design/icons';
import { useTranslation } from 'react-i18next';
import { useInitializationProgress } from '../../hooks/useInitializationProgress';
import './LoadingProgress.css';

const { Text } = Typography;

interface LoadingStep {
  key: string;
  label: string;
  completed: boolean;
  loading: boolean;
}

interface InitializationProgress {
  ui_ready: boolean;
  critical_services_ready: boolean;
  async_init_complete: boolean;
  fully_ready: boolean;
  sync_init_complete: boolean;
  message?: string;
}

interface LoadingProgressProps {
  visible: boolean;
  progress?: InitializationProgress | null;
  onComplete?: () => void;
  mode?: 'fullscreen' | 'compact'; // Add mode prop for different display styles
  title?: string; // Custom title
}

const LoadingProgress: React.FC<LoadingProgressProps> = ({
  visible,
  progress: externalProgress,
  onComplete,
  mode = 'fullscreen',
  title
}) => {
  const { t } = useTranslation();

  // Use external progress if provided, otherwise use internal hook
  // Only use internal hook if no external progress is provided at all (not even null)
  const shouldUseInternalHook = visible && externalProgress === undefined;
  const { progress: internalProgress, isLoading, error } = useInitializationProgress(shouldUseInternalHook);
  const initProgress = externalProgress !== undefined ? externalProgress : internalProgress;

  // Memoize initial steps to prevent recreating array on every render
  const initialSteps = useMemo<LoadingStep[]>(() => [
    { key: 'auth', label: t('loading.authentication'), completed: false, loading: false },
    { key: 'config', label: t('loading.configuration'), completed: false, loading: false },
    { key: 'database', label: t('loading.database'), completed: false, loading: false },
    { key: 'services', label: t('loading.services'), completed: false, loading: false },
    { key: 'network', label: t('loading.network'), completed: false, loading: false },
  ], [t]);

  const [steps, setSteps] = useState<LoadingStep[]>(initialSteps);
  const [currentStep, setCurrentStep] = useState(0);
  const [progress, setProgress] = useState(0); // Start at 0%

  // Update steps based on real initialization progress
  // Optimized with dependency array to reduce unnecessary re-renders
  useEffect(() => {
    if (!visible) return;

    let newProgress = 0;
    let newCurrentStep = 0;

    const newSteps = [...initialSteps];

    // If we have initialization progress data
    if (initProgress) {
      // Authentication step - completed when we have progress data
      newSteps[0] = { ...newSteps[0], completed: true, loading: false };
      newProgress = Math.max(newProgress, 20);
      newCurrentStep = Math.max(newCurrentStep, 0);

      // Configuration step (ui_ready)
      if (initProgress.ui_ready) {
        newSteps[1] = { ...newSteps[1], completed: true, loading: false };
        newProgress = Math.max(newProgress, 40);
        newCurrentStep = Math.max(newCurrentStep, 1);

        // When ui_ready, can navigate to main page, background init continues
        setTimeout(() => {
          onComplete?.();
        }, 200); // Reduced delay for better responsiveness
      } else {
        newSteps[1] = { ...newSteps[1], completed: false, loading: true };
      }

    // Database step (critical_services_ready)
    if (initProgress.critical_services_ready) {
      newSteps[2] = { ...newSteps[2], completed: true, loading: false };
      newProgress = Math.max(newProgress, 60);
      newCurrentStep = Math.max(newCurrentStep, 2);
    } else if (initProgress.ui_ready) {
      newSteps[2] = { ...newSteps[2], completed: false, loading: true };
    }

    // Services step (async_init_complete)
    if (initProgress.async_init_complete) {
      newSteps[3] = { ...newSteps[3], completed: true, loading: false };
      newProgress = Math.max(newProgress, 80);
      newCurrentStep = Math.max(newCurrentStep, 3);
    } else if (initProgress.critical_services_ready) {
      newSteps[3] = { ...newSteps[3], completed: false, loading: true };
    }

    // Network step (fully_ready)
    if (initProgress.fully_ready) {
      newSteps[4] = { ...newSteps[4], completed: true, loading: false };
      newProgress = 100;
      newCurrentStep = 4;
    } else if (initProgress.async_init_complete) {
      newSteps[4] = { ...newSteps[4], completed: false, loading: true };
    }
    } else {
      // No progress data yet - show authentication as loading
      newSteps[0] = { ...newSteps[0], completed: false, loading: true };
      newProgress = 10;
      newCurrentStep = 0;
    }

    setSteps(newSteps);
    setProgress(newProgress);
    setCurrentStep(newCurrentStep);
  }, [visible, initProgress, onComplete, initialSteps]);

  if (!visible) return null;

  // Compact mode for showing in main page
  if (mode === 'compact') {
    return (
      <div className="loading-progress-compact">
        <Card size="small" className="loading-progress-compact-card">
          <div className="loading-progress-compact-content">
            <div className="loading-compact-header">
              <Spin
                indicator={<LoadingOutlined style={{ fontSize: 16 }} spin />}
                spinning={progress < 100}
                size="small"
              />
              <Text className="loading-compact-title">
                {title || (progress < 100 ? t('loading.backgroundInit') : t('loading.complete'))}
              </Text>
            </div>
            <Progress
              percent={progress}
              size="small"
              strokeColor="#1890ff"
              showInfo={false}
              className="loading-compact-progress"
            />
          </div>
        </Card>
      </div>
    );
  }

  // Fullscreen mode for login page
  return (
    <div className="loading-progress-overlay">
      <Card className="loading-progress-card">
        <div className="loading-progress-content">
          <div className="loading-header">
            <Spin
              indicator={<LoadingOutlined style={{ fontSize: 24 }} spin />}
              spinning={progress < 100}
            />
            <Text className="loading-title">
              {title || (progress < 100 ? t('loading.initializing') : t('loading.complete'))}
            </Text>
          </div>
          
          <Progress 
            percent={progress} 
            strokeColor="#1890ff"
            showInfo={false}
            className="loading-progress-bar"
          />
          
          <div className="loading-steps">
            {steps.map((step) => (
              <div key={step.key} className={`loading-step ${step.completed ? 'completed' : ''} ${step.loading ? 'loading' : ''}`}>
                <div className="step-icon">
                  {step.completed ? (
                    <CheckCircleOutlined className="step-check" />
                  ) : step.loading ? (
                    <Spin size="small" />
                  ) : (
                    <div className="step-dot" />
                  )}
                </div>
                <Text className="step-label">{step.label}</Text>
              </div>
            ))}
          </div>
          
          <Text className="loading-description">
            {t('loading.backgroundInit')}
          </Text>
        </div>
      </Card>
    </div>
  );
};

// Wrap component with memo to prevent unnecessary re-renders
export default memo(LoadingProgress);
