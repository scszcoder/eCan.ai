import React from 'react';
import { createRoot } from 'react-dom/client';
import ImagePreviewModal from '../components/ImagePreviewModal';

/**
 * 图片预览管理器
 * 用于在当前页面显示图片预览模态窗口
 */
export class ImagePreviewManager {
    private static modalContainer: HTMLDivElement | null = null;
    private static root: any = null;

    /**
     * 显示图片预览
     * @param imageUrl 图片 URL
     * @param fileName 文件名
     */
    static showImagePreview(imageUrl: string, fileName: string): void {
        // 创建模态容器
        if (!this.modalContainer) {
            this.modalContainer = document.createElement('div');
            this.modalContainer.id = 'image-preview-modal-container';
            document.body.appendChild(this.modalContainer);
            this.root = createRoot(this.modalContainer);
        }

        // 渲染模态组件
        this.root.render(
            React.createElement(ImagePreviewModal, {
                imageUrl,
                fileName,
                onClose: () => this.hideImagePreview()
            })
        );
    }

    /**
     * 隐藏图片预览
     */
    static hideImagePreview(): void {
        if (this.root) {
            this.root.unmount();
            this.root = null;
        }
    }

    /**
     * 清理资源
     */
    static cleanup(): void {
        this.hideImagePreview();
        if (this.modalContainer && this.modalContainer.parentNode) {
            this.modalContainer.parentNode.removeChild(this.modalContainer);
            this.modalContainer = null;
        }
    }
} 