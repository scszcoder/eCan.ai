import React, { useState, useEffect } from 'react';
import { Progress, Typography, Card, Spin } from 'antd';
import { CheckCircleOutlined, LoadingOutlined } from '@ant-design/icons';
import { useTranslation } from 'react-i18next';
import './LoadingProgress.css';

const { Text } = Typography;

interface LoadingStep {
  key: string;
  label: string;
  completed: boolean;
  loading: boolean;
}

interface LoadingProgressProps {
  visible: boolean;
  onComplete?: () => void;
}

const LoadingProgress: React.FC<LoadingProgressProps> = ({ visible, onComplete }) => {
  const { t } = useTranslation();
  const [steps, setSteps] = useState<LoadingStep[]>([
    { key: 'auth', label: t('loading.authentication'), completed: true, loading: false },
    { key: 'config', label: t('loading.configuration'), completed: false, loading: true },
    { key: 'database', label: t('loading.database'), completed: false, loading: false },
    { key: 'services', label: t('loading.services'), completed: false, loading: false },
    { key: 'network', label: t('loading.network'), completed: false, loading: false },
  ]);

  const [currentStep, setCurrentStep] = useState(0);
  const [progress, setProgress] = useState(20); // Start at 20% since auth is complete

  useEffect(() => {
    if (!visible) return;

    // Simulate progressive loading steps
    const intervals: NodeJS.Timeout[] = [];

    // Configuration step
    intervals.push(setTimeout(() => {
      setSteps(prev => prev.map((step, index) => 
        index === 1 ? { ...step, completed: true, loading: false } : 
        index === 2 ? { ...step, loading: true } : step
      ));
      setCurrentStep(1);
      setProgress(40);
    }, 800));

    // Database step
    intervals.push(setTimeout(() => {
      setSteps(prev => prev.map((step, index) => 
        index === 2 ? { ...step, completed: true, loading: false } : 
        index === 3 ? { ...step, loading: true } : step
      ));
      setCurrentStep(2);
      setProgress(60);
    }, 1600));

    // Services step
    intervals.push(setTimeout(() => {
      setSteps(prev => prev.map((step, index) => 
        index === 3 ? { ...step, completed: true, loading: false } : 
        index === 4 ? { ...step, loading: true } : step
      ));
      setCurrentStep(3);
      setProgress(80);
    }, 2400));

    // Network step
    intervals.push(setTimeout(() => {
      setSteps(prev => prev.map((step, index) => 
        index === 4 ? { ...step, completed: true, loading: false } : step
      ));
      setCurrentStep(4);
      setProgress(100);
    }, 3200));

    // Complete
    intervals.push(setTimeout(() => {
      onComplete?.();
    }, 3800));

    return () => {
      intervals.forEach(clearTimeout);
    };
  }, [visible, onComplete]);

  if (!visible) return null;

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
              {progress < 100 ? t('loading.initializing') : t('loading.complete')}
            </Text>
          </div>
          
          <Progress 
            percent={progress} 
            strokeColor={{
              '0%': '#108ee9',
              '100%': '#87d068',
            }}
            showInfo={false}
            className="loading-progress-bar"
          />
          
          <div className="loading-steps">
            {steps.map((step, index) => (
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

export default LoadingProgress;
