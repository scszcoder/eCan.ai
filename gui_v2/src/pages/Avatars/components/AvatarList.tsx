import React, { useMemo, useState, useRef, useEffect } from 'react';
import { Input, Select, Empty, Spin, Rate, Tag, Tooltip } from 'antd';
import {
  SearchOutlined,
  UserOutlined,
  PlayCircleOutlined,
  PictureOutlined,
  VideoCameraOutlined,
  TeamOutlined,
} from '@ant-design/icons';
import { useTranslation } from 'react-i18next';
import styled from '@emotion/styled';
import type { AvatarItem, AvatarSearchField, AvatarViewMode } from '../types';

const { Option } = Select;

// ── Styled Components ──
const ListContainer = styled.div`
  height: 100%;
  display: flex;
  flex-direction: column;
`;

const ToolBar = styled.div`
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 8px 12px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.06);
`;

const SearchRow = styled.div`
  display: flex;
  gap: 8px;
`;

const FilterRow = styled.div`
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
`;

const ScrollArea = styled.div`
  flex: 1;
  padding: 8px 12px;
  overflow-y: auto;
  overflow-x: hidden;
  min-height: 0;
`;

const GridContainer = styled.div`
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(180px, 1fr));
  gap: 12px;
  padding: 4px 0;
`;

const Card = styled.div<{ selected?: boolean }>`
  cursor: pointer;
  border-radius: 12px;
  overflow: hidden;
  background: ${(p) => p.selected
    ? 'linear-gradient(135deg, rgba(59,130,246,0.18) 0%, rgba(147,51,234,0.10) 100%)'
    : 'var(--bg-secondary, #1e293b)'};
  border: 1px solid ${(p) => p.selected ? 'rgba(59,130,246,0.5)' : 'rgba(255,255,255,0.06)'};
  transition: all .25s ease;
  position: relative;

  &:hover {
    transform: translateY(-2px);
    box-shadow: 0 8px 24px rgba(0,0,0,0.35);
    border-color: ${(p) => p.selected ? 'rgba(59,130,246,0.7)' : 'rgba(255,255,255,0.15)'};
  }
`;

const Thumb = styled.div`
  position: relative;
  width: 100%;
  aspect-ratio: 1;
  background: linear-gradient(135deg, #0f172a 0%, #1e293b 100%);
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

const VideoIndicator = styled.div`
  position: absolute;
  bottom: 6px;
  right: 6px;
  background: rgba(0,0,0,0.55);
  border-radius: 50%;
  width: 26px;
  height: 26px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #fff;
  font-size: 13px;
  backdrop-filter: blur(4px);
`;

const PriceBadge = styled.span<{ free?: boolean }>`
  position: absolute;
  top: 8px;
  right: 8px;
  background: ${(p) => p.free
    ? 'linear-gradient(135deg, rgba(34,197,94,0.95), rgba(16,185,129,0.95))'
    : 'linear-gradient(135deg, rgba(245,158,11,0.95), rgba(217,119,6,0.95))'};
  color: #fff;
  font-size: 11px;
  font-weight: 600;
  padding: 3px 8px;
  border-radius: 10px;
  letter-spacing: 0.2px;
  box-shadow: 0 2px 6px rgba(0,0,0,0.25);
`;

const CardBody = styled.div`
  padding: 10px 12px 12px;
