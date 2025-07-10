import { Message } from '../types/chat';
import { logger } from '@/utils/logger';

/**
 * 检查两条消息是否是重复的
 * 基于ID匹配、时间+内容+发送者匹配、以及乐观更新ID匹配
 */
export function isDuplicateMessage(messageA: Message, messageB: Message): boolean {
  // 1. 检查 ID 是否相同
  if (messageA.id === messageB.id) return true;
  
  // 2. 检查是否是同一时间发送的相同内容（时间窗口：5秒内）
  const timeDiff = Math.abs((messageA.createAt || 0) - (messageB.createAt || 0));
  const isSameTime = timeDiff < 5000; // 5秒内
  const isSameContent = JSON.stringify(messageA.content) === JSON.stringify(messageB.content);
  const isSameSender = messageA.senderId === messageB.senderId;
  
  if (isSameTime && isSameContent && isSameSender) return true;
  
  // 3. 检查是否是乐观更新的消息（通过 ID 前缀判断）
  if (messageA.id?.startsWith('user_msg_') && messageB.id?.startsWith('user_msg_')) {
    const mTime = parseInt(messageA.id.split('_')[2]) || 0;
    const msgTime = parseInt(messageB.id.split('_')[2]) || 0;
    const timeDiff = Math.abs(mTime - msgTime);
    if (timeDiff < 1000 && isSameContent && isSameSender) return true;
  }
  
  return false;
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