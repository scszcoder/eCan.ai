import { render, screen, waitFor } from '@testing-library/react';
import '@testing-library/jest-dom';
import { App, Form } from 'antd';

jest.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string, o?: any) => (typeof o === 'object' && o ? `${key}${o.due ? ':' + o.due : ''}` : key) }),
}));

const executeRequest = jest.fn();
jest.mock('@/services/ipc_api', () => ({ get_ipc_api: () => ({ executeRequest }) }));

import { applyRunRules, findAfterCycle, readRunRules } from '@/pages/Tasks/runRules';
import RunRulesFields from '@/pages/Tasks/components/RunRulesFields';
import RunStateTag from '@/pages/Tasks/components/RunStateTag';

describe('run rules <-> task metadata', () => {
  it('reads defaults and round-trips set values', () => {
    expect(readRunRules({})).toEqual({
      run_class: 'normal', max_lateness_min: null, overlap_policy: 'skip',
      after_tasks: [], after_require_success: false, exclusive_resources: [],
    });
    const meta = { task_vars: { store_id: 's3' }, run_class: 'background', max_lateness_min: 30,
      overlap_policy: 'queue_one', after: { tasks: ['a'], require_success: true }, exclusive_resources: ['printer'] };
    expect(applyRunRules({ task_vars: { store_id: 's3' } }, readRunRules(meta))).toEqual(meta);
  });

  it('drops defaults and cleared values instead of storing them', () => {
    const old = { run_class: 'background', after: { tasks: ['a'] }, exclusive_resources: ['x'], keep: 1 };
    expect(applyRunRules(old, { run_class: 'normal', max_lateness_min: null, overlap_policy: 'skip',
      after_tasks: [], exclusive_resources: [' ', ''] })).toEqual({ keep: 1 });
  });

  it('finds dependency cycles by name', () => {
    const tasks = [
      { id: 'b', name: '日报', metadata: { after: { tasks: ['a'] } } },
      { id: 'c', name: '清理', metadata: JSON.stringify({}) },
    ];
    expect(findAfterCycle('a', '抓取', ['b'], tasks)).toEqual(['抓取', '日报', '抓取']);
    expect(findAfterCycle('a', '抓取', ['c'], tasks)).toBeNull();
    expect(findAfterCycle('a', '抓取', ['a'], tasks)).toEqual(['抓取', '抓取']);
  });
});

it('run rule fields list the other tasks as prerequisites', async () => {
  const Wrapper = () => {
    const [form] = Form.useForm();
    return (
      <Form form={form} initialValues={{ run_class: 'normal', after_tasks: [] }}>
        <RunRulesFields currentTaskId="a" allTasks={[{ id: 'a', name: '抓取' }, { id: 'b', name: '日报' }]} />
      </Form>
    );
  };
  render(<App><Wrapper /></App>);
  expect(screen.getByTestId('task-run-rules')).toBeInTheDocument();
  expect(screen.getByText('pages.tasks.runRules.afterTasks')).toBeInTheDocument();
});

describe('task card run-state tag', () => {
  beforeEach(() => executeRequest.mockReset());

  it('shows waiting while a run waits for its browser', async () => {
    executeRequest.mockResolvedValue({ success: true, data: { states: {
      t1: { waiting_resource: { resources: ['browser:store3'], behind: ['抓取'], since: 0, class: 'scheduled' } },
    } } });
    render(<App><RunStateTag taskId="t1" /></App>);
    expect(await screen.findByTestId('task-run-waiting')).toBeInTheDocument();
    expect(executeRequest).toHaveBeenCalledWith('get_task_run_states', {});
  });

  it('shows a missed run', async () => {
    executeRequest.mockResolvedValue({ success: true, data: { states: {
      t2: { last_missed: { at: 'x', due: '2026-10-10 10:30', why: '25 min late' } },
    } } });
    render(<App><RunStateTag taskId="t2" /></App>);
    await waitFor(() => expect(screen.getByTestId('task-run-missed')).toHaveTextContent('2026-10-10 10:30'));
  });
});
