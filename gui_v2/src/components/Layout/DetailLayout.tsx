import React, { useRef } from 'react';
import { Card } from 'antd';
import styled from '@emotion/styled';
import { useEffectOnActive } from 'keepalive-for-react';

const Container = styled.div`
    display: flex;
    gap: 16px;
    height: 100%;
`;

const ListCard = styled(Card)`
    width: 300px;
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

const DetailsCard = styled(Card)`
    flex: 1;
    height: 100%;
    display: flex;
    flex-direction: column;
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
}

const DetailLayout: React.FC<DetailLayoutProps> = ({
    listTitle,
    detailsTitle,
    listContent,
    detailsContent,
}) => {
    // ListScrollPositionSave
    const listCardRef = useRef<HTMLDivElement>(null);
    const savedListScrollPosition = useRef<number>(0);
    
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
        <Container>
            <ListCard ref={listCardRef} variant="borderless" title={listTitle}>
                {listContent}
            </ListCard>
            <DetailsCard variant="borderless" title={detailsTitle}>
                {detailsContent}
            </DetailsCard>
        </Container>
    );
};

export default DetailLayout; 