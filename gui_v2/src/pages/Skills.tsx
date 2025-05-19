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
                            <Tag color={getStatusColor(skill.status)}>{skill.status}</Tag>
                            <Tag color="blue">{skill.category}</Tag>
                        </Space>
                        <SkillProgress>
                            <Tooltip title={`Level: ${skill.level}%`}>
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
            return <Text type="secondary">Select a skill to view details</Text>;
        }

        return (
            <Space direction="vertical" style={{ width: '100%' }}>
                <Title level={4}>{selectedSkill.name}</Title>
                <Text>{selectedSkill.description}</Text>
                <Space>
                    <Tag color={getStatusColor(selectedSkill.status)}>
                        <CheckCircleOutlined /> Status: {selectedSkill.status}
                    </Tag>
                    <Tag color="blue">
                        <ThunderboltOutlined /> Category: {selectedSkill.category}
                    </Tag>
                </Space>
                <Space>
                    <Tag>
                        <ClockCircleOutlined /> Last Used: {selectedSkill.lastUsed}
                    </Tag>
                    <Tag>
                        <StarOutlined /> Usage Count: {selectedSkill.usageCount}
                    </Tag>
                </Space>
                <Card>
                    <Space direction="vertical" style={{ width: '100%' }}>
                        <Text strong>Skill Level</Text>
                        <Progress 
                            percent={selectedSkill.level} 
                            status={selectedSkill.status === 'learning' ? 'active' : 'normal'}
                        />
                        <Text type="secondary">
                            {selectedSkill.level === 100 
                                ? 'Mastered' 
                                : `${selectedSkill.level}% Complete`}
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
                        Level Up
                    </Button>
                    <Button icon={<EditOutlined />}>
                        Edit Skill
                    </Button>
                    <Button icon={<HistoryOutlined />}>
                        View History
                    </Button>
                </Space>
            </Space>
        );
    };

    return (
        <DetailLayout
            listTitle="Skills"
            detailsTitle="Skill Details"
            listContent={renderListContent()}
            detailsContent={renderDetailsContent()}
        />
    );
};

export default Skills; 