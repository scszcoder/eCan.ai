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

const { Text, Title } = Typography;

const SkillItem = styled.div`
    padding: 12px;
    border-bottom: 1px solid #f0f0f0;
    &:last-child {
        border-bottom: none;
    }
    cursor: pointer;
    transition: background-color 0.3s;
    &:hover {
        background-color: #f5f5f5;
    }
`;

const SkillProgress = styled.div`
    margin-top: 8px;
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

const initialSkills: Skill[] = [
    {
        id: 1,
        name: 'Natural Language Processing',
        description: 'Advanced NLP capabilities for text understanding and generation',
        category: 'AI',
        level: 85,
        status: 'active',
        lastUsed: '2 hours ago',
        usageCount: 156,
    },
    {
        id: 2,
        name: 'Image Recognition',
        description: 'Computer vision and image processing capabilities',
        category: 'AI',
        level: 70,
        status: 'learning',
        lastUsed: '1 day ago',
        usageCount: 89,
    },
    {
        id: 3,
        name: 'Data Analysis',
        description: 'Statistical analysis and data visualization',
        category: 'Analytics',
        level: 90,
        status: 'active',
        lastUsed: '5 minutes ago',
        usageCount: 234,
    },
];

const Skills: React.FC = () => {
    const { t } = useTranslation();
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
                lastUsed: 'Just now',
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
                <Title level={4}>{selectedSkill.name}</Title>
                <Text>{selectedSkill.description}</Text>
                <Space>
                    <Tag color={getStatusColor(selectedSkill.status)}>
                        <CheckCircleOutlined /> {t('pages.skills.status')}: {t(`pages.skills.status.${selectedSkill.status}`)}
                    </Tag>
                    <Tag color="blue">
                        <ThunderboltOutlined /> {t('pages.skills.category')}: {selectedSkill.category}
                    </Tag>
                </Space>
                <Space>
                    <Tag>
                        <ClockCircleOutlined /> {t('pages.skills.lastUsed')}: {selectedSkill.lastUsed}
                    </Tag>
                    <Tag>
                        <StarOutlined /> {t('pages.skills.usageCount')}: {selectedSkill.usageCount}
                    </Tag>
                </Space>
                <Card>
                    <Space direction="vertical" style={{ width: '100%' }}>
                        <Text strong>{t('pages.skills.skillLevel')}</Text>
                        <Progress 
                            percent={selectedSkill.level} 
                            status={selectedSkill.status === 'learning' ? 'active' : 'normal'}
                        />
                        <Text type="secondary">
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