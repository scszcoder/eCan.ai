import React, { useCallback, useMemo, useState } from 'react';
import {
    Tag,
    Empty,
    Spin,
    Dropdown,
} from 'antd';
import {
    StarFilled,
    DownloadOutlined,
    HeartOutlined,
    HeartFilled,
    UserOutlined,
    EditOutlined,
    CopyOutlined,
    EyeOutlined,
    FlagOutlined,
    PlayCircleOutlined,
    MoreOutlined,
    CloseOutlined,
    LockOutlined,
    SyncOutlined,
} from '@ant-design/icons';
import { useTranslation } from 'react-i18next';
import styled from '@emotion/styled';
import type { Skill } from '@/types/domain/skill';
import { useSkillStore } from '@/stores/domain/skillStore';
import { ReportSkillModal } from './SkillMarketplaceGrid';
import {
    getSkillPalette,
    formatNumber,
} from './skillPalette';
import { ownerKey } from '@/utils/ownerKey';

const Row = styled.div<{ $selected?: boolean; $variant?: string }>`
    display: grid;
    grid-template-columns: 56px minmax(0, 1.5fr) minmax(0, 2fr) auto auto auto auto;
    gap: 14px;
    align-items: center;
    padding: 14px 16px;
    border-radius: 14px;
    margin: 0 24px 8px;
    background: ${(p) => (p.$selected ? 'var(--primary-bg)' : 'var(--bg-secondary)')};
    border: 1px solid ${(p) =>
        p.$selected ? 'var(--primary-border)' : 'var(--border-color)'};
    cursor: pointer;
    transition: background 0.15s ease, border-color 0.15s ease;

    &:hover {
        background: ${(p) => (p.$selected ? 'var(--primary-bg-hover)' : 'var(--bg-tertiary)')};
        border-color: ${(p) => (p.$selected ? 'var(--primary-border)' : 'var(--border-color-hover)')};
    }

    @media (max-width: 900px) {
        grid-template-columns: 56px 1fr auto;
        gap: 10px;
    }
`;

const IconBadge = styled.div<{ $hue: string; $hueDark: string }>`
    width: 48px;
    height: 48px;
    border-radius: 12px;
    /* Category hue carried as a soft accent tile, matching the grid card. */
    background: color-mix(in srgb, ${(p) => p.$hue} 15%, transparent);
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 22px;
    color: ${(p) => p.$hueDark};

    /* Dark theme: the darker palette hue washes out on a dark tinted tile,
       so lighten the glyph and lift the tint for legibility. */
    body.dark & {
        background: color-mix(in srgb, ${(p) => p.$hue} 22%, transparent);
        color: color-mix(in srgb, ${(p) => p.$hue} 72%, white);
    }
`;

const TitleStack = styled.div`
    display: flex;
    flex-direction: column;
    min-width: 0;
    gap: 4px;
`;

const TitleText = styled.div`
    font-size: 14px;
    font-weight: 600;
    color: var(--text-primary);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
`;

const MetaRow = styled.div`
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 6px;
    font-size: 11px;
    color: var(--text-secondary);
`;

const DescCell = styled.div`
    font-size: 12.5px;
    line-height: 1.5;
    color: var(--text-secondary);
    display: -webkit-box;
    -webkit-line-clamp: 2;
    -webkit-box-orient: vertical;
    overflow: hidden;
    min-width: 0;

    @media (max-width: 900px) {
        display: none;
    }
`;

const Cell = styled.div`
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 2px;
    min-width: 80px;

    .value {
        font-size: 14px;
        font-weight: 700;
        color: var(--text-primary);
        line-height: 1;
    }
    .label {
        font-size: 10px;
        color: var(--text-secondary);
        text-transform: uppercase;
        letter-spacing: 0.4px;
    }

    @media (max-width: 900px) {
        display: none;
    }
`;

const ActionStack = styled.div`
    display: flex;
    align-items: center;
    gap: 6px;
`;

