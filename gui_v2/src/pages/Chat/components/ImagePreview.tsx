import React, { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { FileUtils } from '../utils/fileUtils';
import { protocolHandler } from '../utils/protocolHandler';

interface ImagePreviewProps {
    filePath: string;
    fileName: string;
    mimeType: string;
}

const ImagePreview: React.FC<ImagePreviewProps> = ({ 
    filePath, 
    fileName, 
    mimeType 
}) => {
    const { t } = useTranslation();
    const [imageUrl, setImageUrl] = useState<string>('');
    const [isLoading, setIsLoading] = useState(true);
    const [hasError, setHasError] = useState(false);

    useEffect(() => {
        const loadImage = async () => {
            console.log('[ImagePreview] Loading image with filePath:', filePath);
            
            if (!filePath.startsWith('pyqtfile://')) {
                console.log('[ImagePreview] Not a pyqtfile, using as direct URL');
                setImageUrl(filePath);
                setIsLoading(false);
                return;
            }

            try {
                setIsLoading(true);
                setHasError(false);
                
                console.log('[ImagePreview] Calling FileUtils.getFileThumbnail with:', filePath);
                // 直接使用完整的文件Path，让 FileUtils InternalProcessPathConvert
                const dataUrl = await FileUtils.getFileThumbnail(filePath);
                
                if (dataUrl) {
                    setImageUrl(dataUrl);
                } else {
                    console.log('[ImagePreview] No dataUrl returned');
                    setHasError(true);
                }
            } catch (error) {
                console.error('[ImagePreview] Failed to load pyqtfile image:', error);
                setHasError(true);
            } finally {
                setIsLoading(false);
            }
        };

        loadImage();
    }, [filePath]);

    const handleClick = () => {
        // 直接使用完整的文件Path（Include协议）
        protocolHandler.handleFile(filePath, fileName, mimeType);
    };

    if (isLoading) {
        return (
            <div style={{
                width: '120px',
                height: '80px',
                backgroundColor: 'var(--semi-color-fill-0)',
                borderRadius: '8px',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                border: '1px solid var(--semi-color-border)',
                fontSize: '12px',
                color: 'var(--semi-color-text-2)'
            }}>
                {t('pages.chat.loading')}
            </div>
        );
    }

    if (hasError) {
        return (
            <div 
                style={{
                    width: '120px',
                    height: '80px',
                    backgroundColor: 'var(--semi-color-fill-0)',
                    borderRadius: '8px',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    border: '1px solid var(--semi-color-border)',
                    cursor: 'pointer',
                    fontSize: '12px',
                    color: 'var(--semi-color-text-2)'
                }}
                onClick={handleClick}
            >
                {t('pages.chat.clickToView')}
            </div>
        );
    }

    return (
        <div 
            style={{
                width: '120px',
                height: '80px',
                borderRadius: '8px',
                border: '1px solid var(--semi-color-border)',
                overflow: 'hidden',
                cursor: 'pointer',
                backgroundColor: 'var(--semi-color-fill-0)'
            }}
            onClick={handleClick}
        >
            <img 
                src={imageUrl} 
                alt={fileName}
                style={{
                    width: '100%',
                    height: '100%',
                    objectFit: 'cover'
                }}
            />
        </div>
    );
};

export default ImagePreview; 