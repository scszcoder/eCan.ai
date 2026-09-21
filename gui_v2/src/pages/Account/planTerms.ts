/**
 * Plan terms — the single editable source for what each plan actually costs.
 *
 * Commercial wording lives here rather than in the i18n JSON so that changing a
 * price or an inclusion means editing ONE file, with both languages side by side
 * and no chance of the zh and en copies drifting apart. Page chrome (titles,
 * buttons) still goes through i18n as usual.
 *
 * Anything still awaiting a commercial decision is marked `confirmed: false`;
 * the page renders those with a visible 待确认 badge so an unconfirmed term
 * cannot quietly reach a paying customer.
 */

export interface Bilingual {
  zh: string;
  en: string;
}

export interface TermLine {
  label: Bilingual;
  value: Bilingual;
  /** false → rendered with a "to be confirmed" badge and muted. */
  confirmed?: boolean;
}

export interface PlanTerms {
  key: 'subscription' | 'additional';
  name: Bilingual;
  tagline: Bilingual;
  /** Headline price, already formatted for the region. */
  price: { cn: Bilingual; intl: Bilingual };
  bestFor: Bilingual;
  includes: TermLine[];
  notes: Bilingual[];
}

export const BILLED_UNIT_PRICE_CNY_PER_REPLY = 0.05;

export const PLAN_TERMS: PlanTerms[] = [
  {
    key: 'subscription',
    name: { zh: '订阅套餐', en: 'Subscription Plan' },
    tagline: {
      zh: '每月固定费用，包含一定额度的用量，超出部分按量计费。',
      en: 'A fixed monthly fee that includes an allowance; usage beyond it is billed per unit.',
    },
    price: {
      cn: { zh: '¥68 / 月', en: '¥68 / month' },
      intl: { zh: '见结算页', en: 'See checkout' },
    },
    bestFor: {
      zh: '每月用量稳定、希望账单可预测的店铺。',
      en: 'Shops with steady monthly volume that want a predictable bill.',
    },
    includes: [
      {
        label: { zh: '月费', en: 'Monthly fee' },
        value: { zh: '¥68，按月计费', en: '¥68, billed monthly' },
        confirmed: true,
      },
      {
        label: { zh: '包含额度', en: 'Included allowance' },
        value: {
          zh: '待确认 — 每月包含的客服回复条数尚未最终确定',
          en: 'To be confirmed — the number of included replies per month is not final',
        },
        confirmed: false,
      },
      {
        label: { zh: '超出部分', en: 'Beyond the allowance' },
        value: {
          zh: `每条客服回复 ¥${BILLED_UNIT_PRICE_CNY_PER_REPLY.toFixed(2)}，从账户余额扣除`,
          en: `¥${BILLED_UNIT_PRICE_CNY_PER_REPLY.toFixed(2)} per customer-service reply, deducted from your balance`,
        },
        confirmed: true,
      },
      {
        label: { zh: '支付方式', en: 'Payment methods' },
        value: { zh: '支付宝 / 微信支付', en: 'Alipay / WeChat Pay' },
        confirmed: true,
      },
    ],
    notes: [
      {
        zh: '订阅与余额是两回事：月费开通服务并带来包含额度，超出额度的用量从余额扣除。',
        en: 'The subscription and your balance are separate: the monthly fee enables the service and provides the allowance, while usage beyond it is deducted from your balance.',
      },
    ],
  },
  {
    key: 'additional',
    name: { zh: '附加计划（按量充值）', en: 'Additional Plan (pay as you go)' },
    tagline: {
      zh: '没有月费，先充值再按实际完成的业务量扣费。',
      en: 'No monthly fee — top up first, then pay for the business results actually delivered.',
    },
    price: {
      cn: { zh: '最低充值 ¥0.50', en: 'From ¥0.50' },
      intl: { zh: '最低充值 $0.50', en: 'From $0.50' },
    },
    bestFor: {
      zh: '用量波动大、或想先小额试用的店铺。',
      en: 'Shops with uneven volume, or anyone who wants to start small.',
    },
    includes: [
      {
        label: { zh: '月费', en: 'Monthly fee' },
        value: { zh: '无', en: 'None' },
        confirmed: true,
      },
      {
        label: { zh: '最低充值', en: 'Minimum top-up' },
        value: { zh: '¥0.50', en: '¥0.50' },
        confirmed: true,
      },
      {
        label: { zh: '计费方式', en: 'How you are charged' },
        value: {
          zh: `每条客服回复 ¥${BILLED_UNIT_PRICE_CNY_PER_REPLY.toFixed(2)}，从余额实时扣除`,
          en: `¥${BILLED_UNIT_PRICE_CNY_PER_REPLY.toFixed(2)} per customer-service reply, deducted from your balance as it happens`,
        },
        confirmed: true,
      },
      {
        label: { zh: '余额有效期', en: 'Balance expiry' },
        value: { zh: '待确认', en: 'To be confirmed' },
        confirmed: false,
      },
    ],
    notes: [
      {
        zh: '余额用完后服务会暂停，充值后立即恢复。',
        en: 'Service pauses when the balance runs out and resumes as soon as you top up.',
      },
    ],
  },
];

/** What counts as a billable reply — and, just as importantly, what does not. */
export const BILLING_RULES: { title: Bilingual; billed: Bilingual[]; notBilled: Bilingual[] } = {
  title: { zh: '什么算一条计费回复', en: 'What counts as one billable reply' },
  billed: [
    {
      zh: '顾客的一次提问，我们成功发出的一条回复 = 1 条',
      en: 'One customer question answered by one reply we successfully delivered = 1 unit',
    },
    {
      zh: '同一次提问即使分成两条气泡发出，仍然只算 1 条',
      en: 'Still 1 unit even if that answer is split across two message bubbles',
    },
  ],
  notBilled: [
    {
      zh: '过渡话术（「人工服务正在回复中…」）不计费',
      en: 'Stand-by lines ("we are replying shortly…") are never billed',
    },
    {
      zh: '重试、重复投递不会重复计费 — 同一次提问只计一次',
      en: 'Retries and duplicate delivery are never double-billed — one question, one charge',
    },
    {
      zh: '发送失败、顾客没有收到的回复不计费',
      en: 'Replies that failed to send or the customer never received are not billed',
    },
  ],
};

/**
 * How a skill's price is decided. This is the honest short version of the
 * three-tier trust model in docs/BILLING_METERING_SERVER_TODO.md — customers
 * copying and editing template skills need to know why their bill may switch
 * from per-result back to per-usage.
 */
export const SKILL_PRICING_NOTE: { title: Bilingual; lines: Bilingual[] } = {
  title: { zh: '自建技能怎么计费', en: 'How custom skills are priced' },
  lines: [
    {
      zh: '官方模板技能按业务量计费（如每条回复 ¥0.05），价格公开透明。',
      en: 'Official template skills are billed per business result (e.g. ¥0.05 per reply), at a published price.',
    },
    {
      zh: '复制官方模板后只改话术，计费方式不变。',
      en: 'Copy an official template and only reword the prompts — the pricing carries over unchanged.',
    },
    {
      zh: '如果改动了节点、工具或模型，该技能会先按实际用量（模型调用量）计费，审核通过后再恢复按业务量计费。',
      en: 'If you change nodes, tools or models, that skill bills by actual usage (model consumption) until it has been reviewed, then returns to per-result pricing.',
    },
    {
      zh: '自己创建的技能默认按实际用量计费，可在技能编辑器的「计费」标签页申请审核。',
      en: 'Skills you author yourself bill by actual usage by default; request a review from the Billing tab in the skill editor.',
    },
  ],
};
