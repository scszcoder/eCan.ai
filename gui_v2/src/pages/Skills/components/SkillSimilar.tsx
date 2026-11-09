import React, { useEffect, useState } from 'react';
import { Spin, Empty } from 'antd';
import { useTranslation } from 'react-i18next';
import { StarFilled, DownloadOutlined, ThunderboltOutlined } from '@ant-design/icons';
import styled from '@emotion/styled';
import { get_ipc_api } from '@/services/ipc_api';
import type { Skill } from '@/types/domain/skill';
import {
    getSkillPalette,
    formatNumber,
} from './skillPalette';

const Card = styled.div`
    background: var(--bg-secondary);
    border: 1px solid var(--border-color);
    border-radius: 14px;
    padding: 16px;
    margin-bottom: 16px;
`;

const Header = styled.div`
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-bottom: 12px;
`;

const Title = styled.div`
    font-size: 11px;
    font-weight: 600;
    color: var(--text-tertiary);
    text-transform: uppercase;
    letter-spacing: 0.5px;

    .anticon {
        margin-right: 4px;
    }
`;

const Grid = styled.div`
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(180px, 1fr));
    gap: 10px;
`;

const MiniCard = styled.div`
    background: var(--surface-subtle);
    border: 1px solid var(--border-color);
    border-radius: 10px;
    padding: 12px;
    cursor: pointer;
    transition: all 0.15s ease;
    display: flex;
    align-items: center;
    gap: 10px;

    &:hover {
        background: var(--surface-subtle-hover);
        border-color: rgba(var(--primary-color-rgb), 0.35);
    }
`;

const MiniIcon = styled.div<{ $bg: [string, string] }>`
    width: 36px;
    height: 36px;
    border-radius: 10px;
    background: linear-gradient(135deg, ${(p) => p.$bg[0]}, ${(p) => p.$bg[1]});
    display: flex;
    align-items: center;
    justify-content: center;
    color: var(--tooltip-text);
    font-size: 16px;
    flex-shrink: 0;
`;

const MiniInfo = styled.div`
    flex: 1;
    min-width: 0;

    .name {
        font-size: 13px;
        font-weight: 600;
        color: var(--text-primary);
        white-space: nowrap;
        overflow: hidden;
        text-overflow: ellipsis;
        margin-bottom: 2px;
    }
    .meta {
        font-size: 11px;
        color: var(--text-secondary);
        display: flex;
        align-items: center;
        gap: 6px;
    }
`;

interface Props {
    skill: Skill;
    onOpenSkill: (skill: Skill) => void;
}

const SkillSimilar: React.FC<Props> = ({ skill, onOpenSkill }) => {
    const { t } = useTranslation();
    const [related, setRelated] = useState<Skill[]>([]);
    const [loading, setLoading] = useState(false);

    useEffect(() => {
        if (!skill?.id) return;
        let cancelled = false;
        setLoading(true);
        const api = get_ipc_api();
        if (!api) { setRelated([]); setLoading(false); return; }
        api.listSimilarSkills(String(skill.id), 6)
            .then((resp: any) => {
                if (cancelled) return;
                if (resp?.success) {
                    const data = (resp.data as any)?.data ?? resp.data ?? [];
                    setRelated(Array.isArray(data) ? data : []);
                } else {
                    setRelated([]);
                }
            })
            .catch(() => {
                if (!cancelled) setRelated([]);
            })
            .finally(() => {
                if (!cancelled) setLoading(false);
            });
        return () => {
            cancelled = true;
        };
    }, [skill?.id]);

    return (
        <Card>
            <Header>
                <Title>
                    <ThunderboltOutlined />
                    {t('pages.skills.similar.title', 'You might also like')}
                </Title>
                {loading && <Spin size="small" />}
            </Header>

            {!loading && related.length === 0 ? (
                <Empty
                    image={Empty.PRESENTED_IMAGE_SIMPLE}
                    description={t('pages.skills.similar.empty', 'No similar skills found yet.')}
                />
            ) : (
                <Grid>
                    {related.map((s) => {
                        const palette = getSkillPalette(s);
                        return (
                            <MiniCard key={String((s as any).id)} onClick={() => onOpenSkill(s)}>
                                <MiniIcon $bg={palette.bg}>{palette.icon}</MiniIcon>
                                <MiniInfo>
                                    <div className="name">{s.name}</div>
                                    <div className="meta">
                                        <span>
                                            <StarFilled style={{ color: 'var(--warning-text)', marginRight: 2 }} />
                                            {Number((s as any).rating ?? 5).toFixed(1)}
                                        </span>
                                        <span>
                                            <DownloadOutlined style={{ marginRight: 2 }} />
                                            {formatNumber(Number((s as any).downloadCount ?? 0))}
                                        </span>
                                    </div>
                                </MiniInfo>
                            </MiniCard>
                        );
                    })}
                </Grid>
            )}
        </Card>
    );
};

export default SkillSimilar;
