import React from 'react';
import { Card } from 'antd';
import styled from '@emotion/styled';

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
        overflow: hidden;
        display: flex;
        flex-direction: column;
        padding: 0;
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
        padding: 0;
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
    return (
        <Container>
            <ListCard variant="borderless" title={listTitle}>
                {listContent}
            </ListCard>
            <DetailsCard variant="borderless" title={detailsTitle}>
                {detailsContent}
            </DetailsCard>
        </Container>
    );
};

export default DetailLayout; 