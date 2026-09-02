import React, { useRef, useState, useMemo, useLayoutEffect } from 'react';
import { Typography, Space, Button, Progress, Tooltip, Tag, Form, Input, Row, Col, Checkbox, Select, Tabs, App, Avatar, Dropdown } from 'antd';
import { useEffectOnActive } from 'keepalive-for-react';
import type { TabsProps } from 'antd';
import {
    ThunderboltOutlined,
    CheckCircleOutlined,
    ClockCircleOutlined,
    StarOutlined,
    EditOutlined,
    FileTextOutlined,
    SettingOutlined,
    CodeOutlined,
    AppstoreOutlined,
    TagsOutlined,
    DeleteOutlined,
    LockOutlined,
    UploadOutlined,
    PlayCircleOutlined,
    EyeOutlined,
    UserOutlined,
    TeamOutlined,
    RiseOutlined,
    CalendarOutlined,
    ApartmentOutlined,
    InfoCircleOutlined,
    BulbOutlined,
    ExperimentOutlined,
    RocketOutlined,
    DownloadOutlined,
    DownOutlined,
    GlobalOutlined,
    MoreOutlined,
    HeartOutlined,
} from '@ant-design/icons';

import { useTranslation } from 'react-i18next';
import type { Skill, SkillRunMode, SkillNeedInput } from '@/types/domain/skill';

import { useNavigate } from 'react-router-dom';
import { useSkillStore } from '@/stores/domain/skillStore';
import { useUserStore } from '@/stores/userStore';
import { get_ipc_api } from '@/services/ipc_api';
import { logger } from '@/utils/logger';
import { IPCAPI } from '@/services/ipc/api';
import { StyledFormItem, StyledCard, FormContainer, buttonStyle, primaryButtonStyle } from '@/components/Common/StyledForm';
import { useDeleteConfirm } from '@/components/Common/DeleteConfirmModal';
import { StringArrayInput, NeedInputsEditor, ModeSelector } from './SkillMetadataEditors';
import { SkillReviewPanel } from './SkillReviewPanel';
import SkillChangelog from './SkillChangelog';
import SkillSimilar from './SkillSimilar';
import SkillAuthorPanel from './SkillAuthorPanel';

const { Text, Title } = Typography;
const { TextArea } = Input;

const getStatusColor = (status: Skill['status']): string => {
    switch (status) {
        case 'active':
            return 'success';
        case 'learning':
            return 'processing';
        case 'planned':
            return 'default';
        default:
            return 'default';
    }
};

// Resolve category to icon + gradient palette
const CATEGORY_PALETTE: Record<string, { icon: React.ReactNode; bg: [string, string] }> = {
    automation: { icon: <RocketOutlined />, bg: ['#f59e0b', '#d97706'] },
    analysis: { icon: <RiseOutlined />, bg: ['#8b5cf6', '#7c3aed'] },
    communication: { icon: <TeamOutlined />, bg: ['#06b6d4', '#0891b2'] },
    coding: { icon: <CodeOutlined />, bg: ['#3b82f6', '#2563eb'] },
    development: { icon: <CodeOutlined />, bg: ['#3b82f6', '#2563eb'] },
    vision: { icon: <EyeOutlined />, bg: ['#ec4899', '#db2777'] },
    image: { icon: <EyeOutlined />, bg: ['#ec4899', '#db2777'] },
    api: { icon: <GlobalOutlined />, bg: ['#14b8a6', '#0d9488'] },
    integration: { icon: <ApartmentOutlined />, bg: ['#14b8a6', '#0d9488'] },
    logic: { icon: <BulbOutlined />, bg: ['#a855f7', '#9333ea'] },
    reasoning: { icon: <BulbOutlined />, bg: ['#a855f7', '#9333ea'] },
    cloud: { icon: <GlobalOutlined />, bg: ['#64748b', '#475569'] },
    network: { icon: <GlobalOutlined />, bg: ['#64748b', '#475569'] },
    search: { icon: <ExperimentOutlined />, bg: ['#f97316', '#ea580c'] },
    file: { icon: <FileTextOutlined />, bg: ['#22c55e', '#16a34a'] },
    browser: { icon: <RocketOutlined />, bg: ['#f43f5e', '#e11d48'] },
    general: { icon: <ExperimentOutlined />, bg: ['#64748b', '#475569'] },
    unknown: { icon: <ExperimentOutlined />, bg: ['#64748b', '#475569'] },
};

const inferCategory = (skill: Skill): string => {
    const tags = Array.isArray((skill as any)?.tags) ? (skill as any).tags : [];
    const text = `${skill.name || ''} ${skill.description || ''} ${tags.join(' ')}`.toLowerCase();
    if (/automat|workflow|process|batch|schedule/i.test(text)) return 'automation';
    if (/analy[sz]|data|chart|report|metric|statistic/i.test(text)) return 'analysis';
    if (/chat|message|email|communication|talk|conversation/i.test(text)) return 'communication';
    if (/code|program|develop|script|function|debug/i.test(text)) return 'coding';
    if (/vision|image|photo|visual|ocr|detect|recognize/i.test(text)) return 'vision';
    if (/api|rest|http|integration|webhook|endpoint/i.test(text)) return 'api';
    if (/logic|reason|think|decision|rule|condition/i.test(text)) return 'logic';
    if (/cloud|aws|azure|gcp|server|deploy|network/i.test(text)) return 'cloud';
    if (/test|debug|check|verify|validate/i.test(text)) return 'development';
    if (/search|find|lookup|query|retrieve/i.test(text)) return 'search';
    if (/file|document|upload|download|export|import/i.test(text)) return 'file';
    if (/browser|web|page|click|scroll|navigate/i.test(text)) return 'browser';
    return 'general';
};

const getSkillIcon = (skill: Skill): { icon: React.ReactNode; bg: [string, string] } => {
    if ((skill as any)?.source === 'code') {
        return { icon: <CodeOutlined />, bg: ['#3b82f6', '#2563eb'] };
    }
    const category = (skill as any)?.category || inferCategory(skill);
    return CATEGORY_PALETTE[category] || CATEGORY_PALETTE.general;
};

const getInitials = (text?: string | null): string => {
    if (!text) return '?';
    const cleaned = String(text).trim();
    if (!cleaned) return '?';
    // If it's an email, use the local part
    const at = cleaned.indexOf('@');
    const local = at > 0 ? cleaned.slice(0, at) : cleaned;
    // Split by non-word chars
    const parts = local.split(/[\s._-]+/).filter(Boolean);
    if (parts.length >= 2) {
        return (parts[0][0] + parts[1][0]).toUpperCase();
    }
    return cleaned.slice(0, 2).toUpperCase();
};

const colorFromString = (s?: string | null): string => {
    if (!s) return '#1890ff';
    let hash = 0;
    for (let i = 0; i < s.length; i++) {
        hash = s.charCodeAt(i) + ((hash << 5) - hash);
    }
    const palette = ['#1890ff', '#52c41a', '#faad14', '#f5222d', '#722ed1', '#13c2c2', '#eb2f96', '#fa541c'];
    return palette[Math.abs(hash) % palette.length];
};

// Reusable section card for overview tab
const SectionCard: React.FC<{
    icon: React.ReactNode;
    title: React.ReactNode;
    accent?: string;
    style?: React.CSSProperties;
    children: React.ReactNode;
}> = ({ icon, title, accent = '#1890ff', style, children }) => (
    <div style={{
        position: 'relative',
        background: 'rgba(255,255,255,0.03)',
        border: '1px solid rgba(255,255,255,0.06)',
        borderRadius: 8,
        overflow: 'hidden',
        ...style,
    }}>
        <div style={{
            position: 'absolute', top: 0, left: 0, right: 0, height: 2,
            background: accent, opacity: 0.6,
        }} />
        <div style={{ padding: '10px 14px' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 8 }}>
                <span style={{ color: accent, fontSize: 13, display: 'inline-flex' }}>{icon}</span>
                <Text style={{ color: 'rgba(255,255,255,0.85)', fontSize: 12, fontWeight: 600 }}>{title}</Text>
            </div>
            {children}
        </div>
    </div>
);

interface SkillDetailsProps {
    skill: Skill | null;
    isNew?: boolean;
    onRefresh: () => void;
    onSave?: () => void;
    onSkillChange?: (skill: Skill) => void;
    onCancel?: () => void;
    onDelete?: () => void;
    subscribedSkillIds?: string[];
    onSubscribe?: (skillId: string) => Promise<void>;
    onUnsubscribe?: (skillId: string) => Promise<void>;
}

/**
 * Extended的技能Type，IncludeAll DBAgentSkill 和 EC_Skill Field
 */
