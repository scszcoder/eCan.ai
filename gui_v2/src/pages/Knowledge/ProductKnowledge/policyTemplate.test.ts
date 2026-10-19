import zh from '../../../i18n/locales/zh-CN.json';
import { POLICY_TEMPLATE_ZH } from './policyTemplate';

describe('POLICY_TEMPLATE_ZH', () => {
  it('fills only real 店铺规则 sections, each with text', () => {
    const topics = Object.keys((zh as any).pages.knowledge.ks.policies.hints);
    for (const [topic, text] of Object.entries(POLICY_TEMPLATE_ZH)) {
      expect(topics).toContain(topic);
      expect(text.trim().length).toBeGreaterThan(50);
    }
    expect(Object.keys(POLICY_TEMPLATE_ZH).sort()).toEqual(
      ['after_sales', 'invoice', 'payment', 'promotion', 'returns', 'shipping']);
  });
});
