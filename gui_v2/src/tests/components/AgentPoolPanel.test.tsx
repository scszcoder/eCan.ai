import { render, screen, waitFor } from '@testing-library/react';
import '@testing-library/jest-dom';

jest.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string, o?: any) => (o && o.stores ? `${key}:${o.stores}` : o && o.n != null ? `${key}:${o.n}` : key),
    i18n: { language: 'zh-CN' },
  }),
}));

const executeRequest = jest.fn();
jest.mock('@/services/ipc_api', () => ({ get_ipc_api: () => ({ executeRequest }) }));

import AgentPoolPanel from '@/pages/Agents/components/AgentPoolPanel';

const POOL = {
  settings: { min: 2, max: 3, idle_minutes: 10 },
  scaling: true,
  active_count: 2,
  wait_p50_s: 0.4,
  wait_p90_s: 2.1,
  turns_last_hour: 12,
  expected_turns_this_hour: null,
  members: [
    { id: 'q1', name: '客服小晴', active: true, running: true, load: 2, last_turn: 1 },
    { id: 'q2', name: '客服小欣', active: true, running: true, load: 0, last_turn: 1 },
    { id: 'q3', name: '客服小雪', active: false, running: true, load: 0, last_turn: null },
  ],
};

beforeEach(() => executeRequest.mockReset());

it('shows the pool of a front-desk agent', async () => {
  executeRequest.mockResolvedValue({ success: true, data: { pool: POOL } });
  render(<AgentPoolPanel agentId="fd1" />);
  expect(await screen.findByTestId('agent-pool-panel')).toBeInTheDocument();
  expect(executeRequest).toHaveBeenCalledWith('get_agent_pool', { agent_id: 'fd1' });
  expect(screen.getByTestId('pool-member-q1')).toHaveTextContent('客服小晴 · 2');
  expect(screen.getByTestId('pool-member-q3')).toHaveStyle({ opacity: '0.6' });   // parked
});

it('shows nothing for an agent without a pool', async () => {
  executeRequest.mockResolvedValue({ success: true, data: { pool: null } });
  render(<AgentPoolPanel agentId="qa1" />);
  await waitFor(() => expect(executeRequest).toHaveBeenCalled());
  expect(screen.queryByTestId('agent-pool-panel')).not.toBeInTheDocument();
});


it('says which other stores share the pool', async () => {
  executeRequest.mockResolvedValue({ success: true, data: { pool: { ...POOL, shared_desks: [
    { id: 'fdB', name: '前台小王', store_id: 'douyin-店B', store_name: '店B' },
    { id: 'fdC', name: '前台小李', store_id: 'douyin-店C' },
  ] } } });
  render(<AgentPoolPanel agentId="fdA" />);
  expect(await screen.findByTestId('agent-pool-shared'))
    .toHaveTextContent('pages.agents.pool.sharedWith:店B（前台小王）、douyin-店C（前台小李）');
});

it('an unshared pool says nothing about sharing; a pinned one says it is fixed', async () => {
  executeRequest.mockResolvedValue({ success: true, data: { pool: { ...POOL, pinned: 3, shared_desks: [] } } });
  render(<AgentPoolPanel agentId="fd1" />);
  expect(await screen.findByTestId('agent-pool-panel')).toHaveTextContent('pages.agents.pool.summaryPinned:3');
  expect(screen.queryByTestId('agent-pool-shared')).not.toBeInTheDocument();
});
