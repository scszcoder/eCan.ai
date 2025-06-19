import React from 'react';
import { Content } from 'antd/es/layout/layout';
import styled from '@emotion/styled';

const StyledContent = styled(Content)`
    margin: 24px 16px;
    padding: 24px;
    background: #fff;
    min-height: 0;
    height: 100%;
    border-radius: 8px;
`;

const AppContent: React.FC<{ children: React.ReactNode }> = ({ children }) => (
    <StyledContent>{children}</StyledContent>
);

export default AppContent; 