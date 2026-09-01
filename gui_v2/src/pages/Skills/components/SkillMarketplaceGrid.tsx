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
    border-radius: 12px;
    overflow: hidden;
    display: flex;
    flex-direction: column;
    cursor: pointer;
    transition: transform 0.2s ease, border-color 0.2s ease, box-shadow 0.2s ease;
    border: 1px solid rgba(255, 255, 255, 0.06);
    box-shadow: 0 2px 8px rgba(0, 0, 0, 0.08);
    position: relative;

    &:hover {
        transform: translateY(-2px);
        border-color: rgba(255, 255, 255, 0.1);
        box-shadow: 0 8px 24px rgba(0, 0, 0, 0.15);
    }

    ${(p) => p.$selected ? `
        border-color: rgba(24, 144, 255, 0.4);
        box-shadow: 0 0 0 1px rgba(24, 144, 255, 0.2), 0 4px 16px rgba(24, 144, 255, 0.1);
    ` : ''}
`;

const CardHeader = styled.div<{ $bg: [string, string] }>`
    position: relative;
    padding: 14px 16px;
    background: linear-gradient(135deg, ${(p) => p.$bg[0]}, ${(p) => p.$bg[1]});
    display: flex;
    align-items: center;
    justify-content: space-between;
    min-height: 72px;
`;

const IconBadge = styled.div<{ $bg: [string, string] }>`
    width: 44px;
    height: 44px;
    border-radius: 10px;
    background: linear-gradient(135deg, rgba(255,255,255,0.2), rgba(255,255,255,0.06));
    /* backdrop-filter: blur(8px); 移除以提升低性能电脑性能 */
    /* -webkit-backdrop-filter: blur(8px); */
    border: 1px solid rgba(255, 255, 255, 0.2);
    color: #fff;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 20px;
    transition: transform 0.2s ease;

    &:hover {
        transform: scale(1.06);
    }
`;

const HeaderRight = styled.div`
    display: flex;
    flex-direction: column;
    gap: 6px;
    align-items: flex-end;
    min-width: 0;
    max-width: calc(100% - 54px);
`;

const HeaderBadges = styled.div`
    display: flex;
    flex-direction: row;
    gap: 5px;
    align-items: center;
    min-width: 0;
    max-width: 100%;
`;

const HeaderActions = styled.div`
    display: flex;
    align-items: center;
    gap: 6px;
`;

const HeaderBadge = styled.div<{ $bg: string }>`
    background: ${(p) => p.$bg};
    color: #fff;
    min-width: 0;
    font-size: 10px;
    font-weight: 600;
    padding: 2px 8px;
    border-radius: 999px;
    display: inline-flex;
    align-items: center;
    gap: 3px;
    text-transform: uppercase;
    white-space: nowrap;
    /* backdrop-filter: blur(6px); 移除以提升低性能电脑性能 */
    /* -webkit-backdrop-filter: blur(6px); */
    border: 1px solid rgba(255, 255, 255, 0.12);

    .anticon {
        font-size: 10px;
        flex-shrink: 0;
    }
`;

const OwnerName = styled.span`
    min-width: 0;
    max-width: 180px;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
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

const Body = styled.div`
    padding: 14px 16px 12px;
    display: flex;
    flex-direction: column;
    gap: 10px;
    flex: 1;
`;

const TitleRow = styled.div`
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
    gap: 10px;
`;

const TitleText = styled.div`
    font-size: 16px;
    font-weight: 600;
    color: rgba(241, 245, 249, 0.92);
    line-height: 1.35;
    flex: 1;
    display: -webkit-box;
    -webkit-line-clamp: 1;
    -webkit-box-orient: vertical;
    overflow: hidden;
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
            ? `background: rgba(16, 185, 129, 0.18); color: #34d399;`
            : `background: rgba(245, 158, 11, 0.18); color: #fbbf24;`}
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

