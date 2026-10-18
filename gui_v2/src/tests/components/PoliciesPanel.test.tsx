import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import '@testing-library/jest-dom';
import { App } from 'antd';
import { policyChanges } from '@/pages/Knowledge/ProductKnowledge/policyDoc';

jest.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string, o?: any) => (o && o.defaultValue) || key }),
}));

const ksApi = {
  getPolicies: jest.fn(),
  savePolicy: jest.fn().mockResolvedValue({}),
  deletePolicy: jest.fn().mockResolvedValue({}),
};
jest.mock('@/services/ipc/ksApi', () => ({ ksApi }));

import PoliciesPanel from '@/pages/Knowledge/ProductKnowledge/PoliciesPanel';

const topics = [
  { value: 'returns', label: '退换货' },
  { value: 'shipping', label: '发货与物流' },
  { value: 'invoice', label: '发票' },
];

describe('policy changes', () => {
  it('saves changed sections and clears emptied ones', () => {
    const changes = policyChanges(
      { returns: '新规则', shipping: '', invoice: '可开票' },
      { returns: { id: 'p1', text: '旧规则' }, shipping: { id: 'p2', text: '48小时' }, invoice: { id: 'p3', text: '可开票' } },
    );
    expect(changes.save).toEqual([{ topic: 'returns', text: '新规则' }]);
    expect(changes.remove).toEqual([{ topic: 'shipping', id: 'p2' }]);
  });
});

describe('PoliciesPanel', () => {
  beforeEach(() => {
    ksApi.savePolicy.mockClear();
    ksApi.deletePolicy.mockClear();
    ksApi.getPolicies.mockResolvedValue({
      topics, stores: [],
      defaults: { shipping: { id: 'p2', topic: 'shipping', text: '48小时发货' } },
      overrides: {},
    });
  });

  it('one box per section; one Save writes every changed section', async () => {
    render(<App><PoliciesPanel onChanged={() => {}} /></App>);
    const returns = await screen.findByTestId('policy-returns') as HTMLTextAreaElement;
    const shipping = screen.getByTestId('policy-shipping') as HTMLTextAreaElement;
    expect(shipping.value).toBe('48小时发货');
    // the example is a placeholder, never part of the text that is saved
    expect(returns.value).toBe('');
    expect(returns.placeholder).not.toBe('');
    expect(screen.getByTestId('policy-save')).toBeDisabled();

    fireEvent.change(returns, { target: { value: '七天无理由退换' } });
    fireEvent.change(shipping, { target: { value: '' } });
    fireEvent.click(screen.getByTestId('policy-save'));
    await waitFor(() => expect(ksApi.savePolicy).toHaveBeenCalledWith({ topic: 'returns', text: '七天无理由退换', store_id: null }));
    expect(ksApi.savePolicy).toHaveBeenCalledTimes(1);
    expect(ksApi.deletePolicy).toHaveBeenCalledWith('p2');
  });

  it('the section list jumps to that section', async () => {
    render(<App><PoliciesPanel onChanged={() => {}} /></App>);
    const invoice = await screen.findByTestId('policy-invoice');
    const scroll = jest.fn();
    Element.prototype.scrollIntoView = scroll;   // jsdom has none
    fireEvent.click(screen.getByTestId('policy-jump-invoice'));
    expect(scroll).toHaveBeenCalled();
    expect(document.activeElement).toBe(invoice);
  });
});
