import React, { useState, useEffect } from 'react';
import { Input } from 'antd';
import { SearchOutlined, ShopOutlined, TeamOutlined, DownloadOutlined, RocketOutlined } from '@ant-design/icons';
import { useTranslation } from 'react-i18next';
import styled from '@emotion/styled';

interface HeroStats {
    totalSkills: number;
    totalDownloads: number;
    totalAuthors: number;
    newThisWeek: number;
}

interface HeroProps {
    stats: HeroStats;
    onSearch: (q: string) => void;
    initialSearch?: string;
}

const HeroRoot = styled.div`
    position: relative;
    margin: 18px 24px 8px;
    padding: 28px 28px 22px;
    border-radius: 18px;
    background:
        radial-gradient(900px 240px at 20% 0%, rgba(24, 144, 255, 0.18), transparent 60%),
        radial-gradient(600px 220px at 90% 50%, rgba(82, 196, 26, 0.14), transparent 60%),
        linear-gradient(135deg, rgba(255, 255, 255, 0.04) 0%, rgba(255, 255, 255, 0.02) 100%);
    border: 1px solid rgba(255, 255, 255, 0.08);
    overflow: hidden;
`;

const HeroTitle = styled.div`
    display: flex;
    align-items: center;
    gap: 12px;
    font-size: 26px;
    font-weight: 800;
    color: #fff;
    letter-spacing: -0.4px;
    margin-bottom: 6px;

    .anticon {
        font-size: 28px;
        background: linear-gradient(135deg, #1890ff, #52c41a);
        -webkit-background-clip: text;
        background-clip: text;
        color: transparent;
    }
`;

const HeroSub = styled.div`
    font-size: 14px;
    color: rgba(255, 255, 255, 0.65);
    max-width: 720px;
    line-height: 1.5;
`;

const HeroSearchWrap = styled.div`
    margin-top: 20px;
    max-width: 720px;
`;

const HeroSearch = styled(Input)`
    height: 48px;
    border-radius: 14px;
    background: rgba(255, 255, 255, 0.08);
    border: 1px solid rgba(255, 255, 255, 0.1);
    font-size: 15px;
    padding-left: 16px;

    .ant-input {
        background: transparent;
        color: #fff;
        font-size: 15px;
        &::placeholder {
            color: rgba(255, 255, 255, 0.4);
        }
    }
    &:hover, &:focus {
        background: rgba(255, 255, 255, 0.12);
        border-color: rgba(24, 144, 255, 0.45);
        box-shadow: 0 0 0 4px rgba(24, 144, 255, 0.12);
    }
`;

const StatsRow = styled.div`
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: 14px;
    margin-top: 22px;

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

const SkillMarketplaceHero: React.FC<HeroProps> = ({ stats, onSearch, initialSearch = '' }) => {
    const { t } = useTranslation();
    const [value, setValue] = useState(initialSearch);

    useEffect(() => {
        const handle = setTimeout(() => {
            onSearch(value.trim());
        }, 200);
        return () => clearTimeout(handle);
    }, [value, onSearch]);

    return (
        <HeroRoot>
            <HeroTitle>
                <ShopOutlined />
                {t('pages.skills.heroTitle', 'Skill Store')}
            </HeroTitle>
            <HeroSub>
                {t(
                    'pages.skills.heroSubtitle',
                    'Browse ready-to-use skills built by the community. Install with one click, run anywhere.'
                )}
            </HeroSub>

            <HeroSearchWrap>
                <HeroSearch
                    prefix={<SearchOutlined style={{ color: 'rgba(255,255,255,0.5)', fontSize: 18, marginRight: 10 }} />}
                    placeholder={t('pages.skills.heroSearchPlaceholder', 'Search skills, tags, or authors...')}
                    value={value}
                    onChange={(e) => setValue(e.target.value)}
                    allowClear
                />
            </HeroSearchWrap>

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
