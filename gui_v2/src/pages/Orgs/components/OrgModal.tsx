/**
 * Organization Form Modal Component
 */

import React, { useEffect } from 'react';
import { Modal, Form, Input, Select } from 'antd';
import { useTranslation } from 'react-i18next';
import type { Organization, OrganizationFormData } from '../types';
import { ORGANIZATION_TYPES, FORM_RULES, MODAL_CONFIG, DEFAULT_ORGANIZATION_TYPE } from '../constants';

const { TextArea } = Input;

interface OrganizationModalProps {
  visible: boolean;
  editingOrganization: Organization | null;
  onOk: (values: OrganizationFormData) => Promise<void>;
  onCancel: () => void;
}

const OrganizationModal: React.FC<OrganizationModalProps> = ({
  visible,
  editingOrganization,
  onOk,
  onCancel,
}) => {
  const { t } = useTranslation();
  const [form] = Form.useForm();

  const isEditing = !!editingOrganization;

  useEffect(() => {
    if (visible) {
      if (editingOrganization) {
        form.setFieldsValue({
          name: editingOrganization.name,
          description: editingOrganization.description,
          organization_type: editingOrganization.organization_type,
        });
      } else {
        form.resetFields();
        form.setFieldsValue({
          organization_type: DEFAULT_ORGANIZATION_TYPE,
        });
      }
    }
  }, [visible, editingOrganization, form]);

  const handleOk = async () => {
    try {
      const values = await form.validateFields();
      await onOk(values);
    } catch (error) {
      console.error('Form validation failed:', error);
    }
  };

  const handleCancel = () => {
    form.resetFields();
    onCancel();
  };

  return (
    <Modal
      title={isEditing ? t('org.modal.edit.title') : t('org.modal.create.title')}
      open={visible}
      onOk={handleOk}
      onCancel={handleCancel}
      {...MODAL_CONFIG.CREATE_ORGANIZATION}
    >
      <Form 
        form={form} 
        layout="vertical"
        initialValues={{
          organization_type: DEFAULT_ORGANIZATION_TYPE,
        }}
      >
        <Form.Item
          label={t('org.form.name')}
          name="name"
          rules={FORM_RULES.name.map(rule => ({
            ...rule,
            message: t(rule.message)
          }))}
        >
          <Input placeholder={t('org.form.name')} />
        </Form.Item>

        <Form.Item
          label={t('org.form.description')}
          name="description"
          rules={FORM_RULES.description.map(rule => ({
            ...rule,
            message: t(rule.message)
          }))}
        >
          <TextArea 
            rows={3} 
            placeholder={t('org.form.description')}
          />
        </Form.Item>

        <Form.Item
          label={t('org.form.type')}
          name="organization_type"
          rules={FORM_RULES.organization_type.map(rule => ({
            ...rule,
            message: t(rule.message)
          }))}
        >
          <Select placeholder={t('org.form.type')}>
            {ORGANIZATION_TYPES.map(type => (
              <Select.Option key={type.value} value={type.value}>
                {t(type.key)}
              </Select.Option>
            ))}
          </Select>
        </Form.Item>
      </Form>
    </Modal>
  );
};

export default OrganizationModal;
