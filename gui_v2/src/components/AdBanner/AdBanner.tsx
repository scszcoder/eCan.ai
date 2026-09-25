import React, { useEffect, useRef, useState } from 'react';
import styled from '@emotion/styled';
import { css, keyframes } from '@emotion/react';
import { useTranslation } from 'react-i18next';
import { useNavigate } from 'react-router-dom';
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

// Fund alert (2026-09-15): the old warning scrolled orange text 5 times and
// then hid for 10 minutes, so it was on screen 40s out of every 10 — easy to
// miss entirely, and it offered no way to act. It is now a persistent bar with
// a top-up button, in three tiers:
//
//   low       ≤36 and > 10  static red, dismissible — a heads-up
//   critical  ≤10           red, text scrolling without pause, not dismissible
//   blocked   cloud refused  darkest red, scrolling — work has already stopped
//
// Motion is what the eye catches, so the two tiers that matter keep scrolling
// rather than showing once and going quiet.
const LOW_FUND_THRESHOLD = 36;
const CRITICAL_FUND_THRESHOLD = 10;
const MARQUEE_SECONDS = 9;
const MARQUEE_GAP_PX = 48;

type FundSeverity = 'low' | 'critical' | 'blocked';

const SEVERITY_COLORS: Record<FundSeverity, { bg: string; border: string; text: string }> = {
    low: { bg: 'rgba(220, 38, 38, 0.12)', border: 'rgba(220, 38, 38, 0.5)', text: '#ff4d4f' },
    critical: { bg: 'rgba(220, 38, 38, 0.22)', border: 'rgba(220, 38, 38, 0.85)', text: '#ff7875' },
    blocked: { bg: 'rgba(153, 27, 27, 0.35)', border: 'rgba(239, 68, 68, 1)', text: '#fff1f0' },
};

// Two identical copies slide by as one track, so as the first copy leaves on
// the left the second is already entering on the right. The earlier version
// scrolled a single copy behind `padding-left: 100%`, which left the bar
// EMPTY at the start of every cycle — and the banner appears at exactly that
// moment, so the first thing the user saw was a blank red rectangle.
const marquee = keyframes`
    0%   { transform: translateX(0); }
    100% { transform: translateX(-50%); }
`;

const pulse = keyframes`
    0%, 100% { box-shadow: 0 0 0 0 rgba(239, 68, 68, 0.45); }
    50%      { box-shadow: 0 0 0 4px rgba(239, 68, 68, 0); }
`;

const FundAlertBar = styled.div<{ severity: FundSeverity }>`
    flex: 1;
    height: 32px;
    margin: 0 16px;
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 0 8px 0 12px;
    overflow: hidden;
    border-radius: 6px;
    background: ${props => SEVERITY_COLORS[props.severity].bg};
    border: 1px solid ${props => SEVERITY_COLORS[props.severity].border};
    ${props => props.severity === 'low' ? '' : css`animation: ${pulse} ${props.severity === 'blocked' ? '1s' : '2s'} ease-in-out infinite;`}
`;

const FundAlertViewport = styled.div`
    flex: 1;
    min-width: 0;
    overflow: hidden;
    white-space: nowrap;
`;

const FundAlertTrack = styled.div`
    display: flex;
    width: max-content;
    animation: ${marquee} ${MARQUEE_SECONDS}s linear infinite;
`;

const FundAlertText = styled.span<{ severity: FundSeverity }>`
    color: ${props => SEVERITY_COLORS[props.severity].text};
    font-size: ${props => props.severity === 'blocked' ? '16px' : '13px'};
    font-weight: ${props => props.severity === 'blocked' ? 900 : 700};
    letter-spacing: 0.3px;
    ${props => props.severity === 'low' ? '' : `padding-right: ${MARQUEE_GAP_PX}px;`}
    ${props => props.severity === 'blocked' ? css`
        text-shadow: 0 0 8px rgba(239, 68, 68, 0.9);
    ` : ''}
`;

const TopUpButton = styled.button`
    flex: none;
    /* Centre the label explicitly rather than relying on the button's default
       content alignment: this sits inside a line-height:64px AntD header. */
    display: inline-flex;
    align-items: center;
    justify-content: center;
    min-height: 22px;
    padding: 2px 10px;
    border: 0;
    border-radius: 4px;
    background: #dc2626;
    color: #fff;
    -webkit-text-fill-color: #fff;
    font-size: 12px;
    font-weight: 700;
    line-height: 1.2;
    cursor: pointer;
    white-space: nowrap;

    &:hover { background: #b91c1c; }
`;

const DismissButton = styled.button`
    flex: none;
    width: 20px;
    height: 20px;
    padding: 0;
    border: 0;
    border-radius: 4px;
    background: transparent;
    color: rgba(248, 250, 252, 0.7);
    font-size: 15px;
    line-height: 1;
    cursor: pointer;

    &:hover { color: #fff; }
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
    const billingBlocked = useAccountStore((state) => state.billingBlocked);
    const [lowDismissed, setLowDismissed] = useState(false);
    const navigate = useNavigate();

    const severity: FundSeverity | null = billingBlocked || (fund !== null && fund <= 0)
        ? 'blocked'
        : fund === null
            ? null
            : fund <= CRITICAL_FUND_THRESHOLD
                ? 'critical'
                : fund <= LOW_FUND_THRESHOLD
                    ? 'low'
                    : null;

    // A dismissal only covers the tier it was made in: if the balance keeps
    // falling, or the cloud starts refusing calls, the bar comes back.
    useEffect(() => {
        if (severity !== 'low') setLowDismissed(false);
    }, [severity]);

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

    // The fund alert takes the slot whenever work is at risk. 'critical' and
    // 'blocked' outrank the transient error banner — a stopped account matters
    // more than a 60-second error toast; 'low' stays below it.
    const errorActive = !!(errorBanner && errorBanner.expiresAt > Date.now());
    const showFundAlert = severity === 'blocked' || severity === 'critical'
        || (severity === 'low' && !lowDismissed && !errorActive);
    if (showFundAlert && severity) {
        const text = severity === 'blocked'
            ? t('banner.fundBlocked', 'Cloud AI balance exhausted — tasks are paused. Top up to resume.')
            : severity === 'critical'
                ? t('banner.fundCritical', 'Balance critically low — tasks will stop very soon. Top up now.')
                : t('banner.fundRunningLow', 'Fund running low');
        return (
            <FundAlertBar severity={severity} title={text}>
                <FundAlertViewport>
                    {severity === 'low' ? (
                        <FundAlertText severity={severity}>{text}</FundAlertText>
                    ) : (
                        <FundAlertTrack>
                            <FundAlertText severity={severity}>{text}</FundAlertText>
                            <FundAlertText severity={severity} aria-hidden="true">{text}</FundAlertText>
                        </FundAlertTrack>
                    )}
                </FundAlertViewport>
                <TopUpButton
                    onClick={() => navigate('/account')}
                    title={t('banner.topUpNow', 'Top up now')}
                >
                    {t('banner.topUpNow', 'Top up now')}
                </TopUpButton>
                {severity === 'low' && (
                    <DismissButton
                        onClick={() => setLowDismissed(true)}
                        title={t('common.dismiss', 'Dismiss')}
                    >
                        ×
                    </DismissButton>
                )}
            </FundAlertBar>
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
