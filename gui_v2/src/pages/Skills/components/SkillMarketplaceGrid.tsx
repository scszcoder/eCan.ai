import React, { useState, useMemo, useCallback } from 'react';
import {
    Space,
    Tag,
    Tooltip,
    Button,
    Empty,
    Spin,
    Dropdown,
    Modal,
    Input,
    Form,
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
    RiseOutlined,
    MoreOutlined,
    CloseOutlined,
    CheckCircleOutlined,
    LockOutlined,
    SyncOutlined,
} from '@ant-design/icons';
import { useTranslation } from 'react-i18next';
import styled from '@emotion/styled';
import type { Skill } from '@/types/domain/skill';
import { useSkillStore } from '@/stores/domain/skillStore';
import {
    getSkillPalette,
    formatNumber,
    isPaidSkill,
    safeTags,
} from './skillPalette';
import { ownerKey } from '@/utils/ownerKey';

// ============== Styled ==============
const Grid = styled.div`
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
    gap: 16px;
    padding: 8px 24px 24px;

    @media (max-width: 600px) {
        grid-template-columns: 1fr;
    }
`;

const Card = styled.div<{ $selected?: boolean }>`
    background: var(--bg-secondary);
    border-radius: 16px;
    display: flex;
    flex-direction: column;
    cursor: pointer;
    transition: border-color 0.18s ease, box-shadow 0.18s ease, transform 0.18s ease;
    border: 1px solid var(--border-color);
    box-shadow: var(--elev-2, var(--shadow-md));
    position: relative;

    &:hover {
        transform: translateY(-2px);
        border-color: var(--border-color-hover);
        box-shadow: var(--elev-3, var(--shadow-lg));
    }

    ${(p) => p.$selected ? `
        border-color: var(--primary-border);
        box-shadow: 0 0 0 1px var(--primary-border), var(--elev-2, var(--shadow-md));
    ` : ''}
`;

const CardHeader = styled.div`
    display: flex;
    align-items: flex-start;
    gap: 12px;
    padding: 16px 16px 12px;
`;

const IconBadge = styled.div<{ $hue: string; $hueDark: string }>`
    width: 46px;
    height: 46px;
    border-radius: 13px;
    flex-shrink: 0;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 21px;
    background: ${(p) => `color-mix(in srgb, ${p.$hue} 15%, transparent)`};
    color: ${(p) => p.$hueDark};

    /* In the dark theme both the card and the tinted tile are dark, so the
       darker palette hue ($hueDark) collapses to ~1.6:1. Lighten the glyph
       toward its own hue and let the tile breathe a little more so the icon
       stays legible, while the light theme keeps the crisp darker-hue glyph. */
    body.dark & {
        background: ${(p) => `color-mix(in srgb, ${p.$hue} 22%, transparent)`};
        color: ${(p) => `color-mix(in srgb, ${p.$hue} 72%, white)`};
    }
`;

const HeaderMain = styled.div`
    flex: 1;
    min-width: 0;
    display: flex;
    flex-direction: column;
    gap: 4px;
`;

const TitleText = styled.div`
    font-size: 15.5px;
    font-weight: 600;
    color: var(--text-primary);
    line-height: 1.32;
    display: -webkit-box;
    -webkit-line-clamp: 2;
    -webkit-box-orient: vertical;
    overflow: hidden;
`;

const MetaLine = styled.div`
    display: flex;
    align-items: center;
    gap: 6px;
    flex-wrap: wrap;
    font-size: 11.5px;
    color: var(--text-muted);
    min-width: 0;

    .anticon {
        font-size: 12px;
    }

    .dot {
        width: 3px;
        height: 3px;
        border-radius: 50%;
        background: currentColor;
        opacity: 0.5;
    }
`;

const OwnerName = styled.span`
    min-width: 0;
    max-width: 150px;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
`;

const PriceTag = styled.span<{ $isFree: boolean }>`
    flex-shrink: 0;
    font-size: 10px;
    font-weight: 700;
    padding: 3px 8px;
    border-radius: 6px;
    text-transform: uppercase;
    letter-spacing: 0.4px;
    ${(p) =>
        p.$isFree
            ? `background: var(--success-bg); color: var(--success-text);`
            : `background: var(--warning-bg); color: var(--warning-text);`}
`;

