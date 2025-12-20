// DataStorage键名常量
export const STORAGE_KEYS = {
  KNOWLEDGE_ENTRIES: 'knowledge_entries',
  QA_PAIRS: 'qa_pairs',
  CATEGORIES: 'categories',
  COMMENTS: 'comments',
  VERSIONS: 'versions',
  USER_SETTINGS: 'user_settings',
  SYSTEM_SETTINGS: 'system_settings',
  USER_PERMISSIONS: 'user_permissions',
  ROLES: 'roles',
} as const;

// DataTypeDefinition
export interface StorageData {
  [STORAGE_KEYS.KNOWLEDGE_ENTRIES]: any[];
  [STORAGE_KEYS.QA_PAIRS]: any[];
  [STORAGE_KEYS.CATEGORIES]: any[];
  [STORAGE_KEYS.COMMENTS]: any[];
  [STORAGE_KEYS.VERSIONS]: any[];
  [STORAGE_KEYS.USER_SETTINGS]: any;
  [STORAGE_KEYS.SYSTEM_SETTINGS]: any;
  [STORAGE_KEYS.USER_PERMISSIONS]: any[];
  [STORAGE_KEYS.ROLES]: any[];
}

// StorageService类
class StorageService {
  private storage: Storage;

  constructor() {
    this.storage = localStorage;
  }

  // GetData
  get<T>(key: string, defaultValue?: T): T | null {
    try {
      const item = this.storage.getItem(key);
      return item ? JSON.parse(item) : defaultValue || null;
    } catch (error) {
      console.error(`Error getting data from storage for key: ${key}`, error);
      return defaultValue || null;
    }
  }

  // SettingsData
  set<T>(key: string, value: T): void {
    try {
      this.storage.setItem(key, JSON.stringify(value));
    } catch (error) {
      console.error(`Error setting data to storage for key: ${key}`, error);
    }
  }

  // DeleteData
  remove(key: string): void {
    try {
      this.storage.removeItem(key);
    } catch (error) {
      console.error(`Error removing data from storage for key: ${key}`, error);
    }
  }

  // 清空AllData
  clear(): void {
    try {
      this.storage.clear();
    } catch (error) {
      console.error('Error clearing storage', error);
    }
  }

  // Check键是否存在
  has(key: string): boolean {
    return this.storage.getItem(key) !== null;
  }

  // GetAll键
  keys(): string[] {
    return Object.keys(this.storage);
  }

  // GetStorageSize
  size(): number {
    return this.storage.length;
  }
}

// CreateStorageService实例
export const storageService = new StorageService();

// Data Management Service
export class DataManager {
  // Knowledge entry management
  static getKnowledgeEntries() {
    return storageService.get(STORAGE_KEYS.KNOWLEDGE_ENTRIES, []);
  }

  static setKnowledgeEntries(entries: any[]) {
    storageService.set(STORAGE_KEYS.KNOWLEDGE_ENTRIES, entries);
  }

  static addKnowledgeEntry(entry: any) {
    const entries = this.getKnowledgeEntries();
    entries.unshift(entry);
    this.setKnowledgeEntries(entries);
    return entry;
  }

  static updateKnowledgeEntry(id: number, updates: any) {
    const entries = this.getKnowledgeEntries();
    const index = entries.findIndex(entry => entry.id === id);
    if (index !== -1) {
      entries[index] = { ...entries[index], ...updates };
      this.setKnowledgeEntries(entries);
      return entries[index];
    }
    return null;
  }

  static deleteKnowledgeEntry(id: number) {
    const entries = this.getKnowledgeEntries();
    const filteredEntries = entries.filter(entry => entry.id !== id);
    this.setKnowledgeEntries(filteredEntries);
  }

  // Q&A pair management
  static getQAPairs() {
    return storageService.get(STORAGE_KEYS.QA_PAIRS, []);
  }

  static setQAPairs(pairs: any[]) {
    storageService.set(STORAGE_KEYS.QA_PAIRS, pairs);
  }

  static addQAPair(pair: any) {
    const pairs = this.getQAPairs();
    pairs.unshift(pair);
    this.setQAPairs(pairs);
    return pair;
  }

  static updateQAPair(id: number, updates: any) {
    const pairs = this.getQAPairs();
    const index = pairs.findIndex(pair => pair.id === id);
    if (index !== -1) {
      pairs[index] = { ...pairs[index], ...updates };
      this.setQAPairs(pairs);
      return pairs[index];
    }
    return null;
  }

  // Category management
  static getCategories() {
    return storageService.get(STORAGE_KEYS.CATEGORIES, []);
  }

  static setCategories(categories: any[]) {
    storageService.set(STORAGE_KEYS.CATEGORIES, categories);
  }

  // Comment management
  static getComments() {
    return storageService.get(STORAGE_KEYS.COMMENTS, []);
  }

  static setComments(comments: any[]) {
    storageService.set(STORAGE_KEYS.COMMENTS, comments);
  }

  static addComment(comment: any) {
    const comments = this.getComments();
    comments.unshift(comment);
    this.setComments(comments);
    return comment;
  }

  // Version management
  static getVersions() {
    return storageService.get(STORAGE_KEYS.VERSIONS, []);
  }

  static setVersions(versions: any[]) {
    storageService.set(STORAGE_KEYS.VERSIONS, versions);
  }

