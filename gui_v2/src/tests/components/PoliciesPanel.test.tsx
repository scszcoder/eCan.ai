import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import '@testing-library/jest-dom';
import { App } from 'antd';
import { buildPolicyDoc, parsePolicyDoc, policyChanges } from '@/pages/Knowledge/ProductKnowledge/policyDoc';

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

describe('policy document', () => {
  it('round-trips sections; hints are not saved', () => {
    const doc = buildPolicyDoc(topics, (t) => (t === 'returns' ? '七天无理由' : ''), (t) => `hint ${t}`);
    expect(doc).toContain('## 退换货\n<!-- hint returns -->\n七天无理由');
    const parsed = parsePolicyDoc(doc, topics);
    expect(parsed.texts).toEqual({ returns: '七天无理由', shipping: '', invoice: '' });
    expect(parsed.unknown).toEqual([]);
  });

  it('keeps multi-line text, matches headings by label or key, reports unknown headings', () => {
    const parsed = parsePolicyDoc('## 退换货\n第一行\n\n第二行\n## shipping\n48小时发货\n## 售后\n保修一年', topics);
    expect(parsed.texts.returns).toBe('第一行\n\n第二行');
    expect(parsed.texts.shipping).toBe('48小时发货');
    expect(parsed.unknown).toEqual(['售后']);
  });

  it('saves changed sections and clears emptied ones', () => {
    const changes = policyChanges(
      { texts: { returns: '新规则', shipping: '', invoice: '可开票' }, unknown: [] },
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

  it('shows one document and saves every filled section with one click', async () => {
    render(<App><PoliciesPanel onChanged={() => {}} /></App>);
    const box = await screen.findByTestId('policy-doc') as HTMLTextAreaElement;
    expect(box.value).toContain('## 退换货');
    expect(box.value).toContain('## 发货与物流');
    expect(box.value).toContain('48小时发货');
    const edited = box.value
      .replace('## 退换货\n', '## 退换货\n七天无理由退换\n')
      .replace('48小时发货', '');
    fireEvent.change(box, { target: { value: edited } });
    fireEvent.click(screen.getByTestId('policy-save'));
    await waitFor(() => expect(ksApi.savePolicy).toHaveBeenCalledWith({ topic: 'returns', text: '七天无理由退换', store_id: null }));
    expect(ksApi.savePolicy).toHaveBeenCalledTimes(1);
    expect(ksApi.deletePolicy).toHaveBeenCalledWith('p2');
  });
});
