import React from 'react';
import { Button, Space, Tooltip } from 'antd';
import {
    PlusOutlined,
    EditOutlined,
    DeleteOutlined,
    ReloadOutlined,
    ExportOutlined,
    ImportOutlined,
    SettingOutlined
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
    iconStyle
}) => {
    const buttons = [
        {
            key: 'add',
            icon: <PlusOutlined style={iconStyle} />,
            text: addText,
            onClick: onAdd,
            tooltip: addText
        },
        {
            key: 'edit',
            icon: <EditOutlined style={iconStyle} />,
            text: editText,
            onClick: onEdit,
            tooltip: editText
        },
        {
            key: 'delete',
            icon: <DeleteOutlined style={iconStyle} />,
            text: deleteText,
            onClick: onDelete,
            tooltip: deleteText,
            danger: true
        },
        {
            key: 'refresh',
            icon: <ReloadOutlined style={iconStyle} />,
            text: refreshText,
            onClick: onRefresh,
            tooltip: refreshText
        },
        {
            key: 'export',
            icon: <ExportOutlined style={iconStyle} />,
            text: exportText,
            onClick: onExport,
            tooltip: exportText
        },
        {
            key: 'import',
            icon: <ImportOutlined style={iconStyle} />,
            text: importText,
            onClick: onImport,
            tooltip: importText
        },
        {
            key: 'settings',
            icon: <SettingOutlined style={iconStyle} />,
            text: settingsText,
            onClick: onSettings,
            tooltip: settingsText
        }
    ];

    return (
        <div style={style}>
            <Space wrap size="small">
                {buttons.map(button => (
                    <Tooltip key={button.key} title={button.tooltip}>
                        <Button
                            type="text"
                            icon={button.icon}
                            onClick={button.onClick}
                            danger={button.danger}
                            style={buttonStyle}
                        >
                            {button.text}
                        </Button>
                    </Tooltip>
                ))}
            </Space>
        </div>
    );
};

export default ActionButtons; 