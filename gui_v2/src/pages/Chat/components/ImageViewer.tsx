import React, { useState, useRef, useEffect, useCallback, memo, useMemo } from 'react';
import styled from '@emotion/styled';
import { useTranslation } from 'react-i18next';
import { Button } from '@douyinfe/semi-ui';
import { 
    IconExpand, 
    IconShrink, 
    IconRotate, 
    IconDownload, 
    IconClose,
    IconMaximize,
    IconMinimize,
    IconRefresh
} from '@douyinfe/semi-icons';

const ImageViewerOverlay = styled.div`
    position: fixed;
    top: 0;
    left: 0;
    width: 100%;
    height: 100%;
    background: rgba(0, 0, 0, 0.9);
    display: flex;
    align-items: center;
    justify-content: center;
    z-index: 9999;
    cursor: default;
`;

const ImageContainer = styled.div<{ scale: number; rotation: number }>`
    position: relative;
    max-width: 80%;
    max-height: 80%;
    transform: scale(${props => props.scale}) rotate(${props => props.rotation}deg);
    transition: transform 0.3s ease;
    cursor: grab;
    
    &:active {
        cursor: grabbing;
    }
`;

const Image = styled.img`
    max-width: 100%;
    max-height: 100%;
    object-fit: contain;
    border-radius: 8px;
    box-shadow: 0 4px 20px rgba(0, 0, 0, 0.3);
    user-select: none;
    -webkit-user-drag: none;
`;

const Toolbar = styled.div`
    position: absolute;
    right: 20px;
    top: 50%;
    transform: translateY(-50%);
    display: flex;
    flex-direction: column;
    gap: 8px;
    background: rgba(0, 0, 0, 0.8);
    padding: 12px;
    border-radius: 12px;
    backdrop-filter: blur(10px);
    border: 1px solid rgba(255, 255, 255, 0.2);
    box-shadow: 0 4px 20px rgba(0, 0, 0, 0.3);
`;

const ToolbarColumn = styled.div`
    display: flex;
    flex-direction: column;
    gap: 8px;
`;

const ToolbarRow = styled.div`
    display: flex;
    gap: 8px;
`;

const CloseButton = styled.button`
    position: absolute;
    top: 20px;
    right: 20px;
    background: rgba(0, 0, 0, 0.7);
    border: none;
    border-radius: 50%;
    width: 40px;
    height: 40px;
    display: flex;
    align-items: center;
    justify-content: center;
    cursor: pointer;
    color: white;
    font-size: 18px;
    backdrop-filter: blur(10px);
    border: 1px solid rgba(255, 255, 255, 0.1);
    transition: all 0.2s ease;
    
    &:hover {
        background: rgba(255, 255, 255, 0.1);
        transform: scale(1.1);
    }
`;

const ImageInfo = styled.div`
    position: absolute;
    bottom: 20px;
    left: 20px;
    background: rgba(0, 0, 0, 0.7);
    color: white;
    padding: 8px 12px;
    border-radius: 8px;
    font-size: 14px;
    backdrop-filter: blur(10px);
    border: 1px solid rgba(255, 255, 255, 0.1);
`;

const ZoomInfo = styled.div`
    position: absolute;
    top: 20px;
    left: 20px;
    background: rgba(0, 0, 0, 0.7);
    color: white;
    padding: 8px 12px;
    border-radius: 8px;
    font-size: 14px;
    backdrop-filter: blur(10px);
    border: 1px solid rgba(255, 255, 255, 0.1);
`;

interface ImageViewerProps {
    imageUrl: string;
    fileName: string;
    filePath: string;
    mimeType: string;
    onClose: () => void;
}