`;

const AvatarName = styled.div`
  font-weight: 600;
  font-size: 13px;
  color: var(--text-primary, #e2e8f0);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  margin-bottom: 2px;
`;

const StyleTag = styled.div`
  font-size: 11px;
  color: rgba(148,163,184,0.7);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  margin-bottom: 6px;
`;

const MetaRow = styled.div`
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 4px;
  margin-top: 4px;
  font-size: 11px;
  color: rgba(148,163,184,0.7);
`;

const UserCount = styled.span`
  display: inline-flex;
  align-items: center;
  gap: 3px;
`;

// ── List-view row ──
const ListRow = styled.div<{ selected?: boolean }>`
  display: flex;
  gap: 12px;
  padding: 10px 12px;
  cursor: pointer;
  border-radius: 10px;
  margin-bottom: 6px;
  background: ${(p) => p.selected
    ? 'linear-gradient(135deg, rgba(59,130,246,0.18) 0%, rgba(147,51,234,0.10) 100%)'
    : 'var(--bg-secondary, #1e293b)'};
  border: 1px solid ${(p) => p.selected ? 'rgba(59,130,246,0.5)' : 'rgba(255,255,255,0.05)'};
  transition: all .2s ease;

  &:hover {
    background: ${(p) => p.selected
      ? 'linear-gradient(135deg, rgba(59,130,246,0.22) 0%, rgba(147,51,234,0.12) 100%)'
      : 'var(--bg-tertiary, #334155)'};
    border-color: ${(p) => p.selected ? 'rgba(59,130,246,0.7)' : 'rgba(255,255,255,0.1)'};
  }
`;

const ListThumb = styled.div`
  width: 56px;
  height: 56px;
  border-radius: 8px;
  overflow: hidden;
  background: linear-gradient(135deg, #0f172a 0%, #1e293b 100%);
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  position: relative;

  img, video {
    width: 100%;
    height: 100%;
    object-fit: cover;
  }
`;

const ListInfo = styled.div`
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  justify-content: center;
  gap: 2px;
`;

// ── Props ──
interface AvatarListProps {
  avatars: AvatarItem[];
  loading: boolean;
  selectedId: string | null;
  viewMode: AvatarViewMode;
  onSelect: (avatar: AvatarItem) => void;
}

type PriceFilter = 'all' | 'free' | 'paid';
type TypeFilter = 'all' | 'image' | 'video';
type VisibilityFilter = 'all' | 'public' | 'private';
type SortKey = 'default' | 'newest' | 'popular' | 'rating';

const getImageUrl = (a: AvatarItem) => a.presigned_image_url || a.cloud_image_url || '';
const getVideoUrl = (a: AvatarItem) => a.presigned_video_url || a.cloud_video_url || '';
const hasVideo = (a: AvatarItem) => Boolean(getVideoUrl(a) || a.video_path);
const isFree = (a: AvatarItem) => !a.price;

/**
 * Grid card with hover video preview — when hovering, swap static image for
 * the muted/looping video (if any). Falls back to the static image on leave.
 */
const GridCard: React.FC<{
  avatar: AvatarItem;
  selected: boolean;
  onSelect: (a: AvatarItem) => void;
}> = ({ avatar, selected, onSelect }) => {
  const { t } = useTranslation();
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const [hovering, setHovering] = useState(false);
  const videoUrl = getVideoUrl(avatar);
  const showVideo = hovering && videoUrl;

  useEffect(() => {
    const v = videoRef.current;
    if (!v) return;
    if (showVideo) {
      v.currentTime = 0;
      v.play().catch(() => undefined);
    } else {
      v.pause();
    }
  }, [showVideo]);

  return (
    <Card
      selected={selected}
      onClick={() => onSelect(avatar)}
      onMouseEnter={() => setHovering(true)}
      onMouseLeave={() => setHovering(false)}
    >
      <Thumb>
        {showVideo ? (
          <video
            ref={videoRef}
            src={videoUrl}
            poster={getImageUrl(avatar)}
            muted
            loop
            playsInline
            preload="metadata"
          />
        ) : getImageUrl(avatar) ? (
          <img src={getImageUrl(avatar)} alt={avatar.name} loading="lazy" />
        ) : (
          <UserOutlined style={{ fontSize: 36, color: 'rgba(148,163,184,0.4)' }} />
        )}
        {hasVideo(avatar) && !showVideo && (
          <VideoIndicator><PlayCircleOutlined /></VideoIndicator>
        )}
        <PriceBadge free={isFree(avatar)}>
          {isFree(avatar) ? t('avatar.free') : `$${(avatar.price ?? 0).toFixed(2)}`}
        </PriceBadge>
      </Thumb>
      <CardBody>
        <AvatarName>{avatar.name || t('avatar.untitled')}</AvatarName>
        {avatar.style && <StyleTag>{avatar.style}</StyleTag>}
        <Rate disabled allowHalf value={avatar.rating ?? 0} style={{ fontSize: 11 }} />
        <MetaRow>
          <UserCount>
            <TeamOutlined />
            {avatar.subscribers ?? 0} {t('avatar.users')}
          </UserCount>
          <Tooltip title={hasVideo(avatar) ? t('avatar.video_type') : t('avatar.image_type')}>
            {hasVideo(avatar)
              ? <VideoCameraOutlined style={{ color: 'rgba(96,165,250,0.85)' }} />
              : <PictureOutlined style={{ color: 'rgba(148,163,184,0.6)' }} />}
          </Tooltip>
        </MetaRow>
      </CardBody>
    </Card>
  );
};

const AvatarList: React.FC<AvatarListProps> = ({
  avatars,
  loading,
  selectedId,
  viewMode,
  onSelect,
}) => {
  const { t } = useTranslation();
  const [searchText, setSearchText] = useState('');
  const [searchField, setSearchField] = useState<AvatarSearchField>('name');
  const [priceFilter, setPriceFilter] = useState<PriceFilter>('all');
  const [typeFilter, setTypeFilter] = useState<TypeFilter>('all');
  const [visibilityFilter, setVisibilityFilter] = useState<VisibilityFilter>('all');
  const [sortKey, setSortKey] = useState<SortKey>('default');

  const filtered = useMemo(() => {
    const q = searchText.trim().toLowerCase();
    return avatars.filter((a) => {
      // Search
      if (q) {
        let matched = false;
        switch (searchField) {
          case 'name':
            matched = (a.name || '').toLowerCase().includes(q);
            break;
          case 'artist':
            matched = (a.artist || a.owner || '').toLowerCase().includes(q);
            break;
          case 'style':
            matched = (a.style || '').toLowerCase().includes(q) ||
              (a.tags || []).some((tag) => tag.toLowerCase().includes(q));
            break;
          case 'popularity':
            // Popularity field: query interpreted as minimum subscriber count
            matched = (a.subscribers ?? 0) >= Number(q) || isNaN(Number(q));
            break;
        }
        if (!matched) return false;
      }
      // Price filter
      if (priceFilter === 'free' && !isFree(a)) return false;
      if (priceFilter === 'paid' && isFree(a)) return false;
      // Type filter
      if (typeFilter === 'image' && hasVideo(a)) return false;
      if (typeFilter === 'video' && !hasVideo(a)) return false;
      // Visibility filter
      if (visibilityFilter === 'public' && !a.is_public) return false;
      if (visibilityFilter === 'private' && a.is_public) return false;
      return true;
    });
  }, [avatars, searchText, searchField, priceFilter, typeFilter, visibilityFilter]);

  const sorted = useMemo(() => {
    if (searchField === 'popularity') {
      // For the old popularity search semantic, keep the previous sort-by-subscribers behavior
      return [...filtered].sort((a, b) => (b.subscribers ?? 0) - (a.subscribers ?? 0));
    }
    const list = [...filtered];
    switch (sortKey) {
      case 'newest':
        list.sort((a, b) => {
          const ta = a.created_at ? new Date(a.created_at).getTime() : 0;
          const tb = b.created_at ? new Date(b.created_at).getTime() : 0;
          return tb - ta;
        });
        break;
      case 'popular':
        list.sort((a, b) => (b.subscribers ?? 0) - (a.subscribers ?? 0));
        break;
      case 'rating':
        list.sort((a, b) => (b.rating ?? 0) - (a.rating ?? 0));
        break;
    }
    return list;
  }, [filtered, sortKey, searchField]);

  const hasActiveFilter =
    priceFilter !== 'all' || typeFilter !== 'all' || visibilityFilter !== 'all';

  const clearFilters = () => {
    setPriceFilter('all');
    setTypeFilter('all');
    setVisibilityFilter('all');
  };

  const renderGridCard = (a: AvatarItem) => (
    <GridCard
      key={a.id}
      avatar={a}
      selected={selectedId === a.id}
      onSelect={onSelect}
    />
  );

  const renderListRow = (a: AvatarItem) => {
    const videoUrl = getVideoUrl(a);
    return (
      <ListRow key={a.id} selected={selectedId === a.id} onClick={() => onSelect(a)}>
        <ListThumb>
          {getImageUrl(a) ? (
            <img src={getImageUrl(a)} alt={a.name} loading="lazy" />
          ) : (
            <UserOutlined style={{ fontSize: 24, color: 'rgba(148,163,184,0.4)' }} />
          )}
          {videoUrl && (
            <VideoIndicator style={{ width: 18, height: 18, fontSize: 10, bottom: 2, right: 2 }}>
              <PlayCircleOutlined />
            </VideoIndicator>
          )}
        </ListThumb>
        <ListInfo>
          <AvatarName>{a.name || t('avatar.untitled')}</AvatarName>
          <div style={{ fontSize: 11, color: 'rgba(148,163,184,0.7)' }}>
            {a.style || a.artist || a.owner || t('avatar.unknown')}
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 11, color: 'rgba(148,163,184,0.7)' }}>
            <Rate disabled allowHalf value={a.rating ?? 0} style={{ fontSize: 10 }} />
            <span style={{ color: isFree(a) ? '#52c41a' : '#faad14', fontWeight: 600 }}>
              {isFree(a) ? t('avatar.free') : `$${(a.price ?? 0).toFixed(2)}`}
            </span>
            <UserCount>
              <TeamOutlined />
              {a.subscribers ?? 0}
            </UserCount>
          </div>
        </ListInfo>
        {a.is_public
          ? <Tag color="blue" style={{ marginLeft: 'auto', alignSelf: 'center' }}>{t('avatar.public')}</Tag>
          : <Tag style={{ marginLeft: 'auto', alignSelf: 'center' }}>{t('avatar.private')}</Tag>}
      </ListRow>
    );
  };

  return (
    <ListContainer>
      <ToolBar>
        <SearchRow>
          <Select
            value={searchField}
            onChange={(v) => setSearchField(v)}
            size="small"
            style={{ width: 110 }}
            popupMatchSelectWidth={false}
          >
            <Option value="name">{t('avatar.search_field_name')}</Option>
            <Option value="artist">{t('avatar.search_field_author')}</Option>
            <Option value="style">{t('avatar.search_field_style')}</Option>
          </Select>
          <Input
            placeholder={t('avatar.search_placeholder', { field: t(`avatar.search_field_${searchField}`) })}
            prefix={<SearchOutlined style={{ color: 'rgba(148,163,184,0.5)' }} />}
            size="small"
            allowClear
            value={searchText}
            onChange={(e) => setSearchText(e.target.value)}
            style={{ flex: 1 }}
          />
          <Select
            value={sortKey}
            onChange={(v) => setSortKey(v)}
            size="small"
            style={{ width: 110 }}
            popupMatchSelectWidth={false}
            title={t('avatar.sort.label')}
          >
            <Option value="default">{t('avatar.sort.default')}</Option>
            <Option value="newest">{t('avatar.sort.newest')}</Option>
            <Option value="popular">{t('avatar.sort.popular')}</Option>
            <Option value="rating">{t('avatar.sort.rating')}</Option>
          </Select>
        </SearchRow>
        <FilterRow>
          <Select
            value={priceFilter}
            onChange={setPriceFilter}
            size="small"
            style={{ width: 92 }}
            popupMatchSelectWidth={false}
          >
            <Option value="all">{t('avatar.filter.price_all')}</Option>
            <Option value="free">{t('avatar.filter.price_free')}</Option>
            <Option value="paid">{t('avatar.filter.price_paid')}</Option>
          </Select>
          <Select
            value={typeFilter}
            onChange={setTypeFilter}
            size="small"
            style={{ width: 92 }}
            popupMatchSelectWidth={false}
          >
            <Option value="all">{t('avatar.filter.type_all')}</Option>
            <Option value="image">{t('avatar.filter.type_image')}</Option>
            <Option value="video">{t('avatar.filter.type_video')}</Option>
          </Select>
          <Select
            value={visibilityFilter}
            onChange={setVisibilityFilter}
            size="small"
            style={{ width: 100 }}
            popupMatchSelectWidth={false}
          >
            <Option value="all">{t('avatar.filter.visibility_all')}</Option>
            <Option value="public">{t('avatar.filter.visibility_public')}</Option>
            <Option value="private">{t('avatar.filter.visibility_private')}</Option>
          </Select>
          {hasActiveFilter && (
            <a
              role="button"
              style={{ fontSize: 11, color: 'rgba(96,165,250,0.9)', cursor: 'pointer' }}
              onClick={clearFilters}
            >
              {t('avatar.filter.clear')}
            </a>
          )}
        </FilterRow>
      </ToolBar>

      <ScrollArea>
        {loading ? (
          <div style={{ textAlign: 'center', padding: 48 }}><Spin /></div>
        ) : sorted.length === 0 ? (
          <Empty
            description={t('avatar.no_avatars_found')}
            image={Empty.PRESENTED_IMAGE_SIMPLE}
            style={{ marginTop: 48 }}
          />
        ) : viewMode === 'grid' ? (
          <GridContainer>
            {sorted.map(renderGridCard)}
          </GridContainer>
        ) : (
          sorted.map(renderListRow)
        )}
      </ScrollArea>
    </ListContainer>
  );
};

export default AvatarList;