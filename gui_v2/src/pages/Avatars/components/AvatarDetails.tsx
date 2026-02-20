import React from 'react';
import { Button, Rate, Tag, Descriptions, Typography, Space, message } from 'antd';
import {
  UserOutlined,
  HeartOutlined,
  ShareAltOutlined,
  CalendarOutlined,
} from '@ant-design/icons';
import { useTranslation } from 'react-i18next';
import styled from '@emotion/styled';
import type { AvatarItem } from '../types';

const { Title, Text, Paragraph } = Typography;

// ── Styled Components ──
const Container = styled.div`
  height: 100%;
  overflow-y: auto;
  padding: 0 4px;
`;

const HeroBanner = styled.div`
  position: relative;
  width: 100%;
  border-radius: 12px;
  overflow: hidden;
  background: linear-gradient(135deg, #0f172a 0%, #1e293b 100%);
  margin-bottom: 20px;
`;

const HeroMedia = styled.div`
  width: 100%;
  aspect-ratio: 16 / 9;
  max-height: 320px;
  display: flex;
  align-items: center;
  justify-content: center;
  overflow: hidden;

  img, video {
    width: 100%;
    height: 100%;
    object-fit: cover;
  }
`;

const HeroOverlay = styled.div`
  position: absolute;
  bottom: 0;
  left: 0;
  right: 0;
  padding: 20px 24px;
  background: linear-gradient(transparent, rgba(0,0,0,0.75));
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
`;

const ActionBar = styled.div`
  display: flex;
  gap: 10px;
  margin-bottom: 20px;
`;

const Section = styled.div`
  margin-bottom: 24px;
`;

const SectionTitle = styled.div`
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary, #e2e8f0);
  margin-bottom: 10px;
`;

const StatGrid = styled.div`
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(130px, 1fr));
  gap: 12px;
`;

const StatCard = styled.div`
  background: var(--bg-secondary, #1e293b);
  border-radius: 10px;
  padding: 14px;
  text-align: center;
  border: 1px solid rgba(255,255,255,0.05);
`;

const StatValue = styled.div`
  font-size: 20px;
  font-weight: 700;
  color: var(--text-primary, #e2e8f0);
`;

const StatLabel = styled.div`
  font-size: 11px;
  color: var(--text-secondary, rgba(148,163,184,0.7));
  margin-top: 2px;
`;

const TagsRow = styled.div`
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: 6px;
`;

const DescBox = styled.div`
  .ant-descriptions-item-label {
    color: var(--text-secondary, rgba(148,163,184,0.7)) !important;
    font-size: 12px;
  }
  .ant-descriptions-item-content {
    color: var(--text-primary, #e2e8f0) !important;
    font-size: 13px;
  }
`;

// ── Props ──
interface AvatarDetailsProps {
  avatar: AvatarItem;
}

