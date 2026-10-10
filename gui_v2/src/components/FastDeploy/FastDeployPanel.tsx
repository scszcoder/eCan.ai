import React, { useEffect, useState } from 'react';
import { Button, DatePicker, Input, InputNumber, Radio, Select, Typography, message } from 'antd';
import dayjs from 'dayjs';
import {
    CloseOutlined,
    RightOutlined,
    LeftOutlined,
    PlusOutlined,
    DeleteOutlined,
} from '@ant-design/icons';
import { useTranslation } from 'react-i18next';
import { get_ipc_api } from '../../services/ipc_api';
import {
    FUNCTION_AREAS,
    PLATFORM_DEPLOYS,
    CUSTOM_PLATFORM_DEPLOY,
    platformValue,
    areasFor,
    areaName,
    platformDeployName,
    newStoreId,
    defaultConfig,
    type PlatformDeploy,
    type BusinessScenario,
    type ScenarioConfig,
} from './scenarios';
import { useFastDeployStore } from '../../stores/fastDeployStore';

/** A store from the local catalog (store.catalog). */
interface CatalogStore { store_id: string; name: string; platform: string; store_urls: string[] }

const { Text } = Typography;

interface FastDeployPanelProps {
    open: boolean;
    onClose: () => void;
}

type CreateResult = 'success' | 'failure' | null;

/** The store dropdown's last item: create a store on Generate. */
const NEW_STORE = '__new__';

/** A function area added to this deploy, with its own options. */
interface AddedArea { key: string; scenario: BusinessScenario; config: ScenarioConfig }

const AREA_BY_KEY = Object.fromEntries(FUNCTION_AREAS.map((a) => [a.key, a]));

