import { Attachment, FileInfo, FileContent } from '@/pages/Chat/types/chat';
import { IPCAPI } from './api';
import { APIResponse } from './api';

// 传入 apiInstance，返回 chat 相关方法的对象
export function createChatApi(apiInstance: IPCAPI) {
    return {
        /**
         * 获取聊天列表
         * 查询用户参与的所有会话（含成员，默认不含消息），如需消息请 deep=True
         */
        getChats<T>(userId: string, deep?: boolean): Promise<APIResponse<T>> {
            return apiInstance['executeRequest']('get_chats', { userId, deep });
        },
        /**
         * 创建新会话
         */
        createChat<T>(chat_data: any): Promise<APIResponse<T>> {
            return apiInstance['executeRequest']('create_chat', chat_data);
        },
        /**
         * 发送聊天消息
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
            attachments?: Attachment[];
        }): Promise<APIResponse<T>> {
            return apiInstance['executeRequest']('send_chat', message);
        },
        /**
         * 获取指定会话消息列表
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
         * 获取指定会话通知列表
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
         * 删除会话
         */
        deleteChat<T>(chatId: string): Promise<APIResponse<T>> {
            return apiInstance['executeRequest']('delete_chat', { chatId });
        },
        /**
         * 批量标记消息为已读
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
         * 获取文件信息
         */
        getFileInfo(filePath: string): Promise<APIResponse<FileInfo>> {
            return apiInstance['executeRequest']('get_file_info', { filePath });
        },
        /**
         * 获取文件内容
         */
        getFileContent(filePath: string): Promise<APIResponse<FileContent>> {
            return apiInstance['executeRequest']('get_file_content', { filePath });
        },
        /**
         * 提交chat form 内容
         */
        chatFormSubmit(chatId: string, messageId: string, formId: string, formData: any): Promise<APIResponse<FileContent>> {
            return apiInstance['executeRequest']('chat_form_submit', { chatId, messageId,  formId, formData });
        },
        /**
         * 删除消息
         */
        deleteMessage<T>(chatId: string, messageId: string): Promise<APIResponse<T>> {
            return apiInstance['executeRequest']('delete_message', { chatId, messageId });
        },
    };
} 