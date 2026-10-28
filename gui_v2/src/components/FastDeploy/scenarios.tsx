import React from 'react';
import {
    CustomerServiceOutlined,
    AmazonOutlined,
    TikTokOutlined,
    ShopOutlined,
    ShoppingOutlined,
    ShoppingCartOutlined,
    ClusterOutlined,
    AppstoreAddOutlined,
} from '@ant-design/icons';

export type Region = 'cn' | 'intl';

/** Which config fields a scenario exposes in the config panel. */
export interface ScenarioSchema {
    /** Show the "# of Q&A agents" control (customer-service scenarios). */
    qaAgents?: { default: number; min: number; max: number };
    /** Show the add/replace switch (replace = delete THIS STORE's existing
     *  tasks on the scenario's skills + the agents serving only them, then add). */
    replaceMode?: boolean;
    /** Show the store picker (stores come from the Stores page, URLs included).
     *  Needed wherever the store URL does NOT identify the store: every 飞鸽
     *  seller shares one workstation URL, so a URL-derived id would silently
     *  merge two stores' per-store config and metering. */
    storeId?: boolean;
    /** Several stores at once (picked from the Stores page), one shared Q&A
     *  pool: replaces the single store picker. */
    stores?: boolean;
    /** Store operations: when the after-sales task first runs and how often it
     *  processes orders and messages (the other roles start on a chat message). */
    schedule?: boolean;
    /** Export the store's products into 商品知识 nightly (operations agent). */
    fetchCatalog?: boolean;
    /** Keep the store's current promotions fresh for Q&A (operations agent,
     *  nightly and on any message; answers carry an "as of" time). */
    fetchPromos?: boolean;
    /** Offer to share the Q&A agents of this platform's other stores (on by
     *  default when there are some): the new store's front desk joins them. */
    sharePool?: boolean;
}

export interface BusinessScenario {
    key: string;
    nameEn: string;
    nameZh: string;
    region: Region;
    icon: React.ReactNode;
    schema: ScenarioSchema;
    /** The store platform this scenario deploys to (matches a store's `platform`). */
    platform: string;
}

/** The runtime config values collected for a scenario. */
export interface ScenarioConfig {
    qaAgents?: number;
    mode?: 'add' | 'replace';
    storeId?: string;
    /** Multi-store scenarios: the chosen store ids. */
    stores?: string[];
    /** Operations: after-sales first run (ISO) and repeat interval. */
    scheduleStart?: string;
    scheduleEvery?: number;
    scheduleUnit?: 'minutes' | 'hours' | 'days';
    /** Export the store's products once for review in 商品知识 → 导入. */
    fetchCatalog?: boolean;
    /** Keep the store's current promotions fresh for Q&A (refreshed every 30 min). */
    fetchPromos?: boolean;
    /** Share another store's Q&A agents: that store's front desk agent id
     *  ('' = this store gets its own; undefined = not decided yet). */
    shareWith?: string;
    /** With shareWith: Q&A agents to add to the shared pool. */
    qaExtra?: number;
    /** 售后 agents (电商售后应答) for this store: the front desk routes after-sales
     *  messages and whole cases to them. 0 = none. */
    aftersalesAgents?: number;
}

/** A platform's existing 客服 deployment (front desks sharing Q&A agents). */
export interface CsPool {
    front_desks: { agent_id: string; task_id: string; store_id: string; store_name: string }[];
    qa_task_ids: string[];
    qa_count: number;
}

const CS_SCHEMA: ScenarioSchema = { storeId: true, qaAgents: { default: 6, min: 1, max: 16 } };
const DOUYIN_CS_SCHEMA: ScenarioSchema = {
    qaAgents: { default: 8, min: 1, max: 16 },
    replaceMode: true,
    storeId: true,
    sharePool: true,
};
/** 抖店运营: the store's operations agent (运营-<store>) -- nightly product export
 *  into 商品知识 (auto-applied) and promotions refresh (also on any message). */
