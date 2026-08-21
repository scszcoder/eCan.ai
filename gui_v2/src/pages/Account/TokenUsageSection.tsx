import React, { useState, useEffect, useCallback, useRef } from 'react';
import { Card, Select, Button, Progress, InputNumber, Space, Typography, Spin, message, Collapse, Row, Col, Statistic } from 'antd';
import { DownloadOutlined, SettingOutlined, ReloadOutlined } from '@ant-design/icons';
import { Column, Pie } from '@ant-design/plots';
import styled from '@emotion/styled';
import { useLocation } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { ipcApi } from '../../services/ipc/api';

const { Title, Text } = Typography;

// ─── Types ──────────────────────────────────────────────────────────────────

interface TimeSeriesPoint {
    period: string;
    input_tokens: number;
    output_tokens: number;
    total_tokens: number;
    cost_usd: number;
    invocation_count: number;
}

interface BreakdownModel {
    vendor: string;
    model: string;
    input_tokens: number;
    output_tokens: number;
    total_tokens: number;
    cost_usd: number;
    count: number;
}

interface BreakdownSkill {
    skill_name: string;
    input_tokens: number;
    output_tokens: number;
    total_tokens: number;
    cost_usd: number;
    count: number;
}

interface BreakdownData {
    by_model: BreakdownModel[];
    by_skill: BreakdownSkill[];
    total_invocations: number;
}

interface AlarmData {
    daily: { input_tokens: number; output_tokens: number; total_tokens: number; cost_usd: number };
    monthly: { input_tokens: number; output_tokens: number; total_tokens: number; cost_usd: number; month: number; year: number };
    alarm_levels: { daily_token_limit: number; monthly_token_limit: number };
}

type PeriodKey = '24h' | '3d' | '1w' | '1m' | '12m' | '36m';

// ─── Styled Components ──────────────────────────────────────────────────────

const SectionWrapper = styled.div`
    margin-top: 24px;
`;

const ChartCard = styled(Card)`
    background: rgba(30, 41, 59, 0.6) !important;
    border: 1px solid rgba(255, 255, 255, 0.08) !important;
    border-radius: 12px !important;
    
    .ant-card-body {
        padding: 20px;
    }
`;

const CardTitle = styled.div`
    font-size: 15px;
    font-weight: 600;
    color: #e2e8f0;
    margin-bottom: 16px;
    display: flex;
    align-items: center;
    gap: 8px;
`;

const ChartHeader = styled.div`
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 16px;
    flex-wrap: wrap;
    gap: 12px;
`;

const StatsRow = styled(Row)`
    margin-bottom: 20px;
`;

const StatCard = styled(Col)`
    .ant-statistic-title {
        color: rgba(148, 163, 184, 0.8) !important;
        font-size: 12px;
        text-transform: uppercase;
        letter-spacing: 0.5px;
    }
    
    .ant-statistic-content {
        color: #e2e8f0 !important;
    }
    
    .ant-statistic-content-value {
        font-family: 'SF Mono', 'Fira Code', monospace;
        font-weight: 600;
    }
    
    .ant-statistic-content-suffix {
        font-size: 14px;
        color: rgba(148, 163, 184, 0.6);
    }
`;

const PieRow = styled.div`
    display: flex;
    gap: 24px;
    flex-wrap: wrap;

    > div {
        flex: 1;
        min-width: 300px;
    }
`;

const AlarmCard = styled(Card)`
    background: rgba(30, 41, 59, 0.6) !important;
    border: 1px solid rgba(255, 255, 255, 0.08) !important;
    border-radius: 12px !important;
    
    .ant-card-body {
        padding: 20px;
    }
`;

const AlarmRow = styled.div`
    display: flex;
    gap: 32px;
    flex-wrap: wrap;

    > div {
        flex: 1;
        min-width: 280px;
    }
`;

const AlarmItem = styled.div`
    margin-bottom: 16px;
`;

const AlarmLabel = styled.div`
    font-size: 13px;
    font-weight: 500;
    color: #e2e8f0;
    margin-bottom: 8px;
`;

const ProgressWrapper = styled.div`
    margin-bottom: 4px;
`;

const AlarmMeta = styled.div`
    font-size: 12px;
    color: rgba(148, 163, 184, 0.6);
    display: flex;
    justify-content: space-between;
`;

