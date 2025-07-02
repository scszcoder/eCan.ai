import React from 'react';
import { useTranslation } from 'react-i18next';
import ImagePreview from './ImagePreview';
import { getFileTypeIcon, downloadFileWithNativeDialog } from '../utils/attachmentHandler';
import { protocolHandler } from '../utils/protocolHandler';

interface CustomContentRendererProps {
    content: string;
}

const CustomContentRenderer: React.FC<CustomContentRendererProps> = ({ content }) => {
    const { t } = useTranslation();

    const handleAttachmentClick = async (filePath: string, fileName: string, mimeType: string, isImage: boolean) => {
        if (isImage) {
            // 图片点击时预览
            protocolHandler.handleFile(filePath, fileName, mimeType);
        } else {
            // 文件点击时下载，使用系统原生保存对话框
            try {
                await downloadFileWithNativeDialog(filePath, fileName, mimeType);
            } catch (error) {
                console.error(t('pages.chat.failedToDownloadFile'), error);
                // 回退到原来的方法
                protocolHandler.handleFile(filePath, fileName, mimeType);
            }
        }
    };

    // 解析内容中的附件标记
    const renderContent = () => {
        if (!content) return null;

        const parts = [];
        let currentIndex = 0;
        
        // 使用简单的字符串分割方法来解析附件标记
        // 格式: [类型|文件路径|文件名|MIME类型]
        const attachmentRegex = /\[(image|file)\|([^|]+)\|([^|]+)\|([^\]]+)\]/g;
        let match;
        
        while ((match = attachmentRegex.exec(content)) !== null) {
            const [fullMatch, type, filePath, fileName, mimeType] = match;
            const isImage = type === 'image';
            
            // 添加附件前的文本
            if (match.index > currentIndex) {
                const textBefore = content.slice(currentIndex, match.index);
                if (textBefore.trim()) {
                    parts.push(
                        <span key={`text-${currentIndex}`} style={{ 
                            whiteSpace: 'pre-wrap',
                            color: '#ffffff' // 设置文本为白色
                        }}>
                            {textBefore}
                        </span>
                    );
                }
            }
            
            // 添加附件组件
            if (isImage) {
                // 图片显示预览图
                parts.push(
                    <div
                        key={`attachment-${match.index}`}
                        className="custom-attachment custom-attachment-image"
                    >
                        <div style={{ 
                            display: 'flex', 
                            flexDirection: 'column', 
                            alignItems: 'center',
                            gap: '8px',
                            maxWidth: '150px',
                            overflow: 'hidden'
                        }}>
                            <ImagePreview 
                                filePath={filePath}
                                fileName={fileName}
                                mimeType={mimeType}
                            />
                            <span className="attachment-name" style={{ 
                                fontSize: '12px', 
                                textAlign: 'center',
                                maxWidth: '100%',
                                overflow: 'hidden',
                                textOverflow: 'ellipsis',
                                whiteSpace: 'nowrap',
                                color: '#ffffff' // 设置附件名称为白色
                            }}>
                                {fileName}
                            </span>
                        </div>
                    </div>
                );
            } else {
                // 文件显示下载图标
                parts.push(
                    <div
                        key={`attachment-${match.index}`}
                        className="custom-attachment custom-attachment-file"
                        onClick={() => handleAttachmentClick(filePath, fileName, mimeType, false)}
                        title={`${fileName} (${mimeType})`}
                    >
                        <div style={{ 
                            display: 'flex', 
                            alignItems: 'center', 
                            gap: '8px',
                            padding: '6px 10px',
                            backgroundColor: 'var(--semi-color-fill-0)',
                            borderRadius: '6px',
                            border: '1px solid var(--semi-color-border)',
                            cursor: 'pointer',
                            transition: 'all 0.2s ease',
                            maxWidth: '300px',
                            minWidth: '120px',
                            overflow: 'hidden'
                        }}>
                            <span className="attachment-icon" style={{ 
                                fontSize: '16px',
                                color: 'var(--semi-color-primary)',
                                flexShrink: 0
                            }}>
                                {getFileTypeIcon(fileName, mimeType)}
                            </span>
                            <span className="attachment-name" style={{ 
                                fontSize: '13px',
                                color: '#ffffff', // 设置文件附件名称为白色
                                overflow: 'hidden',
                                textOverflow: 'ellipsis',
                                whiteSpace: 'nowrap',
                                flex: 1,
                                minWidth: 0
                            }}>
                                {fileName}
                            </span>
                            <span style={{ 
                                fontSize: '12px',
                                color: 'var(--semi-color-text-2)',
                                flexShrink: 0
                            }}>
                                ⬇️
                            </span>
                        </div>
                    </div>
                );
            }
            
            currentIndex = match.index + fullMatch.length;
        }
        
        // 添加剩余的文本
        if (currentIndex < content.length) {
            const remainingText = content.slice(currentIndex);
            if (remainingText.trim()) {
                parts.push(
                    <span key={`text-${currentIndex}`} style={{ 
                        whiteSpace: 'pre-wrap',
                        color: '#ffffff' // 设置剩余文本为白色
                    }}>
                        {remainingText}
                    </span>
                );
            }
        }
        
        return parts.length > 0 ? parts : <span style={{ color: '#ffffff' }}>{content}</span>;
    };

    return (
        <div style={{ 
            display: 'flex', 
            flexDirection: 'column', 
            gap: '8px',
            wordBreak: 'break-word',
            whiteSpace: 'pre-wrap',
            maxWidth: '100%',
            overflow: 'hidden',
            color: '#ffffff' // 设置整体文本颜色为白色
        }}>
            {renderContent()}
        </div>
    );
};

export default CustomContentRenderer; 