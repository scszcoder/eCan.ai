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

const Chip = styled.button<{ $active?: boolean; $color?: string; $textColor?: string }>`
    flex-shrink: 0;
    display: inline-flex;
    align-items: center;
    gap: 5px;
    padding: 5px 12px;
    border-radius: 999px;
    /* $color is a var() expression, so hex-alpha suffixes like "$color66"
       are invalid CSS and get dropped. Use color-mix so the tint resolves in
       both themes; $textColor is the AA-safe foreground ramp. */
    border: 1px solid ${(p) =>
        p.$active ? `color-mix(in srgb, ${p.$color || 'var(--primary-color)'} 40%, transparent)` : 'var(--surface-subtle)'};
    background: ${(p) =>
        p.$active
            ? `color-mix(in srgb, ${p.$color || 'var(--primary-color)'} 16%, transparent)`
            : 'var(--surface-subtle)'};
    color: ${(p) => (p.$active ? p.$textColor || p.$color || 'var(--primary-color)' : 'var(--text-secondary)')};
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
                ? `linear-gradient(135deg, ${p.$color || 'var(--primary-color)'}44, ${p.$color || 'var(--primary-color)'}22)`
                : 'var(--surface-subtle)'};
        color: var(--text-primary);
        border-color: ${(p) =>
            p.$active ? `${p.$color || 'var(--primary-color)'}88` : 'var(--border-color-hover)'};
    }
`;

const CATEGORY_DEFS: Array<{ key: string; label: string; color: string; icon: React.ReactNode }> = [
    { key: 'all', label: 'All', color: 'var(--primary-text)', icon: <AppstoreOutlined /> },
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
    { key: 'general', label: 'General', color: 'var(--text-tertiary)', icon: <ExperimentOutlined /> },
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
