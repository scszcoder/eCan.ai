import { eventBus } from '@/utils/eventBus';
import { logger } from '@/utils/logger';

/**
 * ITagManager keeps track of the latest i_tag per chat.
 * Backend sends i_tag in the message.content (object or JSON string).
 * When a new message with a non-empty i_tag arrives, we record it.
 */
class ITagManager {
  private latestTags: Map<string, string> = new Map(); // chatId -> latest_i_tag
  private storageKey = 'chat_latest_i_tags';

  constructor() {
    this.loadFromStorage();
    this.initEventListeners();
  }

  private initEventListeners() {
    eventBus.on('chat:newMessage', (params: any) => {
      try {
        const { chatId, message } = params || {};
        const realChatId = chatId || message?.chatId;
        if (!realChatId) return;

        const contentRaw = message?.content;
        // Only proceed if content exists
        if (!contentRaw) return;

        let contentObj: any = contentRaw;
        if (typeof contentRaw === 'string') {
          if (contentRaw.startsWith('{') || contentRaw.startsWith('[')) {
            try {
              contentObj = JSON.parse(contentRaw);
            } catch (e) {
              // Not a JSON payload; ignore
              return;
            }
          } else {
            // Plain text message, ignore
            return;
          }
        }

        // i_tag is expected on the top level of content dict
        const iTag = contentObj?.i_tag;
        if (typeof iTag === 'string' && iTag.trim().length > 0) {
          this.latestTags.set(realChatId, iTag.trim());
          this.saveToStorage();
        }
      } catch (err) {
        logger.warn('[ITagManager] Failed to process chat:newMessage for i_tag', err as any);
      }
    });
  }

  public getLatest(chatId: string): string | undefined {
    return this.latestTags.get(chatId);
  }

  public setLatest(chatId: string, tag: string | undefined): void {
    if (typeof tag === 'string' && tag.trim().length > 0) {
      this.latestTags.set(chatId, tag.trim());
      this.saveToStorage();
    }
  }

  public clear(chatId: string): void {
    this.latestTags.delete(chatId);
    this.saveToStorage();
  }

  public clearAll(): void {
    this.latestTags.clear();
    this.saveToStorage();
  }

  private saveToStorage(): void {
    try {
      const obj: Record<string, string> = {};
      this.latestTags.forEach((val, key) => {
        obj[key] = val;
      });
      localStorage.setItem(this.storageKey, JSON.stringify(obj));
    } catch {
      // ignore storage errors
    }
  }

  private loadFromStorage(): void {
    try {
      const raw = localStorage.getItem(this.storageKey);
      if (!raw) return;
      const obj = JSON.parse(raw);
      if (obj && typeof obj === 'object') {
        Object.entries(obj).forEach(([k, v]) => {
          if (typeof v === 'string' && v.trim().length > 0) {
            this.latestTags.set(k, v);
          }
        });
      }
    } catch {
      // ignore parse errors
    }
  }
}

export const iTagManager = new ITagManager();
