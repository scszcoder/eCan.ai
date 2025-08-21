import React from 'react';
import { Typography, Space, Button, Progress, Tooltip, Card, Tag, Form, Input, Row, Col, Checkbox, message } from 'antd';
import { 
    ThunderboltOutlined, 
    CheckCircleOutlined,
    ClockCircleOutlined,
    StarOutlined,
    EditOutlined,
    HistoryOutlined,
    FileTextOutlined,
} from '@ant-design/icons';
import { useTranslation } from 'react-i18next';
import { Skill } from '../types';
import ActionButtons from '../../../components/Common/ActionButtons';
import { useNavigate } from 'react-router-dom';
import { get_ipc_api } from '@/services/ipc_api';
import { useUserStore } from '@/stores/userStore';

const { Text, Title } = Typography;

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

type ExtendedSkill = Skill & {
    askid?: number | string;
    owner?: string;
    latest_version?: string;
    path?: string; // diagram text representation file path
    level?: number; // already in Skill but keep optional for safety
    config?: string;
    apps?: string;
    limitations?: string;
    price?: number | string;
    price_model?: string;
    public?: boolean;
    rentable?: boolean;
    members?: string;
};

const DEFAULT_SKILL: Partial<Skill> = {
    id: '' as any,
    name: '',
    description: '',
    category: 'general' as any,
    status: 'planned' as any,
    level: 0 as any,
};

