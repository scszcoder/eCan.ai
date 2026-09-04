import React, { useMemo, useState, useEffect } from 'react';
import { Button, Rate, Tag, Descriptions, Typography, Space, message, Modal, Select, App as AntApp } from 'antd';
import {
  UserOutlined,
  HeartOutlined,
  CalendarOutlined,
  TeamOutlined,
  DownloadOutlined,
  LinkOutlined,
  RocketOutlined,
} from '@ant-design/icons';
import { useTranslation } from 'react-i18next';
import styled from '@emotion/styled';
import type { AvatarItem } from '../types';
import { findRelatedAvatars, useAvatarMarketStore } from '../avatarMarketStore';
import { useAgentStore } from '@/stores/agentStore';
import { useUserStore } from '@/stores/userStore';

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
  border-radius: 14px;
  overflow: hidden;
  background: linear-gradient(135deg, rgba(59,130,246,0.15) 0%, rgba(147,51,234,0.10) 100%);
  margin-bottom: 20px;
  border: 1px solid rgba(255,255,255,0.08);
  box-shadow: 0 8px 24px rgba(0,0,0,0.25), inset 0 1px 0 rgba(255,255,255,0.05);
`;

const HeroMedia = styled.div`
  width: 100%;
  aspect-ratio: 16 / 9;
  max-height: 340px;
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
  padding: 22px 26px;
  background: linear-gradient(transparent, rgba(0,0,0,0.85));
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 16px;
`;

const TabsBar = styled.div`
  display: flex;
  gap: 8px;
  margin-bottom: 20px;
  flex-wrap: wrap;
  padding: 12px 16px;
  border-radius: 10px;
  background: rgba(255, 255, 255, 0.02);
  border: 1px solid rgba(255, 255, 255, 0.05);
`;

const Section = styled.div`
  margin-bottom: 20px;
