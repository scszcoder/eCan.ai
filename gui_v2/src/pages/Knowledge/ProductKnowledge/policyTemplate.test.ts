import { readFileSync } from 'fs';
import { join } from 'path';
import { POLICY_TEMPLATE_ZH } from './policyTemplate';

describe('POLICY_TEMPLATE_ZH', () => {
  it('fills only real 店铺规则 sections, each with text', () => {
    const zh = JSON.parse(readFileSync(join(process.cwd(), 'src/i18n/locales/zh-CN.json'), 'utf-8'));
    const topics = Object.keys(zh.pages.knowledge.ks.policies.hints);
    for (const [topic, text] of Object.entries(POLICY_TEMPLATE_ZH)) {
      expect(topics).toContain(topic);
      expect(text.trim().length).toBeGreaterThan(50);
    }
    expect(Object.keys(POLICY_TEMPLATE_ZH).sort()).toEqual(
      ['after_sales', 'invoice', 'payment', 'promotion', 'returns', 'shipping']);
  });
});