const PillButton = styled.button<{ $variant?: 'subscribe' | 'owned' | 'danger' | 'ghost' }>`
    border-radius: 8px;
    padding: 6px 14px;
    font-size: 12px;
    font-weight: 600;
    cursor: pointer;
    display: inline-flex;
    align-items: center;
    gap: 4px;
    transition: background 0.15s ease, border-color 0.15s ease, color 0.15s ease;
    white-space: nowrap;

    ${(p) => {
        switch (p.$variant) {
            case 'owned':
                return `
                    background: var(--primary-bg);
                    color: var(--primary-text);
                    border: 1px solid var(--primary-border);
                    &:hover { background: var(--primary-bg-hover); }
                `;
            case 'danger':
                return `
                    background: transparent;
                    color: var(--error-text);
                    border: 1px solid var(--error-border);
                    &:hover { background: var(--error-bg); }
                `;
            case 'ghost':
                return `
                    background: var(--surface-subtle-hover);
                    color: var(--text-secondary);
                    border: 1px solid var(--border-color);
                    &:hover { background: var(--highlight-top-strong); color: var(--text-primary); }
                `;
            case 'subscribe':
            default:
                return `
                    background: var(--primary-color);
                    color: var(--text-on-primary);
                    border: 1px solid var(--primary-color);
                    &:hover { background: var(--primary-hover); border-color: var(--primary-hover); }
                `;
        }
    }}

    .anticon {
        font-size: 13px;
    }
`;

const IconButton = styled.button<{ $active?: boolean }>`
    background: ${(p) => (p.$active ? 'var(--error-bg)' : 'transparent')};
    border: 1px solid ${(p) => (p.$active ? 'var(--error-border)' : 'var(--border-color)')};
    color: ${(p) => (p.$active ? 'var(--error-text)' : 'var(--text-secondary)')};
    width: 30px;
    height: 30px;
    border-radius: 8px;
    cursor: pointer;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    transition: background 0.15s ease, border-color 0.15s ease, color 0.15s ease;
    flex-shrink: 0;

    &:hover {
        background: ${(p) => (p.$active ? 'var(--error-bg)' : 'var(--surface-subtle-hover)')};
        color: ${(p) => (p.$active ? 'var(--error-text)' : 'var(--text-primary)')};
    }

    .anticon {
        font-size: 13px;
    }
`;

const isPaidSkillLocal = (s: Skill): boolean => {
    const price = (s as any)?.price;
    if (typeof price === 'number') return price > 0;
    if (typeof price === 'string') {
        const v = Number(price);
        return Number.isFinite(v) && v > 0;
    }
    return false;
};

const getSkillPaletteLocal = getSkillPalette;
void getSkillPaletteLocal;

export interface SkillMarketplaceListProps {
    skills: Skill[];
    loading: boolean;
    onSelectSkill: (skill: Skill) => void;
    selectedSkillId?: string;
    username: string;
    subscribedSkillIds?: string[];
    onSubscribe: (skillId: string) => Promise<void>;
    onUnsubscribe: (skillId: string) => Promise<void>;
    /** Update in place: latest skill + files + all its prompts, links kept. */
    onUpdate?: (skillId: string) => Promise<void>;
    onCopy: (skill: Skill) => Promise<void>;
    onRun?: (skill: Skill) => void;
    onDownload?: (skill: Skill) => Promise<void> | void;
    onReport: (skill: Skill, reason: string, note: string) => Promise<void> | void;
    onFavoriteToggle?: (skill: Skill) => Promise<void> | void;
    onEditInGrid: (skill: Skill) => void;
    variant?: 'default' | 'subscriptions' | 'favorites';
}

