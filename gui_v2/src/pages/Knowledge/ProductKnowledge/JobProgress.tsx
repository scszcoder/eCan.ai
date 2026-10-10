import React from 'react';
import { Alert, Button, Progress, Space, Typography } from 'antd';
import { CheckCircleOutlined, CloseCircleOutlined, LoadingOutlined, StopOutlined } from '@ant-design/icons';
import { useTranslation } from 'react-i18next';
import { ksApi, KSJob } from '@/services/ipc/ksApi';
import { isJobDone } from './useJob';

const { Text } = Typography;

/** Progress card for one long-running job: stage, count, bar, errors, cancel. */
const JobProgress: React.FC<{ job: KSJob; compact?: boolean }> = ({ job, compact }) => {
  const { t } = useTranslation();
  const pct = Math.round((job.progress || 0) * 100);
  const done = isJobDone(job);
  const status = job.status === 'failed' ? 'exception' : job.status === 'succeeded' ? 'success' : done ? 'normal' : 'active';
  const icon = job.status === 'succeeded' ? <CheckCircleOutlined style={{ color: '#52c41a' }} />
    : job.status === 'failed' ? <CloseCircleOutlined style={{ color: '#ff4d4f' }} />
    : job.status === 'cancelled' ? <StopOutlined />
    : <LoadingOutlined />;

  return (
    <div style={{ width: '100%' }}>
      <Space style={{ width: '100%', justifyContent: 'space-between' }}>
        <Space>
          {icon}
          <Text strong>{job.title}</Text>
          <Text type="secondary">
            {t(`pages.knowledge.ks.jobs.stage.${job.stage}`, { defaultValue: job.stage })}
            {job.total > 0 && ` · ${job.done}/${job.total}`}
          </Text>
        </Space>
        {!done && (
          <Button size="small" icon={<StopOutlined />} onClick={() => ksApi.cancelJob(job.id)}>
            {t('pages.knowledge.ks.jobs.cancel')}
          </Button>
        )}
      </Space>
      <Progress percent={done && job.status === 'succeeded' ? 100 : pct} status={status as any} size="small" />
      {!compact && job.message && <Text type="secondary" style={{ fontSize: 12 }}>{job.message}</Text>}
      {!compact && job.errors?.length > 0 && (
        <Alert
          style={{ marginTop: 8 }}
          type={job.status === 'failed' ? 'error' : 'warning'}
          showIcon
          message={t('pages.knowledge.ks.jobs.errors', { count: job.errors.length })}
          description={
            <div style={{ maxHeight: 160, overflow: 'auto', fontSize: 12 }}>
              {job.errors.slice(0, 50).map((e, i) => <div key={i}>{e}</div>)}
            </div>
          }
        />
      )}
    </div>
  );
};

export default JobProgress;
