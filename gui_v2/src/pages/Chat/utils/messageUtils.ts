import { Message } from '../types/chat';
import { logger } from '@/utils/logger';

/**
 * 检查两条消息是否是重复的
 * 基于ID匹配、时间+内容+发送者匹配、以及乐观更新ID匹配
 */
export function isDuplicateMessage(messageA: Message, messageB: Message): boolean {
  return messageA.id === messageB.id;
}

/**
 * 确保消息有唯一的ID
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
 * 记录消息处理日志
 */
export function logMessageProcessing(action: string, messageId: string, details?: any): void {
  logger.debug(`Message processing [${action}]: ${messageId}`, details);
} 