type ExtendedSkill = Skill & {
    // DBAgentSkill Field
    askid?: number;

    // EC_Skill Field
    ui_info?: {
        text?: string;
        icon?: string;
    };
    objectives?: string[];
    need_inputs?: SkillNeedInput[];
    run_mode?: SkillRunMode | string;
    mapping_rules?: any;

    // SerializeField（Used forForm）
    config_json?: string;
    apps_json?: string;
    limitations_json?: string;
    tags_json?: string;
    examples_json?: string;
    inputModes_json?: string;
    outputModes_json?: string;
    objectives_json?: string;
    need_inputs_json?: string;
    mapping_rules_json?: string;

    // Publish/Store metadata (ExtensibleMixin)
    extra_data?: Record<string, any>;
};

const DEFAULT_SKILL: Partial<ExtendedSkill> = {
    id: '',
    name: '',
    description: '',
    version: '0.0.0',
    level: 'entry',
    run_mode: 'development',
    status: 'planned',
    public: false,
    rentable: false,
    price: 0,
};

/**
 * JSON 格式Validate器
 * Allow：空Value、有效的 JSON
 * 拒绝：任何非 JSON 格式的Content
 */
const validateJSON = (t: any) => ({
    validator: (_: any, value: string) => {
        // Allow空Value
        if (!value || value.trim() === '') {
            return Promise.resolve();
        }
        
        // Must是有效的 JSON 格式
        try {
            JSON.parse(value);
            return Promise.resolve();
        } catch (e) {
            return Promise.reject(
                new Error(
                    t('pages.skills.invalidJson') || 
                    'Invalid JSON format. Please enter valid JSON'
                )
            );
        }
    },
});

/**
 * HelperFunction：将对象/数组Convert为 JSON 字符串
 */
const toJsonString = (value: any): string => {
    if (!value) return '';
    if (typeof value === 'string') return value;
    try {
        return JSON.stringify(value, null, 2);
    } catch {
        return String(value);
    }
};

/**
 * HelperFunction：将 JSON 字符串Convert为对象/数组
 */
const fromJsonString = (value: string): any => {
    if (!value || value.trim() === '') return undefined;
    try {
        return JSON.parse(value);
    } catch {
        return value;
    }
};

/**
 * Tag Input component for simple array fields
 */
const TagInput: React.FC<{
    value: string;
    onChange: (value: string) => void;
    placeholder?: string;
    t?: (key: string, defaultValue?: string) => string;
}> = ({ value, onChange, placeholder, t }) => {
    const { t: tLocal } = useTranslation();
    const $t = t || tLocal;
    const [inputValue, setInputValue] = useState('');
    const tagPlaceholder = placeholder ?? $t('pages.skills.tagInputPlaceholder', 'Enter and press Enter');

    const tags = useMemo(() => {
        if (!value || value.trim() === '') return [];
        try {
            const parsed = JSON.parse(value);
            return Array.isArray(parsed) ? parsed : [];
        } catch {
            return [];
        }
    }, [value]);

    const handleAdd = () => {
        if (!inputValue.trim()) return;
        const newTags = [...tags, inputValue.trim()];
        onChange(JSON.stringify(newTags));
        setInputValue('');
    };

    const handleRemove = (tagToRemove: string) => {
        const newTags = tags.filter(t => t !== tagToRemove);
        onChange(JSON.stringify(newTags));
    };

    return (
        <div>
            <Space wrap size={4} style={{ marginBottom: 8 }}>
                {tags.map((tag, idx) => (
                    <Tag
                        key={idx}
                        closable
                        onClose={() => handleRemove(tag)}
                        style={{ marginBottom: 4 }}
                    >
                        {tag}
                    </Tag>
                ))}
            </Space>
            <Input
                value={inputValue}
                onChange={(e) => setInputValue(e.target.value)}
                onPressEnter={handleAdd}
                placeholder={tagPlaceholder}
                suffix={
                    <Button type="text" size="small" onClick={handleAdd} disabled={!inputValue.trim()}>
                        {$t('pages.skills.tagInputAdd', '+Add')}
                    </Button>
                }
            />
        </div>
    );
};

