import { FileUtils } from './fileUtils';
import { get_ipc_api } from '@/services/ipc_api';
import { logger } from '@/utils/logger';

// 根据文件TypeGet对应的图标
export const getFileTypeIcon = (fileName: string, mimeType: string): string => {
    const extension = fileName.split('.').pop()?.toLowerCase() || '';
    const type = mimeType.toLowerCase();
    
    // DocumentationType
    if (type.includes('pdf') || extension === 'pdf') return '📄';
    if (type.includes('word') || extension === 'doc' || extension === 'docx') return '📝';
    if (type.includes('excel') || extension === 'xls' || extension === 'xlsx') return '📊';
    if (type.includes('powerpoint') || extension === 'ppt' || extension === 'pptx') return '📈';
    if (type.includes('text') || extension === 'txt') return '📄';
    
    // Code文件
    if (type.includes('javascript') || extension === 'js') return '📜';
    if (type.includes('typescript') || extension === 'ts') return '📜';
    if (type.includes('python') || extension === 'py') return '🐍';
    if (type.includes('java') || extension === 'java') return '☕';
    if (type.includes('cpp') || extension === 'cpp' || extension === 'c') return '⚙️';
    if (type.includes('html') || extension === 'html' || extension === 'htm') return '🌐';
    if (type.includes('css') || extension === 'css') return '🎨';
    if (type.includes('json') || extension === 'json') return '📋';
    if (type.includes('xml') || extension === 'xml') return '📋';
    
    // 压缩文件
    if (type.includes('zip') || extension === 'zip') return '📦';
    if (type.includes('rar') || extension === 'rar') return '📦';
    if (type.includes('7z') || extension === '7z') return '📦';
    if (type.includes('tar') || extension === 'tar') return '📦';
    if (type.includes('gz') || extension === 'gz') return '📦';
    
    // 音频文件
    if (type.includes('audio') || ['mp3', 'wav', 'flac', 'aac', 'ogg'].includes(extension)) return '🎵';
    
    // 视频文件
    if (type.includes('video') || ['mp4', 'avi', 'mov', 'wmv', 'flv', 'mkv'].includes(extension)) return '🎬';
    
    // Default文件图标
    return '📎';
};

// 使用System原生文件SaveDialog下载文件
export const downloadFileWithNativeDialog = async (filePath: string, fileName: string, mimeType: string): Promise<void> => {
    try {
        // 直接使用完整的文件Path，让 FileUtils InternalProcessPathConvert
        const fileContent = await FileUtils.getFileContent(filePath);
        
        if (!fileContent || !fileContent.dataUrl) {
            throw new Error('Failed to get file content');
        }

        // 从 data URL Create Blob
        const base64Data = fileContent.dataUrl.split(',')[1];
        const binaryData = atob(base64Data);
        const bytes = new Uint8Array(binaryData.length);
        for (let i = 0; i < binaryData.length; i++) {
            bytes[i] = binaryData.charCodeAt(i);
        }
        
        const blob = new Blob([bytes], { type: mimeType });

        // 尝试使用 File System Access API（现代Browser）
        if ('showSaveFilePicker' in window) {
            try {
                const handle = await (window as any).showSaveFilePicker({
                    suggestedName: fileName,
                    types: [{
                        description: 'File',
                        accept: { [mimeType]: [`.${fileName.split('.').pop()}`] }
                    }]
                });
                
                const writable = await handle.createWritable();
                await writable.write(blob);
                await writable.close();
                return;
            } catch (e: any) {
                if (e.name === 'AbortError') {
                    console.log('User cancelled save operation');
                    return;
                }
                throw e;
            }
        }

        // 回退到传统的下载Method
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.style.display = 'none';
        a.href = url;
        a.download = fileName;
        document.body.appendChild(a);
        a.click();
        
        // Cleanup
        setTimeout(() => {
            document.body.removeChild(a);
            URL.revokeObjectURL(url);
        }, 100);

    } catch (error) {
        console.error('Native download failed', error);
        throw error;
    }
};

// Get文件上传ProcessConfiguration
export const getUploadProps = () => ({
    action: '', // Disabled HTTP 上传
    beforeUpload: () => true, // Must返回 true，Allow customRequest Execute
    customRequest: async (options: any) => {
        const { file, onSuccess, onError } = options;
        try {
            // Compatible更多 UI 上传Component的 file 结构，优先用 fileInstance
            let realFile = null;
            if (file.fileInstance instanceof Blob) {
                realFile = file.fileInstance;
            } else if (file.originFileObj instanceof Blob) {
                realFile = file.originFileObj;
            } else if (file instanceof Blob) {
                realFile = file;
            } else if (file.raw instanceof Blob) {
                realFile = file.raw;
            } else {
                for (const key in file) {
                    if (file[key] instanceof Blob) {
                        realFile = file[key];
                        break;
                    }
                }
            }
            if (!realFile) {
                console.error('[uploadProps] Not a Blob/File:', file);
                onError(new Error('Failed to get file content'), file);
                return;
            }
            
            // 优先从 realFile Get type、name、size
            const fileType = realFile.type || file.type || '';
            const fileName = realFile.name || file.name || '';
            const fileSize = realFile.size || file.size || 0;
            
            const reader = new FileReader();
            reader.onload = async (e) => {
                const fileData = e.target?.result;
                if (!fileData) {
                    console.error('[uploadProps] FileReader failed');
                    onError(new Error('Failed to get file content'), file);
                    return;
                }
                const api = get_ipc_api();
                const resp = await api.chatApi.uploadAttachment({
                    name: fileName,
                    type: fileType,
                    size: fileSize,
                    data: fileData as string, // base64 字符串
                });
                logger.debug('[uploadProps] uploadAttachment resp:', resp);
                if (resp.success) {
                    const data: any = resp.data;
                    
                    // 直接使用返回的 URL，不Add协议前缀
                    const filePath = data.url || '';
                    
                    // 只传递可Serialize的 attachment Field，避免 circular JSON
                    const safeAttachment = {
                        name: data.name || file.name || 'unknown',
                        type: data.type || file.type || 'application/octet-stream',
                        size: data.size || file.size || 0,
                        url: filePath, // 直接使用返回的 URL
                        filePath: filePath, // Save文件Path
                        mimeType: data.type || file.type || 'application/octet-stream',
                        isImage: FileUtils.isImageFile(data.type || file.type || ''),
                        status: 'complete',
                        uid: data.uid || file.uid || ('' + Date.now())
                    };
                    
                    onSuccess(safeAttachment, file);
                } else {
                    logger.error('[uploadProps] Attachment upload error:', resp.error);
                    onError(resp.error, file);
                }
            };
            reader.onerror = (e) => {
                console.error('[uploadProps] FileReader onerror', e);
                onError(new Error('FileReader error'), file);
            };
            
            reader.readAsDataURL(realFile);
        } catch (err) {
            console.error('[uploadProps] customRequest catch', err);
            onError(err, file);
        }
    },
}); 