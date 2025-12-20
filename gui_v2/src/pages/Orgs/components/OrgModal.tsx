/**
 * Org Form Modal Component - Simplified Architecture
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
  
  // 只在 Modal 可见时Create Form 实例
  const [form] = Form.useForm();

  const isEditing = !!editingOrg;

  // Memoize form rules to prevent re-creation on every render
  const nameRules = React.useMemo(() => 
    FORM_RULES.name.map(rule => ({
      ...rule,
      message: t(rule.message)
    })), [t]);

  const descriptionRules = React.useMemo(() => 
    FORM_RULES.description.map(rule => ({
      ...rule,
      message: t(rule.message)
    })), [t]);

  const orgTypeRules = React.useMemo(() => 
    FORM_RULES.org_type.map(rule => ({
      ...rule,
      message: t(rule.message)
    })), [t]);

  // Memoize org type options
  const orgTypeOptions = React.useMemo(() => 
    ORG_TYPES.map(type => (
      <Select.Option key={type.value} value={type.value}>
        {t(type.key)}
      </Select.Option>
    )), [t]);

  useEffect(() => {
    if (visible && editingOrg) {
      form.setFieldsValue({
        name: editingOrg.name,
        description: editingOrg.description,
        org_type: editingOrg.org_type,
      });
    } else if (visible) {
      form.resetFields();
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
      destroyOnHidden={true}
      {...MODAL_CONFIG.CREATE_ORG}
    >
      <Form
        form={form}
        layout="vertical"
        initialValues={{
          org_type: DEFAULT_ORG_TYPE,
        }}
        preserve={false}
      >
        <Form.Item
          label={t('pages.org.form.name')}
          name="name"
          rules={nameRules}
        >
          <Input placeholder={t('pages.org.form.name')} />
        </Form.Item>

        <Form.Item
          label={t('pages.org.form.description')}
          name="description"
          rules={descriptionRules}
        >
          <TextArea
            rows={3}
            placeholder={t('pages.org.form.description')}
          />
        </Form.Item>

        <Form.Item
          label={t('pages.org.form.type')}
          name="org_type"
          rules={orgTypeRules}
        >
          <Select placeholder={t('pages.org.form.type')}>
            {orgTypeOptions}
          </Select>
        </Form.Item>
      </Form>
    </Modal>
  );
};

export default OrgModal;