const DOUYIN_STORE_SYNC_SCHEMA: ScenarioSchema = { storeId: true, fetchCatalog: true, fetchPromos: true };
const PDD_CS_SCHEMA: ScenarioSchema = {
    qaAgents: { default: 4, min: 1, max: 16 },
    replaceMode: true,
    storeId: true,
    sharePool: true,
};
/** 拼多多运营: the same chores as 抖店运营 (拼多多商品导出 / 拼多多营销导出). */
const PDD_STORE_SYNC_SCHEMA: ScenarioSchema = { storeId: true, fetchCatalog: true, fetchPromos: true };
// Several stores on this machine: each gets its own login profile + front desk;
// the Q&A agents are one pool shared by all of them.
const MULTI_CS_SCHEMA: ScenarioSchema = {
    stores: true,
    qaAgents: { default: 4, min: 1, max: 24 },
    replaceMode: true,
};
// 多店抖店客服 / 多店拼多多客服: each store also gets its product export + promotions
// refresh, like the single-store desk
const DOUYIN_MULTI_CS_SCHEMA: ScenarioSchema = { ...MULTI_CS_SCHEMA, fetchCatalog: true, fetchPromos: true };
const PDD_MULTI_CS_SCHEMA: ScenarioSchema = { ...MULTI_CS_SCHEMA, fetchCatalog: true, fetchPromos: true };
const OPS_SCHEMA: ScenarioSchema = { storeId: true, schedule: true };

export const SCENARIOS: BusinessScenario[] = [
    { key: 'douyin_cs', nameEn: 'Douyin Store Customer Service', nameZh: '抖店客服', region: 'cn', icon: <CustomerServiceOutlined />, schema: DOUYIN_CS_SCHEMA, platform: 'douyin' },
    { key: 'douyin_store_sync', nameEn: 'Douyin Store Operations — data sync', nameZh: '抖店运营 · 店铺资料同步', region: 'cn', icon: <ShopOutlined />, schema: DOUYIN_STORE_SYNC_SCHEMA, platform: 'douyin' },
    { key: 'douyin_cs_multi', nameEn: 'Douyin Customer Service — several stores', nameZh: '多店抖店客服', region: 'cn', icon: <ClusterOutlined />, schema: DOUYIN_MULTI_CS_SCHEMA, platform: 'douyin' },
    { key: 'pdd_cs', nameEn: 'Pinduoduo Customer Service', nameZh: '拼多多客服', region: 'cn', icon: <CustomerServiceOutlined />, schema: PDD_CS_SCHEMA, platform: 'pinduoduo' },
    { key: 'pdd_store_sync', nameEn: 'Pinduoduo Store Operations — data sync', nameZh: '拼多多运营 · 店铺资料同步', region: 'cn', icon: <ShopOutlined />, schema: PDD_STORE_SYNC_SCHEMA, platform: 'pinduoduo' },
    { key: 'pdd_cs_multi', nameEn: 'Pinduoduo Customer Service — several stores', nameZh: '多店拼多多客服', region: 'cn', icon: <ClusterOutlined />, schema: PDD_MULTI_CS_SCHEMA, platform: 'pinduoduo' },
    { key: 'tmall_cs', nameEn: 'T-Mall Store Customer Service', nameZh: '天猫客服', region: 'cn', icon: <CustomerServiceOutlined />, schema: CS_SCHEMA, platform: 'tmall' },
    { key: 'amazon_ops', nameEn: 'Amazon Operation', nameZh: '亚马逊运营', region: 'intl', icon: <AmazonOutlined />, schema: OPS_SCHEMA, platform: 'amazon' },
    { key: 'ebay_ops', nameEn: 'eBay Operation', nameZh: 'eBay运营', region: 'intl', icon: <ShopOutlined />, schema: OPS_SCHEMA, platform: 'ebay' },
    { key: 'etsy_ops', nameEn: 'Etsy Operation', nameZh: 'Etsy运营', region: 'intl', icon: <ShoppingOutlined />, schema: OPS_SCHEMA, platform: 'etsy' },
    { key: 'shopify_ops', nameEn: 'Shopify Operation', nameZh: 'Shopify运营', region: 'intl', icon: <ShoppingCartOutlined />, schema: OPS_SCHEMA, platform: 'shopify' },
    { key: 'tiktok_ops', nameEn: 'TikTok Store Operation', nameZh: 'Tiktok店铺运营', region: 'intl', icon: <TikTokOutlined />, schema: OPS_SCHEMA, platform: 'tiktok' },
];

