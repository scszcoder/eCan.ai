import React from 'react';
import {
    CustomerServiceOutlined,
    AmazonOutlined,
    TikTokOutlined,
    ShopOutlined,
    ShoppingOutlined,
    ShoppingCartOutlined,
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
}

const CS_SCHEMA: ScenarioSchema = { storeUrls: true, qaAgents: { default: 6, min: 1, max: 16 } };
const DOUYIN_CS_SCHEMA: ScenarioSchema = {
    storeUrls: true,
    qaAgents: { default: 8, min: 1, max: 16 },
    defaultStoreUrl: 'https://im.jinritemai.com/pc_seller_v2/main/workspace',
    replaceMode: true,
    storeId: true,
};
const OPS_SCHEMA: ScenarioSchema = { storeUrls: true };

export const SCENARIOS: BusinessScenario[] = [
    { key: 'douyin_cs', nameEn: 'Douyin Store Customer Service', nameZh: '抖店客服', region: 'cn', icon: <CustomerServiceOutlined />, schema: DOUYIN_CS_SCHEMA, platform: 'douyin' },
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
];

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
    };
}
