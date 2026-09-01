import React from 'react';
import {
    AppstoreOutlined,
    RocketOutlined,
    RiseOutlined,
    MessageOutlined,
    CodeOutlined,
    EyeOutlined,
    ApiOutlined,
    BranchesOutlined,
    CloudOutlined,
    BulbOutlined,
    FileTextOutlined,
    ExperimentOutlined,
    GlobalOutlined,
} from '@ant-design/icons';
import { useTranslation } from 'react-i18next';
import styled from '@emotion/styled';
import type { Skill } from '@/types/domain/skill';

const Chip = styled.button<{ $active?: boolean; $color?: string }>`
    flex-shrink: 0;
    display: inline-flex;
    align-items: center;
    gap: 5px;
    padding: 5px 12px;
    border-radius: 999px;
    border: 1px solid ${(p) =>
        p.$active ? `${p.$color || '#1890ff'}66` : 'rgba(255, 255, 255, 0.08)'};
    background: ${(p) =>
        p.$active
            ? `linear-gradient(135deg, ${p.$color || '#1890ff'}33, ${p.$color || '#1890ff'}11)`
            : 'rgba(255, 255, 255, 0.04)'};
    color: ${(p) => (p.$active ? p.$color || '#1890ff' : 'rgba(255, 255, 255, 0.78)')};
    font-size: 12px;
    font-weight: 500;
    cursor: pointer;
    transition: all 0.15s ease;
    white-space: nowrap;

    .anticon {
        font-size: 12px;
    }

    &:hover {
        background: ${(p) =>
            p.$active
                ? `linear-gradient(135deg, ${p.$color || '#1890ff'}44, ${p.$color || '#1890ff'}22)`
                : 'rgba(255, 255, 255, 0.08)'};
        color: #fff;
        border-color: ${(p) =>
            p.$active ? `${p.$color || '#1890ff'}88` : 'rgba(255, 255, 255, 0.18)'};
    }
`;

const CATEGORY_DEFS: Array<{ key: string; label: string; color: string; icon: React.ReactNode }> = [
    { key: 'all', label: 'All', color: '#1890ff', icon: <AppstoreOutlined /> },
    { key: 'automation', label: 'Automation', color: '#f59e0b', icon: <RocketOutlined /> },
    { key: 'analysis', label: 'Analysis', color: '#8b5cf6', icon: <RiseOutlined /> },
    { key: 'communication', label: 'Communication', color: '#06b6d4', icon: <MessageOutlined /> },
    { key: 'coding', label: 'Coding', color: '#3b82f6', icon: <CodeOutlined /> },
    { key: 'vision', label: 'Vision', color: '#ec4899', icon: <EyeOutlined /> },
    { key: 'api', label: 'API', color: '#14b8a6', icon: <ApiOutlined /> },
    { key: 'logic', label: 'Logic', color: '#a855f7', icon: <BranchesOutlined /> },
    { key: 'cloud', label: 'Cloud', color: '#64748b', icon: <CloudOutlined /> },
    { key: 'search', label: 'Search', color: '#f97316', icon: <BulbOutlined /> },
    { key: 'file', label: 'File', color: '#22c55e', icon: <FileTextOutlined /> },
    { key: 'browser', label: 'Browser', color: '#f43f5e', icon: <GlobalOutlined /> },
    { key: 'general', label: 'General', color: '#8c8c8c', icon: <ExperimentOutlined /> },
];

interface Props {
    active: string;
    onChange: (key: string) => void;
    skills?: Skill[];
}

const SkillCategoryNav: React.FC<Props> = ({ active, onChange }) => {
    const { t } = useTranslation();

    return (
        <>
            {CATEGORY_DEFS.map((def) => (
                <Chip
                    key={def.key}
                    $active={active === def.key}
                    $color={def.color}
                    onClick={() => onChange(def.key)}
                    aria-pressed={active === def.key}
                >
                    {def.icon}
                    {t(`pages.skills.categories.${def.key}`, def.label)}
                </Chip>
            ))}
        </>
    );
};

export default SkillCategoryNav;