const SettingsRow = styled.div`
    margin-top: 16px;
    display: flex;
    gap: 16px;
    align-items: center;
    flex-wrap: wrap;
`;

const InlineButton = styled(Button)`
    display: flex;
    align-items: center;
    gap: 6px;
`;

const EmptyState = styled.div`
    text-align: center;
    padding: 60px 20px;
    color: rgba(148, 163, 184, 0.6);
`;

// ─── Helpers ────────────────────────────────────────────────────────────────

function formatTokenCount(n: number): string {
    if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
    if (n >= 1_000) return `${(n / 1_000).toFixed(1)}K`;
    return String(n);
}

function formatCurrency(n: number): string {
    if (n < 0.01) return '$0.00';
    if (n < 1) return `$${n.toFixed(3)}`;
    return `$${n.toFixed(2)}`;
}

function seriesToCSV(series: TimeSeriesPoint[]): string {
    const header = 'Period,Input Tokens,Output Tokens,Total Tokens,Cost USD,Invocations';
    const rows = series.map(p =>
        `${p.period},${p.input_tokens},${p.output_tokens},${p.total_tokens},${p.cost_usd.toFixed(4)},${p.invocation_count}`
    );
    return [header, ...rows].join('\n');
}

function downloadCSV(content: string, filename: string): void {
    const blob = new Blob([content], { type: 'text/csv;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    a.click();
    URL.revokeObjectURL(url);
}

// ─── Component ──────────────────────────────────────────────────────────────

const TokenUsageSection: React.FC = () => {
    const { t } = useTranslation();

    // === State ===
    const [period, setPeriod] = useState<PeriodKey>('1m');
    const [series, setSeries] = useState<TimeSeriesPoint[]>([]);
    const [granularity, setGranularity] = useState<string>('day');
    const [loadingSeries, setLoadingSeries] = useState(false);

    const [breakdown, setBreakdown] = useState<BreakdownData | null>(null);
    const [loadingBreakdown, setLoadingBreakdown] = useState(false);
    const [pieLabel, setPieLabel] = useState<string>('');

    const [alarmData, setAlarmData] = useState<AlarmData | null>(null);
    const [loadingAlarms, setLoadingAlarms] = useState(false);
    const [editingAlarm, setEditingAlarm] = useState(false);
    const [editDailyLimit, setEditDailyLimit] = useState<number>(500000);
    const [editMonthlyLimit, setEditMonthlyLimit] = useState<number>(10000000);

    const sectionRef = useRef<HTMLDivElement>(null);
    const location = useLocation();

    // === Fetches ===
    const fetchTimeSeries = useCallback(async (p: PeriodKey) => {
        setLoadingSeries(true);
        try {
            const res = await ipcApi.getTokenUsageTimeSeries<{ series: TimeSeriesPoint[]; granularity: string }>(p);
            if (res.success && res.data) {
                setSeries(res.data.series);
                setGranularity(res.data.granularity);
            }
        } catch (e) {
            console.error('[TokenUsageSection] fetchTimeSeries error:', e);
        } finally {
            setLoadingSeries(false);
        }
    }, []);

    const fetchBreakdown = useCallback(async (start?: string, end?: string, label?: string) => {
        setLoadingBreakdown(true);
        try {
            const res = await ipcApi.getTokenUsageBreakdown<BreakdownData>(start, end);
            if (res.success && res.data) {
                setBreakdown(res.data);
                if (label) setPieLabel(label);
            }
        } catch (e) {
            console.error('[TokenUsageSection] fetchBreakdown error:', e);
        } finally {
            setLoadingBreakdown(false);
        }
    }, []);

    const fetchAlarms = useCallback(async () => {
        setLoadingAlarms(true);
        try {
            const res = await ipcApi.getTokenUsageAlarms<AlarmData>();
            if (res.success && res.data) {
                setAlarmData(res.data);
                setEditDailyLimit(res.data.alarm_levels.daily_token_limit);
                setEditMonthlyLimit(res.data.alarm_levels.monthly_token_limit);
            }
        } catch (e) {
            console.error('[TokenUsageSection] fetchAlarms error:', e);
        } finally {
            setLoadingAlarms(false);
        }
    }, []);

    // === Initial loads ===
    useEffect(() => {
        fetchTimeSeries('1m');
        fetchBreakdown(undefined, undefined, 'Last 24 hours');
        fetchAlarms();
    }, [fetchTimeSeries, fetchBreakdown, fetchAlarms]);

    // === Scroll into view ===
    useEffect(() => {
        const state = location.state as { scrollToTokenUsage?: boolean } | null;
        if (state?.scrollToTokenUsage && sectionRef.current) {
            setTimeout(() => {
                sectionRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' });
            }, 300);
        }
    }, [location.state]);

    // === Handlers ===
    const handlePeriodChange = (value: PeriodKey) => {
        setPeriod(value);
        fetchTimeSeries(value);
    };

    const handleDownloadCSV = () => {
        if (!series.length) return;
        const csv = seriesToCSV(series);
        downloadCSV(csv, `token_usage_${period}_${new Date().toISOString().slice(0, 10)}.csv`);
    };

    const handleRefresh = () => {
        fetchTimeSeries(period);
        fetchBreakdown(undefined, undefined, 'Last 24 hours');
        fetchAlarms();
        message.success(t('common.refresh_success', 'Data refreshed successfully'));
    };

    const handleBarClick = useCallback((periodStr: string) => {
        let start: Date;
        let end: Date;
        let label: string;

        if (granularity === 'hour') {
            start = new Date(periodStr.replace(' ', 'T') + ':00');
            end = new Date(start.getTime() + 3600000);
            label = periodStr;
        } else if (granularity === 'day') {
            start = new Date(periodStr + 'T00:00:00');
            end = new Date(start.getTime() + 86400000);
            label = periodStr;
        } else {
            const [y, m] = periodStr.split('-').map(Number);
            start = new Date(y, m - 1, 1);
            end = new Date(y, m, 1);
            label = periodStr;
        }

        fetchBreakdown(start.toISOString(), end.toISOString(), label);
    }, [granularity, fetchBreakdown]);

    const handleSaveAlarm = async () => {
        try {
            const res = await ipcApi.setTokenAlarmLevels<any>(editDailyLimit, editMonthlyLimit);
            if (res.success) {
                message.success(t('common.saveSuccess', 'Saved successfully'));
                setEditingAlarm(false);
                fetchAlarms();
            } else {
                message.error(res.error?.message || t('common.saveFailed', 'Failed to save'));
            }
        } catch (e) {
            message.error(t('common.saveFailed', 'Failed to save'));
        }
    };

    // === Stats ===
    const totalTokens = series.reduce((sum, p) => sum + p.total_tokens, 0);
    const totalCost = series.reduce((sum, p) => sum + p.cost_usd, 0);
    const totalInvocations = series.reduce((sum, p) => sum + p.invocation_count, 0);

    // === Chart Data ===
    const barData = series.flatMap(p => [
        { period: p.period, type: t('tokenUsage.inputTokens', 'Input'), tokens: p.input_tokens },
        { period: p.period, type: t('tokenUsage.outputTokens', 'Output'), tokens: p.output_tokens },
    ]);

    const barConfig = {
        data: barData,
        xField: 'period',
        yField: 'tokens',
        colorField: 'type',
        stack: true,
        color: ['#3b82f6', '#22c55e'],
        legend: {
            position: 'top-right' as const,
            itemLabelFill: '#e2e8f0',
        },
        theme: { type: 'dark' as const },
        axis: {
            x: {
                labelFill: '#94a3b8',
                label: {
                    autoRotate: true,
                    autoHide: true,
                    formatter: (v: string) => {
                        if (granularity === 'hour') return v.slice(11, 16);
                        if (granularity === 'day') return v.slice(5);
                        return v;
                    },
                },
            },
            y: {
                labelFill: '#94a3b8',
                label: {
                    formatter: (v: string) => formatTokenCount(Number(v)),
                },
            },
        },
        tooltip: {
            items: [
                (d: any) => ({
                    name: d.type,
                    value: `${Number(d.tokens).toLocaleString()} ${t('tokenUsage.tokens', 'tokens')}`,
                }),
            ],
        },
        interaction: { elementHighlight: true },
        onReady: (params: { chart: any }) => {
            const { chart } = params;
            chart.on('element:dblclick', (evt: any) => {
                const data = evt?.data?.data;
                if (data?.period) {
                    handleBarClick(data.period);
                }
            });
        },
    };

    // === Pie Data ===
    const modelPieData = (breakdown?.by_model || []).map(m => ({
        type: `${m.vendor}/${m.model}`,
        value: m.total_tokens,
    }));

    const skillPieData = (breakdown?.by_skill || []).map(s => ({
        type: s.skill_name,
        value: s.total_tokens,
    }));

    const pieConfig = (data: { type: string; value: number }[], title: string) => ({
        data,
        angleField: 'value',
        colorField: 'type',
        radius: 0.8,
        innerRadius: 0.55,
        theme: { type: 'dark' as const },
        label: {
            text: (d: any) => `${d.type}`,
            fill: '#e2e8f0',
            fontSize: 11,
        },
        legend: {
            position: 'bottom' as const,
            itemLabelFill: '#e2e8f0',
        },
        tooltip: {
            items: [
                (d: any) => ({
                    name: d.type,
                    value: `${Number(d.value).toLocaleString()} ${t('tokenUsage.tokens', 'tokens')}`,
                }),
            ],
        },
        annotations: [
            {
                type: 'text' as const,
                style: {
                    text: title,
                    x: '50%',
                    y: '50%',
                    textAlign: 'center' as const,
                    fontSize: 12,
                    fill: '#94a3b8',
                },
            },
        ],
    });

    // === Alarm Progress ===
    const dailyPercent = alarmData
        ? Math.min(100, Math.round((alarmData.daily.total_tokens / alarmData.alarm_levels.daily_token_limit) * 100))
        : 0;
    const monthlyPercent = alarmData
        ? Math.min(100, Math.round((alarmData.monthly.total_tokens / alarmData.alarm_levels.monthly_token_limit) * 100))
        : 0;

    const alarmColor = (percent: number) => (percent >= 100 ? '#ef4444' : percent >= 80 ? '#f59e0b' : '#22c55e');

    // === Period Options ===
    const PERIOD_OPTIONS = [
        { value: '24h', label: t('tokenUsage.period24h', 'Last 24 Hours') },
        { value: '3d', label: t('tokenUsage.period3d', 'Last 3 Days') },
        { value: '1w', label: t('tokenUsage.period1w', 'Last 1 Week') },
        { value: '1m', label: t('tokenUsage.period1m', 'Last 1 Month') },
        { value: '12m', label: t('tokenUsage.period12m', 'Last 12 Months') },
        { value: '36m', label: t('tokenUsage.period36m', 'Last 36 Months') },
    ];

    // ─── Render ─────────────────────────────────────────────────────────────

    return (
        <SectionWrapper ref={sectionRef} id="token-usage-section">
            <Collapse
                defaultActiveKey={['token-usage']}
                ghost
                items={[{
                    key: 'token-usage',
                    label: (
                        <Title level={4} style={{ margin: 0, color: '#e2e8f0' }}>
                            {t('tokenUsage.analytics', 'Token Usage Analytics')}
                        </Title>
                    ),
                    children: (
                        <Space direction="vertical" size={20} style={{ width: '100%' }}>
                            {/* ── Stats Cards ── */}
                            <StatsRow gutter={16}>
                                <StatCard span={6}>
                                    <Statistic
                                        title={t('tokenUsage.totalTokens', 'Total Tokens')}
                                        value={totalTokens}
                                        formatter={(val) => formatTokenCount(Number(val))}
                                        valueStyle={{ color: '#e2e8f0', fontFamily: "'SF Mono', 'Fira Code', monospace" }}
                                    />
                                </StatCard>
                                <StatCard span={6}>
                                    <Statistic
                                        title={t('tokenUsage.estimatedCost', 'Est. Cost')}
                                        value={totalCost}
                                        formatter={(val) => formatCurrency(Number(val))}
                                        valueStyle={{ color: '#22c55e', fontFamily: "'SF Mono', 'Fira Code', monospace" }}
                                    />
                                </StatCard>
                                <StatCard span={6}>
                                    <Statistic
                                        title={t('tokenUsage.invocations', 'LLM Calls')}
                                        value={totalInvocations}
                                        valueStyle={{ color: '#e2e8f0', fontFamily: "'SF Mono', 'Fira Code', monospace" }}
                                    />
                                </StatCard>
                                <StatCard span={6}>
                                    <Statistic
                                        title={t('tokenUsage.inputOutput', 'Input / Output')}
                                        value={`${formatTokenCount(series.reduce((s, p) => s + p.input_tokens, 0))} / ${formatTokenCount(series.reduce((s, p) => s + p.output_tokens, 0))}`}
                                        valueStyle={{ color: '#94a3b8', fontSize: 16 }}
                                    />
                                </StatCard>
                            </StatsRow>

                            {/* ── Time Series Chart ── */}
                            <ChartCard>
                                <ChartHeader>
                                    <CardTitle>
                                        {t('tokenUsage.overTime', 'Usage Over Time')}
                                    </CardTitle>
                                    <Space>
                                        <Select
                                            value={period}
                                            onChange={handlePeriodChange}
                                            style={{ width: 160 }}
                                            options={PERIOD_OPTIONS}
                                        />
                                        <InlineButton
                                            icon={<ReloadOutlined />}
                                            onClick={handleRefresh}
                                            loading={loadingSeries}
                                        >
                                            {t('common.refresh', 'Refresh')}
                                        </InlineButton>
                                        <Button
                                            icon={<DownloadOutlined />}
                                            onClick={handleDownloadCSV}
                                            disabled={!series.length}
                                        >
                                            {t('common.export', 'Export')}
                                        </Button>
                                    </Space>
                                </ChartHeader>
                                {loadingSeries ? (
                                    <div style={{ textAlign: 'center', padding: 60 }}><Spin size="large" /></div>
                                ) : series.length > 0 ? (
                                    <>
                                        <Column {...barConfig} height={280} />
                                        <Text type="secondary" style={{ display: 'block', marginTop: 12, textAlign: 'center', fontSize: 12 }}>
                                            {t('tokenUsage.doubleClickToBreakdown', 'Double-click bars to see detailed breakdown')}
                                        </Text>
                                    </>
                                ) : (
                                    <EmptyState>{t('tokenUsage.noData', 'No data available')}</EmptyState>
                                )}
                            </ChartCard>

                            {/* ── Breakdown Pie Charts ── */}
                            <ChartCard>
                                <ChartHeader>
                                    <CardTitle>
                                        {t('tokenUsage.breakdown', 'Token Breakdown')} — {pieLabel}
                                    </CardTitle>
                                </ChartHeader>
                                {loadingBreakdown ? (
                                    <div style={{ textAlign: 'center', padding: 60 }}><Spin size="large" /></div>
                                ) : breakdown ? (
                                    <>
                                        <PieRow>
                                            <div>
                                                <Text strong style={{ display: 'block', marginBottom: 12, color: '#e2e8f0' }}>
                                                    {t('tokenUsage.byModel', 'By Model')}
                                                </Text>
                                                {modelPieData.length > 0 ? (
                                                    <Pie {...pieConfig(modelPieData, t('tokenUsage.model', 'Model'))} height={260} />
                                                ) : (
                                                    <EmptyState>{t('tokenUsage.noModelData', 'No model data')}</EmptyState>
                                                )}
                                            </div>
                                            <div>
                                                <Text strong style={{ display: 'block', marginBottom: 12, color: '#e2e8f0' }}>
                                                    {t('tokenUsage.bySkill', 'By Skill')}
                                                </Text>
                                                {skillPieData.length > 0 ? (
                                                    <Pie {...pieConfig(skillPieData, t('tokenUsage.skill', 'Skill'))} height={260} />
                                                ) : (
                                                    <EmptyState>{t('tokenUsage.noSkillData', 'No skill data')}</EmptyState>
                                                )}
                                            </div>
                                        </PieRow>
                                        <div style={{ marginTop: 16, textAlign: 'center' }}>
                                            <Text style={{ color: '#e2e8f0', fontSize: 13 }}>
                                                {t('tokenUsage.totalLLMInvocations', 'Total LLM Invocations')}: {breakdown.total_invocations.toLocaleString()}
                                            </Text>
                                        </div>
                                    </>
                                ) : (
                                    <EmptyState>{t('tokenUsage.noBreakdownData', 'No breakdown data')}</EmptyState>
                                )}
                            </ChartCard>

                            {/* ── Usage Alerts ── */}
                            <AlarmCard>
                                <CardTitle>
                                    {t('tokenUsage.usageAlerts', 'Usage Alerts')}
                                </CardTitle>
                                {loadingAlarms ? (
                                    <div style={{ textAlign: 'center', padding: 40 }}><Spin /></div>
                                ) : alarmData ? (
                                    <>
                                        <AlarmRow>
                                            <div>
                                                <AlarmItem>
                                                    <AlarmLabel>{t('tokenUsage.dailyUsage', 'Daily Usage')}</AlarmLabel>
                                                    <ProgressWrapper>
                                                        <Progress
                                                            percent={dailyPercent}
                                                            strokeColor={alarmColor(dailyPercent)}
                                                            trailColor="rgba(255,255,255,0.1)"
                                                            format={() => `${formatTokenCount(alarmData.daily.total_tokens)} / ${formatTokenCount(alarmData.alarm_levels.daily_token_limit)}`}
                                                        />
                                                    </ProgressWrapper>
                                                    <AlarmMeta>
                                                        <span>{t('tokenUsage.costToday', 'Cost today')}</span>
                                                        <span style={{ color: '#22c55e' }}>{formatCurrency(alarmData.daily.cost_usd)}</span>
                                                    </AlarmMeta>
                                                </AlarmItem>
                                            </div>
                                            <div>
                                                <AlarmItem>
                                                    <AlarmLabel>{t('tokenUsage.monthlyUsageTitle', 'Monthly Usage')}</AlarmLabel>
                                                    <ProgressWrapper>
                                                        <Progress
                                                            percent={monthlyPercent}
                                                            strokeColor={alarmColor(monthlyPercent)}
                                                            trailColor="rgba(255,255,255,0.1)"
                                                            format={() => `${formatTokenCount(alarmData.monthly.total_tokens)} / ${formatTokenCount(alarmData.alarm_levels.monthly_token_limit)}`}
                                                        />
                                                    </ProgressWrapper>
                                                    <AlarmMeta>
                                                        <span>{t('tokenUsage.costThisMonth', 'Cost this month')}</span>
                                                        <span style={{ color: '#22c55e' }}>{formatCurrency(alarmData.monthly.cost_usd)}</span>
                                                    </AlarmMeta>
                                                </AlarmItem>
                                            </div>
                                        </AlarmRow>
                                        <SettingsRow>
                                            {editingAlarm ? (
                                                <>
                                                    <Space>
                                                        <Text style={{ color: '#e2e8f0' }}>{t('tokenUsage.dailyLimit', 'Daily')}:</Text>
                                                        <InputNumber
                                                            value={editDailyLimit}
                                                            onChange={v => v !== null && setEditDailyLimit(v)}
                                                            min={0}
                                                            step={100000}
                                                            formatter={v => `${v}`.replace(/\B(?=(\d{3})+(?!\d))/g, ',')}
                                                            style={{ width: 140, background: 'rgba(30, 41, 59, 0.8)', borderColor: 'rgba(255,255,255,0.1)' }}
                                                        />
                                                    </Space>
                                                    <Space>
                                                        <Text style={{ color: '#e2e8f0' }}>{t('tokenUsage.monthlyLimit', 'Monthly')}:</Text>
                                                        <InputNumber
                                                            value={editMonthlyLimit}
                                                            onChange={v => v !== null && setEditMonthlyLimit(v)}
                                                            min={0}
                                                            step={1000000}
                                                            formatter={v => `${v}`.replace(/\B(?=(\d{3})+(?!\d))/g, ',')}
                                                            style={{ width: 140, background: 'rgba(30, 41, 59, 0.8)', borderColor: 'rgba(255,255,255,0.1)' }}
                                                        />
                                                    </Space>
                                                    <Button type="primary" onClick={handleSaveAlarm}>{t('common.save', 'Save')}</Button>
                                                    <Button onClick={() => setEditingAlarm(false)}>{t('common.cancel', 'Cancel')}</Button>
                                                </>
                                            ) : (
                                                <Button
                                                    icon={<SettingOutlined />}
                                                    onClick={() => setEditingAlarm(true)}
                                                >
                                                    {t('tokenUsage.setAlarmLevels', 'Set Alarm Levels')}
                                                </Button>
                                            )}
                                        </SettingsRow>
                                    </>
                                ) : (
                                    <EmptyState>{t('tokenUsage.unableToLoadAlarms', 'Unable to load alarm data')}</EmptyState>
                                )}
                            </AlarmCard>
                        </Space>
                    ),
                }]}
            />
        </SectionWrapper>
    );
};

export default TokenUsageSection;
