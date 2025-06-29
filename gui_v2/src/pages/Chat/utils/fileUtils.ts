import { FileInfo, FileContent } from '../types/chat';
import { logger } from '../../../utils/logger';
import React from 'react';
import { createRoot } from 'react-dom/client';
import ImageViewer from '../components/ImageViewer';
import { get_ipc_api } from '@/services/ipc_api';

/**
 * 文件类型常量
 */
export const FILE_TYPES = {
    IMAGE: ['image/jpeg', 'image/jpg', 'image/png', 'image/gif', 'image/webp', 'image/bmp', 'image/svg+xml'],
    DOCUMENT: ['application/pdf', 'application/msword', 'application/vnd.openxmlformats-officedocument.wordprocessingml.document', 'text/plain'],
    SPREADSHEET: ['application/vnd.ms-excel', 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'],
    PRESENTATION: ['application/vnd.ms-powerpoint', 'application/vnd.openxmlformats-officedocument.presentationml.presentation'],
    ARCHIVE: ['application/zip', 'application/x-rar-compressed', 'application/x-7z-compressed'],
    CODE: ['text/javascript', 'text/typescript', 'text/python', 'text/java', 'text/c', 'text/cpp', 'text/html', 'text/css', 'text/xml', 'application/json']
};

/**
 * 文件处理工具类
 * 提供文件信息获取、内容读取、预览等功能
 */
export class FileUtils {
    private static _api: any = null;

    /**
     * 获取 API 实例（懒加载）
     */
    private static get api() {
        if (!this._api) {
            this._api = get_ipc_api();
        }
        return this._api;
    }

    /**
     * 判断文件是否为图片
     */
    static isImageFile(mimeType: string): boolean {
        return FILE_TYPES.IMAGE.includes(mimeType);
    }

    /**
     * 判断文件是否为文档
     */
    static isDocumentFile(mimeType: string): boolean {
        return FILE_TYPES.DOCUMENT.includes(mimeType);
    }

    /**
     * 获取文件图标
     */
    static getFileIcon(mimeType: string): string {
        if (this.isImageFile(mimeType)) return '📷';
        if (this.isDocumentFile(mimeType)) return '📄';
        if (FILE_TYPES.SPREADSHEET.includes(mimeType)) return '📊';
        if (FILE_TYPES.PRESENTATION.includes(mimeType)) return '📈';
        if (FILE_TYPES.ARCHIVE.includes(mimeType)) return '📦';
        if (FILE_TYPES.CODE.includes(mimeType)) return '💻';
        return '📎';
    }

    /**
     * 格式化文件大小
     */
    static formatFileSize(bytes: number): string {
        if (bytes === 0) return '0 B';
        const k = 1024;
        const sizes = ['B', 'KB', 'MB', 'GB'];
        const i = Math.floor(Math.log(bytes) / Math.log(k));
        return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
    }

    /**
     * 从 pyqtfile:// URL 中提取文件路径
     */
    static extractFilePathFromUrl(url: string): string | null {
        if (!url || !url.startsWith('pyqtfile://')) {
            return null;
        }
        return url.replace('pyqtfile://', '');
    }

    /**
     * 获取文件信息
     * @param filePath 文件路径
     * @returns Promise<FileInfo | null>
     */
    static async getFileInfo(filePath: string): Promise<FileInfo | null> {
        try {
            // 标准化路径：移除 pyqtfile:// 前缀，因为后端期望接收不带前缀的路径
            let normalizedPath = filePath;
            if (filePath.startsWith('pyqtfile://')) {
                normalizedPath = filePath.replace('pyqtfile://', '');
            } else if (!filePath.startsWith('pyqtfile:')) {
                // 如果不是 pyqtfile 协议，保持原样
                normalizedPath = filePath;
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
            //logger.debug(`[getFileContent] Input filePath: ${filePath}`);
            
            // 标准化路径：移除 pyqtfile:// 前缀，因为后端期望接收不带前缀的路径
            let normalizedPath = filePath;
            if (filePath.startsWith('pyqtfile://')) {
                normalizedPath = filePath.replace('pyqtfile://', '');
            } else if (!filePath.startsWith('pyqtfile:')) {
                // 如果不是 pyqtfile 协议，保持原样
                normalizedPath = filePath;
            }
            
            //logger.debug(`[getFileContent] Normalized path: ${normalizedPath}`);
            
            const response = await this.api.chat.getFileContent(normalizedPath);
            
            if (response.success && response.data) {
                //logger.debug(`[getFileContent] Success, data received`);
                return response.data;
            } else {
                logger.error('Failed to get file content:', response.error);
                logger.error('Response details:', {
                    success: response.success,
                    error: response.error,
                    data: response.data
                });
                return null;
            }
        } catch (error) {
            logger.error('Error getting file content:', error);
            logger.error('Error details:', {
                message: error instanceof Error ? error.message : 'Unknown error',
                stack: error instanceof Error ? error.stack : undefined,
                filePath
            });
            return null;
        }
    }

    /**
     * 下载文件（通过 pyqtfile:// 协议）
     */
    static async downloadFile(filePath: string, fileName?: string): Promise<void> {
        try {
            logger.debug(`[downloadFile] Starting download for: ${filePath}`);
            
            const fileContent = await this.getFileContent(filePath);
            
            if (!fileContent || !fileContent.dataUrl) {
                throw new Error('文件内容为空');
            }
            
            // 从 data URL 创建 Blob
            const base64Data = fileContent.dataUrl.split(',')[1];
            const binaryData = atob(base64Data);
            const bytes = new Uint8Array(binaryData.length);
            for (let i = 0; i < binaryData.length; i++) {
                bytes[i] = binaryData.charCodeAt(i);
            }
            
            const blob = new Blob([bytes], { type: fileContent.mimeType });
            
            // 创建下载链接
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.style.display = 'none';
            a.href = url;
            a.download = fileName || fileContent.fileName || 'download';
            document.body.appendChild(a);
            a.click();
            
            // 清理
            setTimeout(() => {
                document.body.removeChild(a);
                URL.revokeObjectURL(url);
            }, 100);
            
            logger.debug(`[downloadFile] Download completed: ${fileName || fileContent.fileName}`);
        } catch (error) {
            logger.error('[downloadFile] Download failed:', error);
            throw error;
        }
    }

    /**
     * 获取文件缩略图（仅用于图片）
     */
    static async getFileThumbnail(filePath: string): Promise<string | null> {
        try {
            const fileContent = await this.getFileContent(filePath);
            
            if (!fileContent || !fileContent.dataUrl) {
                return null;
            }
            
            return fileContent.dataUrl;
        } catch (error) {
            logger.error('[getFileThumbnail] Failed to get thumbnail:', error);
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
                    this.downloadFile(filePath, fileInfo.fileName);
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
        // 创建容器元素
        const container = document.createElement('div');
        container.id = 'image-viewer-container';
        document.body.appendChild(container);

        // 创建 React 18 root
        const root = createRoot(container);

        // 关闭函数
        const closeModal = () => {
            if (container && container.parentNode) {
                root.unmount();
                container.parentNode.removeChild(container);
            }
        };

        // 渲染ImageViewer组件
        root.render(
            React.createElement(ImageViewer, {
                imageUrl: dataUrl,
                fileName,
                filePath: `temp://${fileName}`,
                mimeType: 'image/jpeg',
                onClose: closeModal
            })
        );
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