const SkillDetails: React.FC<SkillDetailsProps> = ({ skill, isNew = false, onRefresh, onSave, onSkillChange, onCancel, onDelete, subscribedSkillIds, onSubscribe, onUnsubscribe }) => {
    const { t } = useTranslation();
    const navigate = useNavigate();
    const { message } = App.useApp();  // Use App context for message
    const showDeleteConfirm = useDeleteConfirm();
    const username = useUserStore((s) => s.username) || '';
    const addItem = useSkillStore((s) => s.addItem);
    const updateItem = useSkillStore((s) => s.updateItem);

    // Check if this is a code-based skill (read-only)
    const isCodeSkill = skill?.source === 'code';

    const isResourceMySkillsPath = (p?: string | null) => {
        if (!p) return false;
        const norm = String(p).replace(/\\/g, '/');
        return norm.includes('/resource/my_skills/') || norm.startsWith('resource/my_skills/');
    };

    // ScrollPositionSave
    const scrollContainerRef = useRef<HTMLDivElement>(null);
    const savedScrollPositionRef = useRef<number>(0);

    const [form] = Form.useForm<ExtendedSkill>();
    const [editMode, setEditMode] = React.useState(isNew);
    const [publishLoading, setPublishLoading] = React.useState(false);
    const [subscribeLoading, setSubscribeLoading] = React.useState(false);

    const ownerValue = String(((skill as any)?.owner ?? '')).trim();
    const usernameValue = String((username ?? '')).trim();
    const skillSource = String(((skill as any)?.source ?? '')).trim().toLowerCase();
    const skillPathValue = String(((skill as any)?.path ?? '')).trim();
    const isUiSkill = skillSource === 'ui';
    const isOwnedByOwner = !!ownerValue && !!usernameValue && ownerValue.toLowerCase() === usernameValue.toLowerCase();
    const isOwnedByPath = isResourceMySkillsPath(skillPathValue);
    const isOwnedByUser = !!skill && !isNew && (isOwnedByOwner || isOwnedByPath || (isUiSkill && isOwnedByPath));
    // Skill owned by another user — editor cannot open (no writable local files)
    const isThirdPartySkill = !!skill && !isNew && !isOwnedByUser;
    const canPublish = isOwnedByUser && !isCodeSkill;
    const canEdit = isOwnedByUser && !isCodeSkill;
    const isPublished = !!skill && !isNew && !!(skill as any)?.public;
    const isSubscribed = !!skill && (() => {
        const subscribedSet = new Set((subscribedSkillIds || []).map((id) => String(id)));
        const skillId = String((skill as any)?.id ?? '').trim();
        const skillAskid = String((skill as any)?.askid ?? '').trim();
        return !!(
            (skillId && subscribedSet.has(skillId))
            || (skillAskid && skillAskid !== '0' && subscribedSet.has(skillAskid))
        );
    })();

    const handleTogglePublish = async () => {
        if (!skill || !username || !canPublish) return;
        setPublishLoading(true);
        try {
            const newPublicValue = !isPublished;
            const payload: Partial<Skill> = {
                id: skill.id,
                public: newPublicValue,
                rentable: newPublicValue,
            } as any;

            const api = get_ipc_api();
            const resp = await api.saveAgentSkill(username, payload as any);
            if (!resp.success) {
                message.error(resp.error?.message || t('pages.skills.failedToUpdatePublishStatus', 'Failed to update publish status'));
                return;
            }

            const updatedSkill = { ...skill, public: newPublicValue, rentable: newPublicValue } as any;
            updateItem(String(skill.id), updatedSkill);
            onSkillChange?.(updatedSkill);
            message.success(
                newPublicValue
                    ? t('pages.skills.publishedToStore', 'Published to Store')
                    : t('pages.skills.removedFromStore', 'Removed from Store')
            );
            if (onSave) onSave();
            else onRefresh();
        } catch (e) {
            if (e instanceof Error) message.error(e.message);
        } finally {
            setPublishLoading(false);
        }
    };

    const handleToggleSubscribe = async () => {
        if (!skill || !username) return;
        if (!onSubscribe || !onUnsubscribe) return;
        setSubscribeLoading(true);
        try {
            const skillId = String((skill as any)?.id ?? '');
            if (isSubscribed) {
                await onUnsubscribe(skillId);
                message.success(t('pages.skills.unsubscribed', 'Unsubscribed'));
            } else {
                await onSubscribe(skillId);
                message.success(t('pages.skills.subscribed', 'Subscribed'));
            }
        } catch (e) {
            if (e instanceof Error) message.error(e.message);
        } finally {
            setSubscribeLoading(false);
        }
    };

    React.useEffect(() => {
        if (skill) {
            const s = skill as ExtendedSkill;

            form.setFieldsValue({
                // BaseField
                id: s.id,
                askid: s.askid,
                name: s.name,
                owner: s.owner,
                description: s.description,
                version: s.version,
                path: s.path,
                level: s.level,

                // EC_Skill Field
                run_mode: s.run_mode || 'development',

                // ExtendedField
                price: s.price,
                price_model: s.price_model,
                public: s.public,
                rentable: s.rentable,

                extra_data: (s as any)?.extra_data,

                // JSON Field（Serialize为字符串）
                config_json: toJsonString(s.config),
                apps_json: toJsonString(s.apps),
                limitations_json: toJsonString(s.limitations),
                tags_json: toJsonString(s.tags),
                examples_json: toJsonString(s.examples),
                inputModes_json: toJsonString(s.inputModes),
                outputModes_json: toJsonString(s.outputModes),
                objectives_json: toJsonString(s.objectives),
                need_inputs_json: toJsonString(s.need_inputs),
                mapping_rules_json: toJsonString(s.mapping_rules),
            });
        } else if (isNew) {
            form.setFieldsValue({
                ...DEFAULT_SKILL,
                owner: username,
                version: '0.0.0',
                level: 'entry',
                run_mode: 'development',
                public: false,
                rentable: false,
                price: 0,
            } as any);
            setEditMode(true);
        } else {
            form.resetFields();
            setEditMode(false);
        }
    }, [skill, isNew, form, username]);

    const handleEdit = () => {
        setEditMode(true);
    };

    const handleCancel = () => {
        if (isNew) {
            // 新建模式：清空Form并Notification父ComponentClose面板
            form.resetFields();
            if (onCancel) {
                onCancel();
            }
        } else {
            // Edit模式：Restore原始Data并退出Edit模式（不Close面板）
            if (skill) {
                const s = skill as ExtendedSkill;
                form.setFieldsValue({
                    // BaseField
                    id: s.id,
                    askid: s.askid,
                    name: s.name,
                    owner: s.owner,
                    description: s.description,
                    version: s.version,
                    path: s.path,
                    level: s.level,

                    // EC_Skill Field
                    run_mode: s.run_mode || 'development',

                    // ExtendedField
                    price: s.price,
                    price_model: s.price_model,
                    public: s.public,
                    rentable: s.rentable,

                    extra_data: (s as any)?.extra_data,

                    // JSON Field（Serialize为字符串）
                    config_json: toJsonString(s.config),
                    apps_json: toJsonString(s.apps),
                    limitations_json: toJsonString(s.limitations),
                    tags_json: toJsonString(s.tags),
                    examples_json: toJsonString(s.examples),
                    inputModes_json: toJsonString(s.inputModes),
                    outputModes_json: toJsonString(s.outputModes),
                    objectives_json: toJsonString(s.objectives),
                    need_inputs_json: toJsonString(s.need_inputs),
                    mapping_rules_json: toJsonString(s.mapping_rules),
                });
            }
            setEditMode(false);
            // Edit模式下不调用 onCancel，保持面板Open
        }
    };

    const handleSave = async () => {
        try {
            const values = await form.validateFields();

            // 将 JSON 字符串FieldConvert回对象/数组
            const payload: Partial<Skill> = {
                // BaseField
                // NOTE: id/askid are DISPLAYED on the panel but have no
                // registered Form.Item, so antd's validateFields() omits
                // them — values.id is always undefined and the save then
                // fails "Skill ID is required for save operation". Source
                // identity from the skill prop (authoritative) instead.
                id: (values as any).id ?? (skill as any)?.id,
                askid: (values as any).askid ?? (skill as any)?.askid,
                name: (values as any).name ?? (skill as any)?.name,
                owner: username,
                description: values.description,
                version: values.version,
                path: values.path,
                level: values.level,

                // EC_Skill Field
                run_mode: values.run_mode,

                // ExtendedField
                price: values.price,
                price_model: values.price_model,
                public: values.public,
                rentable: values.rentable,

                extra_data: (values as any).extra_data,

                // 反Serialize JSON Field
                config: fromJsonString(values.config_json || ''),
                apps: fromJsonString(values.apps_json || ''),
                limitations: fromJsonString(values.limitations_json || ''),
                tags: fromJsonString(values.tags_json || ''),
                examples: fromJsonString(values.examples_json || ''),
                inputModes: fromJsonString(values.inputModes_json || ''),
                outputModes: fromJsonString(values.outputModes_json || ''),
                objectives: fromJsonString(values.objectives_json || ''),
                need_inputs: fromJsonString(values.need_inputs_json || ''),
                mapping_rules: fromJsonString(values.mapping_rules_json || ''),
                diagram: skill?.diagram || {},
            };

            // Rename local folder if path indicates a local diagram and name changed
            // Standard approach: uses skillId to uniquely identify the DB record
            try {
                const currentPath = payload.path;
                const skillId = skill?.id;  // Get skill ID for reliable DB update
                const oldNameMatch = currentPath ? String(currentPath).replace(/\\/g, '/').match(/\/([^\/]+)_skill\/diagram_dir\//) : null;
                const oldName = oldNameMatch?.[1];
                const newName = payload.name;
                if (!isNew && currentPath && oldName && newName && oldName !== newName) {
                    const api = IPCAPI.getInstance();
                    // Pass skillId to ensure ID-based DB update
                    const resp = await api.renameSkill(oldName, newName, undefined, skillId);
                    if (resp.success && resp.data?.skillRoot) {
                        const newRoot: string = String(resp.data.skillRoot).replace(/\\/g, '/');
                        // update diagram path in payload to reflect rename
                        payload.path = `${newRoot}/diagram_dir/${newName}_skill.json`;
                    }
                }
            } catch (e) {
                // eslint-disable-next-line no-console
                console.warn('[Skills] rename flow skipped or failed', e);
            }

            const api = get_ipc_api();
            const resp = isNew
                ? await api.newAgentSkill(username, payload as any)
                : await api.saveAgentSkill(username, payload as any);
            if (resp.success) {
                // Merge returned id/data for immediate UI update
                const returned = (resp.data as any) || {};
                const newId = returned.skill_id || returned.id || payload.id;
                const merged: any = { ...payload };
                if (newId) merged.id = newId;

                try {
                    if (isNew) {
                        // Add to local store for immediate feedback
                        addItem(merged as any);
                        // reflect id in form
                        form.setFieldValue('id', merged.id);
                    } else if (merged.id) {
                        updateItem(String(merged.id), merged as any);
                    }
                } catch (e) {
                    console.warn('Failed to update store:', e);
                }

                message.success(t('common.saved'));
                setEditMode(false);
                if (onSave) onSave();
                else onRefresh();
            } else {
                message.error(resp.error?.message || 'Save failed');
            }
        } catch (e) {
            // validation or request error
            if (e instanceof Error) {
                message.error(e.message);
            }
        }
    };

    const goToEditor = () => {
        if (!skill) return;

        // Get the file path from form or skill object
        const filePath = form.getFieldValue('path') || (skill as any).path;

        const previewMode = isCodeSkill && isResourceMySkillsPath(filePath);

        if (!filePath) {
            message.warning(t('pages.skills.noPathWarning', 'This skill has no associated file path'));
            return;
        }

        if (isThirdPartySkill) {
            message.warning(t('pages.skills.thirdPartySkillNoEditor', 'This skill was published by another user and cannot be opened in the editor'));
            return;
        }

        // Navigate to skill editor with file path
        navigate('/skill_editor', {
            state: {
                filePath: filePath,
                skillId: (skill as any).id,
                previewMode
            }
        });
    };

    const goToEditorAndRun = () => {
        if (!skill) return;
        const filePath = form.getFieldValue('path') || (skill as any).path;
        if (!filePath) {
            message.warning(t('pages.skills.noPathWarning', 'This skill has no associated file path'));
            return;
        }
        if (isThirdPartySkill) {
            message.warning(t('pages.skills.thirdPartySkillNoEditor', 'This skill was published by another user and cannot be opened in the editor'));
            return;
        }
        // Navigate to skill editor with run=true flag
        navigate('/skill_editor', {
            state: {
                filePath: filePath,
                skillId: (skill as any).id,
                previewMode: isCodeSkill && isResourceMySkillsPath(filePath),
                autoRun: true
            }
        });
    };

    const handleDelete = () => {
        if (!skill || !username) return;

        logger.info('[SkillDetails] handleDelete called', {
            skillId: String((skill as any)?.id),
            skillIdType: typeof (skill as any)?.id,
            skillName: (skill as any)?.name,
        });

        showDeleteConfirm({
            title: t('pages.skills.deleteSkill', 'Delete Skill'),
            message: t('pages.skills.deleteConfirmMessage', `Are you sure you want to delete "${(skill as any)?.name}"? This action cannot be undone.`),
            okText: t('common.delete', 'Delete'),
            cancelText: t('common.cancel', 'Cancel'),
            onOk: async () => {
                try {
                    logger.info('[SkillDetails] Confirm delete skill', {
                        selectedSkillId: String((skill as any)?.id || ''),
                        selectedSkillName: String((skill as any)?.name || ''),
                        selectedSkillOwner: String((skill as any)?.owner || ''),
                        username,
                    });
                    const api = get_ipc_api();
                    const skillId = String((skill as any).id);
                    logger.info('[SkillDetails] Calling deleteAgentSkill', { username, skillId });
                    const resp = await api.deleteAgentSkill(username, skillId);
                    const deleteResult = resp.data;
                    const deleteSucceeded = Boolean(
                        resp.success && (
                            deleteResult?.db_deleted ||
                            deleteResult?.mem_deleted ||
                            deleteResult?.file_deleted ||
                            deleteResult?.cloud_deleted ||
                            deleteResult?.cloud_cached ||
                            // API call succeeded but skill not found anywhere = already gone, treat as success
                            deleteResult?.message?.includes('not found')
                        )
                    );
                    logger.info('[SkillDetails] deleteAgentSkill response', {
                        outerSuccess: resp.success,
                        skillId,
                        deleteResult,
                    });
                    
                    if (deleteSucceeded) {
                        message.success(t('pages.skills.deleteSuccess', 'Skill deleted successfully'));
                        // Remove from store
                        const removeItem = useSkillStore.getState().removeItem;
                        logger.info('[SkillDetails] Before removeItem, store items:', {
                            skillId,
                            storeItemsCount: useSkillStore.getState().items.length,
                            storeItems: useSkillStore.getState().items.map((s: any) => `${s.name}#${s.id}`),
                        });
                        removeItem(skillId);
                        logger.info('[SkillDetails] After removeItem, store items:', {
                            skillId,
                            storeItemsCount: useSkillStore.getState().items.length,
                            storeItems: useSkillStore.getState().items.map((s: any) => `${s.name}#${s.id}`),
                            stillHasDeletedSkill: useSkillStore.getState().items.some((s: any) => s.id === skillId || String(s.id) === skillId),
                        });
                        // Call onDelete callback to close detail page
                        if (onDelete) {
                            onDelete();
                        } else {
                            // Fallback to refresh if no onDelete callback
                            onRefresh();
                        }
                    } else {
                        const errorMessage =
                            deleteResult?.cloud_error ||
                            deleteResult?.message ||
                            resp.error?.message ||
                            t('pages.skills.deleteError', 'Failed to delete skill');
                        message.error(errorMessage);
                    }
                } catch (error) {
                    console.error('[SkillDetails] Delete error:', error);
                    message.error(t('pages.skills.deleteError', 'Failed to delete skill'));
                }
            },
        });
    };

    if (!skill && !isNew) {
        return <Text type="secondary">{t('pages.skills.selectSkill')}</Text>;
    }

    // Derive safe display values to avoid accessing properties on null during new creation
    const name = (isNew ? form.getFieldValue('name') : (skill as any)?.name) || '';
    const description = (isNew ? form.getFieldValue('description') : (skill as any)?.description) || '';
    const status = (isNew ? 'planned' : (skill as any)?.status) || 'planned';
    const category = (isNew ? 'general' : (skill as any)?.category) || 'general';
    // Map skill level enum string to a proficiency percentage for display
    const LEVEL_PERCENT: Record<string, number> = {
        entry: 33,
        intermediate: 66,
        advanced: 100,
    };
    const rawLevel = (isNew ? (form.getFieldValue('level') || 'entry') : (skill as any)?.level) || 'entry';
    const levelVal = typeof rawLevel === 'number' ? rawLevel : (LEVEL_PERCENT[String(rawLevel).toLowerCase()] ?? 33);

    // Define tabs items using modern API
    const tabItems: TabsProps['items'] = [
        {
            key: 'basic',
            label: <span><SettingOutlined /> {t('pages.skills.tabs.basic', 'BaseInformation')}</span>,
            children: isNew ? (
                <Space direction="vertical" size={16} style={{ width: '100%' }}>
                    <StyledFormItem
                        label={t('common.name', 'Name')}
                        name="name"
                        rules={[{ required: true, message: t('pages.skills.nameRequired', 'Skill name is required') }]}
                    >
                        <Input
                            placeholder={t('pages.skills.namePlaceholder', '输入技能名称')}
                            maxLength={100}
                        />
                    </StyledFormItem>
                    <StyledFormItem
                        label={t('common.description', 'Description')}
                        name="description"
                    >
                        <TextArea
                            rows={3}
                            placeholder={t('pages.skills.descriptionPlaceholder', '简要描述这个技能的功能和用途')}
                        />
                    </StyledFormItem>
                    <StyledFormItem
                        label={t('pages.skills.level', 'Level')}
                        name="level"
                        initialValue="entry"
                    >
                        <Select placeholder={t('pages.skills.levelPlaceholder', '选择技能难度')}>
                            <Select.Option value="entry">{t('pages.skills.levels.entry', 'Entry')}</Select.Option>
                            <Select.Option value="intermediate">{t('pages.skills.levels.intermediate', 'Intermediate')}</Select.Option>
                            <Select.Option value="advanced">{t('pages.skills.levels.advanced', 'Advanced')}</Select.Option>
                            <Select.Option value="expert">{t('pages.skills.levels.expert', 'Expert')}</Select.Option>
                        </Select>
                    </StyledFormItem>
                    <StyledFormItem
                        label={t('pages.skills.tags', 'Tags')}
                        name="tags_json"
                        help={t('pages.skills.tagsHelp', 'Press Enter or click +Add to add tags')}
                    >
                        <TagInput
                            value={form.getFieldValue('tags_json') || ''}
                            onChange={(val) => form.setFieldValue('tags_json', val)}
                        />
                    </StyledFormItem>
                </Space>
            ) : (
                <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
                    {/* Identity + Meta compact card */}
                    <div style={{
                        display: 'grid',
                        gridTemplateColumns: '1fr 1fr 1fr 1fr',
                        gap: 8,
                        padding: '10px 14px',
                        background: 'rgba(255,255,255,0.03)',
                        border: '1px solid rgba(255,255,255,0.06)',
                        borderRadius: 8,
                    }}>
                        <div>
                            <div style={{ fontSize: 9, color: 'rgba(255,255,255,0.35)', textTransform: 'uppercase', letterSpacing: 0.6, marginBottom: 3 }}>{t('common.name', 'Name')}</div>
                            <Text style={{ fontSize: 12, color: 'rgba(255,255,255,0.9)', fontWeight: 500 }}>{(skill as any)?.name || '—'}</Text>
                        </div>
                        <div>
                            <div style={{ fontSize: 9, color: 'rgba(255,255,255,0.35)', textTransform: 'uppercase', letterSpacing: 0.6, marginBottom: 3 }}>{t('common.owner', 'Owner')}</div>
                            <Space size={4}>
                                <Avatar size={14} style={{ background: colorFromString((skill as any)?.owner), fontSize: 8, fontWeight: 700 }}>
                                    {getInitials((skill as any)?.owner)}
                                </Avatar>
                                <Text style={{ fontSize: 12, color: 'rgba(255,255,255,0.9)' }}>{(skill as any)?.owner || '—'}</Text>
                            </Space>
                        </div>
                        <div>
                            <div style={{ fontSize: 9, color: 'rgba(255,255,255,0.35)', textTransform: 'uppercase', letterSpacing: 0.6, marginBottom: 3 }}>{t('pages.skills.version', 'Version')}</div>
                            <Tag style={{ margin: 0, background: 'rgba(255,255,255,0.06)', border: 'none', color: 'rgba(255,255,255,0.7)', fontFamily: 'monospace', fontSize: 11, padding: '0 6px', lineHeight: '16px' }}>
                                v{(skill as any)?.version || '0.0.0'}
                            </Tag>
                        </div>
                        <div>
                            <div style={{ fontSize: 9, color: 'rgba(255,255,255,0.35)', textTransform: 'uppercase', letterSpacing: 0.6, marginBottom: 3 }}>{t('pages.skills.level', 'Level')}</div>
                            <Text style={{ fontSize: 12, color: 'rgba(255,255,255,0.9)' }}>
                                {t(`pages.skills.levels.${(skill as any)?.level || 'entry'}`, String((skill as any)?.level || 'entry'))}
                            </Text>
                        </div>
                        <div style={{ gridColumn: '1 / -1', marginTop: 2 }}>
                            <div style={{ fontSize: 9, color: 'rgba(255,255,255,0.35)', textTransform: 'uppercase', letterSpacing: 0.6, marginBottom: 3 }}>ID</div>
                            <Text
                                copyable={(skill as any)?.id ? { text: String((skill as any).id) } : false}
                                style={{ fontSize: 11, color: 'rgba(255,255,255,0.7)', fontFamily: 'monospace' }}
                            >
                                {String((skill as any)?.id || '—')}
                            </Text>
                        </div>
                    </div>

                    {/* Description */}
                    <StyledFormItem label={t('common.description', 'Description')} name="description" style={{ marginBottom: 0 }}>
                        <TextArea
                            rows={2}
                            placeholder={t('pages.skills.descriptionPlaceholder', 'Enter skill description')}
                        />
                    </StyledFormItem>

                    {/* Objectives */}
                    {(() => {
                        const objs = (() => {
                            try {
                                const raw = (skill as any)?.objectives;
                                if (Array.isArray(raw)) return raw;
                                if (typeof raw === 'string') {
                                    const parsed = JSON.parse(raw);
                                    return Array.isArray(parsed) ? parsed : [];
                                }
                            } catch { /* ignore */ }
                            return [];
                        })();
                        if (objs.length === 0) return null;
                        return (
                            <SectionCard icon={<BulbOutlined />} title={t('pages.skills.objectives', 'Objectives')} accent="#faad14" style={{ marginBottom: 0 }}>
                                <ul style={{ margin: 0, padding: 0, listStyle: 'none', display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0 16px' }}>
                                    {objs.map((o: string, i: number) => (
                                        <li key={i} style={{ display: 'flex', gap: 6, padding: '3px 0', borderBottom: i < objs.length - 1 ? '1px solid rgba(255,255,255,0.04)' : 'none' }}>
                                            <CheckCircleOutlined style={{ color: '#52c41a', marginTop: 2, flexShrink: 0, fontSize: 12 }} />
                                            <Text style={{ color: 'rgba(255,255,255,0.85)', fontSize: 12, lineHeight: 1.5 }}>{o}</Text>
                                        </li>
                                    ))}
                                </ul>
                            </SectionCard>
                        );
                    })()}

                    {/* Examples */}
                    {(() => {
                        const examples = (() => {
                            try {
                                const raw = (skill as any)?.examples;
                                if (Array.isArray(raw)) return raw;
                                if (typeof raw === 'string') {
                                    const parsed = JSON.parse(raw);
                                    return Array.isArray(parsed) ? parsed : [];
                                }
                            } catch { /* ignore */ }
                            return [];
                        })();
                        if (examples.length === 0) return null;
                        return (
                            <SectionCard icon={<ExperimentOutlined />} title={t('pages.skills.examples', 'Usage Examples')} accent="#1890ff" style={{ marginBottom: 0 }}>
                                <Space direction="vertical" size={3} style={{ width: '100%' }}>
                                    {examples.slice(0, 3).map((ex: string, i: number) => (
                                        <div key={i} style={{
                                            padding: '4px 8px',
                                            background: 'rgba(24,144,255,0.06)',
                                            border: '1px solid rgba(24,144,255,0.12)',
                                            borderRadius: 4,
                                            fontFamily: 'monospace',
                                            fontSize: 11,
                                            color: 'rgba(255,255,255,0.8)',
                                            overflow: 'hidden',
                                            textOverflow: 'ellipsis',
                                            whiteSpace: 'nowrap',
                                        }}>
                                            {ex}
                                        </div>
                                    ))}
                                </Space>
                            </SectionCard>
                        );
                    })()}

                    {/* Tags */}
                    {(() => {
                        const tags = (() => {
                            const raw = (skill as any)?.tags;
                            if (Array.isArray(raw)) return raw;
                            if (typeof raw === 'string') {
                                try {
                                    const parsed = JSON.parse(raw);
                                    return Array.isArray(parsed) ? parsed : [];
                                } catch { return []; }
                            }
                            return [];
                        })();
                        if (tags.length === 0) return null;
                        return (
                            <SectionCard icon={<TagsOutlined />} title={t('pages.skills.tags', 'Tags')} accent="#722ed1" style={{ marginBottom: 0 }}>
                                <Space size={[4, 4]} wrap>
                                    {tags.map((tag: string, i: number) => (
                                        <Tag key={i} style={{
                                            background: 'rgba(114,46,209,0.1)',
                                            border: '1px solid rgba(114,46,209,0.25)',
                                            color: '#b37feb',
                                            borderRadius: 4,
                                            padding: '0 6px',
                                            margin: 0,
                                            fontSize: 11,
                                            lineHeight: '18px',
                                        }}>{tag}</Tag>
                                    ))}
                                </Space>
                            </SectionCard>
                        );
                    })()}
                </div>
            ),
        },
        {
            key: 'config',
            label: <span><CodeOutlined /> {t('pages.skills.tabs.config', 'Configuration')}</span>,
            children: (
                <Row gutter={[16, 8]}>
                    <Col span={24}>
                        <StyledFormItem
                            label={t('pages.skills.config', 'Config (JSON)')}
                            name="config_json"
                            help={t('pages.skills.configHelp', 'Enter valid JSON configuration')}
                            validateTrigger={['onChange', 'onBlur']}
                            rules={[validateJSON(t)]}
                            style={{ marginBottom: 0 }}
                        >
                            <TextArea
                                rows={6}
                                placeholder='{"key": "value"}'
                                style={{ fontFamily: 'monospace', fontSize: '12px', lineHeight: '1.6' }}
                            />
                        </StyledFormItem>
                    </Col>
                    <Col span={24}>
                        <StyledFormItem
                            label={t('pages.skills.mappingRules', 'Mapping Rules (JSON)')}
                            name="mapping_rules_json"
                            help={t('pages.skills.mappingRulesHelp', 'State mapping rules for resume/event handling')}
                            validateTrigger={['onChange', 'onBlur']}
                            rules={[validateJSON(t)]}
                            style={{ marginBottom: 0 }}
                        >
                            <TextArea
                                rows={6}
                                placeholder='{"developing": {"mappings": [...]}}'
                                style={{ fontFamily: 'monospace', fontSize: '12px', lineHeight: '1.6' }}
                            />
                        </StyledFormItem>
                    </Col>
                </Row>
            ),
        },
        {
            key: 'metadata',
            label: <span><TagsOutlined /> {t('pages.skills.tabs.meta', 'Metadata')}</span>,
            children: (
                <Row gutter={[16, 8]}>
                    <Col span={24}>
                        <Form.Item noStyle shouldUpdate>
                          {({ getFieldValue }) => {
                            const tagsValue = getFieldValue('tags_json') || '';
                            return (
                              <StyledFormItem
                                label={t('pages.skills.tags', 'Tags')}
                                name="tags_json"
                                help={t('pages.skills.tagsHelp', 'Press Enter or click +Add to add tags')}
                                style={{ marginBottom: 0 }}
                              >
                                <TagInput
                                  value={tagsValue}
                                  onChange={(val) => form.setFieldValue('tags_json', val)}
                                />
                              </StyledFormItem>
                            );
                          }}
                        </Form.Item>
                    </Col>
                    <Col span={24}>
                        <StyledFormItem
                            label={t('pages.skills.examples', 'Examples')}
                            name="examples_json"
                            help={t('pages.skills.examplesHelp', 'Usage examples — click to add')}
                            style={{ marginBottom: 0 }}
                        >
                            <StringArrayInput
                                value={form.getFieldValue('examples_json') || '[]'}
                                onChange={(val) => form.setFieldValue('examples_json', val)}
                                placeholder={t('pages.skills.examplesPlaceholder', 'Type example and press Enter')}
                            />
                        </StyledFormItem>
                    </Col>
                    <Col span={12}>
                        <StyledFormItem
                            label={t('pages.skills.inputModes', 'Input Modes')}
                            name="inputModes_json"
                            help={t('pages.skills.inputModesHelp', 'Click to select')}
                            style={{ marginBottom: 0 }}
                        >
                            <ModeSelector
                                value={form.getFieldValue('inputModes_json') || '[]'}
                                onChange={(val) => form.setFieldValue('inputModes_json', val)}
                            />
                        </StyledFormItem>
                    </Col>
                    <Col span={12}>
                        <StyledFormItem
                            label={t('pages.skills.outputModes', 'Output Modes')}
                            name="outputModes_json"
                            help={t('pages.skills.inputModesHelp', 'Click to select')}
                            style={{ marginBottom: 0 }}
                        >
                            <ModeSelector
                                value={form.getFieldValue('outputModes_json') || '[]'}
                                onChange={(val) => form.setFieldValue('outputModes_json', val)}
                            />
                        </StyledFormItem>
                    </Col>
                    <Col span={24}>
                        <StyledFormItem
                            label={t('pages.skills.objectives', 'Objectives')}
                            name="objectives_json"
                            help={t('pages.skills.objectivesHelp', 'Goals this skill aims to achieve')}
                            style={{ marginBottom: 0 }}
                        >
                            <StringArrayInput
                                value={form.getFieldValue('objectives_json') || '[]'}
                                onChange={(val) => form.setFieldValue('objectives_json', val)}
                                placeholder={t('pages.skills.objectivesPlaceholder', 'Type objective and press Enter')}
                            />
                        </StyledFormItem>
                    </Col>
                    <Col span={24}>
                        <StyledFormItem
                            label={t('pages.skills.needInputs', 'Required Inputs')}
                            name="need_inputs_json"
                            help={t('pages.skills.needInputsHelp', 'Define parameters this skill expects')}
                            style={{ marginBottom: 0 }}
                        >
                            <NeedInputsEditor
                                value={form.getFieldValue('need_inputs_json') || '[]'}
                                onChange={(val) => form.setFieldValue('need_inputs_json', val)}
                            />
                        </StyledFormItem>
                    </Col>
                </Row>
            ),
        },
        {
            key: 'extended',
            label: <span><AppstoreOutlined /> {t('pages.skills.tabs.extended', 'Publishing & Pricing')}</span>,
            children: (
                <Row gutter={[16, 8]}>
                    <Col span={24}>
                        <StyledFormItem
                            label={t('pages.skills.limitations', 'Limitations')}
                            name="limitations_json"
                            help={t('pages.skills.limitationsHelp', 'Known limitations or constraints')}
                            style={{ marginBottom: 0 }}
                        >
                            <StringArrayInput
                                value={form.getFieldValue('limitations_json') || '[]'}
                                onChange={(val) => form.setFieldValue('limitations_json', val)}
                                placeholder={t('pages.skills.limitationsPlaceholder', 'Type limitation and press Enter')}
                            />
                        </StyledFormItem>
                    </Col>
                    <Col span={8}>
                        <StyledFormItem label={t('pages.skills.price', 'Price')} name="price" style={{ marginBottom: 0 }}>
                            <Input type="number" min={0} placeholder="0" />
                        </StyledFormItem>
                    </Col>
                    <Col span={8}>
                        <StyledFormItem label={t('pages.skills.priceModel', 'Price Model')} name="price_model" style={{ marginBottom: 0 }}>
                            <Input placeholder={t('pages.skills.priceModelPlaceholder', 'e.g., per-use, subscription')} />
                        </StyledFormItem>
                    </Col>
                    <Col span={8}>
                        <div style={{ marginTop: 32 }}>
                            <Space size={24}>
                                <StyledFormItem name="public" valuePropName="checked" noStyle>
                                    <Checkbox>{t('pages.skills.public', 'Public')}</Checkbox>
                                </StyledFormItem>
                                <StyledFormItem name="rentable" valuePropName="checked" noStyle>
                                    <Checkbox>{t('pages.skills.rentable', 'Rentable')}</Checkbox>
                                </StyledFormItem>
                            </Space>
                        </div>
                    </Col>
                </Row>
            ),
        },
        {
            key: 'reviews',
            label: <span><StarOutlined /> {t('pages.skills.tabs.reviews', 'Reviews')}</span>,
            children: !isNew ? (
                <SkillReviewPanel
                    skillId={String(skill?.id || '')}
                    username={username}
                    owner={String((skill as any)?.owner || '')}
                />
            ) : (
                <Text type="secondary">{t('pages.skills.reviews.notAvailableNew', 'Reviews are available after saving the skill')}</Text>
            ),
        },
        {
            key: 'activity',
            label: <span><DownloadOutlined /> {t('pages.skills.tabs.activity', 'Activity')}</span>,
            children: !isNew && skill ? (
                <Space direction="vertical" size={16} style={{ width: '100%' }}>
                    <SkillChangelog skill={skill} canEdit={canEdit} />
                    <SkillSimilar
                        skill={skill}
                        onOpenSkill={(s) => {
                            if (onSkillChange) onSkillChange(s);
                        }}
                    />
                    <SkillAuthorPanel
                        skill={skill}
                        onOpenSkill={(s) => {
                            if (onSkillChange) onSkillChange(s);
                        }}
                    />
                </Space>
            ) : (
                <Text type="secondary">{t('pages.skills.activity.notAvailableNew', 'Activity is available after saving the skill')}</Text>
            ),
        },
    ];

    // Direct DOM override of antd Tabs internal padding — survives CSS priority issues
    useLayoutEffect(() => {
        const root = document.querySelector('[data-skills-details]');
        if (!root) return;
        const tabContainer = root.querySelector('.ant-tabs');
        if (!tabContainer) return;
        const contentHolder = tabContainer.querySelector('.ant-tabs-content-holder') as HTMLElement | null;
        const content = tabContainer.querySelector('.ant-tabs-content') as HTMLElement | null;
        const panes = tabContainer.querySelectorAll('.ant-tabs-tabpane');
        if (contentHolder) contentHolder.style.paddingTop = '0';
        if (content) content.style.paddingTop = '0';
        panes.forEach(p => { (p as HTMLElement).style.paddingTop = '0'; });
        const nav = tabContainer.querySelector('.ant-tabs-nav') as HTMLElement | null;
        if (nav) nav.style.marginBottom = '0';
    }, []);

    // 使用 useEffectOnActive 在ComponentActive时RestoreScrollPosition
    useEffectOnActive(
        () => {
            const container = scrollContainerRef.current;
            if (container && savedScrollPositionRef.current > 0) {
                requestAnimationFrame(() => {
                    container.scrollTop = savedScrollPositionRef.current;
                });
            }
            
            return () => {
                const container = scrollContainerRef.current;
                if (container) {
                    savedScrollPositionRef.current = container.scrollTop;
                }
            };
        },
        []
    );

    return (
        <div style={{ position: 'relative', height: '100%', display: 'flex', flexDirection: 'column', background: 'var(--bg-primary)' }}>
            {/* Compact antd Tabs content padding inside SkillDetails */}
            <style>{`
                [data-skills-details] .ant-tabs-content-holder {
                    padding-top: 0 !important;
                }
                [data-skills-details] .ant-tabs-content {
                    padding-top: 0 !important;
                }
                [data-skills-details] .ant-tabs-tabpane {
                    padding: 10px 0 0 !important;
                }
            `}</style>
            <div data-skills-details>
            <FormContainer ref={scrollContainerRef} style={{ flex: 1, overflowY: 'auto', padding: '12px 16px 12px' }}>
                <Space direction="vertical" style={{ width: '100%' }} size={12}>
                {/* Hero Header */}
                <div
                    style={{
                        position: 'relative',
                        padding: '16px 20px',
                        borderRadius: '12px',
                        background: 'linear-gradient(135deg, rgba(24, 144, 255, 0.12) 0%, rgba(82, 196, 26, 0.08) 50%, rgba(114, 46, 209, 0.08) 100%)',
                        border: '1px solid rgba(255, 255, 255, 0.08)',
                        overflow: 'hidden',
                    }}
                >
                    {/* decorative gradient orbs */}
                    <div style={{
                        position: 'absolute', top: -50, right: -40, width: 160, height: 160, borderRadius: '50%',
                        background: 'radial-gradient(circle, rgba(24,144,255,0.18) 0%, transparent 70%)', pointerEvents: 'none',
                    }} />
                    <div style={{
                        position: 'absolute', bottom: -60, left: '40%', width: 200, height: 200, borderRadius: '50%',
                        background: 'radial-gradient(circle, rgba(82,196,26,0.10) 0%, transparent 70%)', pointerEvents: 'none',
                    }} />

                    <div style={{ position: 'relative', display: 'flex', gap: 14, alignItems: 'flex-start' }}>
                        {/* Icon */}
                        <div
                            style={{
                                width: 56, height: 56, borderRadius: 12, flexShrink: 0,
                                display: 'flex', alignItems: 'center', justifyContent: 'center',
                                fontSize: 26, color: '#fff',
                                background: `linear-gradient(135deg, ${(() => { const { bg } = getSkillIcon(skill || ({} as Skill)); return bg.join(', '); })()})`,
                                boxShadow: '0 6px 18px rgba(0, 0, 0, 0.25)',
                            }}
                        >
                            {(() => { const { icon } = getSkillIcon(skill || ({} as Skill)); return icon; })()}
                        </div>

                        {/* Title block */}
                        <div style={{ flex: 1, minWidth: 0 }}>
                            <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4, flexWrap: 'wrap' }}>
                                <Title level={4} style={{ color: 'white', margin: 0, lineHeight: 1.2, fontSize: 20 }}>
                                    {name || t('pages.skills.newSkill', 'New Skill')}
                                </Title>
                                {!isNew && (
                                    <Tag color={getStatusColor(status as any)} style={{ borderRadius: 20, border: 'none', fontWeight: 600, padding: '0 8px', margin: 0, fontSize: 11, lineHeight: '18px' }}>
                                        {t(`pages.skills.status.${status || 'unknown'}`, String(status || 'unknown'))}
                                    </Tag>
                                )}
                                <Tag style={{ borderRadius: 20, border: '1px solid rgba(255,255,255,0.15)', background: 'rgba(255,255,255,0.04)', color: 'rgba(255,255,255,0.85)', fontWeight: 500, padding: '0 8px', margin: 0, fontSize: 11, lineHeight: '18px' }}>
                                    <ThunderboltOutlined style={{ marginRight: 3 }} />
                                    {t(`pages.skills.categories.${category || 'unknown'}`, String(category || 'unknown'))}
                                </Tag>
                                {isCodeSkill && (
                                    <Tag color="orange" style={{ borderRadius: 20, border: 'none', fontWeight: 500, padding: '0 8px', margin: 0, fontSize: 11, lineHeight: '18px' }}>
                                        <LockOutlined style={{ marginRight: 3 }} />
                                        {t('pages.skills.codeSkillReadOnly', 'Code-based')}
                                    </Tag>
                                )}
                            </div>

                            <Text style={{ color: 'rgba(255, 255, 255, 0.7)', fontSize: 13, lineHeight: 1.5, display: 'block', marginBottom: 8 }}>
                                {description || t('pages.skills.noDescription', 'No description available')}
                            </Text>

                            {/* Meta row */}
                            <Space size={14} wrap>
                                {((skill as any)?.owner) && (
                                    <Space size={4}>
                                        <Avatar size={18} style={{ background: colorFromString((skill as any).owner), fontSize: 9, fontWeight: 600 }}>
                                            {getInitials((skill as any).owner)}
                                        </Avatar>
                                        <Text style={{ color: 'rgba(255,255,255,0.6)', fontSize: 12 }}>{(skill as any).owner}</Text>
                                    </Space>
                                )}
                                {((skill as any)?.version) && (
                                    <Space size={4}>
                                        <Tag style={{ margin: 0, background: 'rgba(255,255,255,0.06)', border: 'none', color: 'rgba(255,255,255,0.7)', fontFamily: 'monospace', fontSize: 11, padding: '0 6px', lineHeight: '18px' }}>
                                            v{(skill as any).version}
                                        </Tag>
                                    </Space>
                                )}
                                {!isNew && (skill as any)?.lastUsed && (
                                    <Space size={4}>
                                        <ClockCircleOutlined style={{ color: 'rgba(255,255,255,0.4)', fontSize: 12 }} />
                                        <Text style={{ color: 'rgba(255,255,255,0.6)', fontSize: 12 }}>{(skill as any).lastUsed}</Text>
                                    </Space>
                                )}
                                {!isNew && (skill as any)?.id && (
                                    <Text
                                        copyable={{ text: String((skill as any).id) }}
                                        style={{ color: 'rgba(255,255,255,0.45)', fontSize: 11, fontFamily: 'monospace' }}
                                    >
                                        ID: {String((skill as any).id)}
                                    </Text>
                                )}
                            </Space>
                        </div>

                        {/* Right: Level card */}
                        {!isNew && (
                            <div style={{
                                minWidth: 168,
                                padding: '10px 14px',
                                background: 'rgba(255, 255, 255, 0.04)',
                                borderRadius: 10,
                                border: '1px solid rgba(255, 255, 255, 0.08)',
                                backdropFilter: 'blur(10px)',
                            }}>
                                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 4 }}>
                                    <Text style={{ color: 'rgba(255,255,255,0.5)', fontSize: 10, textTransform: 'uppercase', letterSpacing: 0.5 }}>
                                        {t('pages.skills.proficiency', 'Proficiency')}
                                    </Text>
                                    <div style={{
                                        padding: '1px 8px',
                                        borderRadius: 8,
                                        background: (isNaN(levelVal) ? 0 : levelVal) >= 100
                                            ? 'linear-gradient(135deg, #52c41a, #73d13d)'
                                            : (isNaN(levelVal) ? 0 : levelVal) >= 66
                                            ? 'linear-gradient(135deg, #1890ff, #40a9ff)'
                                            : (isNaN(levelVal) ? 0 : levelVal) >= 33
                                            ? 'linear-gradient(135deg, #faad14, #ffc53d)'
                                            : 'linear-gradient(135deg, #8c8c8c, #bfbfbf)',
                                        color: 'white',
                                        fontSize: 9,
                                        fontWeight: 600,
                                    }}>
                                        {(isNaN(levelVal) ? 0 : levelVal) >= 100
                                            ? t('pages.skills.levelExpert', 'Expert')
                                            : (isNaN(levelVal) ? 0 : levelVal) >= 75
                                            ? t('pages.skills.levelAdvanced', 'Advanced')
                                            : (isNaN(levelVal) ? 0 : levelVal) >= 50
                                            ? t('pages.skills.levelIntermediate', 'Intermediate')
                                            : t('pages.skills.levelBeginner', 'Beginner')}
                                    </div>
                                </div>
                                <div style={{ display: 'flex', alignItems: 'baseline', gap: 4, marginBottom: 4 }}>
                                    <span style={{
                                        fontSize: 22, fontWeight: 700,
                                        background: 'linear-gradient(135deg, #1890ff, #52c41a)',
                                        WebkitBackgroundClip: 'text', WebkitTextFillColor: 'transparent',
                                        fontFamily: 'monospace', lineHeight: 1,
                                    }}>
                                        {isNaN(levelVal) ? 0 : levelVal}
                                    </span>
                                    <span style={{ fontSize: 12, color: 'rgba(255,255,255,0.4)', fontWeight: 500 }}>%</span>
                                </div>
                                <Progress
                                    percent={isNaN(levelVal) ? 0 : levelVal}
                                    status={(status as any) === 'learning' ? 'active' : 'normal'}
                                    strokeColor={{ '0%': '#1890ff', '50%': '#40a9ff', '100%': '#52c41a' }}
                                    trailColor="rgba(255, 255, 255, 0.08)"
                                    size={{ height: 4 }}
                                    showInfo={false}
                                    strokeLinecap="round"
                                />
                            </div>
                        )}
                    </div>

                    {/* Stat cards row */}
                    {!isNew && (
                        <div style={{
                            position: 'relative',
                            marginTop: 12,
                            display: 'grid',
                            gridTemplateColumns: 'repeat(5, 1fr)',
                            gap: 8,
                        }}>
                            {[
                                { icon: <StarOutlined />, label: t('pages.skills.rating', 'Rating'), value: Number((skill as any)?.rating ?? 5).toFixed(1), suffix: '/ 5', color: '#faad14' },
                                { icon: <DownloadOutlined />, label: t('pages.skills.downloads', 'Downloads'), value: Number((skill as any)?.downloadCount ?? 0), suffix: '', color: '#52c41a' },
                                { icon: <HeartOutlined />, label: t('pages.skills.favorites', 'Favorites'), value: Number((skill as any)?.favoriteCount ?? 0), suffix: '', color: '#ff4d4f' },
                                { icon: <TeamOutlined />, label: t('pages.skills.subscribers', 'Subscribers'), value: (skill as any)?.subscriberCount ?? 0, suffix: '', color: '#1890ff' },
                                { icon: <ThunderboltOutlined />, label: t('pages.skills.usageCount', 'Usage'), value: (skill as any)?.usageCount ?? 0, suffix: '', color: '#722ed1' },
                            ].map((s, idx) => (
                                <div key={idx} style={{
                                    padding: '8px 10px',
                                    background: 'rgba(255,255,255,0.04)',
                                    border: '1px solid rgba(255,255,255,0.06)',
                                    borderRadius: 8,
                                    display: 'flex', alignItems: 'center', gap: 8,
                                }}>
                                    <div style={{
                                        width: 26, height: 26, borderRadius: 8,
                                        background: `${s.color}20`,
                                        color: s.color,
                                        display: 'flex', alignItems: 'center', justifyContent: 'center',
                                        fontSize: 13,
                                        flexShrink: 0,
                                    }}>
                                        {s.icon}
                                    </div>
                                    <div style={{ minWidth: 0 }}>
                                        <div style={{ fontSize: 10, color: 'rgba(255,255,255,0.5)', textTransform: 'uppercase', letterSpacing: 0.4, lineHeight: 1.1 }}>{s.label}</div>
                                        <div style={{ fontSize: 14, color: '#fff', fontWeight: 600, lineHeight: 1.2, marginTop: 2, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                                            {String(s.value)}{s.suffix && <span style={{ fontSize: 11, color: 'rgba(255,255,255,0.4)', fontWeight: 400 }}> {s.suffix}</span>}
                                        </div>
                                    </div>
                                </div>
                            ))}
                        </div>
                    )}
                </div>


                {/* Details Form Card */}
                <StyledCard
                    title={
                        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', width: '100%' }}>
                            <Space size={6}>
                                <SettingOutlined style={{ color: '#1890ff' }} />
                                <span style={{ color: 'white' }}>{t('pages.skills.details', 'Skill Details')}</span>
                            </Space>
                            {!isNew && !isThirdPartySkill && (skill as any)?.path && (
                                <Button
                                    size="small"
                                    icon={<EditOutlined />}
                                    onClick={goToEditor}
                                    style={{
                                        border: '1px solid rgba(24,144,255,0.35)',
                                        background: 'rgba(24,144,255,0.08)',
                                        color: 'rgba(24,144,255,0.9)',
                                        fontSize: 12,
                                    }}
                                >
                                    {t('pages.skills.openEditor', 'Open Editor')}
                                </Button>
                            )}
                        </div>
                    }
                    styles={{ body: { padding: '0px 16px 8px' }, header: { padding: '6px 16px', minHeight: 'auto' } }}
                >
                    <Form form={form} layout="vertical" disabled={!editMode}>
                        <Tabs
                            defaultActiveKey="basic"
                            items={tabItems}
                            size="small"
                            tabBarStyle={{ color: 'white', margin: 0, borderBottom: '1px solid rgba(255,255,255,0.06)' }}
                            style={{ paddingTop: 0 }}
                        />
                    </Form>
                </StyledCard>

                {canPublish && (
                    <StyledCard
                        title={t('pages.skills.publishInfo', 'Publish Info')}
                        style={{
                            background: 'rgba(255, 255, 255, 0.02)',
                            border: '1px solid rgba(255, 255, 255, 0.06)'
                        }}
                    >
                        <Space direction="vertical" size={8} style={{ width: '100%' }}>
                            <Text style={{ color: 'rgba(255, 255, 255, 0.85)' }}>
                                {t('pages.skills.publishStatus', 'Status')}: {isPublished ? t('pages.skills.published', 'Published') : t('pages.skills.notPublished', 'Not published')}
                            </Text>
                        </Space>
                    </StyledCard>
                )}

                </Space>
            </FormContainer>
            
            {/* Fixed Action Buttons - Outside FormContainer, won't scroll */}
            <div style={{
                flexShrink: 0,
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
                gap: 12,
                padding: '10px 16px',
                background: 'rgba(15, 23, 42, 0.6)',
                backdropFilter: 'blur(12px)',
                borderTop: '1px solid rgba(255, 255, 255, 0.08)',
            }}>
                {/* Left: secondary / status hint */}
                <div>
                    {!editMode && !isNew && !isCodeSkill && canEdit && (
                        <Text style={{ color: 'rgba(255,255,255,0.45)', fontSize: 12 }}>
                            {isPublished
                                ? <><CheckCircleOutlined style={{ color: '#52c41a', marginRight: 4 }} />{t('pages.skills.published', 'Published')}</>
                                : <><InfoCircleOutlined style={{ marginRight: 4 }} />{t('pages.skills.notPublished', 'Not published')}</>}
                        </Text>
                    )}
                </div>

                <Space size={8}>
                {/* Edit模式Button */}
                {!isNew && editMode && (
                    <>
                        <Button
                            type="primary"
                            onClick={handleSave}
                            style={{ ...primaryButtonStyle, height: 36, minWidth: 88 }}
                            icon={<CheckCircleOutlined />}
                        >
                            {t('common.save', 'Save')}
                        </Button>
                        <Button
                            onClick={handleCancel}
                            style={{ ...buttonStyle, height: 36, minWidth: 80 }}
                        >
                            {t('common.cancel', 'Cancel')}
                        </Button>
                    </>
                )}

                {/* 新建模式Button */}
                {isNew && (
                    <>
                        <Button
                            type="primary"
                            onClick={handleSave}
                            style={{ ...primaryButtonStyle, height: 36, minWidth: 88 }}
                            icon={<CheckCircleOutlined />}
                        >
                            {t('common.create', 'Create')}
                        </Button>
                        <Button
                            onClick={handleCancel}
                            style={{ ...buttonStyle, height: 36, minWidth: 80 }}
                        >
                            {t('common.cancel', 'Cancel')}
                        </Button>
                    </>
                )}

                {/* 查看模式Button */}
                {!editMode && !isNew && (
                    <>
                        {isCodeSkill ? (
                            <Tooltip title={t('pages.skills.codeSkillCannotEdit', 'Code-based skills cannot be edited. Please modify the source code file instead.')}>
                                <Button
                                    icon={<LockOutlined />}
                                    disabled
                                    style={{ ...buttonStyle, height: 36, minWidth: 100 }}
                                >
                                    {t('pages.skills.readOnly', 'Read-only')}
                                </Button>
                            </Tooltip>
                        ) : canEdit ? (
                            <>
                                {/* Primary: Edit */}
                                <Button
                                    type="primary"
                                    icon={<EditOutlined />}
                                    onClick={handleEdit}
                                    style={{ ...primaryButtonStyle, height: 36, minWidth: 88 }}
                                >
                                    {t('pages.skills.edit', 'Edit')}
                                </Button>
                                {/* Secondary: Run */}
                                <Button
                                    icon={<PlayCircleOutlined />}
                                    onClick={goToEditorAndRun}
                                    style={{ ...buttonStyle, height: 36, minWidth: 80 }}
                                >
                                    {t('pages.skills.run', 'Run')}
                                </Button>
                                {/* More menu for less common actions */}
                                <Dropdown
                                    menu={{
                                        items: [
                                            canPublish ? {
                                                key: 'publish',
                                                icon: isPublished ? <DownloadOutlined /> : <UploadOutlined />,
                                                label: isPublished
                                                    ? t('pages.skills.removeFromStore', 'Remove from Store')
                                                    : t('pages.skills.publishToStore', 'Publish to Store'),
                                                onClick: handleTogglePublish,
                                                disabled: publishLoading,
                                            } : null,
                                            {
                                                key: 'delete',
                                                icon: <DeleteOutlined />,
                                                label: t('common.delete', 'Delete'),
                                                danger: true,
                                                onClick: handleDelete,
                                            },
                                        ].filter(Boolean) as any,
                                    }}
                                    placement="topRight"
                                >
                                    <Button icon={<MoreOutlined />} style={{ ...buttonStyle, height: 36, minWidth: 48 }} />
                                </Dropdown>
                            </>
                        ) : (
                            /* Non-owned public skill: subscribe / read-only */
                            <>
                                <Button
                                    type={isSubscribed ? 'default' : 'primary'}
                                    icon={isSubscribed ? <HeartOutlined /> : <DownloadOutlined />}
                                    onClick={handleToggleSubscribe}
                                    loading={subscribeLoading}
                                    style={isSubscribed
                                        ? { ...buttonStyle, height: 36, minWidth: 100, borderColor: '#faad14', color: '#faad14' }
                                        : { ...primaryButtonStyle, height: 36, minWidth: 100 }}
                                >
                                    {isSubscribed ? t('pages.skills.unsubscribe', 'Unsubscribe') : t('pages.skills.subscribe', 'Subscribe')}
                                </Button>
                                <Button
                                    icon={<PlayCircleOutlined />}
                                    onClick={goToEditorAndRun}
                                    disabled={isThirdPartySkill}
                                    style={{ ...buttonStyle, height: 36, minWidth: 80 }}
                                >
                                    {t('pages.skills.run', 'Run')}
                                </Button>
                                <Tooltip title={t('pages.skills.readOnlyPublic', 'This is a public skill. You can subscribe but not edit.')}>
                                    <Button
                                        icon={<LockOutlined />}
                                        disabled
                                        style={{ ...buttonStyle, height: 36, minWidth: 100 }}
                                    >
                                        {t('pages.skills.readOnly', 'Read-only')}
                                    </Button>
                                </Tooltip>
                            </>
                        )}
                    </>
                )}
                </Space>
            </div>
            </div>
        </div>
    );
};

export default SkillDetails;