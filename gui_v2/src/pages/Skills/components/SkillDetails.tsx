import React, { useRef } from 'react';
import { Typography, Space, Button, Progress, Tooltip, Tag, Form, Input, Row, Col, Checkbox, Select, Tabs, App } from 'antd';
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
} from '@ant-design/icons';
import { useTranslation } from 'react-i18next';
import type { Skill, SkillRunMode, SkillNeedInput } from '@/types/domain/skill';

import { useNavigate } from 'react-router-dom';
import { useSkillStore } from '@/stores';
import { get_ipc_api } from '@/services/ipc_api';
import { useUserStore } from '@/stores/userStore';
import { IPCWCClient } from '@/services/ipc/ipcWCClient';
import { StyledFormItem, StyledCard, FormContainer, buttonStyle, primaryButtonStyle } from '@/components/Common/StyledForm';
import { useDeleteConfirm } from '@/components/Common/DeleteConfirmModal';

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

interface SkillDetailsProps {
    skill: Skill | null;
    isNew?: boolean;
    onRefresh: () => void;
    onSave?: () => void;
    onCancel?: () => void;
    onDelete?: () => void;
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

const SkillDetails: React.FC<SkillDetailsProps> = ({ skill, isNew = false, onRefresh, onSave, onCancel, onDelete }) => {
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
                id: values.id,
                askid: values.askid,
                name: values.name,
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
            try {
                const currentPath = payload.path;
                const oldNameMatch = currentPath ? String(currentPath).replace(/\\/g, '/').match(/\/([^\/]+)_skill\/diagram_dir\//) : null;
                const oldName = oldNameMatch?.[1];
                const newName = payload.name;
                if (!isNew && currentPath && oldName && newName && oldName !== newName) {
                    const resp: any = await IPCWCClient.getInstance().sendRequest('skills.rename', { oldName, newName });
                    if (resp?.status === 'success' && resp.result?.skillRoot) {
                        const newRoot: string = String(resp.result.skillRoot).replace(/\\/g, '/');
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

                message.success(t('common.saved', 'Saved'));
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
            message.warning(t('pages.skills.noPathWarning', '该技能没有关联的文件Path'));
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

    const handleDelete = () => {
        if (!skill || !username) return;

        showDeleteConfirm({
            title: t('pages.skills.deleteConfirmTitle', 'Delete Skill'),
            message: t('pages.skills.deleteConfirmMessage', `Are you sure you want to delete "${(skill as any)?.name}"? This action cannot be undone.`),
            okText: t('common.delete', 'Delete'),
            cancelText: t('common.cancel', 'Cancel'),
            onOk: async () => {
                try {
                    const api = get_ipc_api();
                    const resp = await api.deleteAgentSkill(username, String((skill as any).id));
                    
                    if (resp.success) {
                        message.success(t('pages.skills.deleteSuccess', 'Skill deleted successfully'));
                        // Remove from store
                        const removeItem = useSkillStore.getState().removeItem;
                        removeItem(String((skill as any).id));
                        // Call onDelete callback to close detail page
                        if (onDelete) {
                            onDelete();
                        } else {
                            // Fallback to refresh if no onDelete callback
                            onRefresh();
                        }
                    } else {
                        message.error(resp.error?.message || t('pages.skills.deleteError', 'Failed to delete skill'));
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
    const levelVal = (isNew ? (form.getFieldValue('level') ?? 0) : (skill as any)?.level) || 0;

    // Define tabs items using modern API
    const tabItems: TabsProps['items'] = [
        {
            key: 'basic',
            label: <span><SettingOutlined /> {t('pages.skills.tabs.basic', 'BaseInformation')}</span>,
            children: (
                <Row gutter={[24, 0]}>
                    <Col span={12}>
                        <StyledFormItem label="ID" name="id">
                            <Input readOnly />
                        </StyledFormItem>
                    </Col>
                    {(!isNew && (skill as any)?.askid && String((skill as any).askid) !== String((skill as any).id)) && (
                        <Col span={12}>
                            <StyledFormItem label="DB ID" name="askid">
                                <Input readOnly />
                            </StyledFormItem>
                        </Col>
                    )}
                    <Col span={12}>
                        <StyledFormItem label={t('common.name', 'Name')} name="name" rules={[{ required: true }]}>
                            <Input placeholder={t('pages.skills.namePlaceholder', 'Enter skill name')} />
                        </StyledFormItem>
                    </Col>
                    <Col span={12}>
                        <StyledFormItem label={t('common.owner', 'Owner')} name="owner">
                            <Input readOnly />
                        </StyledFormItem>
                    </Col>
                    <Col span={24}>
                        <StyledFormItem label={t('common.description', 'Description')} name="description">
                            <TextArea
                                rows={4}
                                placeholder={t('pages.skills.descriptionPlaceholder', 'Enter skill description')}
                            />
                        </StyledFormItem>
                    </Col>
                    <Col span={8}>
                        <StyledFormItem label={t('pages.skills.version', 'Version')} name="version" rules={[{ required: true }]}>
                            <Input placeholder="0.0.0" />
                        </StyledFormItem>
                    </Col>
                    <Col span={8}>
                        <StyledFormItem label={t('pages.skills.level', 'Level')} name="level">
                            <Select>
                                <Select.Option value="entry">{t('pages.skills.levels.entry', 'Entry')}</Select.Option>
                                <Select.Option value="intermediate">{t('pages.skills.levels.intermediate', 'Intermediate')}</Select.Option>
                                <Select.Option value="advanced">{t('pages.skills.levels.advanced', 'Advanced')}</Select.Option>
                            </Select>
                        </StyledFormItem>
                    </Col>
                    <Col span={8}>
                        <StyledFormItem label={t('pages.skills.runMode', 'Run Mode')} name="run_mode">
                            <Select>
                                <Select.Option value="development">{t('pages.skills.runModes.development', 'Development')}</Select.Option>
                                <Select.Option value="released">{t('pages.skills.runModes.released', 'Released')}</Select.Option>
                            </Select>
                        </StyledFormItem>
                    </Col>
                    <Col span={24}>
                        <StyledFormItem label={t('pages.skills.path', 'Path')}>
                            <Space.Compact style={{ width: '100%' }}>
                                <Form.Item name="path" noStyle>
                                    <Input id="skill-path-input" readOnly placeholder={t('pages.skills.pathPlaceholder', 'Skill file path')} />
                                </Form.Item>
                                <Tooltip title={isCodeSkill && isResourceMySkillsPath(form.getFieldValue('path') || (skill as any)?.path)
                                    ? t('pages.skills.previewFile', '预览')
                                    : t('pages.skills.openEditor', 'Open in Editor')}>
                                    <Button
                                        icon={<FileTextOutlined />}
                                        onClick={goToEditor}
                                        disabled={!(form.getFieldValue('path') || (skill as any)?.path)}
                                    />
                                </Tooltip>
                            </Space.Compact>
                        </StyledFormItem>
                    </Col>
                </Row>
            ),
        },
        {
            key: 'config',
            label: <span><CodeOutlined /> {t('pages.skills.tabs.config', 'Configuration')}</span>,
            children: (
                <Row gutter={[24, 0]}>
                    <Col span={24}>
                        <StyledFormItem
                            label={t('pages.skills.config', 'Config (JSON)')}
                            name="config_json"
                            help={t('pages.skills.configHelp', 'Enter valid JSON configuration')}
                            validateTrigger={['onChange', 'onBlur']}
                            rules={[validateJSON(t)]}
                        >
                            <TextArea
                                rows={8}
                                placeholder='{"key": "value"}'
                                style={{ fontFamily: 'monospace', fontSize: '13px', lineHeight: '1.6' }}
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
                        >
                            <TextArea
                                rows={8}
                                placeholder='{"developing": {"mappings": [...]}}'
                                style={{ fontFamily: 'monospace', fontSize: '13px', lineHeight: '1.6' }}
                            />
                        </StyledFormItem>
                    </Col>
                </Row>
            ),
        },
        {
            key: 'metadata',
            label: <span><TagsOutlined /> {t('pages.skills.tabs.metadata', '元Data')}</span>,
            children: (
                <Row gutter={[24, 0]}>
                    <Col span={24}>
                        <StyledFormItem
                            label={t('pages.skills.tags', 'Tags (JSON Array)')}
                            name="tags_json"
                            help={t('pages.skills.tagsHelp', 'e.g., ["tag1", "tag2"]')}
                            validateTrigger={['onChange', 'onBlur']}
                            rules={[validateJSON(t)]}
                        >
                            <TextArea
                                rows={3}
                                placeholder='["automation", "data-processing"]'
                                style={{ fontFamily: 'monospace' }}
                            />
                        </StyledFormItem>
                    </Col>
                    <Col span={24}>
                        <StyledFormItem
                            label={t('pages.skills.examples', 'Examples (JSON Array)')}
                            name="examples_json"
                            help={t('pages.skills.examplesHelp', 'Usage examples')}
                            validateTrigger={['onChange', 'onBlur']}
                            rules={[validateJSON(t)]}
                        >
                            <TextArea
                                rows={4}
                                placeholder='["Example 1", "Example 2"]'
                                style={{ fontFamily: 'monospace' }}
                            />
                        </StyledFormItem>
                    </Col>
                    <Col span={12}>
                        <StyledFormItem
                            label={t('pages.skills.inputModes', 'Input Modes (JSON Array)')}
                            name="inputModes_json"
                            validateTrigger={['onChange', 'onBlur']}
                            rules={[validateJSON(t)]}
                        >
                            <TextArea
                                rows={3}
                                placeholder='["text", "file"]'
                                style={{ fontFamily: 'monospace' }}
                            />
                        </StyledFormItem>
                    </Col>
                    <Col span={12}>
                        <StyledFormItem
                            label={t('pages.skills.outputModes', 'Output Modes (JSON Array)')}
                            name="outputModes_json"
                            validateTrigger={['onChange', 'onBlur']}
                            rules={[validateJSON(t)]}
                        >
                            <TextArea
                                rows={3}
                                placeholder='["text", "json"]'
                                style={{ fontFamily: 'monospace' }}
                            />
                        </StyledFormItem>
                    </Col>
                    <Col span={24}>
                        <StyledFormItem
                            label={t('pages.skills.objectives', 'Objectives (JSON Array)')}
                            name="objectives_json"
                            help={t('pages.skills.objectivesHelp', 'Skill objectives/goals')}
                            validateTrigger={['onChange', 'onBlur']}
                            rules={[validateJSON(t)]}
                        >
                            <TextArea
                                rows={4}
                                placeholder='["Objective 1", "Objective 2"]'
                                style={{ fontFamily: 'monospace' }}
                            />
                        </StyledFormItem>
                    </Col>
                    <Col span={24}>
                        <StyledFormItem
                            label={t('pages.skills.needInputs', 'Required Inputs (JSON Array)')}
                            name="need_inputs_json"
                            help={t('pages.skills.needInputsHelp', 'Input parameters required by this skill')}
                            validateTrigger={['onChange', 'onBlur']}
                            rules={[validateJSON(t)]}
                        >
                            <TextArea
                                rows={6}
                                placeholder='[{"name": "param1", "type": "string", "required": true}]'
                                style={{ fontFamily: 'monospace' }}
                            />
                        </StyledFormItem>
                    </Col>
                </Row>
            ),
        },
        {
            key: 'extended',
            label: <span><AppstoreOutlined /> {t('pages.skills.tabs.extended', 'Extended')}</span>,
            children: (
                <Row gutter={[24, 0]}>
                    <Col span={24}>
                        <StyledFormItem
                            label={t('pages.skills.apps', 'Apps (JSON)')}
                            name="apps_json"
                            help={t('pages.skills.appsHelp', 'Related applications')}
                            validateTrigger={['onChange', 'onBlur']}
                            rules={[validateJSON(t)]}
                        >
                            <TextArea
                                rows={4}
                                placeholder='[{"name": "app1", "version": "1.0"}]'
                                style={{ fontFamily: 'monospace' }}
                            />
                        </StyledFormItem>
                    </Col>
                    <Col span={24}>
                        <StyledFormItem
                            label={t('pages.skills.limitations', 'Limitations (JSON)')}
                            name="limitations_json"
                            help={t('pages.skills.limitationsHelp', 'Known limitations')}
                            validateTrigger={['onChange', 'onBlur']}
                            rules={[validateJSON(t)]}
                        >
                            <TextArea
                                rows={4}
                                placeholder='["Limitation 1", "Limitation 2"]'
                                style={{ fontFamily: 'monospace' }}
                            />
                        </StyledFormItem>
                    </Col>
                    <Col span={8}>
                        <StyledFormItem label={t('pages.skills.price', 'Price')} name="price">
                            <Input type="number" min={0} placeholder="0" />
                        </StyledFormItem>
                    </Col>
                    <Col span={8}>
                        <StyledFormItem label={t('pages.skills.priceModel', 'Price Model')} name="price_model">
                            <Input placeholder={t('pages.skills.priceModelPlaceholder', 'e.g., per-use, subscription')} />
                        </StyledFormItem>
                    </Col>
                    <Col span={8}>
                        <StyledFormItem label=" " style={{ marginTop: '30px' }}>
                            <Space size={24}>
                                <StyledFormItem name="public" valuePropName="checked" noStyle>
                                    <Checkbox>{t('pages.skills.public', 'Public')}</Checkbox>
                                </StyledFormItem>
                                <StyledFormItem name="rentable" valuePropName="checked" noStyle>
                                    <Checkbox>{t('pages.skills.rentable', 'Rentable')}</Checkbox>
                                </StyledFormItem>
                            </Space>
                        </StyledFormItem>
                    </Col>
                </Row>
            ),
        },
    ];

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
        <div style={{ position: 'relative', height: '100%', display: 'flex', flexDirection: 'column' }}>
            <FormContainer ref={scrollContainerRef} style={{ flex: 1, overflowY: 'auto', paddingBottom: '20px' }}>
                <Space direction="vertical" style={{ width: '100%' }} size={24}>
                {/* Header Card */}
                <StyledCard
                    style={{
                        background: 'linear-gradient(135deg, rgba(24, 144, 255, 0.1) 0%, rgba(24, 144, 255, 0.05) 100%)',
                        border: '1px solid rgba(24, 144, 255, 0.2)'
                    }}
                >
                    <Space direction="vertical" style={{ width: '100%' }} size="middle">
                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: '24px' }}>
                            {/* Left：技能Information */}
                            <div style={{ flex: 1 }}>
                                <Title level={3} style={{ color: 'white', margin: 0, marginBottom: 8 }}>
                                    {name || t('pages.skills.newSkill', 'New Skill')}
                                </Title>
                                <Text style={{ color: 'rgba(255, 255, 255, 0.85)', fontSize: 14 }}>
                                    {description || t('pages.skills.noDescription', 'No description available')}
                                </Text>
                            </div>
                            
                            {/* Right：熟练度等级（仅非新建时Display）*/}
                            {!isNew && (
                                <div style={{ 
                                    minWidth: '280px',
                                    padding: '16px 20px',
                                    background: 'rgba(255, 255, 255, 0.03)',
                                    borderRadius: '12px',
                                    border: '1px solid rgba(255, 255, 255, 0.08)'
                                }}>
                                    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '12px' }}>
                                        <div style={{ display: 'flex', alignItems: 'baseline', gap: '6px' }}>
                                            <span style={{ 
                                                fontSize: '32px', 
                                                fontWeight: 800, 
                                                background: 'linear-gradient(135deg, #1890ff 0%, #52c41a 100%)',
                                                WebkitBackgroundClip: 'text',
                                                WebkitTextFillColor: 'transparent',
                                                fontFamily: 'monospace'
                                            }}>
                                                {isNaN(levelVal) ? 0 : levelVal}
                                            </span>
                                            <span style={{ fontSize: '16px', color: 'rgba(255, 255, 255, 0.45)', fontWeight: 500 }}>%</span>
                                        </div>
                                        <div style={{ 
                                            padding: '4px 12px', 
                                            borderRadius: '12px',
                                            background: (isNaN(levelVal) ? 0 : levelVal) === 100 
                                                ? 'linear-gradient(135deg, #52c41a 0%, #73d13d 100%)'
                                                : (isNaN(levelVal) ? 0 : levelVal) >= 75
                                                ? 'linear-gradient(135deg, #1890ff 0%, #40a9ff 100%)'
                                                : (isNaN(levelVal) ? 0 : levelVal) >= 50
                                                ? 'linear-gradient(135deg, #faad14 0%, #ffc53d 100%)'
                                                : 'linear-gradient(135deg, #8c8c8c 0%, #bfbfbf 100%)',
                                            color: 'white',
                                            fontSize: '11px',
                                            fontWeight: 600
                                        }}>
                                            {(isNaN(levelVal) ? 0 : levelVal) === 100 
                                                ? t('pages.skills.levelExpert', 'Expert')
                                                : (isNaN(levelVal) ? 0 : levelVal) >= 75
                                                ? t('pages.skills.levelAdvanced', 'Advanced')
                                                : (isNaN(levelVal) ? 0 : levelVal) >= 50
                                                ? t('pages.skills.levelIntermediate', 'Intermediate')
                                                : t('pages.skills.levelBeginner', 'Beginner')}
                                        </div>
                                    </div>
                                    <Progress
                                        percent={isNaN(levelVal) ? 0 : levelVal}
                                        status={(status as any) === 'learning' ? 'active' : 'normal'}
                                        strokeColor={{
                                            '0%': '#1890ff',
                                            '50%': '#40a9ff',
                                            '100%': '#52c41a',
                                        }}
                                        trailColor="rgba(255, 255, 255, 0.08)"
                                        size={['100%', 8]}
                                        showInfo={false}
                                        strokeLinecap="round"
                                    />
                                </div>
                            )}
                        </div>

                        <Space wrap size="small">
                            <Tag color={getStatusColor(status as any)} style={{ padding: '4px 12px', fontSize: 13 }}>
                                <CheckCircleOutlined /> {String(t(`pages.skills.status.${status || 'unknown'}`, (status as any) || t('common.unknown', '未知')))}
                            </Tag>
                            <Tag color="blue" style={{ padding: '4px 12px', fontSize: 13 }}>
                                <ThunderboltOutlined /> {String(t(`pages.skills.categories.${category || 'unknown'}`, (category as any) || t('common.unknown', '未知')))}
                            </Tag>
                            {isCodeSkill && (
                                <Tag color="orange" style={{ padding: '4px 12px', fontSize: 13 }}>
                                    <LockOutlined /> {t('pages.skills.codeSkillReadOnly', 'Code-based (Read-only)')}
                                </Tag>
                            )}
                            {!isNew && (
                                <>
                                    <Tag style={{ color: 'white', padding: '4px 12px', fontSize: 13 }}>
                                        <ClockCircleOutlined /> {(skill as any)?.lastUsed || t('pages.skills.neverUsed', 'Never used')}
                                    </Tag>
                                    <Tag style={{ color: 'white', padding: '4px 12px', fontSize: 13 }}>
                                        <StarOutlined /> {(skill as any)?.usageCount ?? 0} {t('pages.skills.uses', 'uses')}
                                    </Tag>
                                </>
                            )}
                        </Space>
                    </Space>
                </StyledCard>


                {/* Details Form Card */}
                <StyledCard
                    title={
                        <Space>
                            <SettingOutlined style={{ color: '#1890ff' }} />
                            <span style={{ color: 'white' }}>{t('pages.skills.details', 'Skill Details')}</span>
                        </Space>
                    }
                >
                    <Form form={form} layout="vertical" disabled={!editMode}>
                        <Tabs
                            defaultActiveKey="basic"
                            items={tabItems}
                            tabBarStyle={{ color: 'white' }}
                        />
                    </Form>
                </StyledCard>

                </Space>
            </FormContainer>
            
            {/* Fixed Action Buttons - Outside FormContainer, won't scroll */}
            <div style={{
                flexShrink: 0,
                display: 'flex',
                justifyContent: 'flex-end',
                gap: '12px',
                padding: '16px 24px',
                background: 'transparent',
                borderTop: '1px solid rgba(255, 255, 255, 0.05)'
            }}>
                {/* Edit模式Button */}
                {!isNew && editMode && (
                    <>
                        <Button 
                            type="primary" 
                            onClick={handleSave} 
                            size="large" 
                            style={primaryButtonStyle}
                            icon={<CheckCircleOutlined />}
                        >
                            {t('common.save', 'Save')}
                        </Button>
                        <Button 
                            onClick={handleCancel}
                            size="large" 
                            style={buttonStyle}
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
                            size="large" 
                            style={primaryButtonStyle}
                            icon={<CheckCircleOutlined />}
                        >
                            {t('common.create', 'Create')}
                        </Button>
                        <Button 
                            onClick={handleCancel}
                            size="large" 
                            style={buttonStyle}
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
                                    size="large"
                                    style={buttonStyle}
                                >
                                    {t('pages.skills.readOnly', 'Read-only')}
                                </Button>
                            </Tooltip>
                        ) : (
                            <>
                                <Button
                                    icon={<EditOutlined />}
                                    onClick={handleEdit}
                                    size="large"
                                    style={buttonStyle}
                                >
                                    {t('pages.skills.editSkill')}
                                </Button>
                                <Button 
                                    icon={<DeleteOutlined />} 
                                    danger 
                                    size="large" 
                                    onClick={handleDelete}
                                    style={buttonStyle}
                                >
                                    {t('common.delete', 'Delete')}
                                </Button>
                            </>
                        )}
                    </>
                )}
            </div>
        </div>
    );
};

export default SkillDetails;