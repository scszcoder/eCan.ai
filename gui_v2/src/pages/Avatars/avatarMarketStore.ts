import { create } from 'zustand';
import { apiRouter } from '../../services/api/api-router';
import { GRAPHQL_QUERIES } from '../../services/api/api-config';
import type { AvatarItem } from './types';

interface AvatarMarketStoreState {
  avatars: AvatarItem[];
  loading: boolean;
  error: string | null;
  fetched: boolean;
  fetch: (username: string) => Promise<void>;
  forceRefresh: (username: string) => Promise<void>;
  upsertAvatar: (avatar: AvatarItem) => void;
}

/**
 * Parse avatar_metadata AWSJSON field and merge marketplace fields
 */
function enrichAvatar(raw: any): AvatarItem {
  const item: AvatarItem = { ...raw };
  // Use presigned URLs first, then cloud URLs
  if (!item.presigned_image_url && item.cloud_image_url) {
    item.presigned_image_url = item.cloud_image_url;
  }
  if (!item.presigned_video_url && item.cloud_video_url) {
    item.presigned_video_url = item.cloud_video_url;
  }
  // Parse avatar_metadata if present
  let meta = (raw as any).avatar_metadata;
  if (typeof meta === 'string') {
    try { meta = JSON.parse(meta); } catch { meta = null; }
  }
  if (meta && typeof meta === 'object') {
    item.artist = meta.artist || item.artist;
    item.style = meta.style || item.style;
    item.tags = meta.tags || item.tags;
    item.price = meta.price ?? item.price ?? 0;
    item.rating = meta.rating ?? item.rating ?? 0;
    item.subscribers = meta.subscribers ?? item.subscribers ?? 0;
  }
  // Defaults
  if (item.price == null) item.price = 0;
  if (item.rating == null) item.rating = 0;
  if (item.subscribers == null) item.subscribers = item.usage_count ?? 0;
  if (!item.artist) item.artist = item.owner || 'Unknown';
  return item;
}

export const useAvatarMarketStore = create<AvatarMarketStoreState>((set, get) => ({
  avatars: [],
  loading: false,
  error: null,
  fetched: false,

  fetch: async (_username: string) => {
    if (get().loading) return;
    if (get().fetched) return;
    set({ loading: true, error: null });
    try {
      // Fetch all avatars (public + user's)
      const response = await apiRouter.execute<any>(
        {
          method: 'avatar.get_all',
          graphql: {
            query: GRAPHQL_QUERIES.GET_AVATAR_RESOURCES,
            resultPath: 'getAvatars'
          }
        },
        {}
      );
      if (response.success) {
        let rows = response.data;
        if (typeof rows === 'string') {
          try { rows = JSON.parse(rows); } catch { rows = []; }
        }
        const list: AvatarItem[] = Array.isArray(rows) ? rows.map(enrichAvatar) : [];
        set({ avatars: list, loading: false, fetched: true });
      } else {
        throw new Error((response as any).error?.message || 'Failed to fetch avatars');
      }
    } catch (e: any) {
      console.error('[AvatarMarketStore] fetch error:', e);
      set({ loading: false, error: e?.message || 'Unknown error' });
    }
  },

  forceRefresh: async (username: string) => {
    set({ fetched: false });
    await get().fetch(username);
  },

  /**
   * Inject a freshly uploaded avatar into the local cache without re-fetching.
   * Used by AvatarUploader's onSuccess handler for an optimistic update.
   */
  upsertAvatar: (avatar: AvatarItem) => {
    set((state) => {
      const idx = state.avatars.findIndex((a) => a.id === avatar.id);
      if (idx === -1) {
        return { avatars: [avatar, ...state.avatars] };
      }
      const next = state.avatars.slice();
      next[idx] = { ...next[idx], ...avatar };
      return { avatars: next };
    });
  },
}));

/**
 * Find avatars that share style / artist with `base`, excluding `base` itself.
 * Pure client-side filter — does not require backend support.
 */
export function findRelatedAvatars(
  base: AvatarItem,
  pool: AvatarItem[],
  limit = 6,
): AvatarItem[] {
  const baseStyle = (base.style || '').toLowerCase();
  const baseArtist = (base.artist || base.owner || '').toLowerCase();
  const scored = pool
    .filter((a) => a.id !== base.id)
    .map((a) => {
      const style = (a.style || '').toLowerCase();
      const artist = (a.artist || a.owner || '').toLowerCase();
      let score = 0;
      if (baseStyle && style && baseStyle === style) score += 3;
      else if (baseStyle && style && (style.includes(baseStyle) || baseStyle.includes(style))) score += 1;
      if (baseArtist && artist && baseArtist === artist) score += 2;
      return { avatar: a, score };
    })
    .filter((x) => x.score > 0)
    .sort((a, b) => {
      if (b.score !== a.score) return b.score - a.score;
      return (b.avatar.subscribers ?? 0) - (a.avatar.subscribers ?? 0);
    });
  return scored.slice(0, limit).map((x) => x.avatar);
}
