import React from 'react';
import { Typography, Space, Button, Progress, Tooltip, Card, Tag, Form, Input, Row, Col, Checkbox, message, Select, Tabs } from 'antd';
import type { TabsProps } from 'antd';
import {
    ThunderboltOutlined,
    CheckCircleOutlined,
    ClockCircleOutlined,
    StarOutlined,
    EditOutlined,
    HistoryOutlined,
    FileTextOutlined,
    SettingOutlined,
    CodeOutlined,
    AppstoreOutlined,
    TagsOutlined,
} from '@ant-design/icons';
import { useTranslation } from 'react-i18next';
import type { Skill, SkillRunMode, SkillNeedInput } from '@/types/domain/skill';

import { useNavigate } from 'react-router-dom';
import { get_ipc_api } from '@/services/ipc_api';
import { useUserStore } from '@/stores/userStore';
import { IPCWCClient } from '@/services/ipc/ipcWCClient';

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
    onLevelUp: (id: number) => void;
    onRefresh: () => void;
    onSave?: () => void;
    onCancel?: () => void;
}

/**
 * 扩展的技能类型，包含所有 DBAgentSkill 和 EC_Skill 字段
 */
type ExtendedSkill = Skill & {
    // DBAgentSkill 字段
    askid?: number;

    // EC_Skill 字段
    ui_info?: {
        text?: string;
        icon?: string;
    };
    objectives?: string[];
    need_inputs?: SkillNeedInput[];
    run_mode?: SkillRunMode | string;
    mapping_rules?: any;

    // 序列化字段（用于表单）
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
 * 辅助函数：将对象/数组转换为 JSON 字符串
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
 * 辅助函数：将 JSON 字符串转换为对象/数组
 */
const fromJsonString = (value: string): any => {
    if (!value || value.trim() === '') return undefined;
    try {
        return JSON.parse(value);
    } catch {
        return value;
    }
};

const SkillDetails: React.FC<SkillDetailsProps> = ({ skill, isNew = false, onLevelUp, onRefresh, onSave, onCancel }) => {
    const { t } = useTranslation();
    const navigate = useNavigate();
    const username = useUserStore((s) => s.username) || '';

    const [form] = Form.useForm<ExtendedSkill>();
    const [editMode, setEditMode] = React.useState(isNew);

    React.useEffect(() => {
        if (skill) {
            const s = skill as ExtendedSkill;
            form.setFieldsValue({
                // 基础字段
                id: s.id,
                askid: s.askid,
                name: s.name,
                owner: s.owner,
                description: s.description,
                version: s.version,
                path: s.path,
                level: s.level,

                // EC_Skill 字段
                run_mode: s.run_mode || 'development',

                // 扩展字段
                price: s.price,
                price_model: s.price_model,
                public: s.public,
                rentable: s.rentable,

                // JSON 字段（序列化为字符串）
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

    const handleSave = async () => {
        try {
            const values = await form.validateFields();

            // 将 JSON 字符串字段转换回对象/数组
            const payload: Partial<Skill> = {
                // 基础字段
                id: values.id,
                askid: values.askid,
                name: values.name,
                owner: username,
                description: values.description,
                version: values.version,
                path: values.path,
                level: values.level,

                // EC_Skill 字段
                run_mode: values.run_mode,

                // 扩展字段
                price: values.price,
                price_model: values.price_model,
                public: values.public,
                rentable: values.rentable,

                // 反序列化 JSON 字段
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
                ? await api.newSkill(username, payload as any)
                : await api.saveSkill(username, payload as any);
            if (resp.success) {
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
        navigate('/skill_editor', { state: { skillId: (skill as any).id } });
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
            label: <span><SettingOutlined /> {t('pages.skills.tabs.basic', '基础信息')}</span>,
            children: (
                <Row gutter={[16, 8]}>
                    <Col span={12}>
                        <Form.Item label="ID" name="id">
                            <Input readOnly />
                        </Form.Item>
                    </Col>
                    <Col span={12}>
                        <Form.Item label="Ask ID" name="askid">
                            <Input readOnly />
                        </Form.Item>
                    </Col>
                    <Col span={12}>
                        <Form.Item label={t('common.name', 'Name')} name="name" rules={[{ required: true }]}>
                            <Input placeholder={t('pages.skills.namePlaceholder', 'Enter skill name')} />
                        </Form.Item>
                    </Col>
                    <Col span={12}>
                        <Form.Item label={t('common.owner', 'Owner')} name="owner">
                            <Input readOnly />
                        </Form.Item>
                    </Col>
                    <Col span={24}>
                        <Form.Item label={t('common.description', 'Description')} name="description">
                            <TextArea
                                rows={4}
                                placeholder={t('pages.skills.descriptionPlaceholder', 'Enter skill description')}
                            />
                        </Form.Item>
                    </Col>
                    <Col span={8}>
                        <Form.Item label={t('pages.skills.version', 'Version')} name="version" rules={[{ required: true }]}>
                            <Input placeholder="0.0.0" />
                        </Form.Item>
                    </Col>
                    <Col span={8}>
                        <Form.Item label={t('pages.skills.level', 'Level')} name="level">
                            <Select>
                                <Select.Option value="entry">{t('pages.skills.levels.entry', 'Entry')}</Select.Option>
                                <Select.Option value="intermediate">{t('pages.skills.levels.intermediate', 'Intermediate')}</Select.Option>
                                <Select.Option value="advanced">{t('pages.skills.levels.advanced', 'Advanced')}</Select.Option>
                            </Select>
                        </Form.Item>
                    </Col>
                    <Col span={8}>
                        <Form.Item label={t('pages.skills.runMode', 'Run Mode')} name="run_mode">
                            <Select>
                                <Select.Option value="development">{t('pages.skills.runModes.development', 'Development')}</Select.Option>
                                <Select.Option value="released">{t('pages.skills.runModes.released', 'Released')}</Select.Option>
                            </Select>
                        </Form.Item>
                    </Col>
                    <Col span={24}>
                        <Form.Item label={t('pages.skills.path', 'Path')} name="path" htmlFor="skill-path-input">
                            <Space.Compact style={{ width: '100%' }}>
                                <Input id="skill-path-input" readOnly placeholder={t('pages.skills.pathPlaceholder', 'Skill file path')} />
                                <Tooltip title={t('pages.skills.openEditor', 'Open in Editor')}>
                                    <Button icon={<FileTextOutlined />} onClick={goToEditor} />
                                </Tooltip>
                            </Space.Compact>
                        </Form.Item>
                    </Col>
                </Row>
            ),
        },
        {
            key: 'config',
            label: <span><CodeOutlined /> {t('pages.skills.tabs.config', '配置')}</span>,
            children: (
                <Row gutter={[16, 8]}>
                    <Col span={24}>
                        <Form.Item
                            label={t('pages.skills.config', 'Config (JSON)')}
                            name="config_json"
                            help={t('pages.skills.configHelp', 'Enter valid JSON configuration')}
                        >
                            <TextArea
                                rows={8}
                                placeholder='{"key": "value"}'
                                style={{ fontFamily: 'monospace' }}
                            />
                        </Form.Item>
                    </Col>
                    <Col span={24}>
                        <Form.Item
                            label={t('pages.skills.mappingRules', 'Mapping Rules (JSON)')}
                            name="mapping_rules_json"
                            help={t('pages.skills.mappingRulesHelp', 'State mapping rules for resume/event handling')}
                        >
                            <TextArea
                                rows={8}
                                placeholder='{"developing": {"mappings": [...]}}'
                                style={{ fontFamily: 'monospace' }}
                            />
                        </Form.Item>
                    </Col>
                </Row>
            ),
        },
        {
            key: 'metadata',
            label: <span><TagsOutlined /> {t('pages.skills.tabs.metadata', '元数据')}</span>,
            children: (
                <Row gutter={[16, 8]}>
                    <Col span={24}>
                        <Form.Item
                            label={t('pages.skills.tags', 'Tags (JSON Array)')}
                            name="tags_json"
                            help={t('pages.skills.tagsHelp', 'e.g., ["tag1", "tag2"]')}
                        >
                            <TextArea
                                rows={3}
                                placeholder='["automation", "data-processing"]'
                                style={{ fontFamily: 'monospace' }}
                            />
                        </Form.Item>
                    </Col>
                    <Col span={24}>
                        <Form.Item
                            label={t('pages.skills.examples', 'Examples (JSON Array)')}
                            name="examples_json"
                            help={t('pages.skills.examplesHelp', 'Usage examples')}
                        >
                            <TextArea
                                rows={4}
                                placeholder='["Example 1", "Example 2"]'
                                style={{ fontFamily: 'monospace' }}
                            />
                        </Form.Item>
                    </Col>
                    <Col span={12}>
                        <Form.Item
                            label={t('pages.skills.inputModes', 'Input Modes (JSON Array)')}
                            name="inputModes_json"
                        >
                            <TextArea
                                rows={3}
                                placeholder='["text", "file"]'
                                style={{ fontFamily: 'monospace' }}
                            />
                        </Form.Item>
                    </Col>
                    <Col span={12}>
                        <Form.Item
                            label={t('pages.skills.outputModes', 'Output Modes (JSON Array)')}
                            name="outputModes_json"
                        >
                            <TextArea
                                rows={3}
                                placeholder='["text", "json"]'
                                style={{ fontFamily: 'monospace' }}
                            />
                        </Form.Item>
                    </Col>
                    <Col span={24}>
                        <Form.Item
                            label={t('pages.skills.objectives', 'Objectives (JSON Array)')}
                            name="objectives_json"
                            help={t('pages.skills.objectivesHelp', 'Skill objectives/goals')}
                        >
                            <TextArea
                                rows={4}
                                placeholder='["Objective 1", "Objective 2"]'
                                style={{ fontFamily: 'monospace' }}
                            />
                        </Form.Item>
                    </Col>
                    <Col span={24}>
                        <Form.Item
                            label={t('pages.skills.needInputs', 'Required Inputs (JSON Array)')}
                            name="need_inputs_json"
                            help={t('pages.skills.needInputsHelp', 'Input parameters required by this skill')}
                        >
                            <TextArea
                                rows={6}
                                placeholder='[{"name": "param1", "type": "string", "required": true}]'
                                style={{ fontFamily: 'monospace' }}
                            />
                        </Form.Item>
                    </Col>
                </Row>
            ),
        },
        {
            key: 'extended',
            label: <span><AppstoreOutlined /> {t('pages.skills.tabs.extended', '扩展')}</span>,
            children: (
                <Row gutter={[16, 8]}>
                    <Col span={24}>
                        <Form.Item
                            label={t('pages.skills.apps', 'Apps (JSON)')}
                            name="apps_json"
                            help={t('pages.skills.appsHelp', 'Related applications')}
                        >
                            <TextArea
                                rows={4}
                                placeholder='[{"name": "app1", "version": "1.0"}]'
                                style={{ fontFamily: 'monospace' }}
                            />
                        </Form.Item>
                    </Col>
                    <Col span={24}>
                        <Form.Item
                            label={t('pages.skills.limitations', 'Limitations (JSON)')}
                            name="limitations_json"
                            help={t('pages.skills.limitationsHelp', 'Known limitations')}
                        >
                            <TextArea
                                rows={4}
                                placeholder='["Limitation 1", "Limitation 2"]'
                                style={{ fontFamily: 'monospace' }}
                            />
                        </Form.Item>
                    </Col>
                    <Col span={8}>
                        <Form.Item label={t('pages.skills.price', 'Price')} name="price">
                            <Input type="number" min={0} placeholder="0" />
                        </Form.Item>
                    </Col>
                    <Col span={8}>
                        <Form.Item label={t('pages.skills.priceModel', 'Price Model')} name="price_model">
                            <Input placeholder={t('pages.skills.priceModelPlaceholder', 'e.g., per-use, subscription')} />
                        </Form.Item>
                    </Col>
                    <Col span={8}>
                        <Form.Item label=" " style={{ marginTop: '30px' }}>
                            <Space size={24}>
                                <Form.Item name="public" valuePropName="checked" noStyle>
                                    <Checkbox>{t('pages.skills.public', 'Public')}</Checkbox>
                                </Form.Item>
                                <Form.Item name="rentable" valuePropName="checked" noStyle>
                                    <Checkbox>{t('pages.skills.rentable', 'Rentable')}</Checkbox>
                                </Form.Item>
                            </Space>
                        </Form.Item>
                    </Col>
                </Row>
            ),
        },
    ];

    return (
        <div style={{ maxHeight: '100%', overflow: 'auto', padding: '8px' }}>
            <Space direction="vertical" style={{ width: '100%' }} size="large">
                {/* Header Card */}
                <Card
                    style={{
                        background: 'linear-gradient(135deg, rgba(24, 144, 255, 0.1) 0%, rgba(24, 144, 255, 0.05) 100%)',
                        border: '1px solid rgba(24, 144, 255, 0.2)'
                    }}
                >
                    <Space direction="vertical" style={{ width: '100%' }} size="middle">
                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                            <div style={{ flex: 1 }}>
                                <Title level={3} style={{ color: 'white', margin: 0, marginBottom: 8 }}>
                                    {name || t('pages.skills.newSkill', 'New Skill')}
                                </Title>
                                <Text style={{ color: 'rgba(255, 255, 255, 0.85)', fontSize: 14 }}>
                                    {description || t('pages.skills.noDescription', 'No description available')}
                                </Text>
                            </div>
                            {!isNew && (
                                <Space>
                                    <Button
                                        type="primary"
                                        icon={<ThunderboltOutlined />}
                                        onClick={() => skill && onLevelUp((skill as any).id)}
                                        disabled={!skill || (skill as any).level === 100}
                                        size="large"
                                    >
                                        {t('pages.skills.levelUp')}
                                    </Button>
                                    {!editMode ? (
                                        <Button
                                            icon={<EditOutlined />}
                                            onClick={handleEdit}
                                            size="large"
                                        >
                                            {t('pages.skills.editSkill')}
                                        </Button>
                                    ) : (
                                        <Space>
                                            <Button type="primary" onClick={handleSave} size="large">
                                                {t('common.save', 'Save')}
                                            </Button>
                                            <Button onClick={() => {
                                                form.resetFields();
                                                setEditMode(false);
                                            }} size="large">
                                                {t('common.cancel', 'Cancel')}
                                            </Button>
                                        </Space>
                                    )}
                                </Space>
                            )}
                            {isNew && (
                                <Space>
                                    <Button type="primary" onClick={handleSave} size="large">
                                        {t('common.create', 'Create')}
                                    </Button>
                                    <Button onClick={() => {
                                        form.resetFields();
                                        if (onCancel) onCancel();
                                    }} size="large">
                                        {t('common.cancel', 'Cancel')}
                                    </Button>
                                </Space>
                            )}
                        </div>

                        <Space wrap size="small">
                            <Tag color={getStatusColor(status as any)} style={{ padding: '4px 12px', fontSize: 13 }}>
                                <CheckCircleOutlined /> {String(t(`pages.skills.status.${status || 'unknown'}`, (status as any) || t('common.unknown', '未知')))}
                            </Tag>
                            <Tag color="blue" style={{ padding: '4px 12px', fontSize: 13 }}>
                                <ThunderboltOutlined /> {String(t(`pages.skills.categories.${category || 'unknown'}`, (category as any) || t('common.unknown', '未知')))}
                            </Tag>
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
                </Card>

                {/* Progress Card */}
                {!isNew && (
                    <Card
                        title={
                            <Space>
                                <ThunderboltOutlined style={{ color: '#1890ff' }} />
                                <span style={{ color: 'white' }}>{t('pages.skills.skillLevel')}</span>
                            </Space>
                        }
                    >
                        <Space direction="vertical" style={{ width: '100%' }} size="middle">
                            <Progress
                                percent={levelVal}
                                status={(status as any) === 'learning' ? 'active' : 'normal'}
                                strokeColor={{
                                    '0%': '#1890ff',
                                    '100%': '#52c41a',
                                }}
                                size={['100%', 12]}
                            />
                            <Text style={{ color: 'rgba(255, 255, 255, 0.85)', fontSize: 14 }}>
                                {levelVal === 100
                                    ? `🎉 ${t('pages.skills.mastered', 'Mastered!')}`
                                    : t('pages.skills.progressMessage', `Keep practicing to reach mastery! (${levelVal}%)`)}
                            </Text>
                        </Space>
                    </Card>
                )}

                {/* Details Form Card */}
                <Card
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
                </Card>

                {/* Action Buttons - Only show if not in edit mode */}
                {!editMode && !isNew && (
                    <Card>
                        <Space wrap>
                            <Button icon={<HistoryOutlined />}>
                                {t('pages.skills.viewHistory')}
                            </Button>
                            <Button onClick={onRefresh}>
                                {t('pages.skills.refresh')}
                            </Button>
                        </Space>
                    </Card>
                )}
            </Space>
        </div>
    );
};

export default SkillDetails;