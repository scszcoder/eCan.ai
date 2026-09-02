import React, { useState } from 'react';
import { Button, Input, InputNumber, Typography, message } from 'antd';
import {
    CloseOutlined,
    PlusOutlined,
    DeleteOutlined,
    RightOutlined,
    LeftOutlined,
} from '@ant-design/icons';
import { useTranslation } from 'react-i18next';
import { get_ipc_api } from '../../services/ipc_api';
import {
    SCENARIOS,
    getScenario,
    scenarioName,
    defaultConfig,
    type BusinessScenario,
    type ScenarioConfig,
} from './scenarios';

const { Text } = Typography;

interface FastDeployPanelProps {
    open: boolean;
    onClose: () => void;
}

type CreateResult = 'success' | 'failure' | null;

const FastDeployPanel: React.FC<FastDeployPanelProps> = ({ open, onClose }) => {
    const { t, i18n } = useTranslation();
    const [selectedKey, setSelectedKey] = useState<string | null>(null);
    const [config, setConfig] = useState<ScenarioConfig>({ storeUrls: [''] });
    const [creating, setCreating] = useState(false);
    const [statusCollapsed, setStatusCollapsed] = useState(false);
    const [statusLines, setStatusLines] = useState<string[]>([]);
    const [result, setResult] = useState<CreateResult>(null);

    const selected = getScenario(selectedKey);

    const openConfig = (s: BusinessScenario) => {
        setSelectedKey(s.key);
        setConfig(defaultConfig(s));
        setCreating(false);
        setStatusLines([]);
        setResult(null);
        setStatusCollapsed(false);
    };

    const cancelConfig = () => {
        // Collapse the entire configuration sub-panel.
        setSelectedKey(null);
        setCreating(false);
        setStatusLines([]);
        setResult(null);
    };

    // ── store-URL list edits ────────────────────────────────────────────
    const setUrl = (idx: number, value: string) =>
        setConfig((c) => ({ ...c, storeUrls: c.storeUrls.map((u, i) => (i === idx ? value : u)) }));
    const addUrl = () => setConfig((c) => ({ ...c, storeUrls: [...c.storeUrls, ''] }));
    const removeUrl = (idx: number) =>
        setConfig((c) => ({ ...c, storeUrls: c.storeUrls.filter((_, i) => i !== idx) }));

    const handleCreate = async () => {
        if (!selected) return;
        const urls = config.storeUrls.map((u) => u.trim()).filter(Boolean);
        if (urls.length === 0) {
            message.warning(t('pages.agents.fast_deploy_need_url', 'Please add at least one store URL'));
            return;
        }
        const payload = {
            scenario: selected.key,
            config: {
                store_urls: urls,
                ...(selected.schema.qaAgents ? { qa_agents: config.qaAgents } : {}),
            },
        };

        setCreating(true);
        setStatusCollapsed(false);
        setResult(null);
        setStatusLines([t('pages.agents.fast_deploy_saving', 'Saving configuration to file…')]);

        try {
            setStatusLines((l) => [...l, t('pages.agents.fast_deploy_generating', 'Generating resources (agents, skills, tasks)…')]);
            const resp = await get_ipc_api().executeRequest<any>('fast_deploy.generate', payload, 300_000);
            const data = (resp?.data as any) || {};
            const extra: string[] = [];
            if (data.config_path) extra.push(`config: ${data.config_path}`);
            if (Array.isArray(data.log)) extra.push(...data.log.map((x: any) => String(x)));
            else if (data.message) extra.push(String(data.message));

            if (resp?.success && data.status === 'success') {
                setStatusLines((l) => [...l, ...extra]);
                setResult('success');
                // Pull the freshly generated agents into the stores so they
                // appear on the Agents page immediately — before this, they
                // only showed up after re-login (2026-09-02 customer report).
                setStatusLines((l) => [...l, t('pages.agents.fast_deploy_refreshing', 'Refreshing agent list…')]);
                try {
                    const { refreshOrgAgents } = await import('../../pages/Agents/utils/refreshOrgAgents');
                    const refreshed = await refreshOrgAgents();
                    setStatusLines((l) => [...l, refreshed
                        ? t('pages.agents.fast_deploy_refreshed', 'Agent list refreshed — new agents are on the Agents page.')
                        : t('pages.agents.fast_deploy_refresh_failed', 'Auto-refresh failed — use the refresh button on the Agents page.')]);
                } catch (refreshErr) {
                    setStatusLines((l) => [...l, String(refreshErr)]);
                }
            } else {
                if (resp?.error?.message) extra.push(String(resp.error.message));
                setStatusLines((l) => [...l, ...extra]);
                setResult('failure');
            }
        } catch (err) {
            setStatusLines((l) => [...l, String(err)]);
            setResult('failure');
        } finally {
            setCreating(false);
        }
    };

    if (!open) return null;

    const showStatus = creating || result !== null || statusLines.length > 0;

    return (
        <div
            style={{
                position: 'absolute',
                top: 56,
                left: 0,
                right: 0,
                zIndex: 9,
                margin: '0 16px',
                maxHeight: '72vh',
                display: 'flex',
                flexDirection: 'column',
                background: 'rgba(30, 41, 59, 0.98)',
                border: '1px solid rgba(255, 255, 255, 0.10)',
                borderRadius: 10,
                boxShadow: '0 12px 32px rgba(0, 0, 0, 0.35)',
                overflow: 'hidden',
            }}
        >
            {/* Panel header */}
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '10px 16px', borderBottom: '1px solid rgba(255,255,255,0.06)' }}>
                <Text strong style={{ color: '#e2e8f0', fontSize: 15 }}>
                    {t('pages.agents.fast_deploy', 'Fast Deploy')}
                </Text>
                <Button type="text" size="small" icon={<CloseOutlined />} onClick={onClose} style={{ color: '#94a3b8' }} />
            </div>

            {/* Scenario grid (top) */}
            <div
                style={{
                    flex: selected ? 2 : 1,
                    minHeight: 0,
                    overflow: 'auto',
                    padding: 16,
                    display: 'grid',
                    gridTemplateColumns: 'repeat(auto-fill, minmax(140px, 1fr))',
                    gap: 14,
                    alignContent: 'start',
                }}
            >
                {SCENARIOS.map((s) => {
                    const isSel = s.key === selectedKey;
                    return (
                        <button
                            key={s.key}
                            type="button"
                            onClick={() => setSelectedKey(s.key)}
                            onDoubleClick={() => openConfig(s)}
                            title={t('pages.agents.fast_deploy_dblclick', 'Double-click to configure')}
                            style={{
                                display: 'flex',
                                flexDirection: 'column',
                                alignItems: 'center',
                                justifyContent: 'center',
                                gap: 8,
                                aspectRatio: '1 / 1',
                                padding: 12,
                                cursor: 'pointer',
                                borderRadius: 10,
                                border: isSel ? '1px solid #38bdf8' : '1px solid rgba(255,255,255,0.10)',
                                background: isSel ? 'rgba(56,189,248,0.12)' : 'rgba(255,255,255,0.03)',
                                color: '#e2e8f0',
                                transition: 'all 0.15s',
                            }}
                        >
                            <span style={{ fontSize: 34, color: isSel ? '#38bdf8' : '#cbd5e1' }}>{s.icon}</span>
                            <span style={{ textAlign: 'center', fontSize: 12, lineHeight: 1.3 }}>
                                {scenarioName(s, i18n.language)}{' '}
                                <span style={{ color: '#64748b' }}>({s.region})</span>
                            </span>
                        </button>
                    );
                })}
            </div>

            {/* Config panel (bottom ~1/3), shown after double-click */}
            {selected && (
                <div
                    style={{
                        flex: 1,
                        minHeight: 0,
                        display: 'flex',
                        flexDirection: 'column',
                        borderTop: '1px solid rgba(255,255,255,0.10)',
                        background: 'rgba(15,23,42,0.6)',
                    }}
                >
                    {/* body: splits left (config) / right (status) once Create is clicked */}
                    <div style={{ flex: 1, minHeight: 0, display: 'flex' }}>
                        {/* Left: config fields */}
                        <div style={{ flex: 1, minWidth: 0, overflow: 'auto', padding: 16 }}>
                            <Text strong style={{ color: '#e2e8f0' }}>
                                {scenarioName(selected, i18n.language)}{' '}
                                <span style={{ color: '#64748b', fontWeight: 400 }}>({selected.region})</span>
                            </Text>

                            {/* Store URLs */}
                            {selected.schema.storeUrls && (
                                <div style={{ marginTop: 14 }}>
                                    <Text style={{ color: '#94a3b8', fontSize: 13 }}>
                                        {t('pages.agents.fast_deploy_store_urls', 'Store URLs')}
                                    </Text>
                                    <div style={{ marginTop: 8, display: 'flex', flexDirection: 'column', gap: 8 }}>
                                        {config.storeUrls.map((url, idx) => (
                                            <div key={idx} style={{ display: 'flex', gap: 8 }}>
                                                <Input
                                                    value={url}
                                                    placeholder="https://…"
                                                    onChange={(e) => setUrl(idx, e.target.value)}
                                                />
                                                <Button
                                                    danger
                                                    icon={<DeleteOutlined />}
                                                    onClick={() => removeUrl(idx)}
                                                />
                                            </div>
                                        ))}
                                        <Button type="dashed" icon={<PlusOutlined />} onClick={addUrl}>
                                            {t('pages.agents.fast_deploy_add_url', 'Add URL')}
                                        </Button>
                                    </div>
                                </div>
                            )}

                            {/* # of Q&A agents */}
                            {selected.schema.qaAgents && (
                                <div style={{ marginTop: 16 }}>
                                    <Text style={{ color: '#94a3b8', fontSize: 13 }}>
                                        {t('pages.agents.fast_deploy_qa_agents', '# of Q&A agents')}
                                    </Text>
                                    <div style={{ marginTop: 8 }}>
                                        <InputNumber
                                            min={selected.schema.qaAgents.min}
                                            max={selected.schema.qaAgents.max}
                                            value={config.qaAgents}
                                            onChange={(v) => setConfig((c) => ({ ...c, qaAgents: typeof v === 'number' ? v : undefined }))}
                                            style={{ width: 120 }}
                                        />
                                        <Text style={{ color: '#64748b', marginLeft: 10, fontSize: 12 }}>
                                            {t('pages.agents.fast_deploy_qa_hint', { defaultValue: 'default {{d}}, max {{m}}', d: selected.schema.qaAgents.default, m: selected.schema.qaAgents.max })}
                                        </Text>
                                    </div>
                                </div>
                            )}
                        </div>

                        {/* Right: status sub-panel (collapsible), appears after Create */}
                        {showStatus && (
                            statusCollapsed ? (
                                <div
                                    onClick={() => setStatusCollapsed(false)}
                                    title={t('pages.agents.fast_deploy_expand_status', 'Expand status')}
                                    style={{
                                        width: 28,
                                        cursor: 'pointer',
                                        borderLeft: '1px solid rgba(255,255,255,0.10)',
                                        display: 'flex',
                                        alignItems: 'center',
                                        justifyContent: 'center',
                                        color: '#94a3b8',
                                        background: 'rgba(255,255,255,0.03)',
                                    }}
                                >
                                    <LeftOutlined />
                                </div>
                            ) : (
                                <div
                                    style={{
                                        flex: '0 0 33%',
                                        minWidth: 200,
                                        borderLeft: '1px solid rgba(255,255,255,0.10)',
                                        display: 'flex',
                                        flexDirection: 'column',
                                        background: 'rgba(2,6,23,0.5)',
                                    }}
                                >
                                    <div
                                        onClick={() => setStatusCollapsed(true)}
                                        title={t('pages.agents.fast_deploy_collapse_status', 'Collapse')}
                                        style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '8px 12px', cursor: 'pointer', borderBottom: '1px solid rgba(255,255,255,0.06)' }}
                                    >
                                        <Text style={{ color: '#cbd5e1', fontSize: 13 }}>
                                            {t('pages.agents.fast_deploy_status', 'Status')}
                                        </Text>
                                        <RightOutlined style={{ color: '#94a3b8', fontSize: 12 }} />
                                    </div>
                                    <div style={{ flex: 1, minHeight: 0, overflow: 'auto', padding: 12, fontFamily: 'monospace', fontSize: 12, color: '#cbd5e1' }}>
                                        {statusLines.map((line, i) => (
                                            <div key={i} style={{ whiteSpace: 'pre-wrap', wordBreak: 'break-all', marginBottom: 4 }}>{line}</div>
                                        ))}
                                        {result === 'success' && (
                                            <div style={{ marginTop: 8, color: '#22c55e', fontWeight: 700 }}>
                                                {t('pages.agents.fast_deploy_success', 'Success')}
                                            </div>
                                        )}
                                        {result === 'failure' && (
                                            <div style={{ marginTop: 8, color: '#ef4444', fontWeight: 700 }}>
                                                {t('pages.agents.fast_deploy_failure', 'Failed')}
                                            </div>
                                        )}
                                    </div>
                                </div>
                            )
                        )}
                    </div>

                    {/* footer: Create / Cancel */}
                    <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 10, padding: '10px 16px', borderTop: '1px solid rgba(255,255,255,0.06)' }}>
                        <Button onClick={cancelConfig}>
                            {t('common.cancel', 'Cancel')}
                        </Button>
                        <Button type="primary" loading={creating} onClick={handleCreate}>
                            {t('pages.agents.fast_deploy_create', 'Create')}
                        </Button>
                    </div>
                </div>
            )}
        </div>
    );
};

export default FastDeployPanel;
