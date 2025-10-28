import { Message } from '../types/chat';
import { logger } from '@/utils/logger';
import { ensureMessageId, isDuplicateMessage, logMessageProcessing } from './messageUtils';

/**
 * 向MessageListAdd新Message，并Process去重逻辑
 * 
 * @param chatMessages When前聊天的MessageList
 * @param message 要Add的新Message
 * @returns Process后的Result，Include是否重复和Process后的Message
 */
export function addMessageToList(chatMessages: Message[], message: Message): { 
  isDuplicate: boolean; 
  messages: Message[];
  newMessage?: Message;
} {
  // Check是否有重复Message
  const isDuplicate = chatMessages.some(m => isDuplicateMessage(m, message));
  
  if (isDuplicate) {
    logMessageProcessing('duplicate_skipped', message.id || 'unknown');
    return { isDuplicate: true, messages: chatMessages };
  }
  
  // 确保Message有唯一ID
  const newMessage = ensureMessageId(message);
  
  // Add到MessageList
  const updatedMessages = [...chatMessages, newMessage];
  
  return { 
    isDuplicate: false, 
    messages: updatedMessages,
    newMessage 
  };
}

/**
 * UpdateMessageList中的指定Message
 * 
 * @param chatMessages MessageList
 * @param messageId 要Update的MessageID
 * @param updates UpdateContent
 * @returns Update后的MessageList
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
 * 对MessageList进行Sort
 * 
 * @param messages MessageList
 * @returns Sort后的MessageList
 */
export function sortMessagesByTime(messages: Message[]): Message[] {
  return [...messages].sort((a, b) => (a.createAt || 0) - (b.createAt || 0));
}

/**
 * 从MessageList中Remove指定ID的Message
 * 
 * @param messages MessageList
 * @param messageId 要Remove的MessageID
 * @returns Remove后的MessageList
 */
export function removeMessageFromList(messages: Message[], messageId: string): Message[] {
  return messages.filter(message => message.id !== messageId);
} 