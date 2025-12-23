import { create } from 'zustand';

/**
 * Account info structure from cloud API
 * Based on convertAccountRecords() from cloud side
 */
export interface AccountInfo {
    actid: number;
    user_name: string;
    subid: string;
    dob: string;
    email: string;
    phone: string;
    addr: string;
    ssn4: string;
    sign_on_date: string;
    last_actions: Record<string, any>;
    pay_method1: string;
    pay1_details: string;
    pay_method2: number;
    pay2_details: string;
    pay_method3: number;
    pay3_details: string;
    subs: string;  // List of subscribed services, empty = free tier
    fund: number;
    quota: number;
    states: string;
}

export interface OrderInfo {
    // Order fields from convertOrderRecords
    [key: string]: any;
}

export interface BotInfo {
    // Bot fields from convertBotRecords
    [key: string]: any;
}

export interface MissionInfo {
    // Mission fields from convertMissionRecords
    [key: string]: any;
}

export interface SkillInfo {
    // Skill fields from convertSkillRecords
    [key: string]: any;
}

export interface APIUsageInfo {
    // API usage fields from convertAPIUsageRecords
    [key: string]: any;
}

export interface APIKeyInfo {
    // API key details
    [key: string]: any;
}

/**
 * Full account data structure from queryAccountInfo
 */
export interface AccountData {
    acctInfo: AccountInfo;
    ordersInfo: OrderInfo[];
    bots: BotInfo[];
    missions: MissionInfo[];
    skills: SkillInfo[];
    api_usage: APIUsageInfo[];
    api_key: APIKeyInfo;
}

interface AccountState {
    accountData: AccountData | null;
    isLoading: boolean;
    error: string | null;
    lastUpdated: number | null;
    
    setAccountData: (data: AccountData | null) => void;
    setLoading: (loading: boolean) => void;
    setError: (error: string | null) => void;
    clearAccountData: () => void;
    
    // Computed getters
    isFreeTier: () => boolean;
    getSubscriptions: () => string[];
}

export const useAccountStore = create<AccountState>((set, get) => ({
    accountData: null,
    isLoading: false,
    error: null,
    lastUpdated: null,
    
    setAccountData: (data) => set({ 
        accountData: data, 
        lastUpdated: Date.now(),
        error: null 
    }),
    
    setLoading: (loading) => set({ isLoading: loading }),
    
    setError: (error) => set({ error, isLoading: false }),
    
    clearAccountData: () => set({ 
        accountData: null, 
        error: null, 
        lastUpdated: null 
    }),
    
    isFreeTier: () => {
        const { accountData } = get();
        if (!accountData?.acctInfo?.subs) return true;
        const subs = accountData.acctInfo.subs;
        // Empty string or empty array means free tier
        if (typeof subs === 'string') {
            return subs.trim() === '' || subs === '[]';
        }
        return true;
    },
    
    getSubscriptions: () => {
        const { accountData } = get();
        if (!accountData?.acctInfo?.subs) return [];
        const subs = accountData.acctInfo.subs;
        if (typeof subs === 'string') {
            try {
                const parsed = JSON.parse(subs);
                return Array.isArray(parsed) ? parsed : [];
            } catch {
                return subs.trim() ? [subs] : [];
            }
        }
        return [];
    },
}));
