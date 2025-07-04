import { Message } from '../types/chat';
import { logger } from '@/utils/logger';
import { ensureMessageId, isDuplicateMessage, logMessageProcessing } from './messageUtils';

/**
 * 向消息列表添加新消息，并处理去重逻辑
 * 
 * @param chatMessages 当前聊天的消息列表
 * @param message 要添加的新消息
 * @returns 处理后的结果，包含是否重复和处理后的消息
 */
export function addMessageToList(chatMessages: Message[], message: Message): { 
  isDuplicate: boolean; 
  messages: Message[];
  newMessage?: Message;
} {
  // 检查是否有重复消息
  const isDuplicate = chatMessages.some(m => isDuplicateMessage(m, message));
  
  if (isDuplicate) {
    logMessageProcessing('duplicate_skipped', message.id || 'unknown');
    return { isDuplicate: true, messages: chatMessages };
  }
  
  // 确保消息有唯一ID
  const newMessage = ensureMessageId(message);
  
  // 添加到消息列表
  const updatedMessages = [...chatMessages, newMessage];
  
  return { 
    isDuplicate: false, 
    messages: updatedMessages,
    newMessage 
  };
}

/**
 * 更新消息列表中的指定消息
 * 
 * @param chatMessages 消息列表
 * @param messageId 要更新的消息ID
 * @param updates 更新内容
 * @returns 更新后的消息列表
 */
export function updateMessageInList(
  chatMessages: Message[], 
  messageId: string, 
  updates: Partial<Message>
): Message[] {
  const updatedMessages = chatMessages.map(message => 
    message.id === messageId ? { ...message, ...updates } : message
  );
  
  logMessageProcessing('update', messageId, { updates });
  return updatedMessages;
}

/**
 * 对消息列表进行排序
 * 
 * @param messages 消息列表
 * @returns 排序后的消息列表
 */
export function sortMessagesByTime(messages: Message[]): Message[] {
  return [...messages].sort((a, b) => (a.createAt || 0) - (b.createAt || 0));
}

/**
 * 从消息列表中移除指定ID的消息
 * 
 * @param messages 消息列表
 * @param messageId 要移除的消息ID
 * @returns 移除后的消息列表
 */
export function removeMessageFromList(messages: Message[], messageId: string): Message[] {
  return messages.filter(message => message.id !== messageId);
} 