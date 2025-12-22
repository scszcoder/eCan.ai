import React, { useEffect, useRef } from 'react';
import styled from '@emotion/styled';
import { CloseOutlined } from '@ant-design/icons';
import { useAdStore } from '../../stores/adStore';

const PopupOverlay = styled.div<{ isVisible: boolean }>`
    position: fixed;
    top: 0;
    left: 0;
    right: 0;
    bottom: 0;
    background: rgba(0, 0, 0, 0.6);
    backdrop-filter: blur(4px);
    display: flex;
    align-items: center;
    justify-content: center;
    z-index: 10000;
    opacity: ${props => props.isVisible ? 1 : 0};
    visibility: ${props => props.isVisible ? 'visible' : 'hidden'};
    transition: opacity 0.3s ease, visibility 0.3s ease;
`;

const PopupContainer = styled.div<{ isVisible: boolean }>`
    position: relative;
    max-width: 520px;
    max-height: 80vh;
    width: 90%;
    background: linear-gradient(145deg, rgba(30, 41, 59, 0.98) 0%, rgba(15, 23, 42, 0.98) 100%);
    border-radius: 16px;
    border: 1px solid rgba(255, 255, 255, 0.1);
    box-shadow: 
        0 24px 48px rgba(0, 0, 0, 0.4),
        0 0 0 1px rgba(255, 255, 255, 0.05) inset;
    overflow: hidden;
    transform: ${props => props.isVisible ? 'scale(1) translateY(0)' : 'scale(0.9) translateY(20px)'};
    transition: transform 0.3s cubic-bezier(0.4, 0, 0.2, 1);
`;

const CloseButton = styled.button`
    position: absolute;
    top: 12px;
    right: 12px;
    width: 32px;
    height: 32px;
    border: none;
    background: rgba(255, 255, 255, 0.1);
    border-radius: 8px;
    cursor: pointer;
    display: flex;
    align-items: center;
    justify-content: center;
    color: rgba(248, 250, 252, 0.7);
    transition: all 0.2s ease;
    z-index: 10;
    
    &:hover {
        background: rgba(255, 255, 255, 0.2);
        color: rgba(248, 250, 252, 1);
    }
`;

const ContentWrapper = styled.div`
    padding: 24px;
    overflow-y: auto;
    max-height: 80vh;
    
    /* Custom scrollbar */
    &::-webkit-scrollbar {
        width: 6px;
    }
    
    &::-webkit-scrollbar-track {
        background: rgba(255, 255, 255, 0.05);
        border-radius: 3px;
    }
    
    &::-webkit-scrollbar-thumb {
        background: rgba(255, 255, 255, 0.2);
        border-radius: 3px;
        
        &:hover {
            background: rgba(255, 255, 255, 0.3);
        }
    }
`;

const AdPopup: React.FC = () => {
    const popupAd = useAdStore((state) => state.popupAd);
    const isPopupVisible = useAdStore((state) => state.isPopupVisible);
    const hidePopup = useAdStore((state) => state.hidePopup);
    const contentRef = useRef<HTMLDivElement>(null);
    
    // Handle escape key to close popup
    useEffect(() => {
        const handleKeyDown = (e: KeyboardEvent) => {
            if (e.key === 'Escape' && isPopupVisible) {
                hidePopup();
            }
        };
        
        window.addEventListener('keydown', handleKeyDown);
        return () => window.removeEventListener('keydown', handleKeyDown);
    }, [isPopupVisible, hidePopup]);
    
    // Handle click outside to close
    const handleOverlayClick = (e: React.MouseEvent) => {
        if (e.target === e.currentTarget) {
            hidePopup();
        }
    };
    
    // Render HTML content safely
    useEffect(() => {
        if (contentRef.current && popupAd?.htmlContent) {
            contentRef.current.innerHTML = popupAd.htmlContent;
        }
    }, [popupAd?.htmlContent, isPopupVisible]);
    
    if (!popupAd) {
        return null;
    }
    
    return (
        <PopupOverlay isVisible={isPopupVisible} onClick={handleOverlayClick}>
            <PopupContainer isVisible={isPopupVisible}>
                <CloseButton 
                    className="ad-popup-close" 
                    onClick={hidePopup}
                    aria-label="Close"
                >
                    <CloseOutlined />
                </CloseButton>
                <ContentWrapper ref={contentRef} />
            </PopupContainer>
        </PopupOverlay>
    );
};

export default AdPopup;