const Body = styled.div`
    padding: 0 16px 14px;
    display: flex;
    flex-direction: column;
    gap: 10px;
    flex: 1;
`;

const Description = styled.div`
    font-size: 12.5px;
    line-height: 1.5;
    color: var(--text-secondary);
    display: -webkit-box;
    -webkit-line-clamp: 2;
    -webkit-box-orient: vertical;
    overflow: hidden;
    min-height: 36px;
`;

const TagsRow = styled.div`
    display: flex;
    flex-wrap: wrap;
    gap: 4px;
`;

const TagPill = styled.span<{ $color?: string; $textColor?: string }>`
    font-size: 11px;
    padding: 2px 8px;
    border-radius: 6px;
    /* $color is a var() expression, so a bare hex-alpha suffix is invalid CSS
       and the whole declaration gets dropped. Mix against the surface instead
       so the tint works in both themes. $textColor is the AA-safe foreground
       ramp for cases where it differs from the fill hue. */
    background: ${(p) => (p.$color ? `color-mix(in srgb, ${p.$color} 10%, transparent)` : 'var(--surface-subtle-hover)')};
    color: ${(p) => p.$textColor || p.$color || 'var(--text-secondary)'};
    border: 1px solid ${(p) => (p.$color ? `color-mix(in srgb, ${p.$color} 20%, transparent)` : 'var(--border-color)')};
`;

const StatsRow = styled.div`
    display: flex;
    align-items: center;
    gap: 14px;
    flex-wrap: wrap;
    white-space: nowrap;
    margin-top: auto;
`;

const Stat = styled.div`
    display: inline-flex;
    align-items: center;
    gap: 4px;
    font-size: 12px;
    color: var(--text-secondary);

    .anticon {
        font-size: 13px;
        opacity: 0.85;
    }
    .stat-value {
        color: var(--text-secondary);
        font-weight: 500;
    }
`;

const Footer = styled.div`
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 8px;
    padding: 12px 16px;
    border-top: 1px solid var(--border-color);
`;

const FooterActions = styled.div`
    display: flex;
    align-items: center;
    gap: 8px;
`;

const PrimaryAction = styled.button<{ $variant?: 'subscribe' | 'owned' | 'favorited' }>`
    border-radius: 8px;
    padding: 7px 16px;
    font-size: 12.5px;
    font-weight: 600;
    cursor: pointer;
    display: inline-flex;
    align-items: center;
    gap: 5px;
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
            case 'favorited':
                return `
                    background: var(--error-fill);
                    color: var(--text-on-primary);
                    border: 1px solid var(--error-fill);
                    &:hover { background: var(--error-color); border-color: var(--error-color); }
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

const FavoriteButton = styled.button<{ $active?: boolean }>`
    background: ${(p) => (p.$active ? 'var(--error-bg)' : 'transparent')};
    border: 1px solid ${(p) => (p.$active ? 'var(--error-border)' : 'var(--border-color)')};
    color: ${(p) => (p.$active ? 'var(--error-text)' : 'var(--text-secondary)')};
    width: 32px;
    height: 32px;
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
        font-size: 14px;
    }
`;

const TrendingRibbon = styled.span`
    display: inline-flex;
    align-items: center;
    gap: 3px;
    font-size: 10px;
    font-weight: 600;
    padding: 2px 7px;
    border-radius: 999px;
    color: var(--warning-text);
    background: color-mix(in srgb, var(--warning-color) 14%, transparent);
    border: 1px solid color-mix(in srgb, var(--warning-color) 30%, transparent);

    .anticon {
        font-size: 10px;
    }
`;

