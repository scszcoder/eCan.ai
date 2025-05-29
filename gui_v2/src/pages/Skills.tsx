import React from 'react';
import { List, Tag, Typography, Space, Button, Progress, Tooltip, Card } from 'antd';
import { 
    RobotOutlined, 
    ThunderboltOutlined, 
    CheckCircleOutlined,
    ClockCircleOutlined,
    StarOutlined,
    EditOutlined,
    HistoryOutlined
} from '@ant-design/icons';
import styled from '@emotion/styled';
import DetailLayout from '../components/Layout/DetailLayout';
import { useDetailView } from '../hooks/useDetailView';
import { useTranslation } from 'react-i18next';
import ActionButtons from '../components/Common/ActionButtons';
import {ipc_api} from '../services/ipc_api';

const { Text, Title } = Typography;

const SkillItem = styled.div`
    padding: 12px;
    border-bottom: 1px solid var(--border-color);
    &:last-child {
        border-bottom: none;
    }
    cursor: pointer;
    transition: all 0.3s ease;
    background-color: var(--bg-secondary);
    border-radius: 8px;
    margin: 4px 0;
    &:hover {
        background-color: var(--bg-tertiary);
        transform: translateX(4px);
        box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
    }
    .ant-typography {
        color: var(--text-primary);
    }
    .ant-tag {
        background-color: var(--bg-primary);
        border-color: var(--border-color);
    }
    .ant-progress-text {
        color: var(--text-primary);
    }
`;

const SkillProgress = styled.div`
    margin-top: 8px;
    padding: 0 4px;
`;

interface Skill {
    id: number;
    name: string;
    description: string;
    category: string;
    level: number;
    status: 'active' | 'learning' | 'planned';
    lastUsed: string;
    usageCount: number;
}

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

const Skills: React.FC = () => {
    const { t } = useTranslation();
    
    const initialSkills: Skill[] = [
        {
            id: 1,
            name: t('pages.skills.categories.Natural Language Processing'),
            description: 'Advanced NLP capabilities for text understanding and generation',
            category: 'AI',
            level: 85,
            status: 'active',
            lastUsed: t('pages.skills.time.hoursAgo', { hours: 2 }),
            usageCount: 156,
        },
        {
            id: 2,
            name: t('pages.skills.categories.Image Recognition'),
            description: 'Computer vision and image processing capabilities',
            category: 'AI',
            level: 70,
            status: 'learning',
            lastUsed: t('pages.skills.time.daysAgo', { days: 1 }),
            usageCount: 89,
        },
        {
            id: 3,
            name: t('pages.skills.categories.Data Analysis'),
            description: 'Statistical analysis and data visualization',
            category: 'Analytics',
            level: 90,
            status: 'active',
            lastUsed: t('pages.skills.time.minutesAgo', { minutes: 5 }),
            usageCount: 234,
        },
    ];

    const {
        selectedItem: selectedSkill,
        items: skills,
        selectItem,
        updateItem,
    } = useDetailView<Skill>(initialSkills);

    const handleLevelUp = (id: number) => {
        const skill = skills.find(s => s.id === id);
        if (skill && skill.level < 100) {
            updateItem(id, {
                level: Math.min(skill.level + 5, 100),
                lastUsed: t('pages.skills.time.justNow'),
                usageCount: skill.usageCount + 1,
            });
        }
    };

    const renderListContent = () => (
        <List
            dataSource={skills}
            renderItem={skill => (
                <SkillItem onClick={() => selectItem(skill)}>
                    <Space direction="vertical" style={{ width: '100%' }}>
                        <Space>
                            <RobotOutlined />
                            <Text strong>{skill.name}</Text>
                        </Space>
                        <Space>
                            <Tag color={getStatusColor(skill.status)}>{t(`pages.skills.status.${skill.status}`)}</Tag>
                            <Tag color="blue">{skill.category}</Tag>
                        </Space>
                        <SkillProgress>
                            <Tooltip title={t('pages.skills.level', { level: skill.level })}>
                                <Progress 
                                    percent={skill.level} 
                                    size="small"
                                    status={skill.status === 'learning' ? 'active' : 'normal'}
                                />
                            </Tooltip>
                        </SkillProgress>
                    </Space>
                </SkillItem>
            )}
        />
    );

    const renderDetailsContent = () => {
        if (!selectedSkill) {
            return <Text type="secondary">{t('pages.skills.selectSkill')}</Text>;
        }

        return (
            <Space direction="vertical" style={{ width: '100%' }}>
                <Title level={4}  style={{ color: 'white' }}>{selectedSkill.name}</Title>
                <Text  style={{ color: 'white' }}>{selectedSkill.description}</Text>
                <Space>
                    <Tag color={getStatusColor(selectedSkill.status)}>
                        <CheckCircleOutlined /> {t('pages.skills.status')}: {t(`pages.skills.status.${selectedSkill.status}`)}
                    </Tag>
                    <Tag color="blue">
                        <ThunderboltOutlined /> {t('pages.skills.category')}: {t(`pages.skills.categories.${selectedSkill.category}`)}
                    </Tag>
                </Space>
                <Space>
                    <Tag style={{color: 'white'}}>
                        <ClockCircleOutlined /> {t('pages.skills.lastUsed')}: {selectedSkill.lastUsed}
                    </Tag>
                    <Tag style={{color: 'white'}}>
                        <StarOutlined /> {t('pages.skills.usageCount')}: {selectedSkill.usageCount}
                    </Tag>
                </Space>
                <Card>
                    <Space direction="vertical" style={{ width: '100%' }}>
                        <Text strong style={{ color: 'white' }}>{t('pages.skills.skillLevel')}</Text>
                        <Progress 
                            percent={selectedSkill.level} 
                            status={selectedSkill.status === 'learning' ? 'active' : 'normal'}
                        />
                        <Text type="secondary"  style={{ color: 'white' }}>
                            {selectedSkill.level === 100 
                                ? t('pages.skills.mastered')
                                : t('pages.skills.complete', { level: selectedSkill.level })}
                        </Text>
                    </Space>
                </Card>
                <Space>
                    <Button 
                        type="primary" 
                        icon={<ThunderboltOutlined />}
                        onClick={() => handleLevelUp(selectedSkill.id)}
                        disabled={selectedSkill.level === 100}
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
                    onRefresh={() => {}}
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
        );
    };

    return (
        <DetailLayout
            listTitle={t('pages.skills.title')}
            detailsTitle={t('pages.skills.details')}
            listContent={renderListContent()}
            detailsContent={renderDetailsContent()}
        />
    );
};

export default Skills; 