import React, { useEffect, useState, useCallback } from 'react';
import styled from '@emotion/styled';
import { useTranslation } from 'react-i18next';
import { useNavigate } from 'react-router-dom';
import { ipcApi } from '../../services/ipc/api';
import { logger } from '../../utils/logger';

// ─── Types ──────────────────────────────────────────────────────────────────

export interface TokenUsageData {
  input_tokens: number;
  output_tokens: number;
  total_tokens: number;
  cost_usd: number;
  /** Cost in the app variant's display currency (CN builds: RMB). */
  cost?: number;
  currency?: 'CNY' | 'USD';
}

// ─── Constants ────────────────────────────────────────────────────────────────

const MONTHLY_TOKEN_LIMIT = 10_000_000;
// Cost is computed and stored server-side (token_tracker at ingest); this
// component only displays what the backend returns — it never recomputes cost.
const CACHE_KEY = 'ecan.tokenUsage.month.v1';

// ─── Helper Functions ────────────────────────────────────────────────────────

const formatNumber = (num: number): string => {
  if (num >= 1_000_000) return `${(num / 1_000_000).toFixed(1)}M`;
  if (num >= 1_000) return `${(num / 1_000).toFixed(1)}K`;
  return num.toLocaleString();
};

const formatCurrency = (num: number, currency: 'CNY' | 'USD' = 'USD'): string => {
  const symbol = currency === 'CNY' ? '¥' : '$';
  if (num < 0.01) return `${symbol}0`;
  return `${symbol}${num.toFixed(2)}`;
};

const getUsageLevel = (percentage: number): 'safe' | 'warning' | 'danger' => {
  if (percentage < 50) return 'safe';
  if (percentage < 80) return 'warning';
  return 'danger';
};

const getUsageColor = (level: 'safe' | 'warning' | 'danger'): string => {
  switch (level) {
    case 'safe': return '#22c55e';
    case 'warning': return '#f59e0b';
    case 'danger': return '#ef4444';
  }
};

// ─── Styled Components ────────────────────────────────────────────────────────

const Wrapper = styled.div`
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 4px 10px;
  cursor: pointer;
  border-radius: 16px;
  transition: all 0.25s cubic-bezier(0.4, 0, 0.2, 1);
  height: 28px;
  background: transparent;
  position: relative;

  &:hover {
    background: rgba(148, 163, 184, 0.08);
  }
`;

const RingContainer = styled.div`
  position: relative;
  width: 20px;
  height: 20px;
  flex-shrink: 0;
`;

const RingSvg = styled.svg`
  position: absolute;
  top: 0;
  left: 0;
  width: 100%;
  height: 100%;
  transform: rotate(-90deg);
`;

const RingBg = styled.circle`
  fill: none;
  stroke: rgba(255, 255, 255, 0.1);
  stroke-width: 2;
`;

const RingFg = styled.circle<{ $level: 'safe' | 'warning' | 'danger' }>`
  fill: none;
  stroke: ${props => getUsageColor(props.$level)};
  stroke-width: 2;
  stroke-linecap: round;
  transition: stroke-dashoffset 0.8s cubic-bezier(0.4, 0, 0.2, 1), stroke 0.3s ease;
`;

const RingCenter = styled.div`
  position: absolute;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
  display: flex;
  align-items: center;
  justify-content: center;
`;

const RingDot = styled.div<{ $level: 'safe' | 'warning' | 'danger' }>`
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: ${props => getUsageColor(props.$level)};
`;

const Content = styled.div`
  display: flex;
  align-items: center;
  gap: 8px;
  line-height: 1;
`;

// Two stacked rows: input tokens on top, output tokens below (MTD).
const TokenColumn = styled.div`
  display: flex;
  flex-direction: column;
  justify-content: center;
  gap: 2px;
`;

const TokenRow = styled.span<{ $level: 'safe' | 'warning' | 'danger' }>`
  font-size: 10px;
  font-weight: 600;
  font-family: 'SF Mono', 'Fira Code', monospace;
  color: ${props => getUsageColor(props.$level)};
  letter-spacing: -0.02em;
  line-height: 1.1;
  white-space: nowrap;
`;

const RowLabel = styled.span`
  display: inline-block;
  width: 10px;
  color: rgba(148, 163, 184, 0.55);
  font-weight: 500;
`;

const CostValue = styled.span`
  font-size: 12px;
  font-weight: 500;
  font-family: 'SF Mono', 'Fira Code', monospace;
  color: rgba(148, 163, 184, 0.6);
  white-space: nowrap;
`;

const LoadingWrapper = styled.div`
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 4px 8px;
  height: 28px;
`;

const LoadingDot = styled.div`
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: #60a5fa;
  animation: pulse 1.5s infinite;

  @keyframes pulse {
    0%, 100% { opacity: 0.3; }
    50% { opacity: 1; }
  }
`;

