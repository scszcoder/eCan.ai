import React, { useMemo, useState } from 'react';
import { Input, Select, Empty, Spin, Rate, Tag } from 'antd';
import {
  SearchOutlined,
  UserOutlined,
  PlayCircleOutlined,
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

const SearchBar = styled.div`
  display: flex;
  gap: 8px;
  padding: 8px 12px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.06);
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
    ? 'linear-gradient(135deg, rgba(24,144,255,0.15) 0%, rgba(24,144,255,0.05) 100%)'
    : 'var(--bg-secondary, #1e293b)'};
  border: 1px solid ${(p) => p.selected ? 'rgba(24,144,255,0.4)' : 'rgba(255,255,255,0.06)'};
  transition: all .25s ease;

  &:hover {
    transform: translateY(-2px);
    box-shadow: 0 6px 20px rgba(0,0,0,0.25);
    border-color: ${(p) => p.selected ? 'rgba(24,144,255,0.6)' : 'rgba(255,255,255,0.12)'};
  }
`;

const Thumb = styled.div`
  position: relative;
  width: 100%;
  aspect-ratio: 1;
  background: var(--bg-tertiary, #0f172a);
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

const VideoIndicator = styled.div`
  position: absolute;
  bottom: 6px;
  right: 6px;
  background: rgba(0,0,0,0.55);
  border-radius: 50%;
  width: 24px;
  height: 24px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #fff;
  font-size: 12px;
`;

const CardBody = styled.div`
  padding: 10px;
`;

const AvatarName = styled.div`
  font-weight: 600;
  font-size: 13px;
  color: var(--text-primary, #e2e8f0);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
`;

const AvatarId = styled.div`
  font-size: 11px;
  color: var(--text-secondary, rgba(148,163,184,0.7));
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  margin-bottom: 4px;
`;

const MetaRow = styled.div`
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 4px;
  margin-top: 4px;
`;

const Price = styled.span<{ free?: boolean }>`
  font-size: 12px;
  font-weight: 600;
  color: ${(p) => p.free ? '#52c41a' : '#faad14'};
`;

const UserCount = styled.span`
  font-size: 11px;
  color: var(--text-secondary, rgba(148,163,184,0.7));
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
    ? 'linear-gradient(135deg, rgba(24,144,255,0.15) 0%, rgba(24,144,255,0.05) 100%)'
    : 'var(--bg-secondary, #1e293b)'};
  border: 1px solid ${(p) => p.selected ? 'rgba(24,144,255,0.4)' : 'rgba(255,255,255,0.05)'};
  transition: all .2s ease;

  &:hover {
    background: ${(p) => p.selected
      ? 'linear-gradient(135deg, rgba(24,144,255,0.2) 0%, rgba(24,144,255,0.08) 100%)'
      : 'var(--bg-tertiary, #334155)'};
    border-color: ${(p) => p.selected ? 'rgba(24,144,255,0.6)' : 'rgba(255,255,255,0.1)'};
  }
`;

const ListThumb = styled.div`
  width: 56px;
  height: 56px;
  border-radius: 8px;
  overflow: hidden;
  background: var(--bg-tertiary, #0f172a);
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: center;

  img {
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
`;

// ── Props ──
interface AvatarListProps {
  avatars: AvatarItem[];
  loading: boolean;
  selectedId: string | null;
  viewMode: AvatarViewMode;
  onSelect: (avatar: AvatarItem) => void;
}

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

  const filtered = useMemo(() => {
    if (!searchText.trim()) return avatars;
    const q = searchText.toLowerCase();
    return avatars.filter((a) => {
      switch (searchField) {
        case 'name':
          return (a.name || '').toLowerCase().includes(q);
        case 'artist':
          return (a.artist || a.owner || '').toLowerCase().includes(q);
        case 'style':
          return (a.style || '').toLowerCase().includes(q) ||
            (a.tags || []).some((t) => t.toLowerCase().includes(q));
        case 'popularity':
          // For popularity treat query as a minimum subscriber count
          return (a.subscribers ?? 0) >= Number(q) || isNaN(Number(q));
        default:
          return true;
      }
    });
  }, [avatars, searchText, searchField]);

  const sorted = useMemo(() => {
    if (searchField === 'popularity') {
      return [...filtered].sort((a, b) => (b.subscribers ?? 0) - (a.subscribers ?? 0));
    }
    return filtered;
  }, [filtered, searchField]);

  const getImageUrl = (a: AvatarItem) =>
    a.presigned_image_url || a.cloud_image_url || '';

  const renderGridCard = (a: AvatarItem) => (
    <Card key={a.id} selected={selectedId === a.id} onClick={() => onSelect(a)}>
      <Thumb>
        {getImageUrl(a) ? (
          <img src={getImageUrl(a)} alt={a.name} loading="lazy" />
        ) : (
          <UserOutlined style={{ fontSize: 36, color: 'rgba(148,163,184,0.4)' }} />
        )}
        {(a.cloud_video_url || a.presigned_video_url || a.video_path) && (
          <VideoIndicator><PlayCircleOutlined /></VideoIndicator>
        )}
      </Thumb>
      <CardBody>
        <AvatarName>{a.name || t('avatar.untitled')}</AvatarName>
        <AvatarId>{a.id}</AvatarId>
        <Rate disabled allowHalf value={a.rating ?? 0} style={{ fontSize: 12 }} />
        <MetaRow>
          <Price free={!a.price}>{a.price ? `$${a.price.toFixed(2)}` : t('avatar.free')}</Price>
          <UserCount>{a.subscribers ?? 0} {t('avatar.users')}</UserCount>
        </MetaRow>
      </CardBody>
    </Card>
  );

  const renderListRow = (a: AvatarItem) => (
    <ListRow key={a.id} selected={selectedId === a.id} onClick={() => onSelect(a)}>
      <ListThumb>
        {getImageUrl(a) ? (
          <img src={getImageUrl(a)} alt={a.name} loading="lazy" />
        ) : (
          <UserOutlined style={{ fontSize: 24, color: 'rgba(148,163,184,0.4)' }} />
        )}
      </ListThumb>
      <ListInfo>
        <AvatarName>{a.name || t('avatar.untitled')}</AvatarName>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <Rate disabled allowHalf value={a.rating ?? 0} style={{ fontSize: 11 }} />
          <Price free={!a.price}>{a.price ? `$${a.price.toFixed(2)}` : t('avatar.free')}</Price>
          <UserCount>{a.subscribers ?? 0} {t('avatar.users')}</UserCount>
        </div>
      </ListInfo>
      {a.is_public && <Tag color="blue" style={{ marginLeft: 'auto', alignSelf: 'center' }}>{t('avatar.public')}</Tag>}
    </ListRow>
  );

  return (
    <ListContainer>
      <SearchBar>
        <Select
          value={searchField}
          onChange={(v) => setSearchField(v)}
          size="small"
          style={{ width: 120 }}
          popupMatchSelectWidth={false}
        >
          <Option value="name">{t('avatar.search_field_name')}</Option>
          <Option value="artist">{t('avatar.search_field_author')}</Option>
          <Option value="style">{t('avatar.search_field_style')}</Option>
          <Option value="popularity">{t('avatar.search_field_popularity')}</Option>
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
      </SearchBar>

      <ScrollArea>
        {loading ? (
          <div style={{ textAlign: 'center', padding: 48 }}><Spin /></div>
        ) : sorted.length === 0 ? (
          <Empty description={t('avatar.no_avatars_found')} image={Empty.PRESENTED_IMAGE_SIMPLE} style={{ marginTop: 48 }} />
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
