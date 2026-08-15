import React, { useEffect, useMemo, useRef, useState } from 'react';
import { Card } from 'antd';
import styled from '@emotion/styled';
import { keyframes } from '@emotion/react';
import { useEffectOnActive } from 'keepalive-for-react';

const Container = styled.div<{ $resizable?: boolean }>`
    display: flex;
    gap: ${props => (props.$resizable ? '0' : '16px')};
    height: 100%;
`;

const ListCard = styled(Card)`
    height: 100%;
    display: flex;
    flex-direction: column;
    .ant-card-head {
        flex-shrink: 0;
    }
    .ant-card-body {
        flex: 1 1 0;
        min-height: 0;
        overflow-x: hidden;
        overflow-y: auto;
        max-height: 100%;
        display: flex;
        flex-direction: column;
        padding: 0 !important;
    }
    .ant-card-head-title {
        color: white;
    }
`;

const Splitter = styled.div`
    width: 10px;
    cursor: col-resize;
    flex: 0 0 auto;
    position: relative;
    user-select: none;
    background: transparent;

    &::before {
        content: '';
        position: absolute;
        left: 50%;
        top: 8px;
        transform: translateX(-50%);
        width: 3px;
        height: calc(100% - 16px);
        border-radius: 2px;
        background: rgba(255, 255, 255, 0.06);
        transition: background 0.15s ease;
    }

    &:hover::before {
        background: rgba(59, 130, 246, 0.45);
    }
`;

const detailsSlideIn = keyframes`
    from {
        opacity: 0;
        transform: translateX(16px);
    }
    to {
        opacity: 1;
        transform: translateX(0);
    }
`;

const DetailsCard = styled(Card, {
    shouldForwardProp: (prop) => prop !== '$fillAvailableWidth',
})<{ $fillAvailableWidth?: boolean }>`
    flex: ${props => props.$fillAvailableWidth ? '1 1 0' : '0 0 480px'};
    min-width: ${props => props.$fillAvailableWidth ? '0' : '400px'};
    max-width: ${props => props.$fillAvailableWidth ? 'none' : '520px'};
    height: 100%;
    display: flex;
    flex-direction: column;
    animation: ${detailsSlideIn} 0.24s ease-out;
    .ant-card-head {
        flex-shrink: 0;
    }
    .ant-card-body {
        flex: 1 1 0;
        min-height: 0;
        overflow: hidden;
        display: flex;
        flex-direction: column;
        padding: 0 !important;
    }
    .ant-card-head-title {
        color: white;
    }
`;

interface DetailLayoutProps {
    listTitle: React.ReactNode;
    detailsTitle: string;
    listContent: React.ReactNode;
    detailsContent: React.ReactNode;

    resizableList?: boolean;
    listWidthStorageKey?: string;
    defaultListWidth?: number;
    minListWidth?: number;
    maxListWidth?: number;
    fillListAvailableWidth?: boolean;
    fillDetailsAvailableWidth?: boolean;
}

const DetailLayout: React.FC<DetailLayoutProps> = ({
    listTitle,
    detailsTitle,
    listContent,
    detailsContent,
    resizableList = false,
    listWidthStorageKey,
    defaultListWidth = 300,
    minListWidth = 260,
    maxListWidth = 520,
    fillListAvailableWidth = false,
    fillDetailsAvailableWidth = false,
}) => {
    // ListScrollPositionSave
    const listCardRef = useRef<HTMLDivElement>(null);
    const savedListScrollPosition = useRef<number>(0);

    const storageKey = useMemo(() => {
        if (!resizableList) return null;
        return listWidthStorageKey || `detail_layout:list_width:${detailsTitle || 'default'}`;
    }, [detailsTitle, listWidthStorageKey, resizableList]);

    const [listWidth, setListWidth] = useState<number>(() => {
        if (!resizableList) return defaultListWidth;
        if (!storageKey) return defaultListWidth;
        try {
            const raw = localStorage.getItem(storageKey);
            const v = raw ? Number(raw) : NaN;
            if (!Number.isFinite(v)) return defaultListWidth;
            return Math.min(maxListWidth, Math.max(minListWidth, v));
        } catch {
            return defaultListWidth;
        }
    });

    const draggingRef = useRef<boolean>(false);
    const dragStartXRef = useRef<number>(0);
    const dragStartWidthRef = useRef<number>(0);

    useEffect(() => {
        if (!resizableList) return;

        const handleMove = (e: MouseEvent) => {
            if (!draggingRef.current) return;
            const dx = e.clientX - dragStartXRef.current;
            const next = Math.min(maxListWidth, Math.max(minListWidth, dragStartWidthRef.current + dx));
            setListWidth(next);
        };

        const handleUp = () => {
            if (!draggingRef.current) return;
            draggingRef.current = false;
            try {
                if (storageKey) localStorage.setItem(storageKey, String(listWidth));
            } catch {
                // ignore
            }
            document.body.style.cursor = '';
            document.body.style.userSelect = '';
        };

        window.addEventListener('mousemove', handleMove);
        window.addEventListener('mouseup', handleUp);
        return () => {
            window.removeEventListener('mousemove', handleMove);
            window.removeEventListener('mouseup', handleUp);
        };
    }, [listWidth, maxListWidth, minListWidth, resizableList, storageKey]);
    
    // 使用 useEffectOnActive 在ComponentActive时RestoreScrollPosition
    useEffectOnActive(
        () => {
            // Get实际的ScrollContainer（Card body）
            const container = listCardRef.current?.querySelector('.ant-card-body') as HTMLDivElement;
            if (container && savedListScrollPosition.current > 0) {
                requestAnimationFrame(() => {
                    container.scrollTop = savedListScrollPosition.current;
                });
            }
            
            return () => {
                const container = listCardRef.current?.querySelector('.ant-card-body') as HTMLDivElement;
                if (container) {
                    savedListScrollPosition.current = container.scrollTop;
                }
            };
        },
        []
    );
    
    return (
        <Container $resizable={resizableList}>
            <ListCard
                ref={listCardRef}
                variant="borderless"
                title={listTitle}
                style={fillListAvailableWidth
                    ? { flex: 1, minWidth: 0 }
                    : { width: resizableList ? listWidth : defaultListWidth }}
            >
                {listContent}
            </ListCard>
            {detailsContent !== undefined && resizableList && (
                <Splitter
                    onMouseDown={(e) => {
                        draggingRef.current = true;
                        dragStartXRef.current = e.clientX;
                        dragStartWidthRef.current = listWidth;
                        document.body.style.cursor = 'col-resize';
                        document.body.style.userSelect = 'none';
                    }}
                />
            )}
            {detailsContent !== undefined ? (
                <DetailsCard $fillAvailableWidth={fillDetailsAvailableWidth} variant="borderless" title={detailsTitle}>
                    {detailsContent}
                </DetailsCard>
            ) : null}
        </Container>
    );
};

export default DetailLayout; 