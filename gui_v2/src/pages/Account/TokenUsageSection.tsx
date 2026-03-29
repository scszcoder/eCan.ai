import React, { useState, useEffect, useCallback, useRef } from 'react';
import { Card, Select, Button, Progress, InputNumber, Space, Typography, Spin, message, Collapse } from 'antd';
import { DownloadOutlined, SettingOutlined } from '@ant-design/icons';
import { Column, Pie } from '@ant-design/plots';
import styled from '@emotion/styled';
import { useLocation } from 'react-router-dom';
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

const PERIOD_OPTIONS: { value: PeriodKey; label: string }[] = [
    { value: '24h', label: 'Last 24 Hours (hourly)' },
    { value: '3d', label: 'Last 3 Days (hourly)' },
    { value: '1w', label: 'Last 1 Week (daily)' },
    { value: '1m', label: 'Last 1 Month (daily)' },
    { value: '12m', label: 'Last 12 Months (monthly)' },
    { value: '36m', label: 'Last 36 Months (monthly)' },
];

// ─── Styled Components ──────────────────────────────────────────────────────

const SectionWrapper = styled.div`
    margin-top: 24px;
`;

const ChartHeader = styled.div`
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 16px;
    flex-wrap: wrap;
    gap: 8px;
`;

const PieRow = styled.div`
    display: flex;
    gap: 24px;
    flex-wrap: wrap;

    > div {
        flex: 1;
        min-width: 320px;
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

const AlarmSettings = styled.div`
    margin-top: 16px;
    display: flex;
    gap: 16px;
    align-items: center;
    flex-wrap: wrap;
