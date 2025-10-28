/**
 * 协议Process器
 * ProcessCustom协议如 pyqtfile:// 的拦截和路由
 * 
 * Main功能：
 * 1. 拦截Page内 pyqtfile:// Link的Click
 * 2. Process直接访问的 pyqtfile:// URL
 * 3. 根据文件Type自动Execute预览或下载
 */
import { logger } from '../../../utils/logger';
import { FileUtils } from './fileUtils';
import { Toast } from '@douyinfe/semi-ui';
import React from 'react';
import { createRoot } from 'react-dom/client';
import ImageViewer from '../components/ImageViewer';

/**
 * 协议Process器类
 * 负责拦截和ProcessCustom协议
 */
export class ProtocolHandler {
    private static instance: ProtocolHandler;
    private isInitialized = false;
    private processingFiles = new Set<string>(); // 防重复Process
    private beforeUnloadHandler: (() => void) | null = null; // Storage beforeunload Process器Reference

    private constructor() {}

    /**
     * Get协议Process器单例
     */
    public static getInstance(): ProtocolHandler {
        if (!ProtocolHandler.instance) {
            ProtocolHandler.instance = new ProtocolHandler();
        }
        return ProtocolHandler.instance;
    }

    /**
     * Initialize协议Process器
     */
    public init(): void {
        if (this.isInitialized) {
            return;
        }

        try {
            // Register pyqtfile:// 协议Process器
            this.registerPyQtFileProtocol();
            
            // 将 protocolHandler Settings到 window 对象上，供其他Component使用
            (window as any).protocolHandler = {
                handleFile: (filePath: string, fileName: string, mimeType: string) => {
                    this.handleFile(filePath, fileName, mimeType);
                }
            };
            
            this.isInitialized = true;
            logger.info('Protocol handler initialized successfully');
        } catch (error) {
            logger.error('Failed to initialize protocol handler:', error);
        }
    }

    /**
     * Register pyqtfile:// 协议Process器
     * SettingsPage内Link拦截和直接访问Process
     */
    private registerPyQtFileProtocol(): void {
        // RemovePage内Link拦截，避免与ChatDetail中的EventProcess冲突
        // this.setupLinkInterceptor();

        // Listen直接访问的 pyqtfile:// URL
        this.setupDirectAccessHandler();
    }

    /**
     * SettingsLink拦截器
     * 拦截Page内All pyqtfile:// Link的Click
     * Note：此Method已Disabled，避免与ChatDetail中的EventProcess冲突
     */
    private setupLinkInterceptor(): void {
        // Disabled此Method，避免重复EventListen
        // document.addEventListener('click', (event) => {
        //     const target = event.target as HTMLElement;
        //     const link = target.closest('a');
        //     
        //     if (link && link.href && link.href.startsWith('pyqtfile://')) {
        //         event.preventDefault();
        //         event.stopPropagation();
        //         
        //         const filePath = this.extractFilePathFromUrl(link.href);
        //         if (filePath) {
        //             this.handlePyQtFileUrl(filePath);
        //         }
        //     }
        // });

        logger.info('Link interceptor disabled to avoid conflicts with ChatDetail');
    }

    /**
     * Settings直接访问Process器
     * ProcessUser直接在Address栏Input pyqtfile:// URL 的情况
     */
    private setupDirectAccessHandler(): void {
        // CheckWhen前Page是否是通过 pyqtfile:// 协议访问的
        if (window.location.protocol === 'pyqtfile:') {
            const filePath = this.extractFilePathFromUrl(window.location.href);
            if (filePath) {
                this.handlePyQtFileUrl(filePath);
            }
        }

        // Create并Save beforeunload Process器Reference
        this.beforeUnloadHandler = () => {
            // PageUnmount时的Cleanup逻辑
            logger.info('Protocol handler cleaning up on page unload');
            this.processingFiles.clear();
        };

        // Listen beforeunload Event
        window.addEventListener('beforeunload', this.beforeUnloadHandler);

        logger.info('Direct access handler setup completed');
    }

    /**
     * Cleanup协议Process器
     * RemoveAllEventListen器，防止内存泄漏
     */
    public cleanup(): void {
        if (!this.isInitialized) {
            return;
        }

        try {
            // Remove beforeunload Listen器
            if (this.beforeUnloadHandler) {
                window.removeEventListener('beforeunload', this.beforeUnloadHandler);
                this.beforeUnloadHandler = null;
            }

            // CleanupProcess中的文件集合
            this.processingFiles.clear();

            // Remove window 对象上的Reference
            if ((window as any).protocolHandler) {
                delete (window as any).protocolHandler;
            }

            this.isInitialized = false;
            logger.info('Protocol handler cleaned up successfully');
        } catch (error) {
            logger.error('Failed to cleanup protocol handler:', error);
        }
    }