const SkillMarketplaceList: React.FC<SkillMarketplaceListProps> = ({
    skills,
    loading,
    onSelectSkill,
    selectedSkillId,
    username,
    subscribedSkillIds = [],
    onSubscribe,
    onUnsubscribe,
    onUpdate,
    onCopy,
    onRun,
    onReport,
    onFavoriteToggle,
    onEditInGrid,
    variant = 'default',
}) => {
    const { t } = useTranslation();
    const [reportSkill, setReportSkill] = useState<Skill | null>(null);

    const meLower = ownerKey(username);
    const favoriteIds = useSkillStore((s) => s.favoriteSkillIds);
    const favoriteSet = useMemo(() => new Set((favoriteIds || []).map(String)), [favoriteIds]);
    const subscribedSet = useMemo(() => new Set((subscribedSkillIds || []).map(String)), [subscribedSkillIds]);

    const isOwnedByMe = useCallback(
        (s: Skill) => {
            const owner = ownerKey((s as any)?.owner);
            const source = String((s as any)?.source || '').toLowerCase();
            if (source === 'code') return true;
            return owner === meLower;
        },
        [meLower]
    );

    const isSubscribed = useCallback(
        (s: Skill) => {
            const id = String((s as any)?.id || '');
            const askid = String((s as any)?.askid || '');
            return subscribedSet.has(id) || (askid && askid !== '0' && subscribedSet.has(askid));
        },
        [subscribedSet]
    );

    const renderRow = (skill: Skill) => {
        const skillIdStr = String((skill as any).id);
        const isSelected = selectedSkillId !== undefined && selectedSkillId === skillIdStr;
        const isFree = !isPaidSkillLocal(skill);
        const owned = isOwnedByMe(skill);
        const subscribed = !owned && isSubscribed(skill);
        const favorited = favoriteSet.has(skillIdStr);
        const palette = getSkillPalette(skill);

        const rating = Number((skill as any).rating ?? 5);
        const reviewCount = Number((skill as any).reviewCount ?? 0);
        const downloads = Number((skill as any).downloadCount ?? 0);

        const source = String((skill as any)?.source || '').toLowerCase();
        const isCode = source === 'code';
        const level = String((skill as any)?.level || 'entry');

        const moreMenuItems = [
            {
                key: 'view',
                icon: <EyeOutlined />,
                label: t('pages.skills.actions.view', 'View'),
                onClick: () => onSelectSkill(skill),
            },
            onRun && {
                key: 'run',
                icon: <PlayCircleOutlined />,
                label: t('pages.skills.run', 'Run'),
                onClick: () => onRun(skill),
            },
            isFree && !owned && onCopy && {
                key: 'copy',
                icon: <CopyOutlined />,
                label: t('common.copy', 'Copy to My Skills'),
                onClick: () => onCopy(skill),
            },
            !owned && onReport && {
                key: 'report',
                icon: <FlagOutlined />,
                label: t('pages.skills.actions.report', 'Report'),
                danger: true,
                onClick: () => setReportSkill(skill),
            },
        ].filter(Boolean) as any[];

        const titleLine = (
            <TitleText>
                {skill.name}
                {isCode && (
                    <Tag color="orange" style={{ marginLeft: 6, fontSize: 10, padding: '0 6px', borderRadius: 6 }}>
                        <LockOutlined /> {t('pages.skills.code', 'Code')}
                    </Tag>
                )}
            </TitleText>
        );

        return (
            <Row key={skillIdStr} $selected={isSelected} onClick={() => onSelectSkill(skill)}>
                <IconBadge $hue={palette.bg[0]} $hueDark={palette.bg[1]}>{palette.icon}</IconBadge>

                <TitleStack>
                    {titleLine}
                    <MetaRow>
                        <Tag color="blue" style={{ margin: 0, fontSize: 10, padding: '0 6px', borderRadius: 6 }}>
                            {t(`pages.skills.levels.${level}`, level)}
                        </Tag>
                        <Tag
                            color={isFree ? 'success' : 'warning'}
                            style={{ margin: 0, fontSize: 10, padding: '0 6px', borderRadius: 6, lineHeight: '16px' }}
                        >
                            {isFree ? t('pages.skills.free', 'Free') : t('pages.skills.paid', 'Paid')}
                        </Tag>
                        {owned ? (
                            <Tag color="green" style={{ margin: 0, fontSize: 10, padding: '0 6px', borderRadius: 6, lineHeight: '16px' }}>
                                {t('pages.skills.ownedBadge', 'Owned')}
                            </Tag>
                        ) : subscribed ? (
                            <Tag color="red" style={{ margin: 0, fontSize: 10, padding: '0 6px', borderRadius: 6, lineHeight: '16px' }}>
                                {t('pages.skills.subscribed', 'Subscribed')}
                            </Tag>
                        ) : null}
                    </MetaRow>
                </TitleStack>

                <DescCell>{skill.description || '—'}</DescCell>

                <Cell>
                    <span className="value">{rating > 0 ? rating.toFixed(1) : '—'}</span>
                    <span className="label">
                        <StarFilled style={{ color: 'var(--warning-text)', marginRight: 2 }} />
                        {t('pages.skills.rating', 'Rating')} · {reviewCount}
                    </span>
                </Cell>

                <Cell>
                    <span className="value">{formatNumber(downloads)}</span>
                    <span className="label">
                        <DownloadOutlined style={{ marginRight: 2 }} />
                        {t('pages.skills.downloads', 'Downloads')}
                    </span>
                </Cell>

                <Cell>
                    <span className="value" style={{ fontSize: 12 }}>
                        {String((skill as any).owner || '').split('@')[0]?.slice(0, 12) || '—'}
                    </span>
                    <span className="label">
                        <UserOutlined style={{ marginRight: 2 }} />
                        {t('common.owner', 'Owner')}
                    </span>
                </Cell>

                <ActionStack onClick={(e) => e.stopPropagation()}>
                    {onFavoriteToggle && !owned && (
                        <IconButton
                            $active={favorited}
                            onClick={() => onFavoriteToggle(skill)}
                            title={favorited ? t('pages.skills.unfavorite', 'Unfavorite') : t('pages.skills.favorite', 'Favorite')}
                        >
                            {favorited ? <HeartFilled /> : <HeartOutlined />}
                        </IconButton>
                    )}

                    {owned ? (
                        <PillButton
                            $variant="owned"
                            onClick={() => onEditInGrid(skill)}
                        >
                            <EditOutlined /> {t('pages.skills.edit', 'Edit')}
                        </PillButton>
                    ) : subscribed && (skill as any)?.update_available ? (
                        <PillButton
                            $variant="subscribe"
                            onClick={() => (onUpdate ?? onSubscribe)(skillIdStr)}
                            title={t('pages.skills.updateAvailableHint', 'A newer version was published — click to update')}
                        >
                            <DownloadOutlined /> {t('pages.skills.updateAction', 'Update')}
                        </PillButton>
                    ) : subscribed ? (
                        <>
                            {onUpdate && (
                                <PillButton
                                    $variant="subscribe"
                                    onClick={() => onUpdate(skillIdStr)}
                                    title={t('pages.skills.updateHint', '获取作者的最新版本及其提示词，不影响已关联的智能体和任务')}
                                >
                                    <SyncOutlined /> {t('pages.skills.updateAction', 'Update')}
                                </PillButton>
                            )}
                            <PillButton
                                $variant="danger"
                                onClick={() => onUnsubscribe(skillIdStr)}
                            >
                                <CloseOutlined /> {t('pages.skills.unsubscribe', 'Unsubscribe')}
                            </PillButton>
                        </>
                    ) : (
                        <PillButton
                            $variant="subscribe"
                            onClick={() => onSubscribe(skillIdStr)}
                        >
                            <DownloadOutlined /> {t('pages.skills.getAction', 'Get')}
                        </PillButton>
                    )}

                    {moreMenuItems.length > 0 && (
                        <Dropdown menu={{ items: moreMenuItems }} trigger={['click']} placement="bottomRight">
                            <IconButton title={t('pages.skills.moreActions', 'More')}>
                                <MoreOutlined />
                            </IconButton>
                        </Dropdown>
                    )}
                </ActionStack>
            </Row>
        );
    };

    if (loading) {
        return (
            <div style={{ padding: 60, textAlign: 'center' }}>
                <Spin size="large" />
            </div>
        );
    }

    if (!skills || skills.length === 0) {
        const emptyMsg =
            variant === 'subscriptions'
                ? t('pages.skills.subscriptions.empty', 'No subscriptions yet. Browse the Skill Store to subscribe.')
                : variant === 'favorites'
                ? t('pages.skills.favoritesEmpty', 'No favorites yet. Tap the heart icon on any skill to add it here.')
                : t('pages.skills.noMatchingSkills', 'No matching skills found');
        return (
            <div style={{ padding: 60, textAlign: 'center' }}>
                <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={emptyMsg} />
            </div>
        );
    }

    return (
        <div style={{ padding: '8px 0 24px' }}>
            {skills.map(renderRow)}
            <ReportSkillModal
                open={!!reportSkill}
                skill={reportSkill}
                onCancel={() => setReportSkill(null)}
                onSubmit={async (reason, note) => {
                    if (reportSkill && onReport) await onReport(reportSkill, reason, note);
                }}
            />
        </div>
    );
};

export default SkillMarketplaceList;
