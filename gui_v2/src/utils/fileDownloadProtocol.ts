/**
 * 简化的文件下载协议处理器
 * 拦截 #download: 链接并通过 IPC 调用后端下载文件
 */

import { message as antMessage } from 'antd';

export interface DownloadHandler {
  downloadFile: (fileName: string) => Promise<{ filePath: string; fileName: string }>;
  t: (key: string, options?: any) => string; // i18n translate function
}

class FileDownloadProtocol {
  private static instance: FileDownloadProtocol;
  private downloadHandler: DownloadHandler | null = null;
  private isInitialized = false;

  private constructor() {}

  public static getInstance(): FileDownloadProtocol {
    if (!FileDownloadProtocol.instance) {
      FileDownloadProtocol.instance = new FileDownloadProtocol();
    }
    return FileDownloadProtocol.instance;
  }

  /**
   * 设置下载处理器
   */
  public setDownloadHandler(handler: DownloadHandler): void {
    this.downloadHandler = handler;
  }

  /**
   * 初始化协议处理器
   */
  public init(): void {
    if (this.isInitialized) {
      return;
    }

    document.addEventListener('click', this.handleClick.bind(this), true);
    this.isInitialized = true;
  }

  /**
   * 清理协议处理器
   */
  public cleanup(): void {
    if (!this.isInitialized) {
      return;
    }

    document.removeEventListener('click', this.handleClick.bind(this), true);
    this.isInitialized = false;
  }

  /**
   * 处理点击事件
   */
  private async handleClick(e: MouseEvent): Promise<void> {
    const target = e.target as HTMLElement;
    const link = target.closest('a');
    
    if (!link) return;

    const href = link.getAttribute('href') || '';
    
    // 检查是否是 #download: 格式的链接
    if (href.startsWith('#download:')) {
      e.preventDefault();
      e.stopPropagation();
      
      const filePath = decodeURIComponent(href.replace('#download:', ''));
      await this.handleDownload(filePath);
    }
  }

  /**
   * 处理下载请求
   */
  private async handleDownload(filePath: string): Promise<void> {
    try {
      // 提取文件名（去掉路径部分）
      const fileName = filePath.split('/').pop() || filePath;
      
      if (!this.downloadHandler) {
        throw new Error('Download handler not initialized');
      }
      
      const { t } = this.downloadHandler;
      
      antMessage.loading({ content: t('pages.knowledge.retrieval.downloading', { fileName }), key: 'file-download' });
      
      // 通过 IPC 调用后端下载文件
      const result = await this.downloadHandler.downloadFile(fileName);
      
      antMessage.success({ 
        content: t('pages.knowledge.retrieval.downloadSuccess', { filePath: result.filePath }), 
        key: 'file-download',
        duration: 3
      });
    } catch (err: any) {
      console.error('[FileDownloadProtocol] Download error:', err);
      const t = this.downloadHandler?.t;
      antMessage.error({ 
        content: t ? t('pages.knowledge.retrieval.downloadFailed', { error: err.message }) : `Download failed: ${err.message}`, 
        key: 'file-download' 
      });
    }
  }
}

// 导出单例
export const fileDownloadProtocol = FileDownloadProtocol.getInstance();