const getOwnerDisplayName = (skill: Skill): string => {
    const value = skill as any;
    const extra = value?.extra_data && typeof value.extra_data === 'object'
        ? value.extra_data
        : {};
    const candidates = [
        value.owner_name,
        value.ownerName,
        value.author_name,
        value.authorName,
        value.nickname,
        value.nickName,
        extra.owner_name,
        extra.ownerName,
        extra.author_name,
        extra.authorName,
        extra.nickname,
        extra.nickName,
        value.owner,
    ];

    const displayName = candidates.find((candidate) =>
        typeof candidate === 'string' && candidate.trim().length > 0
    );
    return displayName?.trim() || 'unknown';
};

// ============== Report Modal ==============
export interface ReportSkillModalProps {
    open: boolean;
    skill: Skill | null;
    onCancel: () => void;
    onSubmit: (reason: string, note: string) => Promise<void>;
}

const getReportReasons = (t: (k: string, d?: string) => string) => [
    { key: 'spam', label: t('pages.skills.reportReason.spam', 'Spam or misleading') },
    { key: 'broken', label: t('pages.skills.reportReason.broken', 'Broken or non-functional') },
    { key: 'unsafe', label: t('pages.skills.reportReason.unsafe', 'Unsafe or malicious') },
    { key: 'duplicate', label: t('pages.skills.reportReason.duplicate', 'Duplicate of another skill') },
    { key: 'other', label: t('pages.skills.reportReason.other', 'Other (please describe)') },
];

const ReportSkillModal: React.FC<ReportSkillModalProps> = ({ open, skill, onCancel, onSubmit }) => {
    const { t } = useTranslation();
    const [reason, setReason] = useState<string>('spam');
    const [note, setNote] = useState('');
    const [submitting, setSubmitting] = useState(false);

    const handleOk = async () => {
        setSubmitting(true);
        try {
            await onSubmit(reason, note);
            onCancel();
            setNote('');
        } finally {
            setSubmitting(false);
        }
    };

    return (
        <Modal
            open={open}
            title={
                <Space>
                    <FlagOutlined style={{ color: 'var(--error-text)' }} />
                    {t('pages.skills.reportTitle', 'Report this skill')}
                </Space>
            }
            onCancel={onCancel}
            onOk={handleOk}
            okText={t('common.submit', 'Submit')}
            cancelText={t('common.cancel', 'Cancel')}
            confirmLoading={submitting}
            destroyOnHidden
        >
            {skill && (
                <div style={{ marginBottom: 12 }}>
                    <Tag color="blue">{skill.name}</Tag>
                </div>
            )}
            <Form layout="vertical">
                <Form.Item label={t('pages.skills.reportReasonLabel', 'Reason')}>
                    <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
                        {getReportReasons(t).map((r) => (
                            <Button
                                key={r.key}
                                size="small"
                                type={reason === r.key ? 'primary' : 'default'}
                                onClick={() => setReason(r.key)}
                            >
                                {r.label}
                            </Button>
                        ))}
                    </div>
                </Form.Item>
                <Form.Item label={t('pages.skills.reportNote', 'Note (optional)')}>
                    <Input.TextArea
                        rows={3}
                        value={note}
                        onChange={(e) => setNote(e.target.value)}
                        placeholder={t('pages.skills.reportNotePlaceholder', 'Describe the issue...')}
                    />
                </Form.Item>
            </Form>
        </Modal>
    );
};

// ============== Main Component ==============
export interface SkillMarketplaceGridProps {
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
    onReport: (skill: Skill, reason: string, note: string) => Promise<void> | void;
    onFavoriteToggle?: (skill: Skill) => Promise<void> | void;
    onEditInGrid: (skill: Skill) => void;
}

