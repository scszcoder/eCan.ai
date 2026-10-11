import React, { useEffect, useState } from 'react';
import { Empty, List, Typography } from 'antd';
import { useTranslation } from 'react-i18next';
import { ksApi, KSJob } from '@/services/ipc/ksApi';
import JobProgress from './JobProgress';

const { Text } = Typography;

/** Recent knowledge-service jobs (imports, re-index), polled every 2 s. */
const JobsList: React.FC = () => {
  const { t } = useTranslation();
  const [jobs, setJobs] = useState<KSJob[]>([]);
  useEffect(() => {
    let alive = true;
    const load = () => ksApi.listJobs(30).then(j => alive && setJobs(j)).catch(() => undefined);
    load();
    const timer = setInterval(load, 2000);
    return () => { alive = false; clearInterval(timer); };
  }, []);
  return (
    <div style={{ padding: '12px 24px' }}>
      {!jobs.length ? <Empty description={t('pages.knowledge.ks.jobs.empty')} /> : (
        <List
          dataSource={jobs}
          renderItem={job => (
            <List.Item>
              <div style={{ width: '100%' }}>
                <JobProgress job={job} />
                <Text type="secondary" style={{ fontSize: 11 }}>{new Date(job.created_at).toLocaleString()}</Text>
              </div>
            </List.Item>
          )}
        />
      )}
    </div>
  );
};

export default JobsList;