const TagPill = styled.span<{ $color?: string }>`
    font-size: 11px;
    padding: 2px 8px;
    border-radius: 6px;
    background: ${(p) => (p.$color ? `${p.$color}1a` : 'rgba(255, 255, 255, 0.06)')};
    color: ${(p) => p.$color || 'var(--text-secondary)'};
    border: 1px solid ${(p) => (p.$color ? `${p.$color}33` : 'rgba(255, 255, 255, 0.06)')};
`;

const StatsRow = styled.div`
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 6px 0;
    border-top: 1px solid rgba(255, 255, 255, 0.05);
    border-bottom: 1px solid rgba(255, 255, 255, 0.05);
    gap: 8px;
    white-space: nowrap;
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

const PrimaryAction = styled.button<{ $variant?: 'subscribe' | 'owned' | 'favorited' }>`
    border: none;
    border-radius: 999px;
    padding: 6px 14px;
    font-size: 12px;
    font-weight: 600;
    cursor: pointer;
    display: inline-flex;
    align-items: center;
    gap: 4px;
    transition: all 0.15s ease;
    white-space: nowrap;

    ${(p) => {
        switch (p.$variant) {
            case 'owned':
                return `
                    background: rgba(82, 196, 26, 0.15);
                    color: #52c41a;
                    border: 1px solid rgba(82, 196, 26, 0.3);
                    &:hover { background: rgba(82, 196, 26, 0.25); }
                `;
            case 'favorited':
                return `
                    background: rgba(245, 34, 45, 0.12);
                    color: #ff4d4f;
                    &:hover { background: rgba(245, 34, 45, 0.18); }
                `;
            case 'subscribe':
            default:
                return `
                    background: linear-gradient(135deg, #1890ff, #40a9ff);
                    color: #fff;
                    &:hover { transform: translateY(-1px); box-shadow: 0 4px 14px rgba(24,144,255,0.35); }
                `;
        }
    }}

    .anticon {
        font-size: 13px;
    }
`;

const FavoriteButton = styled.button<{ $active?: boolean }>`
    background: ${(p) => (p.$active ? 'rgba(245, 34, 45, 0.15)' : 'rgba(255, 255, 255, 0.06)')};
    border: 1px solid ${(p) => (p.$active ? 'rgba(245, 34, 45, 0.35)' : 'rgba(255, 255, 255, 0.08)')};
    color: ${(p) => (p.$active ? '#ff7875' : 'rgba(255, 255, 255, 0.65)')};
    width: 30px;
    height: 30px;
    border-radius: 999px;
    cursor: pointer;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    transition: all 0.15s ease;
    flex-shrink: 0;

    &:hover {
        background: rgba(245, 34, 45, 0.15);
        color: #ff7875;
    }

    .anticon {
        font-size: 14px;
    }
`;

const TrendingRibbon = styled.div`
    position: absolute;
    top: 8px;
    left: 8px;
    z-index: 2;
    background: linear-gradient(135deg, rgba(250,173,20,0.88), rgba(255,122,69,0.88));
    /* backdrop-filter: blur(8px); 移除以提升低性能电脑性能 */
    /* -webkit-backdrop-filter: blur(8px); */
    color: #fff;
    font-size: 10px;
    font-weight: 700;
    padding: 3px 8px;
    border-radius: 999px;
    display: inline-flex;
    align-items: center;
    gap: 4px;
    border: 1px solid rgba(255,255,255,0.22);
    box-shadow: 0 2px 10px rgba(250,173,20,0.25);
    text-transform: uppercase;
    letter-spacing: 0.5px;

    .anticon {
        font-size: 11px;
    }
