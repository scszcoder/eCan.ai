import { Message } from '../types/chat';
import { logger } from '@/utils/logger';

/**
 * Check两条Message是否是重复的
 * Based on ID matching, time+content+sender matching, and optimistic update ID matching
 * 
 * Uses multiple strategies to detect duplicates:
 * 1. Exact ID match (for messages from backend with consistent IDs)
 * 2. Content + sender + approximate time match (for optimistic updates)
 */
export function isDuplicateMessage(messageA: Message, messageB: Message): boolean {
  // Strategy 1: Exact ID match
  if (messageA.id && messageB.id && messageA.id === messageB.id) {
    return true;
  }

  // Strategy 2: For optimistic updates - match by content + sender + time
  // This handles cases where frontend generates temp ID but backend returns different UUID
  const contentA = typeof messageA.content === 'string' ? messageA.content : JSON.stringify(messageA.content);
  const contentB = typeof messageB.content === 'string' ? messageB.content : JSON.stringify(messageB.content);

  if (contentA && contentB && contentA === contentB) {
    // Check sender match (by ID or name)
    const senderMatches =
      (messageA.senderId && messageB.senderId && messageA.senderId === messageB.senderId) ||
      (messageA.senderName && messageB.senderName && messageA.senderName === messageB.senderName);

    if (senderMatches) {
      // Check time match (within 10 seconds to handle timing differences)
      const timeA = messageA.createAt || 0;
      const timeB = messageB.createAt || 0;
      const timeDiff = Math.abs(timeA - timeB);

      if (timeDiff < 10000) { // 10 seconds
        logger.debug(`[isDuplicateMessage] Matched by content+sender+time: content=${contentA.substring(0, 50)}, timeDiff=${timeDiff}ms`);
        return true;
      }
    }
  }

  return false;
}

/**
 * 确保Message有唯一的ID
 */
export function ensureMessageId(message: Message): Message {
  if (!message.id) {
    return {
      ...message,
      id: `msg_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`
    };
  }
  return message;
}

/**
 * 记录MessageProcessLog
 */
export function logMessageProcessing(action: string, messageId: string, details?: any): void {
  let detailsStr = '';
  if (details !== undefined) {
    if (typeof details === 'string') {
      detailsStr = ` - ${details}`;
    } else if (typeof details === 'object' && details !== null) {
      // 将对象Convert为Concise的键Value对字符串
      const entries = Object.entries(details);
      if (entries.length > 0) {
        detailsStr = ` - ${entries.map(([key, value]) => `${key}:${String(value)}`).join(', ')}`;
      }
    } else {
      detailsStr = ` - ${String(details)}`;
    }
  }
  
  logger.debug(`Message processing [${action}]: ${messageId}${detailsStr}`);
} 