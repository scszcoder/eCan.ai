import React from 'react';
import { Space, Button, Tooltip } from 'antd';
import { 
    PlusOutlined, 
    EditOutlined, 
    DeleteOutlined, 
    ReloadOutlined,
    ExportOutlined,
    ImportOutlined,
    SettingOutlined
} from '@ant-design/icons';
import styled from '@emotion/styled';

const ActionContainer = styled.div`
    margin-bottom: 16px;
    display: flex;
    justify-content: space-between;
    align-items: center;
`;

interface ActionButton {
    key: string;
    label: string;
    icon: React.ReactNode;
    type?: 'primary' | 'default' | 'dashed' | 'text' | 'link';
    danger?: boolean;
    disabled?: boolean;
    onClick: () => void;
}

interface ActionButtonsProps {
    leftButtons?: ActionButton[];
    rightButtons?: ActionButton[];
    showDefaultButtons?: boolean;
    onAdd?: () => void;
    onEdit?: () => void;
    onDelete?: () => void;
    onRefresh?: () => void;
    onExport?: () => void;
    onImport?: () => void;
    onSettings?: () => void;
}

const ActionButtons: React.FC<ActionButtonsProps> = ({
    leftButtons = [],
    rightButtons = [],
    showDefaultButtons = true,
    onAdd,
    onEdit,
    onDelete,
    onRefresh,
    onExport,
    onImport,
    onSettings,
}) => {
    const defaultLeftButtons: ActionButton[] = showDefaultButtons ? [
        {
            key: 'add',
            label: 'Add',
            icon: <PlusOutlined />,
            type: 'primary',
            onClick: onAdd || (() => {}),
        },
        {
            key: 'edit',
            label: 'Edit',
            icon: <EditOutlined />,
            onClick: onEdit || (() => {}),
        },
        {
            key: 'delete',
            label: 'Delete',
            icon: <DeleteOutlined />,
            danger: true,
            onClick: onDelete || (() => {}),
        },
    ] : [];

    const defaultRightButtons: ActionButton[] = showDefaultButtons ? [
        {
            key: 'refresh',
            label: 'Refresh',
            icon: <ReloadOutlined />,
            onClick: onRefresh || (() => {}),
        },
        {
            key: 'export',
            label: 'Export',
            icon: <ExportOutlined />,
            onClick: onExport || (() => {}),
        },
        {
            key: 'import',
            label: 'Import',
            icon: <ImportOutlined />,
            onClick: onImport || (() => {}),
        },
        {
            key: 'settings',
            label: 'Settings',
            icon: <SettingOutlined />,
            onClick: onSettings || (() => {}),
        },
    ] : [];

    const renderButton = (button: ActionButton) => (
        <Tooltip key={button.key} title={button.label}>
            <Button
                type={button.type}
                danger={button.danger}
                icon={button.icon}
                onClick={button.onClick}
                disabled={button.disabled}
            >
                {button.label}
            </Button>
        </Tooltip>
    );

    return (
        <ActionContainer>
            <Space>
                {[...defaultLeftButtons, ...leftButtons].map(renderButton)}
            </Space>
            <Space>
                {[...defaultRightButtons, ...rightButtons].map(renderButton)}
            </Space>
        </ActionContainer>
    );
};

export default ActionButtons; 