/**
 * Agent Binding Modal Component
 */

import React, { useEffect } from 'react';
import { Modal, Form, Select, Avatar, Empty, Tag } from 'antd';
import { UserOutlined, CheckCircleOutlined, MinusCircleOutlined } from '@ant-design/icons';
import { useTranslation } from 'react-i18next';
import type { Agent, AgentBindingFormData } from '../types';
import { MODAL_CONFIG } from '../constants';

interface AgentBindingModalProps {
  visible: boolean;
  availableAgents: Agent[];
  selectedOrgId?: string;
  onOk: (values: AgentBindingFormData) => Promise<void>;
  onCancel: () => void;
  onLoadAgents: (selectedOrgId?: string) => void;
}

const AgentBindingModal: React.FC<AgentBindingModalProps> = ({
  visible,
  availableAgents,
  selectedOrgId,
  onOk,
  onCancel,
  onLoadAgents,
}) => {
  const { t } = useTranslation();
  const [form] = Form.useForm();

  // Memoize validation rules to prevent re-creation on every render
  const agentIdsRules = React.useMemo(() => [
    { required: true, message: t('pages.org.form.validation.nameRequired') }
  ], [t]);

  // Memoize filtered agents to prevent re-creation on every render
  const validAgents = React.useMemo(() => 
    availableAgents.filter(agent => agent && agent.id && agent.name),
    [availableAgents]
  );

  useEffect(() => {
    if (visible) {
      form.resetFields();
      onLoadAgents(selectedOrgId);
    }
  }, [visible, selectedOrgId, onLoadAgents, form]);

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
      title={t('pages.org.modal.bind.title')}
      open={visible}
      onOk={handleOk}
      onCancel={handleCancel}
      destroyOnHidden={true}
      {...MODAL_CONFIG.BIND_AGENTS}
    >
      <Form form={form} layout="vertical" preserve={false}>
        <Form.Item
          label={t('pages.org.modal.bind.selectAgents')}
          name="agent_ids"
          rules={agentIdsRules}
        >
          <Select
            mode="multiple"
            placeholder={t('pages.org.modal.bind.selectAgents')}
            optionLabelProp="label"
            style={{ width: '100%' }}
            optionFilterProp="children"
            showSearch
            filterOption={(input, option) => {
              const agent = validAgents.find(a => a && a.id === option?.value);
              return agent?.name?.toLowerCase().includes(input.toLowerCase()) || false;
            }}
            notFoundContent={
              validAgents.length === 0 ? (
                <Empty
                  image={Empty.PRESENTED_IMAGE_SIMPLE}
                  description={t('pages.org.placeholder.noAvailableAgents')}
                />
              ) : null
            }
          >
            {validAgents.map(agent => (
                <Select.Option
                  key={agent.id}
                  value={agent.id}
                  disabled={agent.isBound}
                  label={
                    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                      <div style={{ display: 'flex', alignItems: 'center' }}>
                        <Avatar
                          src={agent.avatar}
                          icon={<UserOutlined />}
                          size="small"
                          style={{ marginRight: 8 }}
                        />
                        <span style={{ color: agent.isBound ? '#999' : 'inherit' }}>
                          {agent.name}
                        </span>
                      </div>
                      {agent.isBound && (
                        <Tag
                          icon={<CheckCircleOutlined />}
                          color="success"
                        >
                          {t('pages.org.binding.bound')}
                        </Tag>
                      )}
                    </div>
                  }
                >
                  <div style={{
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'space-between',
                    opacity: agent.isBound ? 0.6 : 1
                  }}>
                    <div style={{ display: 'flex', alignItems: 'center', flex: 1 }}>
                      <Avatar
                        src={agent.avatar}
                        icon={<UserOutlined />}
                        size="small"
                        style={{ marginRight: 8 }}
                      />
                      <div style={{ flex: 1 }}>
                        <div style={{
                          display: 'flex',
                          alignItems: 'center',
                          justifyContent: 'space-between'
                        }}>
                          <span style={{ color: agent.isBound ? '#999' : 'inherit' }}>
                            {agent.name}
                          </span>
                          {agent.isBound ? (
                            <Tag
                              icon={<CheckCircleOutlined />}
                              color="success"
                            >
                              {t('pages.org.binding.bound')}
                            </Tag>
                          ) : (
                            <Tag
                              icon={<MinusCircleOutlined />}
                              color="default"
                            >
                              {t('pages.org.binding.unbound')}
                            </Tag>
                          )}
                        </div>
                        <div style={{ fontSize: '12px', color: '#666', marginTop: 2 }}>
                          {agent.description || t('pages.org.binding.noDescription')}
                        </div>
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
