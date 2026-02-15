/**
 * Avatar marketplace types
 */

export interface AvatarItem {
  id: string;
  name: string;
  owner: string;
  resource_type: string;
  description?: string;
  cloud_image_url?: string;
  cloud_video_url?: string;
  cloud_image_key?: string;
  cloud_video_key?: string;
  presigned_image_url?: string;
  presigned_video_url?: string;
  is_public?: boolean;
  usage_count?: number;
  image_hash?: string;
  image_path?: string;
  video_path?: string;
  // Marketplace fields (future - stored in avatar_metadata)
  artist?: string;
  style?: string;
  tags?: string[];
  price?: number;         // 0 = free
  rating?: number;        // 0-5 stars
  subscribers?: number;
  created_at?: string;
  updated_at?: string;
}

export type AvatarSearchField = 'name' | 'artist' | 'style' | 'popularity';

export type AvatarViewMode = 'list' | 'grid';