const SkillMarketplaceGrid: React.FC<SkillMarketplaceGridProps> = ({
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

    const handleCardClick = (skill: Skill) => onSelectSkill(skill);

    const renderCard = (skill: Skill) => {
        const skillIdStr = String((skill as any).id);
        const isSelected = selectedSkillId !== undefined && selectedSkillId === skillIdStr;
        const isFree = !isPaidSkill(skill);
        const owned = isOwnedByMe(skill);
        const subscribed = !owned && isSubscribed(skill);
        const favorited = favoriteSet.has(skillIdStr);
        const palette = getSkillPalette(skill);
        const ownerDisplayName = getOwnerDisplayName(skill);

        // Category hue carried only as a soft icon accent, not a full-bleed block.
        const tileHue = palette.bg[0];
        const tileHueDark = palette.bg[1];

        const rating = Number((skill as any).rating ?? 5);
        const reviewCount = Number((skill as any).reviewCount ?? 0);
        const downloads = Number((skill as any).downloadCount ?? 0);
        const trending = Number((skill as any).trendingScore ?? 0);
        const isTrending = trending >= 60 || downloads >= 100;

        const source = String((skill as any)?.source || '').toLowerCase();
        const isCode = source === 'code';
        const level = String((skill as any)?.level || 'entry');
        const tags = safeTags((skill as any)?.tags).slice(0, 3);

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
                onClick: () => onRun?.(skill),
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

        return (
            <Card
                key={skillIdStr}
                $selected={isSelected}
                onClick={() => handleCardClick(skill)}
            >
                <CardHeader>
                    <IconBadge $hue={tileHue} $hueDark={tileHueDark}>{palette.icon}</IconBadge>
                    <HeaderMain>
                        <TitleText title={skill.name}>{skill.name}</TitleText>
                        <MetaLine>
                            <Tooltip title={ownerDisplayName} mouseEnterDelay={0.3}>
                                <span style={{ display: 'inline-flex', alignItems: 'center', gap: 4, minWidth: 0 }}>
                                    <UserOutlined />
                                    <OwnerName>{ownerDisplayName}</OwnerName>
                                </span>
                            </Tooltip>
                            <span className="dot" />
                            <span style={{ display: 'inline-flex', alignItems: 'center', gap: 3 }}>
                                {isCode ? (
                                    <><LockOutlined /> {t('pages.skills.code', 'Code')}</>
                                ) : (skill as any)?.public ? (
                                    <><CheckCircleOutlined /> {t('pages.skills.public', 'Public')}</>
                                ) : (
                                    <><CloseOutlined /> {t('pages.skills.private', 'Private')}</>
                                )}
                            </span>
                            {isTrending && (
                                <TrendingRibbon>
                                    <RiseOutlined /> {t('pages.skills.trending', 'Trending')}
                                </TrendingRibbon>
                            )}
                        </MetaLine>
                    </HeaderMain>
                    <PriceTag $isFree={isFree}>
                        {isFree ? t('pages.skills.free', 'Free') : t('pages.skills.paid', 'Paid')}
                    </PriceTag>
                </CardHeader>

                <Body>
                    {skill.description && <Description>{skill.description}</Description>}

                    {tags.length > 0 && (
                        <TagsRow>
                            {tags.map((tag, idx) => (
                                <TagPill key={`${tag}-${idx}`} $color="var(--accent-color)" $textColor="var(--accent-text)">#{tag}</TagPill>
                            ))}
                        </TagsRow>
                    )}

                    {/* Level + rating + downloads + subscribers on a single row */}
                    <StatsRow>
                        <TagPill $color="var(--primary-color)" $textColor="var(--primary-text)">
                            {t(`pages.skills.levels.${level}`, level)}
                        </TagPill>
                        <Tooltip title={t('pages.skills.rating', 'Rating')}>
                            <Stat>
                                <StarFilled style={{ color: 'var(--warning-text)' }} />
                                <span className="stat-value">{rating.toFixed(1)}</span>
                                <span style={{ fontSize: 11, opacity: 0.7 }}>({reviewCount})</span>
                            </Stat>
                        </Tooltip>
                        <Tooltip title={t('pages.skills.downloads', 'Downloads')}>
                            <Stat>
                                <DownloadOutlined />
                                <span className="stat-value">{formatNumber(downloads)}</span>
                            </Stat>
                        </Tooltip>
                        <Tooltip title={t('pages.skills.subscribers', 'Subscribers')}>
                            <Stat>
                                <UserOutlined />
                                <span className="stat-value">{formatNumber(Number((skill as any).subscriberCount ?? subscribedSkillIds.length))}</span>
                            </Stat>
                        </Tooltip>
                    </StatsRow>
                </Body>

                <Footer>
                    <FooterActions>
                        {onFavoriteToggle && !owned && (
                            <FavoriteButton
                                $active={favorited}
                                onClick={(e) => {
                                    e.stopPropagation();
                                    onFavoriteToggle(skill);
                                }}
                                title={favorited ? t('pages.skills.unfavorite', 'Unfavorite') : t('pages.skills.favorite', 'Favorite')}
                            >
                                {favorited ? <HeartFilled /> : <HeartOutlined />}
                            </FavoriteButton>
                        )}
                        {moreMenuItems.length > 0 && (
                            <Dropdown menu={{ items: moreMenuItems }} trigger={['click']} placement="bottomRight">
                                <FavoriteButton
                                    onClick={(e) => e.stopPropagation()}
                                    title={t('pages.skills.moreActions', 'More actions')}
                                >
                                    <MoreOutlined />
                                </FavoriteButton>
                            </Dropdown>
                        )}
                    </FooterActions>

                    <FooterActions>
                        {owned ? (
                            <PrimaryAction
                                $variant="owned"
                                onClick={(e) => {
                                    e.stopPropagation();
                                    onEditInGrid(skill);
                                }}
                            >
                                <EditOutlined /> {t('pages.skills.edit', 'Edit')}
                            </PrimaryAction>
                        ) : subscribed && (skill as any)?.update_available ? (
                            <PrimaryAction
                                $variant="subscribe"
                                onClick={(e) => {
                                    e.stopPropagation();
                                    (onUpdate ?? onSubscribe)(skillIdStr);
                                }}
                                title={t('pages.skills.updateAvailableHint', 'A newer version was published — click to update')}
                            >
                                <DownloadOutlined /> {t('pages.skills.updateAction', 'Update')}
                            </PrimaryAction>
                        ) : subscribed ? (
                            <Dropdown
                                menu={{
                                    items: [
                                        ...(onUpdate ? [{
                                            key: 'update',
                                            icon: <SyncOutlined />,
                                            label: t('pages.skills.updateAction', 'Update'),
                                            onClick: () => onUpdate(skillIdStr),
                                        }] : []),
                                        {
                                            key: 'unsubscribe',
                                            icon: <CloseOutlined />,
                                            label: t('pages.skills.unsubscribe', 'Unsubscribe'),
                                            danger: true,
                                            onClick: () => onUnsubscribe(skillIdStr),
                                        },
                                        ...moreMenuItems,
                                    ],
                                }}
                                trigger={['click']}
                                placement="bottomRight"
                            >
                                <PrimaryAction
                                    $variant="owned"
                                    onClick={(e) => e.stopPropagation()}
                                >
                                    <CheckCircleOutlined /> {t('pages.skills.subscribed', 'Subscribed')}
                                </PrimaryAction>
                            </Dropdown>
                        ) : (
                            <PrimaryAction
                                $variant="subscribe"
                                onClick={(e) => {
                                    e.stopPropagation();
                                    onSubscribe(skillIdStr);
                                }}
                                title={t('pages.skills.subscribeGet', 'Get')}
                            >
                                <DownloadOutlined /> {t('pages.skills.getAction', 'Get')}
                            </PrimaryAction>
                        )}
                    </FooterActions>
                </Footer>
            </Card>
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
        return (
            <div style={{ padding: 60, textAlign: 'center' }}>
                <Empty
                    image={Empty.PRESENTED_IMAGE_SIMPLE}
                    description={t('pages.skills.noMatchingSkills', 'No matching skills found')}
                />
            </div>
        );
    }

    return (
        <>
            <Grid>{skills.map(renderCard)}</Grid>
            <ReportSkillModal
                open={!!reportSkill}
                skill={reportSkill}
                onCancel={() => setReportSkill(null)}
                onSubmit={async (reason, note) => {
                    if (reportSkill && onReport) await onReport(reportSkill, reason, note);
                }}
            />
        </>
    );
};

export default SkillMarketplaceGrid;
export { ReportSkillModal };
