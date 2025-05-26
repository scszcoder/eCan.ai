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
    overflow: auto;
`;

const DetailsCard = styled(Card)`
    flex: 1;
    height: 100%;
    overflow: auto;
`;

interface DetailLayoutProps {
    listTitle: string;
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