import { render, screen, fireEvent, waitFor, act } from '@testing-library/react';
import '@testing-library/jest-dom';
import { App } from 'antd';

jest.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));

const executeRequest = jest.fn();
jest.mock('../../services/ipc_api', () => ({ get_ipc_api: () => ({ executeRequest }) }));
jest.mock('@/services/ipc_api', () => ({ get_ipc_api: () => ({ executeRequest }) }));

import SubscriptionUpdates from '@/components/Layout/SubscriptionUpdates';
import { useSubscriptionUpdateStore } from '@/stores/subscriptionUpdateStore';

const item = (id: string, extra = {}) => ({ skill_id: id, name: `skill ${id}`, author: 'a', skill_newer: true, prompts: ['pr-1'], ...extra });

beforeEach(() => {
  executeRequest.mockReset();
  useSubscriptionUpdateStore.setState({ items: [], applied: [], checkedAt: 0 });
});

const renderIt = () => render(<App><SubscriptionUpdates /></App>);

it('is hidden with nothing to update, and shows a badge once updates arrive', async () => {
  executeRequest.mockResolvedValue({ success: true, data: { items: [] } });
  renderIt();
  await waitFor(() => expect(executeRequest).toHaveBeenCalledWith('subscription_updates.list', {}));
  expect(screen.queryByTestId('sub-updates-icon')).not.toBeInTheDocument();
  act(() => useSubscriptionUpdateStore.getState().setFromPush([item('s1'), item('s2', { busy: "task 'x': status working" })], []));
  expect(screen.getByTestId('sub-updates-icon')).toBeInTheDocument();
  expect(screen.getByText('2')).toBeInTheDocument();
});

it('Update applies one skill and refreshes the list', async () => {
  executeRequest.mockImplementation((method: string) => Promise.resolve(method === 'subscription_updates.apply'
    ? { success: true, data: { results: [{ skill_id: 's1', name: 'skill s1', ok: true }], items: [item('s2')] } }
    : { success: true, data: { items: [item('s1'), item('s2')] } }));
  renderIt();
  await waitFor(() => expect(screen.getByTestId('sub-updates-icon')).toBeInTheDocument());
  fireEvent.click(screen.getByTestId('sub-updates-icon'));
  const row = await screen.findByTestId('sub-update-s1');
  fireEvent.click(row.querySelector('button') as Element);
  await waitFor(() => expect(executeRequest).toHaveBeenCalledWith('subscription_updates.apply', { skill_ids: ['s1'] }, 300000));
  await waitFor(() => expect(useSubscriptionUpdateStore.getState().items.map((i) => i.skill_id)).toEqual(['s2']));
});