/** Store platforms, one per scenario family, for the New Store form. */
export const PLATFORMS: { value: string; nameEn: string; nameZh: string }[] = [
    { value: 'douyin', nameEn: 'Douyin (抖店)', nameZh: '抖店' },
    { value: 'tmall', nameEn: 'T-Mall', nameZh: '天猫' },
    { value: 'amazon', nameEn: 'Amazon', nameZh: '亚马逊' },
    { value: 'ebay', nameEn: 'eBay', nameZh: 'eBay' },
    { value: 'etsy', nameEn: 'Etsy', nameZh: 'Etsy' },
    { value: 'shopify', nameEn: 'Shopify', nameZh: 'Shopify' },
    { value: 'tiktok', nameEn: 'TikTok Shop', nameZh: 'TikTok 店铺' },
    { value: 'pinduoduo', nameEn: 'Pinduoduo', nameZh: '拼多多' },
    { value: 'temu', nameEn: 'Temu', nameZh: 'Temu' },
    { value: 'shein', nameEn: 'SHEIN', nameZh: '希音 (SHEIN)' },
    { value: 'walmart', nameEn: 'Walmart', nameZh: '沃尔玛' },
    { value: 'jd', nameEn: 'JD.com', nameZh: '京东' },
    { value: '1688', nameEn: '1688', nameZh: '1688' },
    { value: 'alibaba', nameEn: 'Alibaba', nameZh: '阿里巴巴' },
    { value: 'kuaishou', nameEn: 'Kuaishou', nameZh: '快手' },
    { value: 'xiaohongshu', nameEn: 'Xiaohongshu (RED)', nameZh: '小红书' },
    { value: 'xianyu', nameEn: 'Xianyu', nameZh: '闲鱼' },
    { value: 'meituan', nameEn: 'Meituan', nameZh: '美团' },
    { value: 'aliexpress', nameEn: 'AliExpress', nameZh: '速卖通' },
    { value: 'lazada', nameEn: 'Lazada', nameZh: 'Lazada' },
    { value: 'shopee', nameEn: 'Shopee', nameZh: 'Shopee' },
    { value: 'mercadolibre', nameEn: 'Mercado Libre', nameZh: '美客多' },
    { value: 'coupang', nameEn: 'Coupang', nameZh: 'Coupang' },
    { value: 'facebook_marketplace', nameEn: 'Facebook Marketplace', nameZh: 'Facebook Marketplace' },
    { value: 'craigslist', nameEn: 'Craigslist', nameZh: 'Craigslist' },
    { value: 'nextdoor', nameEn: 'Nextdoor', nameZh: 'Nextdoor' },
    { value: 'offerup', nameEn: 'OfferUp', nameZh: 'OfferUp' },
    { value: 'flipkart', nameEn: 'Flipkart', nameZh: 'Flipkart' },
    { value: 'rakuten', nameEn: 'Rakuten', nameZh: '乐天' },
    { value: 'otto', nameEn: 'OTTO', nameZh: 'OTTO' },
];

/**
 * The platform key for what a user typed or a record holds: a known platform's
 * key, English or Chinese name (case-insensitive) all map to its key; anything
 * else is a custom platform and stays as typed. A store saved as "天猫" is a
 * tmall store (2026-10-05: the form's free-text entry stored the name, and
 * Fast Deploy refused the store as "not tmall").
 * Mirrored in agent/ec_agents/store_catalog.py (_PLATFORMS) -- keep both in step.
 */
export function platformValue(text: string | undefined | null): string {
    const t = String(text || '').trim();
    if (!t) return '';
    const k = t.toLowerCase();
    const p = PLATFORMS.find((x) => x.value.toLowerCase() === k
        || x.nameEn.toLowerCase() === k || x.nameZh.toLowerCase() === k);
    return p ? p.value : t;
}

/** Display name for a platform value; a custom platform shows as typed. */
export function platformLabel(value: string | undefined | null, lang: string): string {
    if (!value) return '';
    const v = platformValue(value);
    const p = PLATFORMS.find((x) => x.value === v);
    if (!p) return value;
    return lang && lang.toLowerCase().startsWith('zh') ? p.nameZh : p.nameEn;
}

export function getScenario(key: string | null): BusinessScenario | undefined {
    return key ? SCENARIOS.find((s) => s.key === key) : undefined;
}

export function scenarioName(s: BusinessScenario, lang: string): string {
    return lang && lang.startsWith('zh') ? s.nameZh : s.nameEn;
}

export function defaultConfig(s: BusinessScenario): ScenarioConfig {
    return {
        ...(s.schema.qaAgents ? { qaAgents: s.schema.qaAgents.default } : {}),
        ...(s.schema.replaceMode ? { mode: 'add' as const } : {}),
        ...(s.schema.fetchCatalog ? { fetchCatalog: true } : {}),
        ...(s.schema.fetchPromos ? { fetchPromos: true } : {}),
        ...(s.schema.storeId ? { storeId: '' } : {}),
        ...(s.schema.stores ? { stores: [] } : {}),
        // First after-sales run: the next full hour; then every 30 minutes.
        ...(s.schema.schedule ? {
            scheduleStart: (() => { const d = new Date(); d.setMinutes(0, 0, 0); d.setHours(d.getHours() + 1); return d.toISOString(); })(),
            scheduleEvery: 30,
            scheduleUnit: 'minutes' as const,
        } : {}),
    };
}

