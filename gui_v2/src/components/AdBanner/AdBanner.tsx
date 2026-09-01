import React, { useEffect, useRef, useState } from 'react';
import styled from '@emotion/styled';
import { keyframes } from '@emotion/react';
import { useTranslation } from 'react-i18next';
import { useAdStore } from '../../stores/adStore';
import { useAccountStore } from '../../stores/accountStore';

const scrollAnimation = keyframes`
    0% {
        transform: translateX(0%);
    }
    100% {
        transform: translateX(-100%);
    }
`;

const BannerContainer = styled.div<{ isVisible: boolean }>`
    flex: 1;
    height: 32px;
    overflow: hidden;
    position: relative;
    cursor: pointer;
    margin: 0 16px;
    opacity: ${props => props.isVisible ? 1 : 0};
    transition: opacity 0.3s ease;
    pointer-events: ${props => props.isVisible ? 'auto' : 'none'};
    
    &:hover .scroll-text {
        animation-play-state: paused;
    }
`;

const ScrollWrapper = styled.div`
    position: absolute;
    top: 0;
    left: 0;
    right: 0;
    bottom: 0;
    display: flex;
    align-items: center;
    white-space: nowrap;
`;

const ScrollText = styled.span`
    display: inline-block;
    padding-left: 100%;
    animation: ${scrollAnimation} 12s linear infinite;
    animation-fill-mode: forwards;
    color: rgba(248, 250, 252, 0.85);
    font-size: 13px;
    font-weight: 500;
    letter-spacing: 0.3px;
    
    &:hover {
        color: rgba(59, 130, 246, 1);
    }
`;

// Error banner: static (non-scrolling), red, high-visibility.
// Sits in the same slot as the ad banner and takes priority while set.
const ErrorBannerContainer = styled.div<{ isVisible: boolean }>`
    flex: 1;
    height: 32px;
    margin: 0 16px;
    display: flex;
    align-items: center;
    justify-content: center;
    background: rgba(220, 38, 38, 0.15);
    border: 1px solid rgba(220, 38, 38, 0.55);
    border-radius: 6px;
    opacity: ${props => props.isVisible ? 1 : 0};
    transition: opacity 0.3s ease;
    pointer-events: ${props => props.isVisible ? 'auto' : 'none'};
`;

const ErrorText = styled.span`
    color: #ff4d4f;
    font-size: 13px;
    font-weight: 700;
    letter-spacing: 0.3px;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    padding: 0 12px;
`;

// Low-fund warning (2026-08-31): when the balance drops to ≤36 RMB, an
// orange "Fund running low" scrolls across this banner slot 5 times, and the
// cycle repeats every 10 minutes while the balance stays low.
const LOW_FUND_THRESHOLD = 36;
const LOW_FUND_PASSES = 5;
const LOW_FUND_PASS_SECONDS = 8;
const LOW_FUND_CYCLE_MS = 10 * 60_000;

const LowFundText = styled.span`
    display: inline-block;
    padding-left: 100%;
    animation: ${scrollAnimation} ${LOW_FUND_PASS_SECONDS}s linear ${LOW_FUND_PASSES};
    animation-fill-mode: forwards;
    color: #fa8c16;
    font-size: 13px;
    font-weight: 700;
    letter-spacing: 0.3px;
`;

const AdBanner: React.FC = () => {
    const bannerAd = useAdStore((state) => state.bannerAd);
    const popupAd = useAdStore((state) => state.popupAd);
    const errorBanner = useAdStore((state) => state.errorBanner);
    const showPopup = useAdStore((state) => state.showPopup);
    const clearExpiredAds = useAdStore((state) => state.clearExpiredAds);
    const [isVisible, setIsVisible] = useState(false);
    const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);
    const { t } = useTranslation();
    const fund = useAccountStore((state) => state.getFund());
    const [lowFundPass, setLowFundPass] = useState(false);

    // Low-fund cycle: while fund ≤ threshold, show the scrolling warning for
    // 5 passes, then hide until the next 10-minute tick.
    useEffect(() => {
        if (fund === null || fund > LOW_FUND_THRESHOLD) {
            setLowFundPass(false);
            return;
        }
        let hideTimer: ReturnType<typeof setTimeout> | null = null;
        const runCycle = () => {
            setLowFundPass(true);
            hideTimer = setTimeout(
                () => setLowFundPass(false),
                LOW_FUND_PASSES * LOW_FUND_PASS_SECONDS * 1000 + 500,
            );
        };
        runCycle();
        const cycle = setInterval(runCycle, LOW_FUND_CYCLE_MS);
        return () => {
            clearInterval(cycle);
            if (hideTimer) clearTimeout(hideTimer);
            setLowFundPass(false);
        };
    }, [fund === null || fund > LOW_FUND_THRESHOLD]);

    // Check for expired ads/banners periodically. Use a shorter 5s tick so
    // transient error banners (default ~60s) clear close to their expiry
    // instead of lingering up to 30s after.
    useEffect(() => {
        intervalRef.current = setInterval(() => {
            clearExpiredAds();
        }, 5_000);

        return () => {
            if (intervalRef.current) {
                clearInterval(intervalRef.current);
            }
        };
    }, [clearExpiredAds]);

    // Update visibility based on banner/error presence
    useEffect(() => {
        const now = Date.now();
        const errorActive = !!(errorBanner && errorBanner.expiresAt > now);
        const adActive = !!(bannerAd && bannerAd.expiresAt > now);
        setIsVisible(errorActive || adActive);
    }, [bannerAd, errorBanner]);

    const handleClick = () => {
        if (popupAd && popupAd.expiresAt > Date.now()) {
            showPopup();
        }
    };

    // Low-fund warning takes the slot during its passes (below the error
    // banner in priority, above ordinary ads).
    if (lowFundPass && !(errorBanner && errorBanner.expiresAt > Date.now())) {
        return (
            <BannerContainer isVisible={true}>
                <ScrollWrapper>
                    <LowFundText key={`lowfund-${lowFundPass}`}>
                        {t('banner.fundRunningLow', 'Fund running low')}
                    </LowFundText>
                </ScrollWrapper>
            </BannerContainer>
        );
    }

    // Error banner takes precedence over ad banner.
    if (errorBanner && errorBanner.expiresAt > Date.now()) {
        return (
            <ErrorBannerContainer isVisible={isVisible} title={errorBanner.text}>
                <ErrorText>{errorBanner.text}</ErrorText>
            </ErrorBannerContainer>
        );
    }

    if (!bannerAd) {
        return <BannerContainer isVisible={false} />;
    }

    return (
        <BannerContainer isVisible={isVisible} onClick={handleClick} title="Click for details">
            <ScrollWrapper>
                <ScrollText className="scroll-text">
                    {bannerAd.text}
                </ScrollText>
            </ScrollWrapper>
        </BannerContainer>
    );
};

export default AdBanner;
