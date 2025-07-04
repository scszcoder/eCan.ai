import React, { useMemo, useCallback } from 'react';
import { useTranslation } from 'react-i18next';
import ImagePreview from './ImagePreview';
import { getFileTypeIcon, downloadFileWithNativeDialog } from '../utils/attachmentHandler';
import { protocolHandler } from '../utils/protocolHandler';

// 定义样式对象，提高重用性和一致性
const styles = {
    container: {
        display: 'flex', 
        flexDirection: 'column' as const, 
        gap: '8px',
        wordBreak: 'break-word' as const,
        whiteSpace: 'pre-wrap' as const,
        maxWidth: '100%',
        overflow: 'hidden',
        color: '#ffffff'
    },
    text: {
        whiteSpace: 'pre-wrap' as const,
        color: '#ffffff'
    },
    imageContainer: {
        display: 'flex', 
        flexDirection: 'column' as const, 
        alignItems: 'center',
        gap: '8px',
        maxWidth: '150px',
        overflow: 'hidden'
    },
    attachmentName: {
        fontSize: '12px', 
        textAlign: 'center' as const,
        maxWidth: '100%',
        overflow: 'hidden',
        textOverflow: 'ellipsis',
        whiteSpace: 'nowrap' as const,
        color: '#ffffff'
    },
    fileContainer: {
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
    },
    fileIcon: {
        fontSize: '16px',
        color: 'var(--semi-color-primary)',
        flexShrink: 0
    },
    fileName: {
        fontSize: '13px',
        color: '#ffffff',
        overflow: 'hidden',
        textOverflow: 'ellipsis',
        whiteSpace: 'nowrap' as const,
        flex: 1,
        minWidth: 0
    },
    downloadIcon: {
        fontSize: '12px',
        color: 'var(--semi-color-text-2)',
        flexShrink: 0
    }
};

// 提取可重用组件：文本部分
const TextContent: React.FC<{ text: string }> = React.memo(({ text }) => {
    if (!text.trim()) return null;
    return (
        <span style={styles.text}>
            {text}
        </span>
    );
});

// 提取可重用组件：图片附件
const ImageAttachment: React.FC<{
    filePath: string;
    fileName: string;
    mimeType: string;
}> = React.memo(({ filePath, fileName, mimeType }) => {
    return (
        <div
            className="custom-attachment custom-attachment-image"
        >
            <div style={styles.imageContainer}>
                <ImagePreview 
                    filePath={filePath}
                    fileName={fileName}
                    mimeType={mimeType}
                />
                <span className="attachment-name" style={styles.attachmentName}>
                    {fileName}
                </span>
            </div>
        </div>
    );
});

// 提取可重用组件：文件附件
const FileAttachment: React.FC<{
    filePath: string;
    fileName: string;
    mimeType: string;
    onClick: (filePath: string, fileName: string, mimeType: string, isImage: boolean) => void;
}> = React.memo(({ filePath, fileName, mimeType, onClick }) => {
    return (
        <div
            className="custom-attachment custom-attachment-file"
            onClick={() => onClick(filePath, fileName, mimeType, false)}
            title={`${fileName} (${mimeType})`}
        >
            <div style={styles.fileContainer}>
                <span className="attachment-icon" style={styles.fileIcon}>
                    {getFileTypeIcon(fileName, mimeType)}
                </span>
                <span className="attachment-name" style={styles.fileName}>
                    {fileName}
                </span>
                <span style={styles.downloadIcon}>
                    ⬇️
                </span>
            </div>
        </div>
    );
});

interface CustomContentRendererProps {
    content: string;
}

const CustomContentRenderer: React.FC<CustomContentRendererProps> = ({ content }) => {
    const { t } = useTranslation();

    // 使用 useCallback 优化事件处理
    const handleAttachmentClick = useCallback(async (
        filePath: string, 
        fileName: string, 
        mimeType: string, 
        isImage: boolean
    ) => {
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
    }, [t]);

    // 使用 useMemo 优化内容解析，防止重复渲染时重新计算
    const renderedContent = useMemo(() => {
        if (!content) return null;

        const parts: JSX.Element[] = [];
        let currentIndex = 0;
        
        // 使用正则表达式匹配附件标记：[类型|文件路径|文件名|MIME类型]
        const attachmentRegex = /\[(image|file)\|([^|]+)\|([^|]+)\|([^\]]+)\]/g;
        let match;
        
        while ((match = attachmentRegex.exec(content)) !== null) {
            const [fullMatch, type, filePath, fileName, mimeType] = match;
            const isImage = type === 'image';
            
            // 添加附件前的文本
            if (match.index > currentIndex) {
                const textBefore = content.slice(currentIndex, match.index);
                parts.push(
                    <TextContent 
                        key={`text-${currentIndex}`} 
                        text={textBefore}
                    />
                );
            }
            
            // 添加附件组件
            if (isImage) {
                parts.push(
                    <ImageAttachment
                        key={`attachment-${match.index}`}
                        filePath={filePath}
                        fileName={fileName}
                        mimeType={mimeType}
                    />
                );
            } else {
                parts.push(
                    <FileAttachment
                        key={`attachment-${match.index}`}
                        filePath={filePath}
                        fileName={fileName}
                        mimeType={mimeType}
                        onClick={handleAttachmentClick}
                    />
                );
            }
            
            currentIndex = match.index + fullMatch.length;
        }
        
        // 添加剩余的文本
        if (currentIndex < content.length) {
            const remainingText = content.slice(currentIndex);
            parts.push(
                <TextContent 
                    key={`text-${currentIndex}`} 
                    text={remainingText}
                />
            );
        }
        
        return parts.length > 0 ? parts : <span style={styles.text}>{content}</span>;
    }, [content, handleAttachmentClick]);

    return (
        <div style={styles.container}>
            {renderedContent}
        </div>
    );
};

export default React.memo(CustomContentRenderer); 