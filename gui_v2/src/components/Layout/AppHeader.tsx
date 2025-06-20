import React from 'react';
import { Header } from 'antd/es/layout/layout';
import { Button, Badge, Dropdown, Space, Avatar } from 'antd';
import { MenuFoldOutlined, MenuUnfoldOutlined, BellOutlined, UserOutlined } from '@ant-design/icons';
import styled from '@emotion/styled';
import { useTranslation } from 'react-i18next';

const StyledHeader = styled(Header)`
    padding: 0 24px;
    background: #fff;
    display: flex;
    align-items: center;
    justify-content: space-between;
    box-shadow: 0 2px 8px rgba(0, 0, 0, 0.06);
`;

const HeaderRight = styled.div`
    display: flex;
    align-items: center;
    gap: 16px;
`;

interface AppHeaderProps {
    collapsed: boolean;
    onCollapse: () => void;
    userMenuItems: any[];
    onLogout: () => void;
}

const AppHeader: React.FC<AppHeaderProps> = ({ collapsed, onCollapse, userMenuItems, onLogout }) => {
    const { t } = useTranslation();
    return (
        <StyledHeader>
            <Button
                type="text"
                icon={collapsed ? <MenuUnfoldOutlined /> : <MenuFoldOutlined />}
                onClick={onCollapse}
                style={{ fontSize: '16px', width: 64, height: 64 }}
            />
            <HeaderRight>
                <Badge count={5}>
                    <Button
                        type="text"
                        icon={<BellOutlined />}
                        style={{ fontSize: '16px', color: 'white' }}
                    />
                </Badge>
                <Dropdown
                    menu={{ items: userMenuItems }}
                >
                    <Space style={{ cursor: 'pointer' }}>
                        <Avatar icon={<UserOutlined />} />
                        <span>{t('common.username')}</span>
                    </Space>
                </Dropdown>
            </HeaderRight>
        </StyledHeader>
    );
};

export default AppHeader; 