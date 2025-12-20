/**
 * Base Store Types
 * Defines base types and interfaces for all stores
 */

/**
 * Base resource interface - all resources must have an id
 */
export interface BaseResource {
  id: string;
}

/**
 * Base Store state interface
 */
export interface BaseStoreState<T extends BaseResource> {
  // Data
  items: T[];
  
  // State
  loading: boolean;
  error: string | null;
  lastFetched: number | null;
  
  // Basic CRUD operations
  setItems: (items: T[]) => void;
  addItem: (item: T) => void;
  updateItem: (id: string, updates: Partial<T>) => void;
  removeItem: (id: string) => void;
  
  // Query methods
  getItemById: (id: string) => T | null;
  getItems: () => T[];
  
  // Data fetching
  fetchItems: (username: string, ...args: any[]) => Promise<void>;
  shouldFetch: () => boolean;
  forceRefresh: (username: string, ...args: any[]) => Promise<void>;

  // State management
  setLoading: (loading: boolean) => void;
  setError: (error: string | null) => void;
  clearData: () => void;
}

/**
 * API response interface
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
 * Resource API interface - all API services must implement this
 */
export interface ResourceAPI<T extends BaseResource> {
  getAll(username: string, ...args: any[]): Promise<APIResponse<T[]>>;
  getById(username: string, id: string): Promise<APIResponse<T>>;
  create(username: string, item: T): Promise<APIResponse<T>>;
  update(username: string, id: string, updates: Partial<T>): Promise<APIResponse<T>>;
  delete(username: string, id: string): Promise<APIResponse<void>>;
}

/**
 * Store configuration options
 */
export interface StoreOptions {
  /** Store name, used as key for persistent storage */
  name: string;
  
  /** Whether to enable persistence */
  persist?: boolean;
  
  /** Cache expiration time (milliseconds), defaults to 5 minutes */
  cacheDuration?: number;
  
  /** Whether to include loading and error state in persistence */
  persistLoadingState?: boolean;
}

/**
 * Cache strategy
 */
export const CACHE_DURATION = {
  /** 1 minute */
  SHORT: 1 * 60 * 1000,
  /** 5 minutes */
  MEDIUM: 5 * 60 * 1000,
  /** 15 minutes */
  LONG: 15 * 60 * 1000,
  /** 1 hour */
  VERY_LONG: 60 * 60 * 1000,
} as const;

