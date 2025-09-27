import React from 'react';
import { Button, Space, Tooltip, Dropdown, Menu } from 'antd';
import {
    PlusOutlined,
    EditOutlined,
    DeleteOutlined,
    ReloadOutlined,
    ExportOutlined,
    ImportOutlined,
    SettingOutlined,
    MoreOutlined
} from '@ant-design/icons';

interface ActionButtonsProps {
    onAdd?: () => void;
    onEdit?: () => void;
    onDelete?: () => void;
    onRefresh?: () => void;
    onExport?: () => void;
    onImport?: () => void;
    onSettings?: () => void;
    addText?: string;
    editText?: string;
    deleteText?: string;
    refreshText?: string;
    exportText?: string;
    importText?: string;
    settingsText?: string;
    style?: React.CSSProperties;
    buttonStyle?: React.CSSProperties;
    iconStyle?: React.CSSProperties;
    visibleButtons?: ('add' | 'edit' | 'delete' | 'refresh' | 'export' | 'import' | 'settings')[];
}

const ActionButtons: React.FC<ActionButtonsProps> = ({
    onAdd,
    onEdit,
    onDelete,
    onRefresh,
    onExport,
    onImport,
    onSettings,
    addText,
    editText,
    deleteText,
    refreshText,
    exportText,
    importText,
    settingsText,
    style,
    buttonStyle,
    iconStyle,
    visibleButtons = ['add']
}) => {
    const allButtons = [
        {
            key: 'add',
            icon: <PlusOutlined style={iconStyle} />,
            label: addText,
            onClick: onAdd,
            tooltip: addText
        },
        {
            key: 'edit',
            icon: <EditOutlined style={iconStyle} />,
            label: editText,
            onClick: onEdit,
            tooltip: editText
        },
        {
            key: 'delete',
            icon: <DeleteOutlined style={iconStyle} />,
            label: deleteText,
            onClick: onDelete,
            tooltip: deleteText,
            danger: true
        },
        {
            key: 'refresh',
            icon: <ReloadOutlined style={iconStyle} />,
            label: refreshText,
            onClick: onRefresh,
            tooltip: refreshText
        },
        {
            key: 'export',
            icon: <ExportOutlined style={iconStyle} />,
            label: exportText,
            onClick: onExport,
            tooltip: exportText
        },
        {
            key: 'import',
            icon: <ImportOutlined style={iconStyle} />,
            label: importText,
            onClick: onImport,
            tooltip: importText
        },
        {
            key: 'settings',
            icon: <SettingOutlined style={iconStyle} />,
            label: settingsText,
            onClick: onSettings,
            tooltip: settingsText
        }
    ];

    const displayButtons = allButtons.filter(button => 
        visibleButtons.includes(button.key as any) && button.label
    );
    
    const menuButtons = allButtons.filter(button => 
        !visibleButtons.includes(button.key as any) && button.label
    );

    const menu = (
        <Menu items={menuButtons} />
    );

    return (
        <div style={{ 
            display: 'flex', 
            justifyContent: 'space-between', 
            alignItems: 'center',
            ...style 
        }}>
            <Space size="small">
                {displayButtons.map(button => (
                    <Tooltip
                        key={button.key}
                        title={button.tooltip}
                        mouseEnterDelay={0.5}
                        mouseLeaveDelay={0.1}
                        placement="top"
                    >
                        <Button
                            type="text"
                            icon={button.icon}
                            onClick={button.onClick}
                            danger={button.danger}
                            style={buttonStyle}
                        >
                            {button.label}
                        </Button>
                    </Tooltip>
                ))}
            </Space>
            
            {menuButtons.length > 0 && (
                <Dropdown menu={{ items: menuButtons }} placement="bottomRight" trigger={['click']}>
                    <Button
                        type="text"
                        icon={<MoreOutlined style={iconStyle} />}
                        style={buttonStyle}
                    />
                </Dropdown>
            )}
        </div>
    );
};

export default ActionButtons; 