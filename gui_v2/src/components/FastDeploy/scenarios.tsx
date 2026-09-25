import React from 'react';
import {
    CustomerServiceOutlined,
    AmazonOutlined,
    TikTokOutlined,
    ShopOutlined,
    ShoppingOutlined,
    ShoppingCartOutlined,
    ClusterOutlined,
} from '@ant-design/icons';

export type Region = 'cn' | 'intl';

/** Which config fields a scenario exposes in the config panel. */
export interface ScenarioSchema {
    /** Show the add/modify/delete store-URL list. */
    storeUrls: boolean;
    /** Show the "# of Q&A agents" control (customer-service scenarios). */
    qaAgents?: { default: number; min: number; max: number };
    /** Pre-filled first store URL (the platform's fixed workstation page). */
    defaultStoreUrl?: string;
    /** Show the add/replace switch (replace = delete THIS STORE's existing
     *  tasks on the scenario's skills + the agents serving only them, then add). */
    replaceMode?: boolean;
    /** Show the store-id field. Needed wherever the store URL does NOT identify
     *  the store: every 飞鸽 seller shares one workstation URL, so a URL-derived
     *  id would silently merge two stores' per-store config and metering. */
    storeId?: boolean;
    /** Several stores at once (picked from the Stores page), one shared Q&A
     *  pool: replaces the single store picker and the URL list. */
    stores?: boolean;
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
    storeUrls: string[];
    qaAgents?: number;
    mode?: 'add' | 'replace';
    storeId?: string;
    /** Only for a store created from this panel: its display name. */
    storeName?: string;
    /** Multi-store scenarios: the chosen store ids. */
    stores?: string[];
}

const CS_SCHEMA: ScenarioSchema = { storeUrls: true, qaAgents: { default: 6, min: 1, max: 16 } };
const DOUYIN_CS_SCHEMA: ScenarioSchema = {
    storeUrls: true,
    qaAgents: { default: 8, min: 1, max: 16 },
    defaultStoreUrl: 'https://im.jinritemai.com/pc_seller_v2/main/workspace',
    replaceMode: true,
    storeId: true,
};
const PDD_CS_SCHEMA: ScenarioSchema = {
    storeUrls: true,
    qaAgents: { default: 4, min: 1, max: 16 },
    defaultStoreUrl: 'https://mms.pinduoduo.com/chat-merchant/index.html',
    replaceMode: true,
    storeId: true,
};
// Several stores on this machine: each gets its own login profile + front desk;
// the Q&A agents are one pool shared by all of them.
const MULTI_CS_SCHEMA: ScenarioSchema = {
    storeUrls: false,
    stores: true,
    qaAgents: { default: 4, min: 1, max: 24 },
    replaceMode: true,
};
const OPS_SCHEMA: ScenarioSchema = { storeUrls: true };

export const SCENARIOS: BusinessScenario[] = [
    { key: 'douyin_cs', nameEn: 'Douyin Store Customer Service', nameZh: '抖店客服', region: 'cn', icon: <CustomerServiceOutlined />, schema: DOUYIN_CS_SCHEMA, platform: 'douyin' },
    { key: 'douyin_cs_multi', nameEn: 'Douyin Customer Service — several stores', nameZh: '多店抖店客服', region: 'cn', icon: <ClusterOutlined />, schema: MULTI_CS_SCHEMA, platform: 'douyin' },
    { key: 'pdd_cs', nameEn: 'Pinduoduo Customer Service', nameZh: '拼多多客服', region: 'cn', icon: <CustomerServiceOutlined />, schema: PDD_CS_SCHEMA, platform: 'pinduoduo' },
    { key: 'pdd_cs_multi', nameEn: 'Pinduoduo Customer Service — several stores', nameZh: '多店拼多多客服', region: 'cn', icon: <ClusterOutlined />, schema: MULTI_CS_SCHEMA, platform: 'pinduoduo' },
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

/** Display name for a platform value; a custom platform shows as typed. */
export function platformLabel(value: string | undefined | null, lang: string): string {
    if (!value) return '';
    const p = PLATFORMS.find((x) => x.value === value);
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
        storeUrls: [s.schema.defaultStoreUrl ?? ''],
        ...(s.schema.qaAgents ? { qaAgents: s.schema.qaAgents.default } : {}),
        ...(s.schema.replaceMode ? { mode: 'add' as const } : {}),
        ...(s.schema.storeId ? { storeId: '' } : {}),
        ...(s.schema.stores ? { stores: [] } : {}),
    };
}