`;

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
                    <FlagOutlined style={{ color: '#ff4d4f' }} />
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
                <Form.Item label={t('pages.skills.reportReason', 'Reason')}>
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
    onCopy,
    onRun,
    onReport,
    onFavoriteToggle,
    onEditInGrid,
}) => {
    const { t } = useTranslation();
    const [reportSkill, setReportSkill] = useState<Skill | null>(null);

    const meLower = (username || '').toLowerCase();
    const favoriteIds = useSkillStore((s) => s.favoriteSkillIds);
    const favoriteSet = useMemo(() => new Set((favoriteIds || []).map(String)), [favoriteIds]);
    const subscribedSet = useMemo(() => new Set((subscribedSkillIds || []).map(String)), [subscribedSkillIds]);

    const isOwnedByMe = useCallback(
        (s: Skill) => {
            const owner = String((s as any)?.owner || '').toLowerCase();
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
                {isTrending && (
                    <TrendingRibbon>
                        <RiseOutlined /> {t('pages.skills.trending', 'Trending')}
                    </TrendingRibbon>
                )}

                <CardHeader $bg={palette.bg}>
                    <IconBadge>{palette.icon}</IconBadge>
                    <HeaderRight>
                        <HeaderBadges>
                            <Tooltip title={ownerDisplayName} mouseEnterDelay={0.3}>
                                <HeaderBadge $bg="rgba(0,0,0,0.35)">
                                    <UserOutlined />
                                    <OwnerName>{ownerDisplayName}</OwnerName>
                                </HeaderBadge>
                            </Tooltip>
                            <HeaderBadge $bg="rgba(0,0,0,0.35)">
                                {isCode ? (
                                    <><LockOutlined /> {t('pages.skills.code', 'Code')}</>
                                ) : (skill as any)?.public ? (
                                    <><CheckCircleOutlined /> {t('pages.skills.public', 'Public')}</>
                                ) : (
                                    <><CloseOutlined /> {t('pages.skills.private', 'Private')}</>
                                )}
                            </HeaderBadge>
                        </HeaderBadges>
                        <HeaderActions>
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
                                        onSubscribe(skillIdStr);
                                    }}
                                    title={t('pages.skills.updateAvailableHint', 'A newer version was published — click to update')}
                                >
                                    <DownloadOutlined /> {t('pages.skills.updateAction', 'Update')}
                                </PrimaryAction>
                            ) : subscribed ? (
                                <Dropdown
                                    menu={{
                                        items: [
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
                            {moreMenuItems.length > 0 && (
                                <Dropdown menu={{ items: moreMenuItems }} trigger={['click']} placement="bottomRight">
                                    <FavoriteButton
                                        onClick={(e) => e.stopPropagation()}
                                        title={t('pages.skills.moreActions', 'More actions')}
                                        style={{ width: 28, height: 28 }}
                                    >
                                        <MoreOutlined />
                                    </FavoriteButton>
                                </Dropdown>
                            )}
                        </HeaderActions>
                    </HeaderRight>
                </CardHeader>

                <Body>
                    <TitleRow>
                        <TitleText>{skill.name}</TitleText>
                        <PriceTag $isFree={isFree}>
                            {isFree ? t('pages.skills.free', 'Free') : t('pages.skills.paid', 'Paid')}
                        </PriceTag>
                    </TitleRow>

                    {(skill as any)?.id && (
                        <div
                            title={String((skill as any).id)}
                            style={{
                                fontSize: 10.5,
                                fontFamily: 'monospace',
                                color: 'rgba(255,255,255,0.35)',
                                overflow: 'hidden',
                                textOverflow: 'ellipsis',
                                whiteSpace: 'nowrap',
                                marginTop: -2,
                            }}
                        >
                            {String((skill as any).id)}
                        </div>
                    )}

                    {skill.description && <Description>{skill.description}</Description>}

                    {tags.length > 0 && (
                        <TagsRow>
                            {tags.map((tag, idx) => (
                                <TagPill key={`${tag}-${idx}`} $color="#722ed1">#{tag}</TagPill>
                            ))}
                        </TagsRow>
                    )}

                    {/* Level + rating + downloads + subscribers on a single row */}
                    <StatsRow>
                        <TagPill $color="#1890ff">
                            {t(`pages.skills.levels.${level}`, level)}
                        </TagPill>
                        <Tooltip title={t('pages.skills.rating', 'Rating')}>
                            <Stat>
                                <StarFilled style={{ color: '#faad14' }} />
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
