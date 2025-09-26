/**
 * Org Form Modal Component
 */

import React, { useEffect } from 'react';
import { Modal, Form, Input, Select } from 'antd';
import { useTranslation } from 'react-i18next';
import type { Org, OrgFormData } from '../types';
import { ORG_TYPES, FORM_RULES, MODAL_CONFIG, DEFAULT_ORG_TYPE } from '../constants';

const { TextArea } = Input;

interface OrgModalProps {
  visible: boolean;
  editingOrg: Org | null;
  onOk: (values: OrgFormData) => Promise<void>;
  onCancel: () => void;
}

const OrgModal: React.FC<OrgModalProps> = ({
  visible,
  editingOrg,
  onOk,
  onCancel,
}) => {
  const { t } = useTranslation();
  const [form] = Form.useForm();

  const isEditing = !!editingOrg;

  useEffect(() => {
    if (visible) {
      if (editingOrg) {
        form.setFieldsValue({
          name: editingOrg.name,
          description: editingOrg.description,
          org_type: editingOrg.org_type,
        });
      } else {
        form.resetFields();
        form.setFieldsValue({
          org_type: DEFAULT_ORG_TYPE,
        });
      }
    }
  }, [visible, editingOrg, form]);

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
      title={isEditing ? t('pages.org.modal.edit.title') : t('pages.org.modal.create.title')}
      open={visible}
      onOk={handleOk}
      onCancel={handleCancel}
      {...MODAL_CONFIG.CREATE_ORG}
    >
      <Form
        form={form}
        layout="vertical"
        initialValues={{
          org_type: DEFAULT_ORG_TYPE,
        }}
      >
        <Form.Item
          label={t('pages.org.form.name')}
          name="name"
          rules={FORM_RULES.name.map(rule => ({
            ...rule,
            message: t(rule.message)
          }))}
        >
          <Input placeholder={t('pages.org.form.name')} />
        </Form.Item>

        <Form.Item
          label={t('pages.org.form.description')}
          name="description"
          rules={FORM_RULES.description.map(rule => ({
            ...rule,
            message: t(rule.message)
          }))}
        >
          <TextArea
            rows={3}
            placeholder={t('pages.org.form.description')}
          />
        </Form.Item>

        <Form.Item
          label={t('pages.org.form.type')}
          name="org_type"
          rules={FORM_RULES.org_type.map(rule => ({
            ...rule,
            message: t(rule.message)
          }))}
        >
          <Select placeholder={t('pages.org.form.type')}>
            {ORG_TYPES.map(type => (
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

export default OrgModal;
