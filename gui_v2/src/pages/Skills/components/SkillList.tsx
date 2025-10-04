import React from 'react';
import { List, Tag, Typography, Space, Progress, Tooltip } from 'antd';
import { RobotOutlined } from '@ant-design/icons';
import styled from '@emotion/styled';
import { useTranslation } from 'react-i18next';
import type { Skill } from '@/stores';

const { Text } = Typography;

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

interface SkillListProps {
    skills: Skill[];
    loading: boolean;
    onSelectSkill: (skill: Skill) => void;
}

const SkillList: React.FC<SkillListProps> = ({ skills, loading, onSelectSkill }) => {
    const { t } = useTranslation();

    return (
        <List
            dataSource={skills}
            loading={loading}
            renderItem={skill => (
                <SkillItem onClick={() => onSelectSkill(skill)}>
                    <Space direction="vertical" style={{ width: '100%' }}>
                        <Space>
                            <RobotOutlined />
                            <Text strong>{skill.name}</Text>
                        </Space>
                        <Space>
                            <Tag color={getStatusColor(skill.status)}>{t(`pages.skills.status.${skill.status || 'unknown'}`, skill.status || t('common.unknown', '未知'))}</Tag>
                            <Tag color="blue">{t(`pages.skills.categories.${skill.category || 'unknown'}`, skill.category || t('common.unknown', '未知'))}</Tag>
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
};

export default SkillList; 