import { Attachment, FileInfo, FileContent } from '@/pages/Chat/types/chat';
import { IPCAPI } from './api';
import { APIResponse } from './api';

// 传入 apiInstance，返回 chat 相关Method的对象
export function createChatApi(apiInstance: IPCAPI) {
    return {
        /**
         * Get聊天List
         * QueryUser参与的All会话（含成员，Default不含Message），如需Message请 deep=True
         */
        getChats<T>(userId: string, deep?: boolean): Promise<APIResponse<T>> {
            return apiInstance['executeRequest']('get_chats', { userId, deep });
        },
        /**
         * Search聊天（按MessageContent）
         * QueryUser参与的会话中Include指定文本的会话
         */
        searchChats<T>(userId: string, searchText: string, deep?: boolean): Promise<APIResponse<T>> {
            return apiInstance['executeRequest']('search_chats', { userId, searchText, deep });
        },
        /**
         * Create新会话
         */
        createChat<T>(chat_data: any): Promise<APIResponse<T>> {
            return apiInstance['executeRequest']('create_chat', chat_data);
        },
        /**
         * Send聊天Message
         */
        sendChat<T>(message: {
            chatId: string;
            role: string;
            content: string;
            senderId: string;
            createAt: string;
            id?: string;
            status?: string;
            senderName?: string;
            time?: string;
            ext?: any;
            i_tag?: string;
            attachments?: Attachment[];
        }): Promise<APIResponse<T>> {
            return apiInstance['executeRequest']('send_chat', message);
        },
        /**
         * Get指定会话MessageList
         */
        getChatMessages<T>(params: {
            chatId: string;
            limit?: number;
            offset?: number;
            reverse?: boolean;
        }): Promise<APIResponse<T>> {
            return apiInstance['executeRequest']('get_chat_messages', params);
        },
        /**
         * Get指定会话NotificationList
         */
        getChatNotifications<T>(params: {
            chatId: string;
            limit?: number;
            offset?: number;
            reverse?: boolean;
        }): Promise<APIResponse<T>> {
            return apiInstance['executeRequest']('get_chat_notifications', params);
        },
        /**
         * Delete会话
         */
        deleteChat<T>(chatId: string): Promise<APIResponse<T>> {
            return apiInstance['executeRequest']('delete_chat', { chatId });
        },
        /**
         * 批量标记Message为已读
         */
        markMessageAsRead<T>(messageIds: string[], userId: string): Promise<APIResponse<T>> {
            return apiInstance['executeRequest']('mark_message_as_read', { messageIds, userId });
        },
        /**
         * 上传附件
         */
        uploadAttachment<T>(params: {
            name: string;
            type: string;
            size: number;
            data: string | ArrayBuffer;
        }): Promise<APIResponse<T>> {
            return apiInstance['executeRequest']('upload_attachment', params);
        },
        /**
         * Get文件Information
         */
        getFileInfo(filePath: string): Promise<APIResponse<FileInfo>> {
            return apiInstance['executeRequest']('get_file_info', { filePath });
        },
        /**
         * Get文件Content
         */
        getFileContent(filePath: string): Promise<APIResponse<FileContent>> {
            return apiInstance['executeRequest']('get_file_content', { filePath });
        },
        /**
         * Submitchat form Content
         */
        chatFormSubmit(chatId: string, messageId: string, formId: string, formData: any): Promise<APIResponse<FileContent>> {
            return apiInstance['executeRequest']('chat_form_submit', { chatId, messageId,  formId, formData });
        },
        /**
         * DeleteMessage
         */
        deleteMessage<T>(chatId: string, messageId: string): Promise<APIResponse<T>> {
            return apiInstance['executeRequest']('delete_message', { chatId, messageId });
        },
        /**
         * 清除会话未读数
         */
        cleanChatUnRead<T>(chatId: string): Promise<APIResponse<T>> {
            return apiInstance['executeRequest']('clean_chat_unread', { chatId });
        },
    };
} 