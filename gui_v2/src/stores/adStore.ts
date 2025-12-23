import { create } from 'zustand';

export interface AdBannerData {
    id: string;
    text: string;
    expiresAt: number; // Unix timestamp in ms
}

export interface AdPopupData {
    id: string;
    htmlContent: string;
    expiresAt: number; // Unix timestamp in ms
}

interface AdState {
    bannerAd: AdBannerData | null;
    popupAd: AdPopupData | null;
    isPopupVisible: boolean;
    
    setBannerAd: (ad: AdBannerData | null) => void;
    setPopupAd: (ad: AdPopupData | null) => void;
    showPopup: () => void;
    hidePopup: () => void;
    clearExpiredAds: () => void;
}

export const useAdStore = create<AdState>((set, get) => ({
    bannerAd: null,
    popupAd: null,
    isPopupVisible: false,
    
    setBannerAd: (ad) => set({ bannerAd: ad }),
    setPopupAd: (ad) => set({ popupAd: ad }),
    showPopup: () => set({ isPopupVisible: true }),
    hidePopup: () => set({ isPopupVisible: false }),
    
    clearExpiredAds: () => {
        const now = Date.now();
        const { bannerAd, popupAd } = get();
        
        if (bannerAd && bannerAd.expiresAt <= now) {
            set({ bannerAd: null });
        }
        if (popupAd && popupAd.expiresAt <= now) {
            set({ popupAd: null, isPopupVisible: false });
        }
    },
}));

// Test function to simulate backend pushing ads (for unit testing)
export const pushTestAds = (durationMs: number = 60000) => {
    const expiresAt = Date.now() + durationMs;
    
    // Set banner ad
    useAdStore.getState().setBannerAd({
        id: 'test-banner-1',
        text: '🎉 Special Offer! Get 50% off on all premium plans. Limited time only! Click here to learn more. 🚀 New features available now!',
        expiresAt,
    });
    
    // Set popup ad with HTML content
    useAdStore.getState().setPopupAd({
        id: 'test-popup-1',
        htmlContent: `
            <div style="text-align: center; padding: 20px;">
                <img src="https://via.placeholder.com/400x200/3b82f6/ffffff?text=Special+Offer" alt="Ad Banner" style="max-width: 100%; border-radius: 12px; margin-bottom: 20px;" />
                <h2 style="color: #f8fafc; margin-bottom: 12px; font-size: 24px;">🎉 Exclusive Deal!</h2>
                <p style="color: rgba(248, 250, 252, 0.8); margin-bottom: 20px; font-size: 16px; line-height: 1.6;">
                    Upgrade to our Premium Plan today and unlock all features!<br/>
                    <strong style="color: #3b82f6;">50% OFF</strong> for the first 3 months.
                </p>
                <div style="display: flex; gap: 12px; justify-content: center; flex-wrap: wrap;">
                    <button onclick="window.location.href='/account/payment-plan'" style="
                        background: linear-gradient(135deg, #3b82f6 0%, #8b5cf6 100%);
                        color: white;
                        border: none;
                        padding: 12px 32px;
                        border-radius: 8px;
                        font-size: 16px;
                        font-weight: 600;
                        cursor: pointer;
                        transition: transform 0.2s, box-shadow 0.2s;
                    " onmouseover="this.style.transform='scale(1.05)'; this.style.boxShadow='0 8px 24px rgba(59, 130, 246, 0.4)';" onmouseout="this.style.transform='scale(1)'; this.style.boxShadow='none';">
                        Get Started Now
                    </button>
                    <button onclick="document.querySelector('.ad-popup-close')?.click()" style="
                        background: transparent;
                        color: rgba(248, 250, 252, 0.7);
                        border: 1px solid rgba(248, 250, 252, 0.3);
                        padding: 12px 32px;
                        border-radius: 8px;
                        font-size: 16px;
                        cursor: pointer;
                        transition: all 0.2s;
                    " onmouseover="this.style.borderColor='rgba(248, 250, 252, 0.6)'; this.style.color='rgba(248, 250, 252, 0.9)';" onmouseout="this.style.borderColor='rgba(248, 250, 252, 0.3)'; this.style.color='rgba(248, 250, 252, 0.7)';">
                        Maybe Later
                    </button>
                </div>
                <p style="color: rgba(248, 250, 252, 0.5); margin-top: 16px; font-size: 12px;">
                    Offer expires in 24 hours. Terms and conditions apply.
                </p>
            </div>
        `,
        expiresAt,
    });
    
    console.log('[AdStore] Test ads pushed, will expire in', durationMs / 1000, 'seconds');
};

// Clear test ads
export const clearTestAds = () => {
    useAdStore.getState().setBannerAd(null);
    useAdStore.getState().setPopupAd(null);
    useAdStore.getState().hidePopup();
    console.log('[AdStore] Test ads cleared');
};