const ImageViewer: React.FC<ImageViewerProps> = memo(({ 
    imageUrl, 
    fileName, 
    filePath, 
    mimeType, 
    onClose 
}) => {
    const { t } = useTranslation();
    const [scale, setScale] = useState(1);
    const [rotation, setRotation] = useState(0);
    const [isDragging, setIsDragging] = useState(false);
    const [dragStart, setDragStart] = useState({ x: 0, y: 0 });
    const [position, setPosition] = useState({ x: 0, y: 0 });
    const [isFullscreen, setIsFullscreen] = useState(false);
    const imageRef = useRef<HTMLImageElement>(null);
    const containerRef = useRef<HTMLDivElement>(null);

    // Scale功能
    const handleZoomIn = useCallback(() => {
        setScale(prev => Math.min(prev * 1.2, 5));
    }, []);

    const handleZoomOut = useCallback(() => {
        setScale(prev => Math.max(prev / 1.2, 0.1));
    }, []);

    // Rotate功能
    const handleRotate = useCallback(() => {
        setRotation(prev => (prev + 90) % 360);
    }, []);

    // Reset功能
    const handleReset = useCallback(() => {
        setScale(1);
        setRotation(0);
        setPosition({ x: 0, y: 0 });
    }, []);

    // 全屏功能
    const handleToggleFullscreen = useCallback(() => {
        if (!document.fullscreenElement) {
            containerRef.current?.requestFullscreen();
            setIsFullscreen(true);
        } else {
            document.exitFullscreen();
            setIsFullscreen(false);
        }
    }, []);

    // 键盘快捷键
    useEffect(() => {
        const handleKeyDown = (e: KeyboardEvent) => {
            switch (e.key) {
                case 'Escape':
                    onClose();
                    break;
                case '+':
                case '=':
                    e.preventDefault();
                    handleZoomIn();
                    break;
                case '-':
                    e.preventDefault();
                    handleZoomOut();
                    break;
                case 'r':
                    e.preventDefault();
                    handleRotate();
                    break;
                case 'f':
                    e.preventDefault();
                    handleToggleFullscreen();
                    break;
                case '0':
                    e.preventDefault();
                    handleReset();
                    break;
            }
        };

        document.addEventListener('keydown', handleKeyDown);
        return () => document.removeEventListener('keydown', handleKeyDown);
    }, [onClose, handleZoomIn, handleZoomOut, handleRotate, handleToggleFullscreen, handleReset]);

    // 鼠标滚轮Scale
    const handleWheel = useCallback((e: WheelEvent) => {
        e.preventDefault();
        if (e.deltaY < 0) {
            setScale(prev => Math.min(prev * 1.2, 5));
        } else {
            setScale(prev => Math.max(prev / 1.2, 0.1));
        }
    }, []);

    useEffect(() => {
        const container = containerRef.current;
        if (container) {
            container.addEventListener('wheel', handleWheel, { passive: false });
            return () => container.removeEventListener('wheel', handleWheel);
        }
    }, [handleWheel]);

    // 鼠标Drag
    const handleMouseDown = useCallback((e: React.MouseEvent) => {
        if (e.button === 0) { // 左键
            setIsDragging(true);
            setDragStart({ x: e.clientX - position.x, y: e.clientY - position.y });
        }
    }, [position.x, position.y]);

    const handleMouseMove = useCallback((e: React.MouseEvent) => {
        if (isDragging) {
            setPosition({
                x: e.clientX - dragStart.x,
                y: e.clientY - dragStart.y
            });
        }
    }, [isDragging, dragStart.x, dragStart.y]);

    const handleMouseUp = useCallback(() => {
        setIsDragging(false);
    }, []);

    // Tool栏ClickEventProcess
    const handleToolbarClick = useCallback((e: React.MouseEvent) => {
        e.stopPropagation();
    }, []);

    // 图片ContainerClickEventProcess
    const handleImageContainerClick = useCallback((e: React.MouseEvent) => {
        e.stopPropagation();
    }, []);

    // 下载功能
    const handleDownload = useCallback(async () => {
        try {
            // If imageUrl 已经是 data URL，直接使用
            if (imageUrl.startsWith('data:')) {
                // 从 data URL Create Blob
                const base64Data = imageUrl.split(',')[1];
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
                                description: 'Image File',
                                accept: { [mimeType]: [`.${fileName.split('.').pop()}`] }
                            }]
                        });
                        
                        const writable = await handle.createWritable();
                        await writable.write(blob);
                        await writable.close();
                        return;
                    } catch (e: any) {
                        if (e.name === 'AbortError') {
                            console.log(t('pages.chat.userCancelledSave'));
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
            } else {
                // If是Network图片，直接下载
                const a = document.createElement('a');
                a.style.display = 'none';
                a.href = imageUrl;
                a.download = fileName;
                document.body.appendChild(a);
                a.click();
                
                // Cleanup
                setTimeout(() => {
                    document.body.removeChild(a);
                }, 100);
            }

        } catch (error) {
            console.error(t('pages.chat.nativeDownloadFailed'), error);
        }
    }, [imageUrl, fileName, mimeType, t]);

    return (
        <ImageViewerOverlay onClick={onClose}>
            <ImageContainer
                ref={containerRef}
                scale={scale}
                rotation={rotation}
                style={{
                    transform: `scale(${scale}) rotate(${rotation}deg) translate(${position.x}px, ${position.y}px)`
                }}
                onMouseDown={handleMouseDown}
                onMouseMove={handleMouseMove}
                onMouseUp={handleMouseUp}
                onMouseLeave={handleMouseUp}
                onClick={handleImageContainerClick}
            >
                <Image
                    ref={imageRef}
                    src={imageUrl}
                    alt={fileName}
                    draggable={false}
                />
            </ImageContainer>

            {/* CloseButton */}
            <CloseButton onClick={onClose}>
                <IconClose />
            </CloseButton>

            {/* Tool栏 */}
            <Toolbar onClick={handleToolbarClick}>
                <ToolbarRow>
                    <Button
                        icon={<IconExpand />}
                        type="tertiary"
                        theme="borderless"
                        onClick={handleZoomIn}
                        title={t('pages.chat.zoomIn')}
                        style={{ 
                            color: 'white', 
                            background: 'rgba(255, 255, 255, 0.1)',
                            border: '1px solid rgba(255, 255, 255, 0.2)',
                            transition: 'all 0.2s ease'
                        }}
                    />
                    <Button
                        icon={<IconShrink />}
                        type="tertiary"
                        theme="borderless"
                        onClick={handleZoomOut}
                        title={t('pages.chat.zoomOut')}
                        style={{ 
                            color: 'white', 
                            background: 'rgba(255, 255, 255, 0.1)',
                            border: '1px solid rgba(255, 255, 255, 0.2)',
                            transition: 'all 0.2s ease'
                        }}
                    />
                </ToolbarRow>
                
                <ToolbarRow>
                    <Button
                        icon={<IconRotate />}
                        type="tertiary"
                        theme="borderless"
                        onClick={handleRotate}
                        title={t('pages.chat.rotate')}
                        style={{ 
                            color: 'white', 
                            background: 'rgba(255, 255, 255, 0.1)',
                            border: '1px solid rgba(255, 255, 255, 0.2)',
                            transition: 'all 0.2s ease'
                        }}
                    />
                    <Button
                        icon={<IconRefresh />}
                        type="tertiary"
                        theme="borderless"
                        onClick={handleReset}
                        title={t('pages.chat.reset')}
                        style={{ 
                            color: 'white', 
                            background: 'rgba(255, 255, 255, 0.1)',
                            border: '1px solid rgba(255, 255, 255, 0.2)',
                            transition: 'all 0.2s ease'
                        }}
                    />
                </ToolbarRow>

                <ToolbarRow>
                    <Button
                        icon={isFullscreen ? <IconMinimize /> : <IconMaximize />}
                        type="tertiary"
                        theme="borderless"
                        onClick={handleToggleFullscreen}
                        title={t('pages.chat.fullscreen')}
                        style={{ 
                            color: 'white', 
                            background: 'rgba(255, 255, 255, 0.1)',
                            border: '1px solid rgba(255, 255, 255, 0.2)',
                            transition: 'all 0.2s ease'
                        }}
                    />
                    <Button
                        icon={<IconDownload />}
                        type="tertiary"
                        theme="borderless"
                        onClick={handleDownload}
                        title={t('pages.chat.download')}
                        style={{ 
                            color: 'white', 
                            background: 'rgba(255, 255, 255, 0.1)',
                            border: '1px solid rgba(255, 255, 255, 0.2)',
                            transition: 'all 0.2s ease'
                        }}
                    />
                </ToolbarRow>
            </Toolbar>

            {/* ScaleInformation */}
            <ZoomInfo>
                {Math.round(scale * 100)}% | {rotation}°
            </ZoomInfo>

            {/* 图片Information */}
            <ImageInfo>
                {fileName} ({mimeType})
            </ImageInfo>
        </ImageViewerOverlay>
    );
});

export default ImageViewer; 