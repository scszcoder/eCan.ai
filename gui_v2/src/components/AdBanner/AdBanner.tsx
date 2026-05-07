import React, { useEffect, useRef, useState } from 'react';
import styled from '@emotion/styled';
import { keyframes } from '@emotion/react';
import { useAdStore } from '../../stores/adStore';

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

const AdBanner: React.FC = () => {
    const bannerAd = useAdStore((state) => state.bannerAd);
    const popupAd = useAdStore((state) => state.popupAd);
    const errorBanner = useAdStore((state) => state.errorBanner);
    const showPopup = useAdStore((state) => state.showPopup);
    const clearExpiredAds = useAdStore((state) => state.clearExpiredAds);
    const [isVisible, setIsVisible] = useState(false);
    const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

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