    /**
     * 从 URL 中提取文件Path
     */
    private extractFilePathFromUrl(url: string): string | null {
        try {
            if (url.startsWith('pyqtfile://')) {
                // Remove协议前缀
                const path = url.replace('pyqtfile://', '');
                return path || null;
            }
        } catch (error) {
            logger.error('Failed to extract file path from URL:', error);
        }
        return null;
    }

    /**
     * Process pyqtfile:// URL
     */
    private async handlePyQtFileUrl(filePath: string): Promise<void> {
        try {
            logger.info(`Handling pyqtfile:// URL: ${filePath}`);
            
            // 使用 FileUtils Get文件Information，确保PathProcess一致性
            const fileInfo = await FileUtils.getFileInfo(filePath);
            
            if (fileInfo) {
                // 根据文件Type决定Process方式
                if (FileUtils.isImageFile(fileInfo.mimeType || '')) {
                    // 图片文件：Display预览
                    await this.showImagePreview(filePath, fileInfo.fileName, fileInfo.mimeType || '');
                } else {
                    // 其他文件：下载
                    await this.downloadFile(filePath, fileInfo.fileName);
                }
            } else {
                logger.error('Failed to get file info for path:', filePath);
                Toast.error('文件不存在或无法访问');
            }
        } catch (error) {
            logger.error('Failed to handle pyqtfile URL:', error);
            Toast.error('Process文件时发生Error');
        }
    }

    /**
     * Display图片预览
     */
    private async showImagePreview(filePath: string, fileName: string, mimeType: string): Promise<void> {
        try {
            const imageUrl = await FileUtils.getFileThumbnail(filePath);
            
            if (imageUrl) {
                // Create预览模态框
                this.createImagePreviewModal(imageUrl, fileName, filePath, mimeType);
            } else {
                Toast.error('无法Load图片预览');
            }
        } catch (error) {
            logger.error('Failed to show image preview:', error);
            Toast.error('Display图片预览Failed');
        }
    }

    /**
     * 下载文件
     */
    private async downloadFile(filePath: string, fileName: string): Promise<void> {
        try {
            await FileUtils.downloadFile(filePath, fileName);
            Toast.success(`文件 ${fileName} 下载Success`);
        } catch (error) {
            logger.error('Failed to download file:', error);
            Toast.error('文件下载Failed');
        }
    }

    /**
     * Create图片预览模态框
     */
    private createImagePreviewModal(imageUrl: string, fileName: string, filePath: string, mimeType: string): void {
        // CreateContainer元素
        const container = document.createElement('div');
        container.id = 'image-viewer-container';
        document.body.appendChild(container);

        // Create React 18 root
        const root = createRoot(container);

        // CloseFunction
        const closeModal = () => {
            if (container && container.parentNode) {
                root.unmount();
                container.parentNode.removeChild(container);
            }
        };

        // RenderImageViewerComponent
        root.render(
            React.createElement(ImageViewer, {
                imageUrl,
                fileName,
                filePath,
                mimeType,
                onClose: closeModal
            })
        );
    }

    /**
     * Process文件下载
     * 供ExternalComponent调用的PublicMethod
     */
    public async handleFile(filePath: string, fileName: string, mimeType: string): Promise<void> {
        // 防重复Process
        if (this.processingFiles.has(filePath)) {
            logger.info(`File ${filePath} is already being processed, skipping`);
            return;
        }

        this.processingFiles.add(filePath);
        
        try {
            logger.info(`Handling file download: ${filePath}, ${fileName}, ${mimeType}`);
            
            if (FileUtils.isImageFile(mimeType)) {
                // 图片文件：Display预览
                await this.showImagePreview(filePath, fileName, mimeType);
            } else {
                // 其他文件：下载
                await this.downloadFile(filePath, fileName);
            }
        } catch (error) {
            logger.error('Failed to handle file:', error);
            Toast.error('Process文件时发生Error');
        } finally {
            // DelayRemoveProcessStatus，避免Fast重复Click
            setTimeout(() => {
                this.processingFiles.delete(filePath);
            }, 2000);
        }
    }
}

// Export单例实例
export const protocolHandler = ProtocolHandler.getInstance(); 