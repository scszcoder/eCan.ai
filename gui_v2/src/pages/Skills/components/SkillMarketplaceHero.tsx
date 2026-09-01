import React from 'react';
import { useTranslation } from 'react-i18next';
import styled from '@emotion/styled';
import { ShopOutlined, TeamOutlined, DownloadOutlined, RocketOutlined } from '@ant-design/icons';

interface HeroStats {
    totalSkills: number;
    totalDownloads: number;
    totalAuthors: number;
    newThisWeek: number;
}

interface HeroProps {
    stats: HeroStats;
}

const HeroRoot = styled.div`
    margin: 18px 24px 8px;
    padding: 22px 24px;
    border-radius: 18px;
    background:
        radial-gradient(900px 240px at 20% 0%, rgba(24, 144, 255, 0.18), transparent 60%),
        radial-gradient(600px 220px at 90% 50%, rgba(82, 196, 26, 0.14), transparent 60%),
        linear-gradient(135deg, rgba(255, 255, 255, 0.04) 0%, rgba(255, 255, 255, 0.02) 100%);
    border: 1px solid rgba(255, 255, 255, 0.08);
    overflow: hidden;
`;

const StatsRow = styled.div`
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: 14px;

    @media (max-width: 720px) {
        grid-template-columns: repeat(2, 1fr);
    }
`;

const StatCard = styled.div`
    background: rgba(255, 255, 255, 0.04);
    border: 1px solid rgba(255, 255, 255, 0.08);
    border-radius: 14px;
    padding: 14px 16px;
    display: flex;
    align-items: center;
    gap: 12px;

    .stat-icon {
        width: 38px;
        height: 38px;
        border-radius: 12px;
        display: flex;
        align-items: center;
        justify-content: center;
        font-size: 18px;
    }
    .stat-value {
        font-size: 20px;
        font-weight: 700;
        color: #fff;
        line-height: 1;
    }
    .stat-label {
        font-size: 11px;
        color: rgba(255, 255, 255, 0.55);
        margin-top: 4px;
        text-transform: uppercase;
        letter-spacing: 0.5px;
    }
`;

const formatNumber = (n: number): string => {
    if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
    if (n >= 1_000) return `${(n / 1_000).toFixed(1)}K`;
    return String(n || 0);
};

const SkillMarketplaceHero: React.FC<HeroProps> = ({ stats }) => {
    const { t } = useTranslation();

    return (
        <HeroRoot>
            <StatsRow>
                <StatCard>
                    <div className="stat-icon" style={{ background: 'rgba(24, 144, 255, 0.18)', color: '#1890ff' }}>
                        <ShopOutlined />
                    </div>
                    <div>
                        <div className="stat-value">{formatNumber(stats.totalSkills)}</div>
                        <div className="stat-label">{t('pages.skills.heroStats.skills', 'Skills')}</div>
                    </div>
                </StatCard>
                <StatCard>
                    <div className="stat-icon" style={{ background: 'rgba(82, 196, 26, 0.18)', color: '#52c41a' }}>
                        <DownloadOutlined />
                    </div>
                    <div>
                        <div className="stat-value">{formatNumber(stats.totalDownloads)}</div>
                        <div className="stat-label">{t('pages.skills.downloads', 'Downloads')}</div>
                    </div>
                </StatCard>
                <StatCard>
                    <div className="stat-icon" style={{ background: 'rgba(250, 173, 20, 0.18)', color: '#faad14' }}>
                        <TeamOutlined />
                    </div>
                    <div>
                        <div className="stat-value">{formatNumber(stats.totalAuthors)}</div>
                        <div className="stat-label">{t('pages.skills.heroStats.authors', 'Authors')}</div>
                    </div>
                </StatCard>
                <StatCard>
                    <div className="stat-icon" style={{ background: 'rgba(245, 34, 45, 0.18)', color: '#ff4d4f' }}>
                        <RocketOutlined />
                    </div>
                    <div>
                        <div className="stat-value">{formatNumber(stats.newThisWeek)}</div>
                        <div className="stat-label">{t('pages.skills.heroStats.newThisWeek', 'New This Week')}</div>
                    </div>
                </StatCard>
            </StatsRow>
        </HeroRoot>
    );
};

export default SkillMarketplaceHero;