`;

const SectionTitle = styled.div`
  font-size: 13px;
  font-weight: 600;
  color: var(--text-primary, #e2e8f0);
  margin-bottom: 8px;
  text-transform: uppercase;
  letter-spacing: 0.4px;
  opacity: 0.85;
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

const RelatedRow = styled.div`
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(110px, 1fr));
  gap: 10px;
`;

const RelatedCard = styled.div`
  cursor: pointer;
  border-radius: 10px;
  overflow: hidden;
  background: var(--bg-secondary, #1e293b);
  border: 1px solid rgba(255,255,255,0.06);
  transition: all .2s ease;

  &:hover {
    transform: translateY(-2px);
    border-color: rgba(96,165,250,0.4);
  }
`;

const RelatedThumb = styled.div`
  width: 100%;
  aspect-ratio: 1;
  background: linear-gradient(135deg, #0f172a 0%, #1e293b 100%);
  display: flex;
  align-items: center;
  justify-content: center;
  overflow: hidden;

  img {
    width: 100%;
    height: 100%;
    object-fit: cover;
  }
`;

const RelatedName = styled.div`
  padding: 6px 8px;
  font-size: 11px;
  color: var(--text-primary, #e2e8f0);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
`;

// ── Apply-to-Agent button ──
const ApplyToAgentButton: React.FC<{ avatar: AvatarItem }> = ({ avatar }) => {
  const { t } = useTranslation();
  const { message: antdMessage } = AntApp.useApp();
  const username = useUserStore((s) => s.username);
  const agents = useAgentStore((s) => s.agents);
  const fetchAgents = useAgentStore((s) => s.fetchAgents);
  const saveAgent = useAgentStore((s) => s.saveAgent);
  const [open, setOpen] = useState(false);
  const [selectedAgentId, setSelectedAgentId] = useState<string | undefined>(undefined);
  const [submitting, setSubmitting] = useState(false);

  // Make sure we have an agent list when the modal opens.
  useEffect(() => {
    if (!open || agents.length > 0 || !username) return;
    fetchAgents(username).catch(() => undefined);
  }, [open, agents.length, username, fetchAgents]);

  const agentOptions = useMemo(() => {
    return agents
      .map((a) => {
        const card = (a as any).card;
        const id = card?.id || '';
        const name = card?.name || id || t('avatar.untitled');
        return { id: String(id), name: String(name), currentAvatarId: (a as any).avatar_resource_id };
      })
      .filter((o) => o.id);
  }, [agents, t]);

  const handleApply = async () => {
    if (!selectedAgentId || !username) return;
    const target = agents.find((a) => ((a as any).card?.id || '') === selectedAgentId);
    if (!target) return;

    const next: any = { ...target, avatar_resource_id: avatar.id };
    // Backend mutation expects `card` shape — preserve it.
    if (!(next as any).card && (target as any).card) {
      (next as any).card = (target as any).card;
    }

    setSubmitting(true);
    try {
      await saveAgent(username, next);
      antdMessage.success(t('avatar.apply_success', { name: avatar.name || avatar.id }));
      setOpen(false);
      setSelectedAgentId(undefined);
    } catch (e: any) {
      antdMessage.error(t('avatar.apply_failed'));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <>
      <Button
        type="primary"
        size="large"
        icon={<RocketOutlined />}
        onClick={() => setOpen(true)}
        disabled={!username}
      >
        {t('avatar.apply_to_agent')}
      </Button>
      <Modal
        open={open}
        onCancel={() => { if (!submitting) setOpen(false); }}
        title={t('avatar.apply_to_agent')}
        okText={t('avatar.apply_to_agent')}
        okButtonProps={{ disabled: !selectedAgentId, loading: submitting }}
        onOk={handleApply}
        destroyOnHidden
      >
        <Select
          showSearch
          placeholder={t('avatar.apply_placeholder', 'Select an agent')}
          value={selectedAgentId}
          onChange={(v) => setSelectedAgentId(v)}
          style={{ width: '100%' }}
          optionFilterProp="label"
          notFoundContent={
            agents.length === 0
              ? t('common.loading', 'Loading…')
              : t('avatar.no_description')
          }
          options={agentOptions.map((o) => ({
            value: o.id,
            label: o.currentAvatarId === avatar.id
              ? `${o.name}  ✓`
              : o.name,
          }))}
        />
      </Modal>
    </>
  );
};

// ── Props ──
interface AvatarDetailsProps {
  avatar: AvatarItem;
  onSelectRelated?: (avatar: AvatarItem) => void;
}

const AvatarDetails: React.FC<AvatarDetailsProps> = ({ avatar, onSelectRelated }) => {
  const { t } = useTranslation();
  const allAvatars = useAvatarMarketStore((s) => s.avatars);
  const imageUrl = avatar.presigned_image_url || avatar.cloud_image_url || '';
  const videoUrl = avatar.presigned_video_url || avatar.cloud_video_url || '';
  const hasVideo = !!videoUrl;

  const handleCopyLink = async () => {
    if (!imageUrl && !videoUrl) {
      message.warning(t('avatar.no_description'));
      return;
    }
    try {
      await navigator.clipboard.writeText(imageUrl || videoUrl);
      message.success(t('avatar.share'));
    } catch {
      // Fallback: do nothing if clipboard is unavailable (e.g. insecure context)
    }
  };

  const handleDownload = () => {
    const url = videoUrl || imageUrl;
    if (!url) {
      message.warning(t('avatar.no_description'));
      return;
    }
    const a = document.createElement('a');
    a.href = url;
    a.download = avatar.name || avatar.id || 'avatar';
    a.target = '_blank';
    a.rel = 'noopener';
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
  };

  const related = findRelatedAvatars(avatar, allAvatars, 6);

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
          <div style={{ minWidth: 0 }}>
            <Title level={4} style={{ color: '#fff', margin: 0, marginBottom: 2 }}>
              {avatar.name || t('avatar.untitled')}
            </Title>
            <Text style={{ color: 'rgba(255,255,255,0.75)', fontSize: 12 }}>
              {t('avatar.by')} {avatar.artist || avatar.owner || t('avatar.unknown')}
              {avatar.style ? ` · ${avatar.style}` : ''}
            </Text>
          </div>
          <div style={{ textAlign: 'right', flexShrink: 0 }}>
            <Rate disabled allowHalf value={avatar.rating ?? 0} style={{ fontSize: 14 }} />
            <div style={{ color: 'rgba(255,255,255,0.7)', fontSize: 11, marginTop: 2 }}>
              <TeamOutlined /> {avatar.subscribers ?? 0} {t('avatar.subscribers')}
            </div>
          </div>
        </HeroOverlay>
      </HeroBanner>

      {/* Action bar — sticky inside modal body */}
      <TabsBar>
        <ApplyToAgentButton avatar={avatar} />
        <Button icon={<LinkOutlined />} size="middle" onClick={handleCopyLink}>
          {t('avatar.share')}
        </Button>
        <Button icon={<DownloadOutlined />} size="middle" onClick={handleDownload}>
          {t('avatar.download')}
        </Button>
        <Button icon={<HeartOutlined />} size="middle">
          {t('avatar.favorite')}
        </Button>
      </TabsBar>

      {/* Overview + Tags + Details — one section, no StatGrid duplication */}
      <Section>
        <SectionTitle>{t('avatar.description')}</SectionTitle>
        {avatar.description ? (
          <Paragraph style={{ color: 'var(--text-secondary, rgba(148,163,184,0.85))', fontSize: 13 }}>
            {avatar.description}
          </Paragraph>
        ) : (
          <Text style={{ color: 'var(--text-secondary, rgba(148,163,184,0.5))', fontSize: 13, fontStyle: 'italic' }}>
            {t('avatar.no_description')}
          </Text>
        )}
      </Section>

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

      <Section>
        <SectionTitle>{t('avatar.details')}</SectionTitle>
        <DescBox>
          <Descriptions column={1} size="small" bordered={false} colon={false}>
            <Descriptions.Item label={t('avatar.creator_artist')}>
              {avatar.artist || avatar.owner || '—'}
            </Descriptions.Item>
            <Descriptions.Item label={t('avatar.style')}>
              {avatar.style || '—'}
            </Descriptions.Item>
            <Descriptions.Item label={t('avatar.visibility')}>
              {avatar.is_public
                ? <Tag color="green">{t('avatar.public')}</Tag>
                : <Tag>{t('avatar.private')}</Tag>}
            </Descriptions.Item>
            <Descriptions.Item label={t('avatar.price')}>
              {avatar.price ? `$${avatar.price.toFixed(2)}` : t('avatar.free')}
            </Descriptions.Item>
            <Descriptions.Item label={t('avatar.type')}>
              {hasVideo ? t('avatar.video_type') : t('avatar.image_type')}
            </Descriptions.Item>
            {avatar.created_at && (
              <Descriptions.Item label={t('avatar.created')}>
                <Space size={4}>
                  <CalendarOutlined />
                  {new Date(avatar.created_at).toLocaleDateString()}
                </Space>
              </Descriptions.Item>
            )}
          </Descriptions>
        </DescBox>
      </Section>

      {related.length > 0 && (
        <Section>
          <SectionTitle>{t('avatar.related')}</SectionTitle>
          <RelatedRow>
            {related.map((r) => {
              const rImg = r.presigned_image_url || r.cloud_image_url || '';
              return (
                <RelatedCard key={r.id} onClick={() => onSelectRelated?.(r)}>
                  <RelatedThumb>
                    {rImg ? (
                      <img src={rImg} alt={r.name} loading="lazy" />
                    ) : (
                      <UserOutlined style={{ fontSize: 24, color: 'rgba(148,163,184,0.4)' }} />
                    )}
                  </RelatedThumb>
                  <RelatedName>{r.name || t('avatar.untitled')}</RelatedName>
                </RelatedCard>
              );
            })}
          </RelatedRow>
        </Section>
      )}
    </Container>
  );
};

export default AvatarDetails;