const SkillDetails: React.FC<SkillDetailsProps> = ({ skill, isNew = false, onLevelUp, onRefresh, onSave, onCancel }) => {
    const { t } = useTranslation();
    const navigate = useNavigate();
    const username = useUserStore((s) => s.username) || '';

    const [form] = Form.useForm<ExtendedSkill>();
    const [editMode, setEditMode] = React.useState(isNew);

    React.useEffect(() => {
        if (skill) {
            const s = skill as unknown as ExtendedSkill;
            form.setFieldsValue({
                id: s.id as any,
                askid: s.askid,
                name: s.name,
                owner: s.owner,
                description: s.description,
                latest_version: s.latest_version,
                path: s.path,
                level: s.level,
                config: s.config,
                apps: s.apps,
                limitations: s.limitations,
                price: s.price as any,
                price_model: s.price_model,
                public: s.public,
                rentable: s.rentable,
                members: s.members,
            } as any);
        } else if (isNew) {
            form.setFieldsValue({
                id: '' as any,
                name: '',
                owner: username,
                description: '',
                latest_version: '1.0.0',
                level: 0,
                config: '',
                apps: '',
                limitations: '',
                price: '' as any,
                price_model: '',
                public: false,
                rentable: false,
                members: '',
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
            // send to backend via IPC
            const payload = {
                ...values,
                id: (values as any).id,
                owner: username,
            } as ExtendedSkill;
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

    return (
        <div style={{ maxHeight: '100%', overflow: 'auto' }}>
            <Space direction="vertical" style={{ width: '100%' }}>
                <Title level={4}  style={{ color: 'white' }}>{name || t('pages.skills.newSkill', 'New Skill')}</Title>
                <Text  style={{ color: 'white' }}>{description}</Text>
                <Space>
                    <Tag color={getStatusColor(status as any)}>
                        <CheckCircleOutlined /> {t('pages.skills.statusLabel', '状态')}: {t(`pages.skills.status.${status || 'unknown'}`, (status as any) || t('common.unknown', '未知'))}
                    </Tag>
                    <Tag color="blue">
                        <ThunderboltOutlined /> {t('pages.skills.category')}: {t(`pages.skills.categories.${category || 'unknown'}`, (category as any) || t('common.unknown', '未知'))}
                    </Tag>
                </Space>
                <Space>
                    <Tag style={{color: 'white'}}>
                        <ClockCircleOutlined /> {t('pages.skills.lastUsed')}: {(skill as any)?.lastUsed || '-'}
                    </Tag>
                    <Tag style={{color: 'white'}}>
                        <StarOutlined /> {t('pages.skills.usageCount')}: {(skill as any)?.usageCount ?? 0}
                    </Tag>
                </Space>
                <Card>
                    <Space direction="vertical" style={{ width: '100%' }}>
                        <Text strong style={{ color: 'white' }}>{t('pages.skills.skillLevel')}</Text>
                        <Progress
                            percent={levelVal}
                            status={(status as any) === 'learning' ? 'active' : 'normal'}
                        />
                        <Text type="secondary"  style={{ color: 'white' }}>
                            {levelVal === 100
                                ? t('pages.skills.mastered')
                                : t('pages.skills.entryPercent', { percent: levelVal })}
                        </Text>
                    </Space>
                </Card>
                {/* Details form */}
                <Card>
                    <Form form={form} layout="vertical" disabled={!editMode}>
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
                                    <Input />
                                </Form.Item>
                            </Col>
                            <Col span={12}>
                                <Form.Item label={t('common.owner', 'Owner')} name="owner">
                                    <Input readOnly />
                                </Form.Item>
                            </Col>
                            <Col span={24}>
                                <Form.Item label={t('common.description', 'Description')} name="description">
                                    <Input.TextArea rows={6} style={{ overflowX: 'auto', overflowY: 'auto', whiteSpace: 'pre' }} />
                                </Form.Item>
                            </Col>
                            <Col span={12}>
                                <Form.Item label={t('pages.skills.latestVersion', 'Latest Version')} name="latest_version">
                                    <Input readOnly />
                                </Form.Item>
                            </Col>
                            <Col span={12}>
                                <Form.Item label="Diagram" name="path">
                                    <Space>
                                        <Input readOnly />
                                        <Tooltip title={form.getFieldValue('path') || ''}>
                                            <Button icon={<FileTextOutlined />} onClick={goToEditor} disabled={!editMode} />
                                        </Tooltip>
                                    </Space>
                                </Form.Item>
                            </Col>
                            <Col span={12}>
                                <Form.Item label={t('pages.skills.level', 'Level')} name="level">
                                    <Input />
                                </Form.Item>
                            </Col>
                            <Col span={24}>
                                <Form.Item label="Config" name="config">
                                    <Input.TextArea rows={6} style={{ overflowX: 'auto', overflowY: 'auto', whiteSpace: 'pre' }} />
                                </Form.Item>
                            </Col>
                            <Col span={24}>
                                <Form.Item label={t('pages.skills.apps', 'Apps')} name="apps">
                                    <Input.TextArea rows={6} style={{ overflowX: 'auto', overflowY: 'auto', whiteSpace: 'pre' }} />
                                </Form.Item>
                            </Col>
                            <Col span={24}>
                                <Form.Item label={t('pages.skills.limitations', 'Limitations')} name="limitations">
                                    <Input.TextArea rows={6} style={{ overflowX: 'auto', overflowY: 'auto', whiteSpace: 'pre' }} />
                                </Form.Item>
                            </Col>
                            <Col span={8}>
                                <Form.Item label={t('pages.skills.price', 'Price')} name="price">
                                    <Input />
                                </Form.Item>
                            </Col>
                            <Col span={8}>
                                <Form.Item label={t('pages.skills.priceModel', 'Price Model')} name="price_model">
                                    <Input />
                                </Form.Item>
                            </Col>
                            <Col span={8}>
                                <Form.Item label=" ">
                                    <Space size={24}>
                                        <Form.Item name="public" valuePropName="checked" noStyle>
                                            <Checkbox disabled={!editMode}>{t('pages.skills.public', 'Public')}</Checkbox>
                                        </Form.Item>
                                        <Form.Item name="rentable" valuePropName="checked" noStyle>
                                            <Checkbox disabled={!editMode}>{t('pages.skills.rentable', 'Rentable')}</Checkbox>
                                        </Form.Item>
                                    </Space>
                                </Form.Item>
                            </Col>
                            <Col span={24}>
                                <Form.Item label={t('pages.skills.members', 'Members')} name="members">
                                    <Input readOnly />
                                </Form.Item>
                            </Col>
                        </Row>
                    </Form>
                </Card>
                {/* Buttons moved to bottom */}
                <Space>
                    <Button
                        type="primary"
                        icon={<ThunderboltOutlined />}
                        onClick={() => skill && onLevelUp((skill as any).id)}
                        disabled={!skill || (skill as any).level === 100}
                    >
                        {t('pages.skills.levelUp')}
                    </Button>
                    <Button icon={<EditOutlined />} onClick={handleEdit} disabled={editMode}>
                        {t('pages.skills.editSkill')}
                    </Button>
                    {editMode && (
                        <>
                            <Button type="primary" onClick={handleSave}>
                                {isNew ? t('common.create', 'Create') : t('common.save', 'Save')}
                            </Button>
                            <Button onClick={() => {
                                form.resetFields();
                                setEditMode(false);
                                if (isNew && onCancel) onCancel();
                            }}>
                                {t('common.cancel', 'Cancel')}
                            </Button>
                        </>
                    )}
                    <Button icon={<HistoryOutlined />}>
                        {t('pages.skills.viewHistory')}
                    </Button>
                </Space>
                <ActionButtons
                    onAdd={() => {}}
                    onEdit={handleEdit}
                    onDelete={() => {}}
                    onRefresh={onRefresh}
                    onExport={() => {}}
                    onImport={() => {}}
                    onSettings={() => {}}
                    addText={t('pages.skills.addSkill')}
                    editText={t('pages.skills.editSkill')}
                    deleteText={t('pages.skills.deleteSkill')}
                    refreshText={t('pages.skills.refreshSkills')}
                    exportText={t('pages.skills.exportSkills')}
                    importText={t('pages.skills.importSkills')}
                    settingsText={t('pages.skills.skillSettings')}
                />
            </Space>
        </div>
    );
};

export default SkillDetails;