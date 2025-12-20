import { Message } from '../types/chat';
import { logger } from '@/utils/logger';

/**
 * Check两条Message是否是重复的
 * Based onID匹配、Time+Content+Send者匹配、以及乐观UpdateID匹配
 */
export function isDuplicateMessage(messageA: Message, messageB: Message): boolean {
  return messageA.id === messageB.id;
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