`;

// ─── Helpers ────────────────────────────────────────────────────────────────

function formatTokenCount(n: number): string {
    if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
    if (n >= 1_000) return `${(n / 1_000).toFixed(1)}K`;
    return String(n);
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
    // === State: Subsection 1 - Bar Chart ===
    const [period, setPeriod] = useState<PeriodKey>('1m');
    const [series, setSeries] = useState<TimeSeriesPoint[]>([]);
    const [granularity, setGranularity] = useState<string>('day');
    const [loadingSeries, setLoadingSeries] = useState(false);

    // === State: Subsection 2 - Pie Charts ===
    const [breakdown, setBreakdown] = useState<BreakdownData | null>(null);
    const [loadingBreakdown, setLoadingBreakdown] = useState(false);
    const [pieLabel, setPieLabel] = useState<string>('Last 24 hours');

    // === State: Subsection 3 - Alarms ===
    const [alarmData, setAlarmData] = useState<AlarmData | null>(null);
    const [loadingAlarms, setLoadingAlarms] = useState(false);
    const [editingAlarm, setEditingAlarm] = useState(false);
    const [editDailyLimit, setEditDailyLimit] = useState<number>(500000);
    const [editMonthlyLimit, setEditMonthlyLimit] = useState<number>(10000000);

    const sectionRef = useRef<HTMLDivElement>(null);
    const location = useLocation();

    // === Fetch: Time Series ===
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

    // === Fetch: Breakdown ===
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

    // === Fetch: Alarms ===
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

    // === Scroll into view if navigated from header double-click ===
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

    const handleBarClick = useCallback((periodStr: string) => {
        // Compute start/end from clicked bar period and granularity
        let start: Date;
        let end: Date;
        let label: string;

        if (granularity === 'hour') {
            // period format: "2026-03-29 14:00"
            start = new Date(periodStr.replace(' ', 'T') + ':00');
            end = new Date(start.getTime() + 3600000);
            label = periodStr;
        } else if (granularity === 'day') {
            // period format: "2026-03-29"
            start = new Date(periodStr + 'T00:00:00');
            end = new Date(start.getTime() + 86400000);
            label = periodStr;
        } else {
            // period format: "2026-03"
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
                message.success('Alarm levels updated');
                setEditingAlarm(false);
                fetchAlarms();
            } else {
                message.error(res.error?.message || 'Failed to save alarm levels');
            }
        } catch (e) {
            message.error('Failed to save alarm levels');
        }
    };

    // ─── Subsection 1: Bar Chart ───

    // Transform series into stacked bar chart data
    const barData = series.flatMap(p => [
        { period: p.period, type: 'Input Tokens', tokens: p.input_tokens },
        { period: p.period, type: 'Output Tokens', tokens: p.output_tokens },
    ]);

    const barConfig = {
        data: barData,
        xField: 'period',
        yField: 'tokens',
        colorField: 'type',
        stack: true,
        color: ['#52c41a', '#f59e0b'],
        legend: {
            position: 'top-right' as const,
            itemLabelFill: '#ffffff',
        },
        theme: { type: 'classicDark' as const },
        axis: {
            x: {
                labelFill: '#ffffffcc',
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
                labelFill: '#ffffffcc',
                label: {
                    formatter: (v: string) => formatTokenCount(Number(v)),
                },
            },
        },
        tooltip: {
            items: [
                (d: any) => ({
                    name: d.type,
                    value: `${Number(d.tokens).toLocaleString()} tokens`,
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

    // ─── Subsection 2: Pie Charts ───

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
        innerRadius: 0.5,
        theme: { type: 'classicDark' as const },
        label: {
            text: (d: any) => `${d.type}`,
            fill: '#ffffffcc',
            fontSize: 11,
        },
        legend: {
            position: 'bottom' as const,
            itemLabelFill: '#ffffff',
        },
        tooltip: {
            items: [
                (d: any) => ({
                    name: d.type,
                    value: `${Number(d.value).toLocaleString()} tokens`,
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
                    fontSize: 14,
                    fill: '#ffffffcc',
                },
            },
        ],
    });

    // ─── Subsection 3: Alarm Progress ───

    const dailyPercent = alarmData
        ? Math.min(100, Math.round((alarmData.daily.total_tokens / alarmData.alarm_levels.daily_token_limit) * 100))
        : 0;
    const monthlyPercent = alarmData
        ? Math.min(100, Math.round((alarmData.monthly.total_tokens / alarmData.alarm_levels.monthly_token_limit) * 100))
        : 0;

    const alarmColor = (percent: number) => (percent >= 100 ? '#ff4d4f' : '#52c41a');

    // ─── Render ─────────────────────────────────────────────────────────────

    return (
        <SectionWrapper ref={sectionRef} id="token-usage-section">
            <Collapse
                defaultActiveKey={[]}
                ghost
                items={[{
                    key: 'token-usage',
                    label: <Title level={4} style={{ margin: 0 }}>Token Usage Analytics</Title>,
                    children: (
                        <Space direction="vertical" size={24} style={{ width: '100%' }}>
                            {/* ── Subsection 1: Time Series Bar Chart ── */}
                            <Card>
                                <ChartHeader>
                                    <Title level={5} style={{ margin: 0 }}>Token Usage Over Time</Title>
                                    <Space>
                                        <Select
                                            value={period}
                                            onChange={handlePeriodChange}
                                            style={{ width: 240 }}
                                            options={PERIOD_OPTIONS}
                                        />
                                        <Button
                                            icon={<DownloadOutlined />}
                                            onClick={handleDownloadCSV}
                                            disabled={!series.length}
                                        >
                                            Download CSV
                                        </Button>
                                    </Space>
                                </ChartHeader>
                                {loadingSeries ? (
                                    <div style={{ textAlign: 'center', padding: 60 }}><Spin size="large" /></div>
                                ) : series.length > 0 ? (
                                    <div>
                                        <Column {...barConfig} height={320} />
                                        <Text type="secondary" style={{ display: 'block', marginTop: 8, textAlign: 'center' }}>
                                            Double-click on any bar to see detailed breakdown for that period
                                        </Text>
                                    </div>
                                ) : (
                                    <div style={{ textAlign: 'center', padding: 60 }}>
                                        <Text type="secondary">No token usage data for this period</Text>
                                    </div>
                                )}
                            </Card>

                            {/* ── Subsection 2: Pie Chart Breakdown ── */}
                            <Card>
                                <Title level={5} style={{ margin: 0, marginBottom: 16 }}>
                                    Token Breakdown — {pieLabel}
                                </Title>
                                {loadingBreakdown ? (
                                    <div style={{ textAlign: 'center', padding: 60 }}><Spin size="large" /></div>
                                ) : breakdown ? (
                                    <>
                                        <PieRow>
                                            <div>
                                                <Text strong style={{ display: 'block', marginBottom: 8 }}>
                                                    A) By Model
                                                </Text>
                                                {modelPieData.length > 0 ? (
                                                    <Pie {...pieConfig(modelPieData, 'Model')} height={300} />
                                                ) : (
                                                    <Text type="secondary">No model data</Text>
                                                )}
                                            </div>
                                            <div>
                                                <Text strong style={{ display: 'block', marginBottom: 8 }}>
                                                    B) By Skill
                                                </Text>
                                                {skillPieData.length > 0 ? (
                                                    <Pie {...pieConfig(skillPieData, 'Skill')} height={300} />
                                                ) : (
                                                    <Text type="secondary">No skill data</Text>
                                                )}
                                            </div>
                                        </PieRow>
                                        <div style={{ marginTop: 16, textAlign: 'center' }}>
                                            <Text strong style={{ fontSize: 16 }}>
                                                Total LLM Invocations: {breakdown.total_invocations.toLocaleString()}
                                            </Text>
                                        </div>
                                    </>
                                ) : (
                                    <Text type="secondary">No breakdown data</Text>
                                )}
                            </Card>

                            {/* ── Subsection 3: Usage Alarms ── */}
                            <Card>
                                <Title level={5} style={{ margin: 0, marginBottom: 16 }}>Usage Alerts</Title>
                                {loadingAlarms ? (
                                    <div style={{ textAlign: 'center', padding: 40 }}><Spin /></div>
                                ) : alarmData ? (
                                    <>
                                        <AlarmRow>
                                            <div>
                                                <Text strong>Daily Usage</Text>
                                                <div style={{ marginTop: 8 }}>
                                                    <Progress
                                                        percent={dailyPercent}
                                                        strokeColor={alarmColor(dailyPercent)}
                                                        format={() =>
                                                            `${formatTokenCount(alarmData.daily.total_tokens)} / ${formatTokenCount(alarmData.alarm_levels.daily_token_limit)}`
                                                        }
                                                    />
                                                    <Text type="secondary" style={{ fontSize: 12 }}>
                                                        Cost today: ${alarmData.daily.cost_usd.toFixed(2)}
                                                    </Text>
                                                </div>
                                            </div>
                                            <div>
                                                <Text strong>Monthly Usage</Text>
                                                <div style={{ marginTop: 8 }}>
                                                    <Progress
                                                        percent={monthlyPercent}
                                                        strokeColor={alarmColor(monthlyPercent)}
                                                        format={() =>
                                                            `${formatTokenCount(alarmData.monthly.total_tokens)} / ${formatTokenCount(alarmData.alarm_levels.monthly_token_limit)}`
                                                        }
                                                    />
                                                    <Text type="secondary" style={{ fontSize: 12 }}>
                                                        Cost this month: ${alarmData.monthly.cost_usd.toFixed(2)}
                                                    </Text>
                                                </div>
                                            </div>
                                        </AlarmRow>
                                        <AlarmSettings>
                                            {editingAlarm ? (
                                                <>
                                                    <Space>
                                                        <Text>Daily limit:</Text>
                                                        <InputNumber
                                                            value={editDailyLimit}
                                                            onChange={v => v !== null && setEditDailyLimit(v)}
                                                            min={0}
                                                            step={100000}
                                                            formatter={v => `${v}`.replace(/\B(?=(\d{3})+(?!\d))/g, ',')}
                                                            style={{ width: 160 }}
                                                        />
                                                    </Space>
                                                    <Space>
                                                        <Text>Monthly limit:</Text>
                                                        <InputNumber
                                                            value={editMonthlyLimit}
                                                            onChange={v => v !== null && setEditMonthlyLimit(v)}
                                                            min={0}
                                                            step={1000000}
                                                            formatter={v => `${v}`.replace(/\B(?=(\d{3})+(?!\d))/g, ',')}
                                                            style={{ width: 160 }}
                                                        />
                                                    </Space>
                                                    <Button type="primary" onClick={handleSaveAlarm}>Save</Button>
                                                    <Button onClick={() => setEditingAlarm(false)}>Cancel</Button>
                                                </>
                                            ) : (
                                                <Button
                                                    icon={<SettingOutlined />}
                                                    onClick={() => setEditingAlarm(true)}
                                                >
                                                    Set Alarm Levels
                                                </Button>
                                            )}
                                        </AlarmSettings>
                                    </>
                                ) : (
                                    <Text type="secondary">Unable to load alarm data</Text>
                                )}
                            </Card>
                        </Space>
                    ),
                }]}
            />
        </SectionWrapper>
    );
};

export default TokenUsageSection;
