import React, { useEffect, useState } from 'react';
import { Avatar, Spin, Typography, Empty } from 'antd';
import { useTranslation } from 'react-i18next';
import { UserOutlined, ShopOutlined, DownloadOutlined } from '@ant-design/icons';
import styled from '@emotion/styled';
import { get_ipc_api } from '@/services/ipc_api';
import type { Skill } from '@/types/domain/skill';
import { getInitials, colorFromString } from './skillPalette';

const { Text } = Typography;

const Card = styled.div`
    background: var(--bg-secondary);
    border: 1px solid rgba(255, 255, 255, 0.06);
    border-radius: 14px;
    padding: 16px;
    margin-bottom: 16px;
`;

const Header = styled.div`
    display: flex;
    align-items: center;
    gap: 12px;
    margin-bottom: 12px;
`;

const AuthorName = styled.div`
    font-size: 15px;
    font-weight: 600;
    color: var(--text-primary);
`;

const AuthorMeta = styled.div`
    font-size: 12px;
    color: var(--text-secondary);
`;

const SkillsGrid = styled.div`
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(180px, 1fr));
    gap: 10px;
`;

const MiniSkillCard = styled.div`
    background: rgba(255, 255, 255, 0.04);
    border: 1px solid rgba(255, 255, 255, 0.08);
    border-radius: 10px;
    padding: 10px 12px;
    cursor: pointer;
    transition: all 0.15s ease;

    &:hover {
        background: rgba(255, 255, 255, 0.08);
        border-color: rgba(24, 144, 255, 0.35);
    }

    .name {
        font-size: 13px;
        font-weight: 600;
        color: var(--text-primary);
        margin-bottom: 4px;
        white-space: nowrap;
        overflow: hidden;
        text-overflow: ellipsis;
    }
    .meta {
        font-size: 11px;
        color: var(--text-secondary);
        display: flex;
        align-items: center;
        gap: 8px;
    }
`;

interface Props {
    skill: Skill;
    onOpenSkill: (skill: Skill) => void;
}

const SkillAuthorPanel: React.FC<Props> = ({ skill, onOpenSkill }) => {
    const { t } = useTranslation();
    const owner = String((skill as any)?.owner || '').trim();
    const excludeId = String((skill as any)?.id || '');
    const [related, setRelated] = useState<Skill[]>([]);
    const [loading, setLoading] = useState(false);

    useEffect(() => {
        if (!owner) {
            setRelated([]);
            return;
        }
        let cancelled = false;
        setLoading(true);
        const api = get_ipc_api();
        if (!api) { setRelated([]); setLoading(false); return; }
        api.listSkillsByOwner(owner, excludeId, 8)
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
    }, [owner, excludeId]);

    if (!owner) return null;

    return (
        <Card>
            <Header>
                <Avatar size={48} style={{ background: colorFromString(owner), fontSize: 18, fontWeight: 700 }}>
                    {getInitials(owner)}
                </Avatar>
                <div style={{ flex: 1, minWidth: 0 }}>
                    <AuthorName>
                        <UserOutlined style={{ marginRight: 6, color: 'var(--primary-color)' }} />
                        {owner}
                    </AuthorName>
                    <AuthorMeta>
                        {t('pages.skills.authorPanel.subtitle', 'Author of this skill')}
                    </AuthorMeta>
                </div>
            </Header>
            <div style={{ marginBottom: 8, display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                <Text style={{ fontSize: 11, color: 'rgba(255,255,255,0.5)', textTransform: 'uppercase', letterSpacing: 0.5 }}>
                    {t('pages.skills.authorPanel.moreFromAuthor', 'More from this author')}
                </Text>
                {loading && <Spin size="small" />}
            </div>
            {!loading && related.length === 0 ? (
                <Empty
                    image={Empty.PRESENTED_IMAGE_SIMPLE}
                    description={t('pages.skills.authorPanel.noMore', 'No other public skills by this author')}
                />
            ) : (
                <SkillsGrid>
                    {related.map((s) => (
                        <MiniSkillCard key={String((s as any).id)} onClick={() => onOpenSkill(s)}>
                            <div className="name">{s.name}</div>
                            <div className="meta">
                                <span>
                                    <ShopOutlined /> v{(s as any).version || '0.0.0'}
                                </span>
                                <span>
                                    <DownloadOutlined /> {Number((s as any).downloadCount || 0)}
                                </span>
                            </div>
                        </MiniSkillCard>
                    ))}
                </SkillsGrid>
            )}
        </Card>
    );
};

export default SkillAuthorPanel;
