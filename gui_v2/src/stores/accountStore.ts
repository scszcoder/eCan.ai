import { create } from 'zustand';
import { getRegionSync } from '../contexts/AppConfigContext';

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
    /** Server-verified contact flags (verify_account_info resolver). Absent on
     *  older backends — treat missing as "unknown", only explicit false counts
     *  as unverified. */
    email_verified?: boolean;
    phone_verified?: boolean;
    /** ISO date after which an incomplete account is deactivated (server-set,
     *  60 days from signup). */
    verify_deadline?: string;
}

export interface VerificationStatus {
    /** false only when the server explicitly reports something unverified */
    complete: boolean;
    missing: Array<'email' | 'phone'>;
    /** days until deactivation; null when unknown/complete */
    daysLeft: number | null;
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
    /** Fetch fresh account info from the cloud (used by the 20-min poller
     *  and the Account page refresh). Safe to call repeatedly. */
    fetchAccountInfo: () => Promise<boolean>;

    // Computed getters
    isFreeTier: () => boolean;
    getSubscriptions: () => string[];
    /** Current fund balance, or null when unknown. */
    getFund: () => number | null;
    /** Contact-verification completeness (red-flag indicator). */
    getVerificationStatus: () => VerificationStatus;
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

    fetchAccountInfo: async () => {
        try {
            const { ipcApi } = await import('../services/ipc/api');
            const response = await ipcApi.executeRequest('get_account_info', {});
            if (response?.success && response.data) {
                const data = (response.data as any).accountInfo || response.data;
                set({ accountData: data, lastUpdated: Date.now(), error: null });
                return true;
            }
            set({ error: (response as any)?.error?.message || 'fetch failed' });
            return false;
        } catch (e: any) {
            set({ error: e?.message || String(e) });
            return false;
        }
    },
    
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
    
    getFund: () => {
        const { accountData } = get();
        const fund = accountData?.acctInfo?.fund;
        if (typeof fund !== 'number' || Number.isNaN(fund)) return null;
        // CN billing went server-authoritative (2026-09-01): accounts.fund
        // is integer fen. Normalize to yuan here so every consumer (display,
        // low-fund threshold) works in currency units. Intl stays USD as-is.
        return getRegionSync() === 'cn' ? fund / 100 : fund;
    },

    getVerificationStatus: () => {
        const { accountData } = get();
        const info = accountData?.acctInfo;
        const missing: Array<'email' | 'phone'> = [];
        // Only an explicit false counts — older backends omit the flags.
        if (info?.email_verified === false) missing.push('email');
        if (info?.phone_verified === false) missing.push('phone');
        let daysLeft: number | null = null;
        if (missing.length) {
            const deadlineSrc = info?.verify_deadline
                || (info?.sign_on_date
                    ? new Date(new Date(info.sign_on_date).getTime() + 60 * 86400_000).toISOString()
                    : null);
            if (deadlineSrc) {
                const ms = new Date(deadlineSrc).getTime() - Date.now();
                daysLeft = Number.isNaN(ms) ? null : Math.max(0, Math.ceil(ms / 86400_000));
            }
        }
        return { complete: missing.length === 0, missing, daysLeft };
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