const AvatarDetails: React.FC<AvatarDetailsProps> = ({ avatar }) => {
  const { t } = useTranslation();
  const imageUrl = avatar.presigned_image_url || avatar.cloud_image_url || '';
  const videoUrl = avatar.presigned_video_url || avatar.cloud_video_url || '';
  const hasVideo = !!videoUrl;

  const handleSubscribe = () => {
    message.success(t('avatar.subscribed_success', { name: avatar.name || avatar.id }));
  };

  return (
    <Container>
      {/* Hero banner with image/video */}
      <HeroBanner>
        <HeroMedia>
          {hasVideo ? (
            <video src={videoUrl} poster={imageUrl} controls muted loop playsInline />
          ) : imageUrl ? (
            <img src={imageUrl} alt={avatar.name} />
          ) : (
            <UserOutlined style={{ fontSize: 72, color: 'rgba(148,163,184,0.3)' }} />
          )}
        </HeroMedia>
        <HeroOverlay>
          <div>
            <Title level={4} style={{ color: '#fff', margin: 0 }}>
              {avatar.name || t('avatar.untitled')}
            </Title>
            <Text style={{ color: 'rgba(255,255,255,0.7)', fontSize: 12 }}>
              {t('avatar.by')} {avatar.artist || avatar.owner || t('avatar.unknown')}
            </Text>
          </div>
          <div style={{ textAlign: 'right' }}>
            <Rate disabled allowHalf value={avatar.rating ?? 0} style={{ fontSize: 14 }} />
            <div style={{ color: 'rgba(255,255,255,0.6)', fontSize: 11, marginTop: 2 }}>
              {avatar.subscribers ?? 0} {t('avatar.subscribers')}
            </div>
          </div>
        </HeroOverlay>
      </HeroBanner>

      {/* Action buttons */}
      <ActionBar>
        <Button type="primary" size="large" onClick={handleSubscribe} style={{ minWidth: 140 }}>
          {avatar.price ? t('avatar.subscribe_price', { price: avatar.price.toFixed(2) }) : t('avatar.subscribe_free')}
        </Button>
        <Button icon={<HeartOutlined />} size="large">{t('avatar.favorite')}</Button>
        <Button icon={<ShareAltOutlined />} size="large">{t('avatar.share')}</Button>
      </ActionBar>

      {/* Stats */}
      <Section>
        <SectionTitle>{t('avatar.statistics')}</SectionTitle>
        <StatGrid>
          <StatCard>
            <StatValue>{avatar.subscribers ?? avatar.usage_count ?? 0}</StatValue>
            <StatLabel>{t('avatar.subscribers')}</StatLabel>
          </StatCard>
          <StatCard>
            <StatValue>{avatar.rating?.toFixed(1) ?? '—'}</StatValue>
            <StatLabel>{t('avatar.rating')}</StatLabel>
          </StatCard>
          <StatCard>
            <StatValue>{avatar.price ? `$${avatar.price.toFixed(2)}` : t('avatar.free')}</StatValue>
            <StatLabel>{t('avatar.price')}</StatLabel>
          </StatCard>
          <StatCard>
            <StatValue>{avatar.resource_type || '—'}</StatValue>
            <StatLabel>{t('avatar.type')}</StatLabel>
          </StatCard>
        </StatGrid>
      </Section>

      {/* Description */}
      {avatar.description && (
        <Section>
          <SectionTitle>{t('avatar.description')}</SectionTitle>
          <Paragraph style={{ color: 'var(--text-secondary, rgba(148,163,184,0.8))', fontSize: 13 }}>
            {avatar.description}
          </Paragraph>
        </Section>
      )}

      {/* Tags */}
      {avatar.tags && avatar.tags.length > 0 && (
        <Section>
          <SectionTitle>{t('avatar.tags')}</SectionTitle>
          <TagsRow>
            {avatar.tags.map((tag) => (
              <Tag key={tag} color="blue">{tag}</Tag>
            ))}
          </TagsRow>
        </Section>
      )}

      {/* Details table */}
      <Section>
        <SectionTitle>{t('avatar.details')}</SectionTitle>
        <DescBox>
          <Descriptions column={1} size="small" bordered={false} colon={false}>
            <Descriptions.Item label={t('avatar.id')}>{avatar.id}</Descriptions.Item>
            <Descriptions.Item label={t('avatar.creator_artist')}>{avatar.artist || avatar.owner || '—'}</Descriptions.Item>
            <Descriptions.Item label={t('avatar.style')}>{avatar.style || '—'}</Descriptions.Item>
            <Descriptions.Item label={t('avatar.type')}>{avatar.resource_type || '—'}</Descriptions.Item>
            <Descriptions.Item label={t('avatar.visibility')}>
              {avatar.is_public ? <Tag color="green">{t('avatar.public')}</Tag> : <Tag>{t('avatar.private')}</Tag>}
            </Descriptions.Item>
            {avatar.created_at && (
              <Descriptions.Item label={t('avatar.created')}>
                <Space size={4}>
                  <CalendarOutlined />
                  {new Date(avatar.created_at).toLocaleDateString()}
                </Space>
              </Descriptions.Item>
            )}
            {avatar.image_hash && (
              <Descriptions.Item label={t('avatar.image_hash')}>
                <Text copyable style={{ fontSize: 12 }}>{avatar.image_hash}</Text>
              </Descriptions.Item>
            )}
          </Descriptions>
        </DescBox>
      </Section>
    </Container>
  );
};

export default AvatarDetails;
