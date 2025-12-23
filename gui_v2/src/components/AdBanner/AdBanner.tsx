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

const AdBanner: React.FC = () => {
    const bannerAd = useAdStore((state) => state.bannerAd);
    const popupAd = useAdStore((state) => state.popupAd);
    const showPopup = useAdStore((state) => state.showPopup);
    const clearExpiredAds = useAdStore((state) => state.clearExpiredAds);
    const [isVisible, setIsVisible] = useState(false);
    const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);
    
    // Check for expired ads periodically
    useEffect(() => {
        intervalRef.current = setInterval(() => {
            clearExpiredAds();
        }, 1000);
        
        return () => {
            if (intervalRef.current) {
                clearInterval(intervalRef.current);
            }
        };
    }, [clearExpiredAds]);
    
    // Update visibility based on banner ad presence
    useEffect(() => {
        if (bannerAd && bannerAd.expiresAt > Date.now()) {
            setIsVisible(true);
        } else {
            setIsVisible(false);
        }
    }, [bannerAd]);
    
    const handleClick = () => {
        if (popupAd && popupAd.expiresAt > Date.now()) {
            showPopup();
        }
    };
    
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
