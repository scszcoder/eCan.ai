/**
 * Base Store Types
 * 定义所有 store 的基础类型和接口
 */

/**
 * 基础资源接口 - 所有资源必须有 id
 */
export interface BaseResource {
  id: string;
}

/**
 * 基础 Store 状态接口
 */
export interface BaseStoreState<T extends BaseResource> {
  // 数据
  items: T[];
  
  // 状态
  loading: boolean;
  error: string | null;
  lastFetched: number | null;
  
  // 基础 CRUD 操作
  setItems: (items: T[]) => void;
  addItem: (item: T) => void;
  updateItem: (id: string, updates: Partial<T>) => void;
  removeItem: (id: string) => void;
  
  // 查询方法
  getItemById: (id: string) => T | null;
  getItems: () => T[];
  
  // 数据获取
  fetchItems: (username: string, ...args: any[]) => Promise<void>;
  shouldFetch: () => boolean;
  forceRefresh: (username: string, ...args: any[]) => Promise<void>;

  // 状态管理
  setLoading: (loading: boolean) => void;
  setError: (error: string | null) => void;
  clearData: () => void;
}

/**
 * API 响应接口
 */
export interface APIResponse<T> {
  success: boolean;
  data?: T;
  error?: {
    code: string;
    message: string;
  };
}

/**
 * 资源 API 接口 - 所有 API 服务必须实现
 */
export interface ResourceAPI<T extends BaseResource> {
  getAll(username: string, ...args: any[]): Promise<APIResponse<T[]>>;
  getById(username: string, id: string): Promise<APIResponse<T>>;
  create(username: string, item: T): Promise<APIResponse<T>>;
  update(username: string, id: string, updates: Partial<T>): Promise<APIResponse<T>>;
  delete(username: string, id: string): Promise<APIResponse<void>>;
}

/**
 * Store 配置选项
 */
export interface StoreOptions {
  /** Store 名称，用于持久化存储的 key */
  name: string;
  
  /** 是否启用持久化 */
  persist?: boolean;
  
  /** 缓存过期时间（毫秒），默认 5 分钟 */
  cacheDuration?: number;
  
  /** 是否在持久化时包含 loading 和 error 状态 */
  persistLoadingState?: boolean;
}

/**
 * 缓存策略
 */
export const CACHE_DURATION = {
  /** 1 分钟 */
  SHORT: 1 * 60 * 1000,
  /** 5 分钟 */
  MEDIUM: 5 * 60 * 1000,
  /** 15 分钟 */
  LONG: 15 * 60 * 1000,
  /** 1 小时 */
  VERY_LONG: 60 * 60 * 1000,
} as const;