// Backend status lines can carry a URL the user must act on (e.g. the Chrome
// download link from the douyin_cs pre-check) — render it as a clickable link.
const URL_RE = /(https?:\/\/[^\s"'”“]+)/g;
function linkify(line: string): React.ReactNode {
    const parts = line.split(URL_RE);
    if (parts.length === 1) return line;
    return parts.map((p, i) =>
        /^https?:\/\//.test(p) ? (
            <a
                key={i}
                href={p}
                onClick={(e) => { e.preventDefault(); window.open(p, '_blank'); }}
                style={{ color: '#60a5fa', textDecoration: 'underline', cursor: 'pointer' }}
            >
                {p}
            </a>
        ) : (
            <React.Fragment key={i}>{p}</React.Fragment>
        )
    );
}

const FastDeployPanel: React.FC<FastDeployPanelProps> = ({ open, onClose }) => {
    const { t, i18n } = useTranslation();
    const lang = i18n.language;
    const [platform, setPlatform] = useState<PlatformDeploy | null>(null);
    const [creating, setCreating] = useState(false);
    const [statusCollapsed, setStatusCollapsed] = useState(false);
    const [statusLines, setStatusLines] = useState<string[]>([]);
    const [result, setResult] = useState<CreateResult>(null);

    // Store: one from the catalog, or a new one the CLI creates on Generate.
    const presetStoreId = useFastDeployStore((s) => s.storeId);
    const [catalog, setCatalog] = useState<CatalogStore[]>([]);
    const [storeChoice, setStoreChoice] = useState<string>('');
    const [newName, setNewName] = useState('');
    // "Other platform": the platform name as the user typed it.
    const [customPlatform, setCustomPlatform] = useState('');
    const [storeUrl, setStoreUrl] = useState('');
    // Function areas: the picker's current pick and the ones added so far.
    const [areaPick, setAreaPick] = useState<string | undefined>(undefined);
    const [added, setAdded] = useState<AddedArea[]>([]);

    const loadCatalog = () => get_ipc_api().getStoreCatalog<{ stores: CatalogStore[] }>().then((res) => {
        if (res.success && res.data) setCatalog(res.data.stores || []);
    }).catch(() => { /* the picker offers only "new store" */ });
    useEffect(() => {
        if (open) loadCatalog();
    }, [open]);

    const areaRows = platform ? areasFor(platform) : [];
    const firstOpenArea = (rows: ReturnType<typeof areasFor>, have: AddedArea[]) =>
        rows.find((r) => r.scenario && !have.some((a) => a.key === r.area.key))?.area.key;

    const resetRun = () => { setCreating(false); setStatusLines([]); setResult(null); setStatusCollapsed(false); };

    const urlOf = (sid: string) => catalog.find((x) => x.store_id === sid)?.store_urls?.[0] || '';

    const pickStore = (sid: string) => {
        setStoreChoice(sid);
        setNewName('');
        setStoreUrl(sid === NEW_STORE ? '' : urlOf(sid));
    };

    const openPlatform = (p: PlatformDeploy, sid = '') => {
        setPlatform(p);
        setCustomPlatform('');
        setAdded([]);
        setAreaPick(firstOpenArea(areasFor(p), []));
        setStoreChoice(sid);
        setNewName('');
        setStoreUrl(sid ? urlOf(sid) : '');
        resetRun();
    };

    // Opened from a store's page: go straight to that store's platform.
    useEffect(() => {
        if (!open || !presetStoreId || !catalog.length) return;
        const st = catalog.find((x) => x.store_id === presetStoreId);
        const p = st && PLATFORM_DEPLOYS.find((x) => x.platform === platformValue(st.platform));
        if (p) openPlatform(p, presetStoreId);
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [open, presetStoreId, catalog]);

    const addArea = () => {
        const row = areaRows.find((r) => r.area.key === areaPick);
        if (!row?.scenario || added.some((a) => a.key === row.area.key)) return;
        const next = [...added, { key: row.area.key, scenario: row.scenario, config: defaultConfig(row.scenario) }];
        setAdded(next);
        setAreaPick(firstOpenArea(areaRows, next));
    };
    const removeArea = (key: string) => {
        const next = added.filter((a) => a.key !== key);
        setAdded(next);
        setAreaPick(firstOpenArea(areaRows, next));
    };
    const setAreaConfig = (key: string, patch: Partial<ScenarioConfig>) =>
        setAdded((list) => list.map((a) => (a.key === key ? { ...a, config: { ...a.config, ...patch } } : a)));

    // The platform key stores are saved under: a listed platform's key, or what
    // the user typed (a listed platform's name typed here maps to its key).
    const platKey = platform?.custom ? platformValue(customPlatform) : (platform?.platform || '');
    const isNew = storeChoice === NEW_STORE;
    const storeId = isNew ? newStoreId(platKey, newName) : storeChoice;

    const cancelConfig = () => { setPlatform(null); setAdded([]); resetRun(); };

    const handleCreate = async () => {
        if (!platform) return;
        if (!platKey) {
            message.warning(t('pages.agents.fast_deploy_need_platform', 'Enter the platform name'));
            return;
        }
        if (!storeChoice || (isNew && !newName.trim())) {
            message.warning(isNew
                ? t('pages.agents.fast_deploy_need_store_name', 'Enter the new store\'s name')
                : t('pages.agents.fast_deploy_need_store_pick', 'Choose a store, or pick "New store"'));
            return;
        }
        if (isNew && catalog.some((x) => x.store_id === storeId)) {
            message.warning(t('pages.agents.fast_deploy_store_exists',
                { defaultValue: 'A store with id {{id}} already exists — pick it from the list', id: storeId }));
            return;
        }
        if (!added.length) {
            if (isNew) {
                await createStoreOnly();
                return;
            }
            message.warning(t('pages.agents.fast_deploy_need_area', 'Add at least one function area'));
            return;
        }
        for (const a of added) {
            const c = a.config;
            if (a.scenario.schema.schedule && !(c.scheduleStart && (c.scheduleEvery || 0) >= 1 && c.scheduleUnit)) {
                message.warning(t('pages.agents.fast_deploy_need_schedule', 'Set when after-sales first runs and how often'));
                return;
            }
        }
        const url = storeUrl.trim();

        setCreating(true);
        setStatusCollapsed(false);
        setResult(null);
        setStatusLines([]);
        let ok = true;
        // The CLI creates a new store (or saves an edited URL) before the first deploy.
        let storeReady = !isNew;
        let urlSaved = isNew || url === (isNew ? '' : urlOf(storeChoice));
        for (const a of added) {
            const c = a.config;
            const label = areaName(AREA_BY_KEY[a.key], lang);
            setStatusLines((l) => [...l, t('pages.agents.fast_deploy_generating_area',
                { defaultValue: '{{area}}: generating agents and tasks…', area: label })]);
            const payload = {
                scenario: a.scenario.key,
                config: {
                    store_id: storeId,
                    ...(!storeReady ? { new_store: { name: newName.trim(), platform: platKey, urls: url ? [url] : [] } } : {}),
                    ...(storeReady && !urlSaved ? { store_url: url } : {}),
                    ...(a.scenario.schema.schedule ? { schedule: {
                        start: c.scheduleStart, every: c.scheduleEvery, unit: c.scheduleUnit,
                    } } : {}),
                    ...(a.scenario.schema.qaAgents ? { qa_agents: c.qaAgents } : {}),
                    ...(a.scenario.schema.replaceMode ? { mode: c.mode || 'add' } : {}),
                },
            };
            try {
                const resp = await get_ipc_api().executeRequest<any>('fast_deploy.generate', payload, 300_000);
                const data = (resp?.data as any) || {};
                const extra: string[] = [];
                if (Array.isArray(data.log)) extra.push(...data.log.map((x: any) => String(x)));
                else if (data.message) extra.push(String(data.message));
                if (data.store_created) storeReady = true;
                if (data.store_url_saved) urlSaved = true;
                if (resp?.success && data.status === 'success' && !data.stub) {
                    setStatusLines((l) => [...l, ...extra]);
                } else {
                    // A stub is a plan only: nothing was created (天猫客服 reported
                    // "success" with no agents, 2026-10-05).
                    if (data.stub) extra.push(t('pages.agents.fast_deploy_stub',
                        'This scenario is not available yet: only a plan was made, no agents or tasks were created.'));
                    if (resp?.error?.message) extra.push(String(resp.error.message));
                    setStatusLines((l) => [...l, ...extra]);
                    ok = false;
                    break;
                }
            } catch (err) {
                setStatusLines((l) => [...l, String(err)]);
                ok = false;
                break;
            }
        }
        if (isNew && storeReady) {
            // The new store is in the catalog now: select it, so a second
            // Generate deploys into it instead of creating it again.
            await loadCatalog();
            setStoreChoice(storeId);
            setNewName('');
        }
        if (ok) {
            // Pull the freshly generated agents into the stores so they appear on
            // the Agents page immediately (2026-09-02 customer report).
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
        }
        setResult(ok ? 'success' : 'failure');
        setCreating(false);
    };

    // No function area to deploy (a custom platform, or one whose areas are all
    // still to come): Generate creates just the store, with the CLI.
    const createStoreOnly = async () => {
        const url = storeUrl.trim();
        setCreating(true);
        setStatusCollapsed(false);
        setResult(null);
        setStatusLines([t('pages.agents.fast_deploy_creating_store', { defaultValue: 'Creating store {{id}}…', id: storeId })]);
        let ok = false;
        try {
            const resp = await get_ipc_api().executeRequest<any>('fast_deploy.create_store', {
                store_id: storeId, name: newName.trim(), platform: platKey, urls: url ? [url] : [],
            }, 120_000);
            const data = (resp?.data as any) || {};
            ok = !!(resp?.success && data.store_created);
            const lines = (Array.isArray(data.log) ? data.log : []).map((x: any) => String(x));
            if (resp?.error?.message) lines.push(String(resp.error.message));
            setStatusLines((l) => [...l, ...lines]);
        } catch (err) {
            setStatusLines((l) => [...l, String(err)]);
        }
        if (ok) {
            await loadCatalog();
            setStoreChoice(storeId);
            setNewName('');
        }
        setResult(ok ? 'success' : 'failure');
        setCreating(false);
    };

    if (!open) return null;

    const showStatus = creating || result !== null || statusLines.length > 0;
    const fieldLabel = (text: string) => <Text style={{ color: '#94a3b8', fontSize: 13 }}>{text}</Text>;
    const hint = (text: string) => <Text style={{ color: '#64748b', fontSize: 12, display: 'block', marginTop: 6 }}>{text}</Text>;

    const areaOptions = (a: AddedArea) => {
        const { schema } = a.scenario;
        const c = a.config;
        return (
            <>
                {schema.schedule && (
                    <div style={{ marginTop: 10 }}>
                        {fieldLabel(t('pages.agents.fast_deploy_schedule', 'After-sales: process orders and messages'))}
                        <div style={{ marginTop: 8, display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'center' }}>
                            <DatePicker
                                showTime={{ format: 'HH:mm' }}
                                format="YYYY-MM-DD HH:mm"
                                value={c.scheduleStart ? dayjs(c.scheduleStart) : null}
                                onChange={(v) => setAreaConfig(a.key, { scheduleStart: v ? v.toISOString() : undefined })}
                                placeholder={t('pages.agents.fast_deploy_schedule_start', 'First run')}
                            />
                            <Text style={{ color: '#94a3b8' }}>{t('pages.agents.fast_deploy_schedule_every', 'then every')}</Text>
                            <InputNumber
                                min={1}
                                value={c.scheduleEvery}
                                onChange={(v) => setAreaConfig(a.key, { scheduleEvery: typeof v === 'number' ? v : undefined })}
                                style={{ width: 90 }}
                            />
                            <Select
                                value={c.scheduleUnit}
                                onChange={(v) => setAreaConfig(a.key, { scheduleUnit: v })}
                                style={{ width: 100 }}
                                options={[
                                    { value: 'minutes', label: t('pages.agents.fast_deploy_unit_minutes', 'minutes') },
                                    { value: 'hours', label: t('pages.agents.fast_deploy_unit_hours', 'hours') },
                                    { value: 'days', label: t('pages.agents.fast_deploy_unit_days', 'days') },
                                ]}
                            />
                        </div>
                        {hint(t('pages.agents.fast_deploy_schedule_hint', 'Deploys one agent per role (after-sales, pre-sales, sales, marketing, procurement, research, manager). After-sales runs on this schedule; the others start when the manager (or you) sends them a message.'))}
                    </div>
                )}
                {schema.qaAgents && (
                    <div style={{ marginTop: 10 }}>
                        {fieldLabel(t('pages.agents.fast_deploy_qa_agents', '# of Q&A agents'))}
                        <div style={{ marginTop: 8 }}>
                            <InputNumber
                                min={schema.qaAgents.min}
                                max={schema.qaAgents.max}
                                value={c.qaAgents}
                                onChange={(v) => setAreaConfig(a.key, { qaAgents: typeof v === 'number' ? v : undefined })}
                                style={{ width: 120 }}
                            />
                            <Text style={{ color: '#64748b', marginLeft: 10, fontSize: 12 }}>
                                {t('pages.agents.fast_deploy_qa_hint', { defaultValue: 'default {{d}}, max {{m}}', d: schema.qaAgents.default, m: schema.qaAgents.max })}
                            </Text>
                        </div>
                    </div>
                )}
                {schema.replaceMode && (
                    <div style={{ marginTop: 10 }}>
                        {fieldLabel(t('pages.agents.fast_deploy_mode', 'Mode'))}
                        <div style={{ marginTop: 8 }}>
                            <Radio.Group
                                value={c.mode || 'add'}
                                onChange={(e) => setAreaConfig(a.key, { mode: e.target.value })}
                                options={[
                                    { label: t('pages.agents.fast_deploy_mode_add', 'Add'), value: 'add' },
                                    { label: t('pages.agents.fast_deploy_mode_replace', 'Replace'), value: 'replace' },
                                ]}
                                optionType="button"
                                buttonStyle="solid"
                            />
                            <div style={{ color: '#64748b', marginTop: 6, fontSize: 12 }}>
                                {c.mode === 'replace'
                                    ? t('pages.agents.fast_deploy_mode_replace_hint')
                                    : t('pages.agents.fast_deploy_mode_add_hint', 'Keeps existing tasks and agents; adds new ones.')}
                            </div>
                        </div>
                    </div>
                )}
            </>
        );
    };

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

            {/* Platform buttons (top) */}
            <div
                style={{
                    flex: platform ? '0 0 auto' : 1,
                    minHeight: 0,
                    overflow: 'auto',
                    padding: 16,
                    display: 'grid',
                    gridTemplateColumns: 'repeat(auto-fill, minmax(110px, 1fr))',
                    gap: 12,
                    alignContent: 'start',
                }}
            >
                {[...PLATFORM_DEPLOYS, CUSTOM_PLATFORM_DEPLOY].map((p) => {
                    const isSel = p.custom ? !!platform?.custom : (!platform?.custom && p.platform === platform?.platform);
                    return (
                        <button
                            key={p.custom ? '__custom__' : p.platform}
                            type="button"
                            data-testid={`fd-platform-${p.custom ? 'custom' : p.platform}`}
                            onClick={() => openPlatform(p)}
                            style={{
                                display: 'flex',
                                flexDirection: 'column',
                                alignItems: 'center',
                                justifyContent: 'center',
                                gap: 6,
                                padding: '12px 8px',
                                cursor: 'pointer',
                                borderRadius: 10,
                                border: isSel ? '1px solid #38bdf8' : '1px solid rgba(255,255,255,0.10)',
                                background: isSel ? 'rgba(56,189,248,0.12)' : 'rgba(255,255,255,0.03)',
                                color: '#e2e8f0',
                                transition: 'all 0.15s',
                            }}
                        >
                            <span style={{ fontSize: 28, color: isSel ? '#38bdf8' : '#cbd5e1' }}>{p.icon}</span>
                            <span style={{ textAlign: 'center', fontSize: 12, lineHeight: 1.3 }}>
                                {platformDeployName(p, lang)}
                                {!p.custom && <>{' '}<span style={{ color: '#64748b' }}>({p.region})</span></>}
                            </span>
                        </button>
                    );
                })}
            </div>

            {/* Config: store, function areas and their options */}
            {platform && (
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
                    {/* body: splits left (config) / right (status) once Generate is clicked */}
                    <div style={{ flex: 1, minHeight: 0, display: 'flex' }}>
                        {/* Left: config fields */}
                        <div style={{ flex: 1, minWidth: 0, overflow: 'auto', padding: 16 }}>
                            <Text strong style={{ color: '#e2e8f0' }}>
                                {platformDeployName(platform, lang)}
                                {!platform.custom && <>{' '}<span style={{ color: '#64748b', fontWeight: 400 }}>({platform.region})</span></>}
                            </Text>

                            {platform.custom && (
                                <div style={{ marginTop: 16 }}>
                                    {fieldLabel(t('pages.agents.fast_deploy_platform_name', 'Platform'))}
                                    <div style={{ marginTop: 8 }}>
                                        <Input
                                            data-testid="fd-platform-name"
                                            value={customPlatform}
                                            onChange={(e) => { setCustomPlatform(e.target.value); setStoreChoice(''); setNewName(''); }}
                                            placeholder={t('pages.agents.fast_deploy_platform_name_ph', 'Platform name, e.g. 微店')}
                                        />
                                    </div>
                                    {hint(t('pages.agents.fast_deploy_platform_custom_hint', 'Any platform not on the list. Agents cannot be generated for it yet — Generate creates the store.'))}
                                </div>
                            )}

                            {/* store: one of this platform's stores, or a new one. The id,
                                not the URL, identifies a store (every 飞鸽 seller shares one
                                workstation URL). */}
                            <div style={{ marginTop: 16 }}>
                                {fieldLabel(t('pages.agents.fast_deploy_store', 'Store'))}
                                <div style={{ marginTop: 8 }}>
                                    <Select
                                        data-testid="fd-store"
                                        style={{ width: '100%' }}
                                        value={storeChoice || undefined}
                                        placeholder={t('pages.agents.fast_deploy_store_pick', 'Choose a store')}
                                        onChange={(v) => pickStore(v)}
                                        options={[
                                            ...catalog
                                                .filter((x) => !!platKey && platformValue(x.platform) === platKey)
                                                .map((x) => ({ value: x.store_id,
                                                    label: x.name && x.name !== x.store_id ? `${x.name} (${x.store_id})` : x.store_id })),
                                            { value: NEW_STORE, label: `＋ ${t('pages.agents.fast_deploy_store_new', 'New store')}` },
                                        ]}
                                    />
                                </div>
                                {isNew && (
                                    <div style={{ marginTop: 8 }}>
                                        <Input
                                            data-testid="fd-store-name"
                                            value={newName}
                                            onChange={(e) => setNewName(e.target.value)}
                                            placeholder={t('pages.agents.fast_deploy_store_name', 'New store name')}
                                        />
                                        {hint(storeId
                                            ? t('pages.agents.fast_deploy_store_id', { defaultValue: 'Store id: {{id}} (permanent; created when you click Generate)', id: storeId })
                                            : t('pages.agents.fast_deploy_store_id_auto', 'The store id is generated from the name.'))}
                                    </div>
                                )}
                            </div>

                            <div style={{ marginTop: 14 }}>
                                {fieldLabel(t('pages.agents.fast_deploy_store_url', 'Store URL (optional)'))}
                                <div style={{ marginTop: 8 }}>
                                    <Input
                                        data-testid="fd-store-url"
                                        value={storeUrl}
                                        onChange={(e) => setStoreUrl(e.target.value)}
                                        placeholder="https://"
                                    />
                                </div>
                                {hint(t('pages.agents.fast_deploy_store_url_hint', 'Leave empty to use the platform\'s seller workspace — sign the store in once and it opens there.'))}
                            </div>

                            {/* function areas: pick one, add it, then set its options */}
                            <div style={{ marginTop: 16 }}>
                                {fieldLabel(t('pages.agents.fast_deploy_areas', 'Function areas'))}
                                <div style={{ marginTop: 8, display: 'flex', gap: 8 }}>
                                    <Select
                                        data-testid="fd-area"
                                        style={{ flex: 1 }}
                                        value={areaPick}
                                        onChange={(v) => setAreaPick(v)}
                                        placeholder={t('pages.agents.fast_deploy_area_pick', 'Choose a function area')}
                                        options={areaRows.map((r) => ({
                                            value: r.area.key,
                                            label: r.scenario ? areaName(r.area, lang)
                                                : `${areaName(r.area, lang)} (${t('pages.agents.fast_deploy_area_soon', 'coming soon')})`,
                                            disabled: !r.scenario || added.some((a) => a.key === r.area.key),
                                        }))}
                                    />
                                    <Button
                                        data-testid="fd-area-add"
                                        icon={<PlusOutlined />}
                                        onClick={addArea}
                                        disabled={!areaPick}
                                        title={t('pages.agents.fast_deploy_area_add', 'Add')}
                                    />
                                </div>
                                {added.map((a) => (
                                    <div
                                        key={a.key}
                                        data-testid={`fd-area-${a.key}`}
                                        style={{ marginTop: 10, padding: '10px 12px', borderRadius: 8, border: '1px solid rgba(255,255,255,0.10)', background: 'rgba(255,255,255,0.02)' }}
                                    >
                                        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                                            <Text strong style={{ color: '#e2e8f0' }}>{areaName(AREA_BY_KEY[a.key], lang)}</Text>
                                            <Button
                                                type="text"
                                                size="small"
                                                icon={<DeleteOutlined />}
                                                style={{ color: '#94a3b8' }}
                                                data-testid={`fd-area-del-${a.key}`}
                                                onClick={() => removeArea(a.key)}
                                                title={t('pages.agents.fast_deploy_area_remove', 'Remove')}
                                            />
                                        </div>
                                        {areaOptions(a)}
                                    </div>
                                ))}
                            </div>
                        </div>

                        {/* Right: status sub-panel (collapsible), appears after Generate */}
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
                                            <div key={i} style={{ whiteSpace: 'pre-wrap', wordBreak: 'break-all', marginBottom: 4 }}>{linkify(line)}</div>
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

                    {/* footer: Generate / Cancel */}
                    <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 10, padding: '10px 16px', borderTop: '1px solid rgba(255,255,255,0.06)' }}>
                        <Button onClick={cancelConfig}>
                            {t('common.cancel', 'Cancel')}
                        </Button>
                        <Button type="primary" data-testid="fd-generate" loading={creating} onClick={handleCreate}>
                            {t('pages.agents.fast_deploy_generate', 'Generate')}
                        </Button>
                    </div>
                </div>
            )}
        </div>
    );
};

export default FastDeployPanel;
