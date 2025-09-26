/**
 * Agent Binding Modal Component
 */

import React, { useEffect } from 'react';
import { Modal, Form, Select, Avatar, Empty } from 'antd';
import { UserOutlined } from '@ant-design/icons';
import { useTranslation } from 'react-i18next';
import type { Agent, AgentBindingFormData } from '../types';
import { MODAL_CONFIG } from '../constants';

interface AgentBindingModalProps {
  visible: boolean;
  availableAgents: Agent[];
  onOk: (values: AgentBindingFormData) => Promise<void>;
  onCancel: () => void;
  onLoadAgents: () => void;
}

const AgentBindingModal: React.FC<AgentBindingModalProps> = ({
  visible,
  availableAgents,
  onOk,
  onCancel,
  onLoadAgents,
}) => {
  const { t } = useTranslation();
  const [form] = Form.useForm();

  useEffect(() => {
    if (visible) {
      form.resetFields();
      onLoadAgents();
    }
  }, [visible, form, onLoadAgents]);

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
      title={t('org.modal.bind.title')}
      open={visible}
      onOk={handleOk}
      onCancel={handleCancel}
      {...MODAL_CONFIG.BIND_AGENTS}
    >
      <Form form={form} layout="vertical">
        <Form.Item
          label={t('org.modal.bind.selectAgents')}
          name="agent_ids"
          rules={[
            { required: true, message: t('org.form.validation.nameRequired') }
          ]}
        >
          <Select
            mode="multiple"
            placeholder={t('org.modal.bind.selectAgents')}
            optionLabelProp="label"
            style={{ width: '100%' }}
            notFoundContent={
              availableAgents.length === 0 ? (
                <Empty 
                  image={Empty.PRESENTED_IMAGE_SIMPLE}
                  description={t('org.placeholder.noAvailableAgents')}
                />
              ) : null
            }
          >
            {availableAgents.map(agent => (
              <Select.Option 
                key={agent.id} 
                value={agent.id}
                label={
                  <div style={{ display: 'flex', alignItems: 'center' }}>
                    <Avatar 
                      src={agent.avatar} 
                      icon={<UserOutlined />} 
                      size="small" 
                      style={{ marginRight: 8 }}
                    />
                    {agent.name}
                  </div>
                }
              >
                <div style={{ display: 'flex', alignItems: 'center' }}>
                  <Avatar 
                    src={agent.avatar} 
                    icon={<UserOutlined />} 
                    size="small" 
                    style={{ marginRight: 8 }}
                  />
                  <div>
                    <div>{agent.name}</div>
                    <div style={{ fontSize: '12px', color: '#666' }}>
                      {agent.description || '-'}
                    </div>
                  </div>
                </div>
              </Select.Option>
            ))}
          </Select>
        </Form.Item>
      </Form>
    </Modal>
  );
};

export default AgentBindingModal;
