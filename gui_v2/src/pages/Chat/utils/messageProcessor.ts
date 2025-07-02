import { Message } from '../types/chat';
import { FileUtils } from './fileUtils';

// Import the Semi UI Message type
import { Message as SemiMessage } from '@douyinfe/semi-foundation/lib/es/chat/foundation';

// 处理消息内容，简化为字符串类型，并确保返回符合 Semi UI 的消息格式
export const processMessageContent = (message: Message): SemiMessage => {
    // 创建一个新的消息对象，保留原始消息的所有属性
    const processedMessage: any = { ...message };

    // 确保消息有唯一的 id
    if (!processedMessage.id) {
        processedMessage.id = `msg_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
    }

    // 构建文本内容
    let textContent = '';
    
    // 处理原始文本内容
    if (typeof message.content === 'string' && message.content.trim()) {
        textContent = message.content;
    } else if (Array.isArray(message.content)) {
        // 如果已经是数组，提取文本内容
        const textItems = message.content
            .filter(item => item.type === 'text' && item.text)
            .map(item => item.text);
        textContent = textItems.join('\n');
    }

    // 处理附件，将附件信息添加到文本内容中
    if (message.attachments && message.attachments.length > 0) {
        const attachmentTexts = message.attachments.map((attachment, index) => {
            const mimeType = attachment.mimeType || attachment.type || 'application/octet-stream';
            const isImage = attachment.isImage || FileUtils.isImageFile(mimeType);
            const rawFilePath = attachment.filePath || attachment.url || '';
            const fileName = attachment.name || `file_${index}`;
            
            // 检查文件路径是否有效
            if (!rawFilePath || rawFilePath.trim() === '') {
                return null; // 跳过无效的附件
            }
            
            // 使用 pyqtfile:// 协议生成文件路径
            const filePath = rawFilePath.startsWith('pyqtfile://') 
                ? rawFilePath 
                : `pyqtfile://${rawFilePath}`;
            
            const attachmentText = isImage 
                ? `[image|${filePath}|${fileName}|${mimeType}]`
                : `[file|${filePath}|${fileName}|${mimeType}]`;
            
            return attachmentText;
        }).filter(Boolean); // 过滤掉 null 值
        
        if (attachmentTexts.length > 0) {
            if (textContent) {
                textContent += '\n' + attachmentTexts.join('\n');
            } else {
                textContent = attachmentTexts.join('\n');
            }
        }
    }

    // 将处理后的文本内容赋值给消息
    processedMessage.content = textContent;
    
    // 移除原始的 attachments 字段，防止 Semi UI 渲染原生附件组件
    // 因为我们已经将附件信息转换为文本内容，使用自定义渲染器处理
    delete processedMessage.attachments;

    return processedMessage as SemiMessage;
};

// 对消息进行去重和处理
export const processAndDeduplicateMessages = (messages: Message[]): SemiMessage[] => {
    if (!messages || !Array.isArray(messages)) {
        return [];
    }

    // 改进的去重处理，确保没有重复的消息
    const uniqueMessages = messages.reduce((acc: Message[], message) => {
        // 检查是否已存在相同的消息
        const exists = acc.find(m => {
            // 1. 检查 ID 是否相同
            if (m.id === message.id) return true;
            
            // 2. 检查是否是同一时间发送的相同内容（时间窗口：5秒内）
            const timeDiff = Math.abs((m.createAt || 0) - (message.createAt || 0));
            const isSameTime = timeDiff < 5000; // 5秒内
            const isSameContent = JSON.stringify(m.content) === JSON.stringify(message.content);
            const isSameSender = m.senderId === message.senderId;
            
            if (isSameTime && isSameContent && isSameSender) return true;
            
            // 3. 检查是否是乐观更新的消息（通过 ID 前缀判断）
            if (m.id.startsWith('user_msg_') && message.id.startsWith('user_msg_')) {
                const mTime = parseInt(m.id.split('_')[2]) || 0;
                const msgTime = parseInt(message.id.split('_')[2]) || 0;
                const timeDiff = Math.abs(mTime - msgTime);
                if (timeDiff < 1000 && isSameContent && isSameSender) return true;
            }
            
            return false;
        });
        
        if (!exists) {
            acc.push(message);
        }
        return acc;
    }, []);
    
    // 按时间排序，确保消息顺序稳定
    uniqueMessages.sort((a, b) => (a.createAt || 0) - (b.createAt || 0));
    
    const processedMessages = uniqueMessages.map((message) => {
        const processed = processMessageContent(message);
        // 确保每个消息都有唯一的 key，使用消息 ID 而不是索引
        processed.key = `msg_${processed.id}`;
        return processed;
    });
    
    return processedMessages;
}; 