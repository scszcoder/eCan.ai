import React, { useEffect, useState, useCallback } from 'react';
import styled from '@emotion/styled';
import { keyframes } from '@emotion/react';
import { DollarOutlined } from '@ant-design/icons';
import { useNavigate } from 'react-router-dom';
import { ipcApi } from '../../services/ipc/api';
import { logger } from '../../utils/logger';

// Custom 3-circle token icon component
const TokenIcon: React.FC<{ className?: string }> = ({ className }) => (
    <svg
        className={className}
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth="2"
        width="1em"
        height="1em"
    >
        {/* 3 hollow circles in triangular arrangement - spread out to avoid overlap */}
        <circle cx="12" cy="5" r="4" />
        <circle cx="5" cy="17" r="4" />
        <circle cx="19" cy="17" r="4" />
    </svg>
);

// LED glow animation
const ledGlow = keyframes`
    0%, 100% {
        text-shadow: 0 0 10px currentColor, 0 0 20px currentColor, 0 0 30px currentColor;
    }
    50% {
        text-shadow: 0 0 5px currentColor, 0 0 10px currentColor, 0 0 15px currentColor;
    }
`;

interface TokenUsageData {
    input_tokens: number;
    output_tokens: number;
    total_tokens: number;
    cost_usd: number;
}

interface LEDDisplayProps {
    color: string;
}

const Container = styled.div`
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 4px 12px;
    background: rgba(0, 0, 0, 0.6);
    border-radius: 6px;
    border: 1px solid rgba(255, 255, 255, 0.1);
    font-family: 'Courier New', monospace;
    user-select: none;
    cursor: pointer;

    &:hover {
        border-color: rgba(0, 255, 0, 0.3);
    }
`;

const LEDDisplay = styled.div<LEDDisplayProps & { isHovered?: boolean }>`
    display: flex;
    flex-direction: column;
    gap: 2px;
    color: #00ff00;
    animation: ${ledGlow} 2s ease-in-out infinite;
    animation-play-state: ${props => props.isHovered ? 'running' : 'paused'};
    font-size: 11px;
    font-weight: bold;
    line-height: 1.2;
    letter-spacing: 1px;
`;

const LEDRow = styled.div`
    display: flex;
    align-items: center;
    gap: 6px;
`;

const LEDLabel = styled.span`
    opacity: 0.7;
    font-size: 9px;
    min-width: 24px;
`;

const LEDValue = styled.span`
    min-width: 90px;
    text-align: right;
    font-variant-numeric: tabular-nums;
`;

const ToggleIcon = styled.div`
    display: flex;
    align-items: center;
    justify-content: center;
    width: 24px;
    height: 24px;
    color: #00ff00;
    cursor: pointer;
    transition: all 0.2s;
    font-size: 16px;
    
    &:hover {
        color: #00ff88;
        transform: scale(1.1);
    }
    
    &:active {
        transform: scale(0.95);
    }
`;

// Thresholds in USD
const THRESHOLD_LOW = 30;
const THRESHOLD_HIGH = 60;

const formatNumber = (num: number, maxDigits: number = 9): string => {
    const str = num.toLocaleString('en-US');
    return str.padStart(maxDigits, ' ');
};

const formatCurrency = (num: number): string => {
    return `$${num.toFixed(2).padStart(8, ' ')}`;
};

// Color is now fixed to green, thresholds kept for potential future use
const getColorForCost = (cost: number): string => {
    return '#00ff00'; // Always green
};

export const TokenUsageDisplay: React.FC = () => {
    const [data, setData] = useState<TokenUsageData | null>(null);
    const [showDollars, setShowDollars] = useState(false);
    const [loading, setLoading] = useState(true);
    const [isHovered, setIsHovered] = useState(false);
    const [isPageVisible, setIsPageVisible] = useState(true);
    const navigate = useNavigate();

    const handleDoubleClick = useCallback(() => {
        navigate('/account', { state: { scrollToTokenUsage: true } });
    }, [navigate]);

    const fetchTokenUsage = useCallback(async () => {
        // Skip fetch when page is hidden to save resources
        if (!isPageVisible) return;
        
        try {
            const response = await ipcApi.getMonthlyTokenUsage<TokenUsageData>();
            if (response.success && response.data) {
                setData(response.data);
                logger.debug('[TokenUsageDisplay] Fetched token usage:', response.data);
            } else {
                logger.error('[TokenUsageDisplay] Failed to fetch token usage:', response.error);
            }
        } catch (error) {
            logger.error('[TokenUsageDisplay] Error fetching token usage:', error);
        } finally {
            setLoading(false);
        }
    }, [isPageVisible]);

    // Page visibility handler - pause animations and fetches when hidden
    useEffect(() => {
        const handleVisibilityChange = () => {
            const visible = !document.hidden;
            setIsPageVisible(visible);
        };
        
        document.addEventListener('visibilitychange', handleVisibilityChange);
        return () => document.removeEventListener('visibilitychange', handleVisibilityChange);
    }, []);

    // Initial fetch
    useEffect(() => {
        fetchTokenUsage();
    }, [fetchTokenUsage]);

    // Auto-refresh every 5 minutes (token usage doesn't change rapidly)
    useEffect(() => {
        const interval = setInterval(() => {
            fetchTokenUsage();
        }, 5 * 60 * 1000); // 5 minutes

        return () => clearInterval(interval);
    }, [fetchTokenUsage]);

    if (loading || !data) {
        return (
            <Container>
                <LEDDisplay color="#666666">
                    <LEDRow>
                        <LEDLabel>---</LEDLabel>
                        <LEDValue>Loading...</LEDValue>
                    </LEDRow>
                </LEDDisplay>
            </Container>
        );
    }

    const color = getColorForCost(data.cost_usd);

    return (
        <Container
            onDoubleClick={handleDoubleClick}
            title="Double-click to view detailed token usage"
            onMouseEnter={() => setIsHovered(true)}
            onMouseLeave={() => setIsHovered(false)}
        >
            <LEDDisplay color={color} isHovered={isHovered && isPageVisible}>
                {showDollars ? (
                    <>
                        <LEDRow>
                            <LEDLabel>IN</LEDLabel>
                            <LEDValue>{formatCurrency((data.input_tokens / 1000) * 0.01)}</LEDValue>
                        </LEDRow>
                        <LEDRow>
                            <LEDLabel>OUT</LEDLabel>
                            <LEDValue>{formatCurrency((data.output_tokens / 1000) * 0.02)}</LEDValue>
                        </LEDRow>
                        <LEDRow>
                            <LEDLabel>TOT</LEDLabel>
                            <LEDValue>{formatCurrency(data.cost_usd)}</LEDValue>
                        </LEDRow>
                    </>
                ) : (
                    <>
                        <LEDRow>
                            <LEDLabel>IN</LEDLabel>
                            <LEDValue>{formatNumber(data.input_tokens)}</LEDValue>
                        </LEDRow>
                        <LEDRow>
                            <LEDLabel>OUT</LEDLabel>
                            <LEDValue>{formatNumber(data.output_tokens)}</LEDValue>
                        </LEDRow>
                        <LEDRow>
                            <LEDLabel>TOT</LEDLabel>
                            <LEDValue>{formatNumber(data.total_tokens)}</LEDValue>
                        </LEDRow>
                    </>
                )}
            </LEDDisplay>
            <ToggleIcon onClick={() => setShowDollars(!showDollars)}>
                {showDollars ? <DollarOutlined /> : <TokenIcon />}
            </ToggleIcon>
        </Container>
    );
};

export default TokenUsageDisplay;