// ─── Main Component ──────────────────────────────────────────────────────────

export const TokenUsageDisplay: React.FC = () => {
  const { i18n } = useTranslation();
  const navigate = useNavigate();
  const [data, setData] = useState<TokenUsageData | null>(null);
  const [loading, setLoading] = useState(true);

  const fetchTokenUsage = useCallback(async () => {
    try {
      const response = await ipcApi.getMonthlyTokenUsage<TokenUsageData>();
      if (response.success && response.data) {
        setData(response.data);
        logger.debug('[TokenUsageDisplay] Fetched:', response.data);
        // Persist the last networked reading so the pill isn't blank on next
        // launch or while offline.
        try { localStorage.setItem(CACHE_KEY, JSON.stringify(response.data)); } catch { /* storage may be unavailable */ }
      }
    } catch (error) {
      logger.error('[TokenUsageDisplay] Error:', error);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    // Seed from the last saved reading immediately, then refresh from backend.
    try {
      const raw = localStorage.getItem(CACHE_KEY);
      if (raw) setData(JSON.parse(raw));
    } catch { /* ignore */ }
    fetchTokenUsage();
    const interval = setInterval(fetchTokenUsage, 5 * 60 * 1000);
    return () => clearInterval(interval);
  }, [fetchTokenUsage]);

  const handleClick = () => {
    navigate('/account', { state: { scrollToTokenUsage: true } });
  };

  const language = i18n.language;
  const isCN = language === 'zh-CN';

  const inputTokens = data?.input_tokens ?? 0;
  const outputTokens = data?.output_tokens ?? 0;
  const totalTokens = data?.total_tokens ?? inputTokens + outputTokens;
  const currency = data?.currency ?? 'USD';
  const totalCost = data?.cost ?? data?.cost_usd ?? 0;

  const usagePercentage = (totalTokens / MONTHLY_TOKEN_LIMIT) * 100;
  const usageLevel = getUsageLevel(usagePercentage);

  // Ring calculations
  const radius = 9;
  const circumference = 2 * Math.PI * radius;
  const progressOffset = circumference - (circumference * Math.min(usagePercentage, 100)) / 100;

  const titleHint = isCN
    ? `本月至今：输入 ${inputTokens.toLocaleString()} / 输出 ${outputTokens.toLocaleString()} 词元，费用 ${formatCurrency(totalCost, currency)}。点击查看详情`
    : `Month to date: ${inputTokens.toLocaleString()} in / ${outputTokens.toLocaleString()} out tokens, ${formatCurrency(totalCost, currency)}. Click for details`;

  if (loading) {
    return (
      <LoadingWrapper>
        <LoadingDot />
      </LoadingWrapper>
    );
  }

  return (
    <Wrapper onClick={handleClick} title={titleHint}>
      {/* Compact Ring Indicator */}
      <RingContainer>
        <RingSvg viewBox={`0 0 ${radius * 2} ${radius * 2}`}>
          <RingBg cx={radius} cy={radius} r={radius - 1} />
          <RingFg
            cx={radius}
            cy={radius}
            r={radius - 1}
            $level={usageLevel}
            style={{
              strokeDasharray: circumference,
              strokeDashoffset: progressOffset,
            }}
          />
        </RingSvg>
        <RingCenter>
          <RingDot $level={usageLevel} />
        </RingCenter>
      </RingContainer>

      {/* Month-to-date stats: input / output token lines + fee */}
      <Content>
        <TokenColumn>
          <TokenRow $level={usageLevel}>
            <RowLabel>↑</RowLabel>
            {formatNumber(inputTokens)}
          </TokenRow>
          <TokenRow $level={usageLevel}>
            <RowLabel>↓</RowLabel>
            {formatNumber(outputTokens)}
          </TokenRow>
        </TokenColumn>
        <CostValue>{formatCurrency(totalCost, currency)}</CostValue>
      </Content>
    </Wrapper>
  );
};

// ─── Compact Badge ──────────────────────────────────────────────────────────

export const TokenUsageBadge: React.FC<{ tokens?: number; cost?: number }> = ({ tokens, cost }) => {
  const { i18n } = useTranslation();
  const isCN = i18n.language === 'zh-CN';
  const displayValue = cost !== undefined
    ? formatCurrency(cost)
    : tokens !== undefined
      ? formatNumber(tokens)
      : '—';
  const label = isCN ? '词元' : 'Tokens';

  return (
    <span style={{
      display: 'inline-block',
      padding: '2px 8px',
      background: 'rgba(34, 197, 94, 0.15)',
      border: '1px solid rgba(34, 197, 94, 0.25)',
      borderRadius: '4px',
      fontSize: '12px',
      fontWeight: 600,
      color: '#22c55e',
      fontFamily: "'SF Mono', 'Fira Code', monospace"
    }}>
      {label}: {displayValue}
    </span>
  );
};

export default TokenUsageDisplay;
