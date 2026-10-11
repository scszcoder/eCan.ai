import React from 'react';
import { Tag, Tooltip } from 'antd';
import { ClockCircleOutlined } from '@ant-design/icons';
import { useTranslation } from 'react-i18next';
import { useTaskRunState } from '../hooks/useTaskRunState';

/** Waiting for a resource / prerequisites, or the last missed run (from the runner). */
const RunStateTag: React.FC<{ taskId?: string }> = ({ taskId }) => {
  const { t } = useTranslation();
  const st = useTaskRunState(taskId);
  if (!st) return null;
  const k = (key: string, def: string, o?: any): string =>
    String(t(`pages.tasks.runRules.${key}`, { defaultValue: def, ...(o || {}) }));
  if (st.waiting_resource || st.waiting_after) {
    const tip = st.waiting_resource
      ? k('waitingResource', 'Waiting for {{res}} (behind {{who}})', {
        res: st.waiting_resource.resources.join(', '), who: st.waiting_resource.behind.join(', ') || '…' })
      : k('waitingAfter', 'Waiting for {{who}} to finish', { who: (st.waiting_after || []).join(', ') });
    return (
      <Tooltip title={tip}>
        <Tag color="gold" icon={<ClockCircleOutlined />} style={{ margin: 0 }} data-testid="task-run-waiting">
          {k('waiting', 'Waiting')}
        </Tag>
      </Tooltip>
    );
  }
  if (st.last_missed) {
    return (
      <Tooltip title={k('missedTip', 'Missed the {{due}} run: {{why}}', { due: st.last_missed.due, why: st.last_missed.why })}>
        <Tag color="red" style={{ margin: 0 }} data-testid="task-run-missed">
          {k('missed', 'Missed {{due}}', { due: st.last_missed.due })}
        </Tag>
      </Tooltip>
    );
  }
  return null;
};

export default RunStateTag;
