import React from 'react';
import { Content } from 'antd/es/layout/layout';
import styled from '@emotion/styled';

const StyledContent = styled(Content)`
    margin: 20px;
    padding: 0;
    background: transparent;
    min-height: 0;
    height: 100%;
    border-radius: 0;
    position: relative;
`;

const AppContent: React.FC<{ children: React.ReactNode }> = ({ children }) => (
    <StyledContent>{children}</StyledContent>
);

export default React.memo(AppContent); 