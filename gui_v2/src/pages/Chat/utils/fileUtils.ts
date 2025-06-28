import { createIPCAPI } from '@/services/ipc/api';
import { FileInfo, FileContent } from '@/pages/Chat/types/chat';
import { logger } from '@/utils/logger';
import { ImagePreviewManager } from './imagePreviewManager';

/**
 * 文件处理工具类
 * 提供文件信息获取、内容读取、预览等功能
 */
export class FileUtils {
    private static api = createIPCAPI();

    /**
     * 获取文件信息
     * @param filePath 文件路径
     * @returns Promise<FileInfo | null>
     */
    static async getFileInfo(filePath: string): Promise<FileInfo | null> {
        try {
            // 如果是绝对路径，转换为 pyqtfile: 协议格式
            let normalizedPath = filePath;
            if (!filePath.startsWith('pyqtfile:')) {
                normalizedPath = `pyqtfile://${filePath}`;
            }
            
            const response = await this.api.chat.getFileInfo(normalizedPath);
            if (response.success && response.data) {
                return response.data;
            } else {
                logger.error('Failed to get file info:', response.error);
                return null;
            }
        } catch (error) {
            logger.error('Error getting file info:', error);
            return null;
        }
    }

    /**
     * 获取文件内容
     * @param filePath 文件路径
     * @returns Promise<FileContent | null>
     */
    static async getFileContent(filePath: string): Promise<FileContent | null> {
        try {
            // 如果是绝对路径，转换为 pyqtfile: 协议格式
            let normalizedPath = filePath;
            if (!filePath.startsWith('pyqtfile:')) {
                normalizedPath = `pyqtfile://${filePath}`;
            }
            
            const response = await this.api.chat.getFileContent(normalizedPath);
            if (response.success && response.data) {
                return response.data;
            } else {
                logger.error('Failed to get file content:', response.error);
                return null;
            }
        } catch (error) {
            logger.error('Error getting file content:', error);
            return null;
        }
    }

    /**
     * 预览文件（图片显示，其他文件下载）
     * @param filePath 文件路径
     * @returns Promise<boolean> 是否成功处理
     */
    static async previewFile(filePath: string): Promise<boolean> {
        try {
            // 首先获取文件信息
            const fileInfo = await this.getFileInfo(filePath);
            
            if (!fileInfo) {
                console.error('[FileUtils] Failed to get file info');
                return false;
            }

            // 如果是图片文件，直接获取内容并显示预览
            if (fileInfo.isImage) {
                const fileContent = await this.getFileContent(filePath);
                
                if (fileContent) {
                    this.showImagePreview(fileContent.dataUrl, fileInfo.fileName);
                    return true;
                }
            } else {
                // 非图片文件，下载文件
                const fileContent = await this.getFileContent(filePath);
                
                if (fileContent) {
                    this.downloadFile(fileContent.dataUrl, fileInfo.fileName);
                    return true;
                }
            }

            console.error('[FileUtils] Failed to process file');
            return false;
        } catch (error) {
            logger.error('Error previewing file:', error);
            return false;
        }
    }

    /**
     * 显示图片预览
     * @param dataUrl 图片的 data URL
     * @param fileName 文件名
     */
    private static showImagePreview(dataUrl: string, fileName: string): void {
        // 使用图片预览管理器显示模态窗口
        ImagePreviewManager.showImagePreview(dataUrl, fileName);
    }

    /**
     * 下载文件
     * @param dataUrl 文件的 data URL
     * @param fileName 文件名
     */
    private static downloadFile(dataUrl: string, fileName: string): void {
        try {
            const link = document.createElement('a');
            link.href = dataUrl;
            link.download = fileName;
            document.body.appendChild(link);
            link.click();
            document.body.removeChild(link);
        } catch (error) {
            console.error('[FileUtils] Download failed:', error);
        }
    }

    /**
     * 检查是否为本地文件路径
     * @param url 文件 URL 或路径
     * @returns boolean
     */
    static isLocalFile(url: string): boolean {
        // 检查是否为本地文件路径（不是 http/https 协议）
        // 支持 pyqtfile: 协议和绝对路径格式
        return !url.startsWith('http://') && 
               !url.startsWith('https://') && 
               !url.startsWith('data:') &&
               (url.startsWith('pyqtfile:') || 
                url.startsWith('/') || 
                /^[A-Za-z]:\\/.test(url)); // Windows 路径
    }

    /**
     * 处理附件点击事件
     * @param attachment 附件对象
     * @returns Promise<boolean> 是否成功处理
     */
    static async handleAttachmentClick(attachment: { url?: string; name?: string }): Promise<boolean> {
        if (!attachment.url) {
            logger.warn('Attachment has no URL');
            return false;
        }

        // 如果是本地文件，使用我们的 API 处理
        if (this.isLocalFile(attachment.url)) {
            // 直接使用原始路径，让 previewFile 方法处理路径转换
            return await this.previewFile(attachment.url);
        } else {
            // 如果是网络文件，直接打开
            window.open(attachment.url, '_blank');
            return true;
        }
    }
} 