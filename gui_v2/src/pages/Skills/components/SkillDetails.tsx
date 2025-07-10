import React from 'react';
import { Typography, Space, Button, Progress, Tooltip, Card, Tag } from 'antd';
import { 
    ThunderboltOutlined, 
    CheckCircleOutlined,
    ClockCircleOutlined,
    StarOutlined,
    EditOutlined,
    HistoryOutlined,
} from '@ant-design/icons';
import { useTranslation } from 'react-i18next';
import { Skill } from '../types';
import ActionButtons from '../../../components/Common/ActionButtons';

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
    onLevelUp: (id: number) => void;
    onRefresh: () => void;
}

const SkillDetails: React.FC<SkillDetailsProps> = ({ skill, onLevelUp, onRefresh }) => {
    const { t } = useTranslation();

    if (!skill) {
        return <Text type="secondary">{t('pages.skills.selectSkill')}</Text>;
    }

    return (
        <div style={{ maxHeight: '100%', overflow: 'auto' }}>
            <Space direction="vertical" style={{ width: '100%' }}>
                <Title level={4}  style={{ color: 'white' }}>{skill.name}</Title>
                <Text  style={{ color: 'white' }}>{skill.description}</Text>
                <Space>
                    <Tag color={getStatusColor(skill.status)}>
                        <CheckCircleOutlined /> {t('pages.skills.statusLabel', '状态')}: {t(`pages.skills.status.${skill.status || 'unknown'}`, skill.status || t('common.unknown', '未知'))}
                    </Tag>
                    <Tag color="blue">
                        <ThunderboltOutlined /> {t('pages.skills.category')}: {t(`pages.skills.categories.${skill.category || 'unknown'}`, skill.category || t('common.unknown', '未知'))}
                    </Tag>
                </Space>
                <Space>
                    <Tag style={{color: 'white'}}>
                        <ClockCircleOutlined /> {t('pages.skills.lastUsed')}: {skill.lastUsed}
                    </Tag>
                    <Tag style={{color: 'white'}}>
                        <StarOutlined /> {t('pages.skills.usageCount')}: {skill.usageCount}
                    </Tag>
                </Space>
                <Card>
                    <Space direction="vertical" style={{ width: '100%' }}>
                        <Text strong style={{ color: 'white' }}>{t('pages.skills.skillLevel')}</Text>
                        <Progress
                            percent={skill.level}
                            status={skill.status === 'learning' ? 'active' : 'normal'}
                        />
                        <Text type="secondary"  style={{ color: 'white' }}>
                            {skill.level === 100
                                ? t('pages.skills.mastered')
                                : t('pages.skills.entryPercent', { percent: skill.level })}
                        </Text>
                    </Space>
                </Card>
                <Space>
                    <Button
                        type="primary"
                        icon={<ThunderboltOutlined />}
                        onClick={() => onLevelUp(skill.id)}
                        disabled={skill.level === 100}
                    >
                        {t('pages.skills.levelUp')}
                    </Button>
                    <Button icon={<EditOutlined />}>
                        {t('pages.skills.editSkill')}
                    </Button>
                    <Button icon={<HistoryOutlined />}>
                        {t('pages.skills.viewHistory')}
                    </Button>
                </Space>
                <ActionButtons
                    onAdd={() => {}}
                    onEdit={() => {}}
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