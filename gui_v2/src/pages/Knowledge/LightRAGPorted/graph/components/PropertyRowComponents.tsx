import React from 'react';
import { EditOutlined } from '@ant-design/icons';
import { Tooltip, Typography, theme } from 'antd';
import { useTranslation } from 'react-i18next';

const { Text } = Typography;

interface PropertyNameProps {
  name: string;
}

export const PropertyName: React.FC<PropertyNameProps> = ({ name }) => {
  const { t } = useTranslation();
  const { token } = theme.useToken();

  const getPropertyNameTranslation = (propName: string) => {
    // Try to find translation, fallback to propName if not found
    const translationKey = `graphPanel.propertiesView.node.propertyNames.${propName}`;
    const translation = t(translationKey);
    return translation === translationKey ? propName : translation;
  };

  return (
    <span style={{ color: token.colorTextSecondary, whiteSpace: 'nowrap', fontWeight: 500 }}>
      {getPropertyNameTranslation(name)}
    </span>
  );
};

interface EditIconProps {
  onClick: () => void;
}

export const EditIcon: React.FC<EditIconProps> = ({ onClick }) => {
  const { token } = theme.useToken();
  return (
    <div style={{ cursor: 'pointer', display: 'inline-flex', alignItems: 'center' }}>
      <EditOutlined 
        style={{ fontSize: 12, color: token.colorTextSecondary }} 
        onClick={onClick} 
      />
    </div>
  );
};

interface PropertyValueProps {
  value: any;
  onClick?: () => void;
  tooltip?: string;
}

export const PropertyValue: React.FC<PropertyValueProps> = ({ value, onClick, tooltip }) => {
  const { token } = theme.useToken();
  const displayValue = typeof value === 'object' ? JSON.stringify(value) : String(value);
  
  return (
    <div style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', flex: 1 }}>
      <Tooltip title={tooltip || displayValue} placement="left">
        <Text 
          style={{ 
            cursor: onClick ? 'pointer' : 'default', 
            maxWidth: '100%',
            color: token.colorText
          }} 
          ellipsis
          onClick={onClick}
        >
          {displayValue}
        </Text>
      </Tooltip>
    </div>
  );
};
