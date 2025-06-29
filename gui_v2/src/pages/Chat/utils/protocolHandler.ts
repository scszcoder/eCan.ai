/**
 * 协议处理器
 * 处理自定义协议如 pyqtfile:// 的拦截和路由
 * 
 * 主要功能：
 * 1. 拦截页面内 pyqtfile:// 链接的点击
 * 2. 处理直接访问的 pyqtfile:// URL
 * 3. 根据文件类型自动执行预览或下载
 */
import { logger } from '../../../utils/logger';
import { FileUtils } from './fileUtils';
import { Toast } from '@douyinfe/semi-ui';
import React from 'react';
import { createRoot } from 'react-dom/client';
import ImageViewer from '../components/ImageViewer';

/**
 * 协议处理器类
 * 负责拦截和处理自定义协议
 */
export class ProtocolHandler {
    private static instance: ProtocolHandler;
    private isInitialized = false;
    private processingFiles = new Set<string>(); // 防重复处理

    private constructor() {}

    /**
     * 获取协议处理器单例
     */
    public static getInstance(): ProtocolHandler {
        if (!ProtocolHandler.instance) {
            ProtocolHandler.instance = new ProtocolHandler();
        }
        return ProtocolHandler.instance;
    }

    /**
     * 初始化协议处理器
     */
    public init(): void {
        if (this.isInitialized) {
            return;
        }

        try {
            // 注册 pyqtfile:// 协议处理器
            this.registerPyQtFileProtocol();
            
            // 将 protocolHandler 设置到 window 对象上，供其他组件使用
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
     * 注册 pyqtfile:// 协议处理器
     * 设置页面内链接拦截和直接访问处理
     */
    private registerPyQtFileProtocol(): void {
        // 移除页面内链接拦截，避免与ChatDetail中的事件处理冲突
        // this.setupLinkInterceptor();

        // 监听直接访问的 pyqtfile:// URL
        this.setupDirectAccessHandler();
    }

    /**
     * 设置链接拦截器
     * 拦截页面内所有 pyqtfile:// 链接的点击
     * 注意：此方法已禁用，避免与ChatDetail中的事件处理冲突
     */
    private setupLinkInterceptor(): void {
        // 禁用此方法，避免重复事件监听
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
     * 设置直接访问处理器
     * 处理用户直接在地址栏输入 pyqtfile:// URL 的情况
     */
    private setupDirectAccessHandler(): void {
        // 检查当前页面是否是通过 pyqtfile:// 协议访问的
        if (window.location.protocol === 'pyqtfile:') {
            const filePath = this.extractFilePathFromUrl(window.location.href);
            if (filePath) {
                this.handlePyQtFileUrl(filePath);
            }
        }

        // 监听 beforeunload 事件，处理页面加载时的协议检查
        window.addEventListener('beforeunload', () => {
            // 这里可以添加清理逻辑
        });

        logger.info('Direct access handler setup completed');
    }

    /**
     * 从 URL 中提取文件路径
     */
    private extractFilePathFromUrl(url: string): string | null {
        try {
            if (url.startsWith('pyqtfile://')) {
                // 移除协议前缀
                const path = url.replace('pyqtfile://', '');
                return path || null;
            }
        } catch (error) {
            logger.error('Failed to extract file path from URL:', error);
        }
        return null;
    }

    /**
     * 处理 pyqtfile:// URL
     */
    private async handlePyQtFileUrl(filePath: string): Promise<void> {
        try {
            logger.info(`Handling pyqtfile:// URL: ${filePath}`);
            
            // 使用 FileUtils 获取文件信息，确保路径处理一致性
            const fileInfo = await FileUtils.getFileInfo(filePath);
            
            if (fileInfo) {
                // 根据文件类型决定处理方式
                if (FileUtils.isImageFile(fileInfo.mimeType || '')) {
                    // 图片文件：显示预览
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
            Toast.error('处理文件时发生错误');
        }
    }

    /**
     * 显示图片预览
     */
    private async showImagePreview(filePath: string, fileName: string, mimeType: string): Promise<void> {
        try {
            const imageUrl = await FileUtils.getFileThumbnail(filePath);
            
            if (imageUrl) {
                // 创建预览模态框
                this.createImagePreviewModal(imageUrl, fileName, filePath, mimeType);
            } else {
                Toast.error('无法加载图片预览');
            }
        } catch (error) {
            logger.error('Failed to show image preview:', error);
            Toast.error('显示图片预览失败');
        }
    }

    /**
     * 下载文件
     */
    private async downloadFile(filePath: string, fileName: string): Promise<void> {
        try {
            await FileUtils.downloadFile(filePath, fileName);
            Toast.success(`文件 ${fileName} 下载成功`);
        } catch (error) {
            logger.error('Failed to download file:', error);
            Toast.error('文件下载失败');
        }
    }

    /**
     * 创建图片预览模态框
     */
    private createImagePreviewModal(imageUrl: string, fileName: string, filePath: string, mimeType: string): void {
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
                imageUrl,
                fileName,
                filePath,
                mimeType,
                onClose: closeModal
            })
        );
    }

    /**
     * 处理文件下载
     * 供外部组件调用的公共方法
     */
    public async handleFile(filePath: string, fileName: string, mimeType: string): Promise<void> {
        // 防重复处理
        if (this.processingFiles.has(filePath)) {
            logger.info(`File ${filePath} is already being processed, skipping`);
            return;
        }

        this.processingFiles.add(filePath);
        
        try {
            logger.info(`Handling file download: ${filePath}, ${fileName}, ${mimeType}`);
            
            if (FileUtils.isImageFile(mimeType)) {
                // 图片文件：显示预览
                await this.showImagePreview(filePath, fileName, mimeType);
            } else {
                // 其他文件：下载
                await this.downloadFile(filePath, fileName);
            }
        } catch (error) {
            logger.error('Failed to handle file:', error);
            Toast.error('处理文件时发生错误');
        } finally {
            // 延迟移除处理状态，避免快速重复点击
            setTimeout(() => {
                this.processingFiles.delete(filePath);
            }, 2000);
        }
    }
}

// 导出单例实例
export const protocolHandler = ProtocolHandler.getInstance(); 