  static addVersion(version: any) {
    const versions = this.getVersions();
    versions.unshift(version);
    this.setVersions(versions);
    return version;
  }

  // User settings management
  static getUserSettings() {
    return storageService.get(STORAGE_KEYS.USER_SETTINGS, {});
  }

  static setUserSettings(settings: any) {
    storageService.set(STORAGE_KEYS.USER_SETTINGS, settings);
  }

  static updateUserSettings(updates: any) {
    const settings = this.getUserSettings();
    const newSettings = { ...settings, ...updates };
    this.setUserSettings(newSettings);
    return newSettings;
  }

  // System settings management
  static getSystemSettings() {
    return storageService.get(STORAGE_KEYS.SYSTEM_SETTINGS, {});
  }

  static setSystemSettings(settings: any) {
    storageService.set(STORAGE_KEYS.SYSTEM_SETTINGS, settings);
  }

  // User permission management
  static getUserPermissions() {
    return storageService.get(STORAGE_KEYS.USER_PERMISSIONS, []);
  }

  static setUserPermissions(permissions: any[]) {
    storageService.set(STORAGE_KEYS.USER_PERMISSIONS, permissions);
  }

  // Role management
  static getRoles() {
    return storageService.get(STORAGE_KEYS.ROLES, []);
  }

  static setRoles(roles: any[]) {
    storageService.set(STORAGE_KEYS.ROLES, roles);
  }

  // DataExport
  static exportData() {
    const data: StorageData = {
      [STORAGE_KEYS.KNOWLEDGE_ENTRIES]: this.getKnowledgeEntries(),
      [STORAGE_KEYS.QA_PAIRS]: this.getQAPairs(),
      [STORAGE_KEYS.CATEGORIES]: this.getCategories(),
      [STORAGE_KEYS.COMMENTS]: this.getComments(),
      [STORAGE_KEYS.VERSIONS]: this.getVersions(),
      [STORAGE_KEYS.USER_SETTINGS]: this.getUserSettings(),
      [STORAGE_KEYS.SYSTEM_SETTINGS]: this.getSystemSettings(),
      [STORAGE_KEYS.USER_PERMISSIONS]: this.getUserPermissions(),
      [STORAGE_KEYS.ROLES]: this.getRoles(),
    };
    return data;
  }

  // DataImport
  static importData(data: Partial<StorageData>) {
    Object.entries(data).forEach(([key, value]) => {
      if (value !== undefined) {
        storageService.set(key, value);
      }
    });
  }

  // DataBackup
  static backup() {
    const data = this.exportData();
    const timestamp = new Date().toISOString().replace(/[:.]/g, '-');
    const filename = `knowledge-backup-${timestamp}.json`;
    
    const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  }

  // DataRestore
  static async restore(file: File): Promise<boolean> {
    try {
      const text = await file.text();
      const data = JSON.parse(text);
      this.importData(data);
      return true;
    } catch (error) {
      console.error('Error restoring data:', error);
      return false;
    }
  }
}

// InitializeDefaultData
export const initializeDefaultData = () => {
  // InitializeDefault知识条目
  if (!storageService.has(STORAGE_KEYS.KNOWLEDGE_ENTRIES)) {
    const defaultEntries = [
      {
        id: 1,
        title: 'Fast开始指南',
        content: '本Documentation介绍如何Fast上手使用System...',
        category: '技术Documentation',
        tags: ['入门', '指南', 'Fast'],
        createdAt: '2024-01-15',
        updatedAt: '2024-01-15',
      },
      {
        id: 2,
        title: 'API 参考Documentation',
        content: 'Detailed的 API Interface说明和使用Example...',
        category: '技术Documentation',
        tags: ['API', 'Development', 'Interface'],
        createdAt: '2024-01-14',
        updatedAt: '2024-01-14',
      },
    ];
    DataManager.setKnowledgeEntries(defaultEntries);
  }

  // InitializeDefault问答对
  if (!storageService.has(STORAGE_KEYS.QA_PAIRS)) {
    const defaultQAPairs = [
      {
        id: 1,
        question: '如何Create新Documentation？',
        answer: 'Click"新建Documentation"Button，填写标题和Content即可Create新Documentation。',
        asker: 'UserA',
        createdAt: '2024-01-15',
        category: '技术Documentation',
        status: 'approved',
      },
    ];
    DataManager.setQAPairs(defaultQAPairs);
  }

  // InitializeDefaultCategory
  if (!storageService.has(STORAGE_KEYS.CATEGORIES)) {
    const defaultCategories = [
      {
        id: 'tech',
        title: '技术Documentation',
        level: 0,
        documentCount: 15,
        children: [
          {
            id: 'tech-user',
            title: 'User指南',
            level: 1,
            parentKey: 'tech',
            documentCount: 8,
          },
        ],
      },
    ];
    DataManager.setCategories(defaultCategories);
  }

  // InitializeDefaultSystemSettings
  if (!storageService.has(STORAGE_KEYS.SYSTEM_SETTINGS)) {
    const defaultSystemSettings = {
      theme: 'light',
      language: 'zh-CN',
      autoSave: true,
      autoSaveInterval: 30,
      aiResponseLength: 'detailed',
      autoTransferToHuman: true,
      autoClassifyQuestions: true,
    };
    DataManager.setSystemSettings(defaultSystemSettings);
  }
}; 