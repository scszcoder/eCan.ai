import React, { useEffect } from 'react';
import styled from '@emotion/styled';
import { IconClose, IconPlus, IconMinus, IconRotate } from '@douyinfe/semi-icons';
import { Button, Tooltip } from '@douyinfe/semi-ui';

const ModalOverlay = styled.div`
    position: fixed;
    top: 0;
    left: 0;
    right: 0;
    bottom: 0;
    background: rgba(0, 0, 0, 0.8);
    display: flex;
    align-items: center;
    justify-content: center;
    z-index: 9999;
    backdrop-filter: blur(4px);
`;

const ModalContent = styled.div`
    position: relative;
    max-width: 90vw;
    max-height: 90vh;
    display: flex;
    flex-direction: column;
    align-items: center;
    background: transparent;
`;

const ImageContainer = styled.div`
    position: relative;
    display: flex;
    align-items: center;
    justify-content: center;
    max-width: 100%;
    max-height: 100%;
    overflow: hidden;
    border-radius: 8px;
    box-shadow: 0 8px 32px rgba(0, 0, 0, 0.3);
`;

const StyledImage = styled.img<{ scale: number; rotation: number }>`
    max-width: 100%;
    max-height: 100%;
    object-fit: contain;
    transform: scale(${props => props.scale}) rotate(${props => props.rotation}deg);
    transition: transform 0.3s ease;
    cursor: grab;
    
    &:active {
        cursor: grabbing;
    }
`;

const ImageInfo = styled.div`
    position: absolute;
    bottom: -60px;
    left: 50%;
    transform: translateX(-50%);
    background: rgba(0, 0, 0, 0.7);
    color: white;
    padding: 8px 16px;
    border-radius: 20px;
    font-size: 14px;
    white-space: nowrap;
    backdrop-filter: blur(8px);
`;

const CloseButton = styled.div`
    position: absolute;
    top: -50px;
    right: 0;
    background: rgba(0, 0, 0, 0.7);
    border: none;
    color: white;
    border-radius: 50%;
    width: 40px;
    height: 40px;
    display: flex;
    align-items: center;
    justify-content: center;
    backdrop-filter: blur(8px);
    cursor: pointer;
    
    &:hover {
        background: rgba(0, 0, 0, 0.8);
        color: white;
    }
`;

const ControlButtons = styled.div`
    position: absolute;
    top: -50px;
    left: 0;
    display: flex;
    gap: 8px;
`;

const ControlButton = styled.div<{ disabled?: boolean }>`
    background: ${props => props.disabled ? 'rgba(0, 0, 0, 0.4)' : 'rgba(0, 0, 0, 0.7)'};
    border: none;
    color: ${props => props.disabled ? 'rgba(255, 255, 255, 0.5)' : 'white'};
    border-radius: 50%;
    width: 40px;
    height: 40px;
    display: flex;
    align-items: center;
    justify-content: center;
    backdrop-filter: blur(8px);
    cursor: ${props => props.disabled ? 'not-allowed' : 'pointer'};
    
    &:hover {
        background: ${props => props.disabled ? 'rgba(0, 0, 0, 0.4)' : 'rgba(0, 0, 0, 0.8)'};
        color: ${props => props.disabled ? 'rgba(255, 255, 255, 0.5)' : 'white'};
    }
`;

interface ImagePreviewModalProps {
    imageUrl: string;
    fileName: string;
    onClose: () => void;
}

export const ImagePreviewModal: React.FC<ImagePreviewModalProps> = ({
    imageUrl,
    fileName,
    onClose
}) => {
    const [scale, setScale] = React.useState(1);
    const [rotation, setRotation] = React.useState(0);
    const [isDragging, setIsDragging] = React.useState(false);
    const [dragStart, setDragStart] = React.useState({ x: 0, y: 0 });
    const [position, setPosition] = React.useState({ x: 0, y: 0 });

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
            }
        };

        window.addEventListener('keydown', handleKeyDown);
        return () => window.removeEventListener('keydown', handleKeyDown);
    }, [onClose]);

    // 鼠标滚轮缩放
    const handleWheel = (e: React.WheelEvent) => {
        e.preventDefault();
        if (e.deltaY < 0) {
            handleZoomIn();
        } else {
            handleZoomOut();
        }
    };

    const handleZoomIn = () => {
        setScale(prev => Math.min(prev * 1.2, 5));
    };

    const handleZoomOut = () => {
        setScale(prev => Math.max(prev / 1.2, 0.1));
    };

    const handleRotate = () => {
        setRotation(prev => (prev + 90) % 360);
    };

    const handleReset = () => {
        setScale(1);
        setRotation(0);
        setPosition({ x: 0, y: 0 });
    };

    const handleMouseDown = (e: React.MouseEvent) => {
        if (scale > 1) {
            setIsDragging(true);
            setDragStart({ x: e.clientX - position.x, y: e.clientY - position.y });
        }
    };

    const handleMouseMove = (e: React.MouseEvent) => {
        if (isDragging) {
            setPosition({
                x: e.clientX - dragStart.x,
                y: e.clientY - dragStart.y
            });
        }
    };

    const handleMouseUp = () => {
        setIsDragging(false);
    };

    const handleOverlayClick = (e: React.MouseEvent) => {
        if (e.target === e.currentTarget) {
            onClose();
        }
    };

    return (
        <ModalOverlay onClick={handleOverlayClick}>
            <ModalContent>
                <ImageContainer>
                    <StyledImage
                        src={imageUrl}
                        alt={fileName}
                        scale={scale}
                        rotation={rotation}
                        style={{
                            transform: `scale(${scale}) rotate(${rotation}deg) translate(${position.x}px, ${position.y}px)`
                        }}
                        onWheel={handleWheel}
                        onMouseDown={handleMouseDown}
                        onMouseMove={handleMouseMove}
                        onMouseUp={handleMouseUp}
                        onMouseLeave={handleMouseUp}
                        draggable={false}
                    />
                </ImageContainer>
                
                <ImageInfo>
                    {fileName} • {Math.round(scale * 100)}% • {rotation}°
                </ImageInfo>
                
                <CloseButton onClick={onClose}>
                    <IconClose size="large" />
                </CloseButton>
                
                <ControlButtons>
                    <Tooltip content="放大 (Ctrl + +)">
                        <ControlButton
                            onClick={handleZoomIn}
                            disabled={scale >= 5}
                        >
                            <IconPlus size="large" />
                        </ControlButton>
                    </Tooltip>
                    
                    <Tooltip content="缩小 (Ctrl + -)">
                        <ControlButton
                            onClick={handleZoomOut}
                            disabled={scale <= 0.1}
                        >
                            <IconMinus size="large" />
                        </ControlButton>
                    </Tooltip>
                    
                    <Tooltip content="旋转 (R)">
                        <ControlButton onClick={handleRotate}>
                            <IconRotate size="large" />
                        </ControlButton>
                    </Tooltip>
                    
                    <Tooltip content="重置">
                        <ControlButton onClick={handleReset}>
                            <span style={{ fontSize: '12px', fontWeight: 'bold' }}>R</span>
                        </ControlButton>
                    </Tooltip>
                </ControlButtons>
            </ModalContent>
        </ModalOverlay>
    );
};

export default ImagePreviewModal; 