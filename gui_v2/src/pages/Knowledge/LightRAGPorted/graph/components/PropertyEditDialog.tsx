import React, { useState, useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import { Modal, Input, Checkbox, Button, Alert } from 'antd';

const { TextArea } = Input;

interface PropertyEditDialogProps {
  isOpen: boolean;
  onClose: () => void;
  onSave: (value: string, options?: { allowMerge?: boolean }) => void;
  propertyName: string;
  initialValue: string;
  isSubmitting?: boolean;
  errorMessage?: string | null;
}

const PropertyEditDialog: React.FC<PropertyEditDialogProps> = ({
  isOpen,
  onClose,
  onSave,
  propertyName,
  initialValue,
  isSubmitting = false,
  errorMessage = null
}) => {
  const { t } = useTranslation();
  const [value, setValue] = useState('');
  const [allowMerge, setAllowMerge] = useState(false);

  useEffect(() => {
    if (isOpen) {
      setValue(initialValue);
      setAllowMerge(false);
    }
  }, [isOpen, initialValue]);

  const getPropertyNameTranslation = (name: string) => {
    const translationKey = `graphPanel.propertiesView.node.propertyNames.${name}`;
    const translation = t(translationKey);
    return translation === translationKey ? name : translation;
  };

  const handleSave = async () => {
    const trimmedValue = value.trim();
    if (trimmedValue !== '') {
      const options = propertyName === 'entity_id' ? { allowMerge } : undefined;
      await onSave(trimmedValue, options);
    }
  };

  const getTextareaConfig = (name: string) => {
    switch (name) {
      case 'description':
        return { minRows: 5, maxRows: 20 };
      case 'entity_id':
        return { minRows: 1, maxRows: 2 };
      case 'keywords':
        return { minRows: 2, maxRows: 6 };
      default:
        return { minRows: 2, maxRows: 8 };
    }
  };

  return (
    <Modal
      title={t('graphPanel.propertiesView.editProperty', {
        property: getPropertyNameTranslation(propertyName),
        defaultValue: `Edit ${propertyName}`
      })}
      open={isOpen}
      onCancel={onClose}
      footer={[
        <Button key="cancel" onClick={onClose} disabled={isSubmitting}>
          {t('common.cancel')}
        </Button>,
        <Button 
          key="save" 
          type="primary" 
          onClick={handleSave} 
          loading={isSubmitting}
        >
          {t('common.save')}
        </Button>
      ]}
    >
      <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
        <div>{t('graphPanel.propertiesView.editPropertyDescription', 'Update the property value below:')}</div>
        
        {errorMessage && (
          <Alert message={errorMessage} type="error" showIcon />
        )}

        <TextArea
          value={value}
          onChange={(e) => setValue(e.target.value)}
          autoSize={getTextareaConfig(propertyName)}
          disabled={isSubmitting}
        />

        {propertyName === 'entity_id' && (
          <div style={{ 
            padding: 12, 
            border: '1px solid #d9d9d9', 
            borderRadius: 6, 
            background: 'rgba(0,0,0,0.02)'
          }}>
            <Checkbox
              checked={allowMerge}
              onChange={(e) => setAllowMerge(e.target.checked)}
              disabled={isSubmitting}
            >
              {t('graphPanel.propertiesView.mergeOptionLabel', 'Allow Merge')}
            </Checkbox>
            <div style={{ fontSize: 12, color: '#888', marginTop: 4, marginLeft: 24 }}>
              {t('graphPanel.propertiesView.mergeOptionDescription', 'If checked, renaming to an existing entity name will merge this entity into the existing one.')}
            </div>
          </div>
        )}
      </div>
    </Modal>
  );
};

export default PropertyEditDialog;