/** A business function a store can be staffed for. */
export interface FunctionArea { key: string; nameEn: string; nameZh: string }

/** Function areas in picker order; 客服 first (the default). */
export const FUNCTION_AREAS: FunctionArea[] = [
    { key: 'cs', nameEn: 'Customer service', nameZh: '客服' },
    { key: 'ops', nameEn: 'Operations', nameZh: '运营' },
    { key: 'presales', nameEn: 'Pre-sales', nameZh: '售前' },
    { key: 'aftersales', nameEn: 'After-sales', nameZh: '售后' },
    { key: 'marketing', nameEn: 'Marketing', nameZh: '营销' },
    { key: 'research', nameEn: 'Research', nameZh: '调研' },
    { key: 'manager', nameEn: 'Manager', nameZh: '经理' },
];

/** One Fast Deploy button: a store platform and the scenario behind each of
 *  its function areas (an area without a scenario is shown grayed out). */
export interface PlatformDeploy {
    platform: string;
    nameEn: string;
    nameZh: string;
    region: Region;
    icon: React.ReactNode;
    areas: Partial<Record<string, string>>;
    /** "Other platform": the user types the platform name. */
    custom?: boolean;
}

export const PLATFORM_DEPLOYS: PlatformDeploy[] = [
    { platform: 'douyin', nameEn: 'Douyin Store', nameZh: '抖店', region: 'cn', icon: <TikTokOutlined />, areas: { cs: 'douyin_cs', ops: 'douyin_store_sync' } },
    { platform: 'tmall', nameEn: 'Taobao / T-Mall', nameZh: '淘宝/天猫', region: 'cn', icon: <ShoppingOutlined />, areas: { cs: 'tmall_cs' } },
    { platform: 'pinduoduo', nameEn: 'Pinduoduo', nameZh: '拼多多', region: 'cn', icon: <ShoppingCartOutlined />, areas: { cs: 'pdd_cs', ops: 'pdd_store_sync' } },
    { platform: 'jd', nameEn: 'JD.com', nameZh: '京东', region: 'cn', icon: <ShopOutlined />, areas: {} },
    { platform: 'amazon', nameEn: 'Amazon', nameZh: '亚马逊', region: 'intl', icon: <AmazonOutlined />, areas: { ops: 'amazon_ops' } },
    { platform: 'ebay', nameEn: 'eBay', nameZh: 'eBay', region: 'intl', icon: <ShopOutlined />, areas: { ops: 'ebay_ops' } },
    { platform: 'etsy', nameEn: 'Etsy', nameZh: 'Etsy', region: 'intl', icon: <ShoppingOutlined />, areas: { ops: 'etsy_ops' } },
    { platform: 'shopify', nameEn: 'Shopify', nameZh: 'Shopify', region: 'intl', icon: <ShoppingCartOutlined />, areas: { ops: 'shopify_ops' } },
    { platform: 'tiktok', nameEn: 'TikTok Shop', nameZh: 'TikTok 店铺', region: 'intl', icon: <TikTokOutlined />, areas: { ops: 'tiktok_ops' } },
];

/** The last button: a platform not on the list, named by the user (stores
 *  only for now -- no function area deploys to an arbitrary platform). */
export const CUSTOM_PLATFORM_DEPLOY: PlatformDeploy = {
    platform: '', nameEn: 'Other platform', nameZh: '其他平台', region: 'cn', icon: <AppstoreAddOutlined />, areas: {}, custom: true,
};

/** The areas a platform's picker lists: the ones it can deploy first (客服 at
 *  the top when available), then the rest grayed out. Operations is listed
 *  only where a platform has it. */
export function areasFor(p: PlatformDeploy): { area: FunctionArea; scenario?: BusinessScenario }[] {
    const rows = FUNCTION_AREAS
        .filter((a) => a.key !== 'ops' || p.areas.ops)
        .map((a) => ({ area: a, scenario: getScenario(p.areas[a.key] || null) }));
    return [...rows.filter((r) => r.scenario), ...rows.filter((r) => !r.scenario)];
}

export function areaName(a: FunctionArea, lang: string): string {
    return lang && lang.startsWith('zh') ? a.nameZh : a.nameEn;
}

export function platformDeployName(p: PlatformDeploy, lang: string): string {
    return lang && lang.startsWith('zh') ? p.nameZh : p.nameEn;
}

/** A new store's permanent id -- the Stores page's rule (platform-name). */
export function newStoreId(platform: string, name: string): string {
    const n = name.trim();
    return n ? `${platform}-${n}` : '';
}
