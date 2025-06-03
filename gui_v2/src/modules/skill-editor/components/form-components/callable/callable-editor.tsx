import React, { useState, useEffect } from 'react';
import { Modal, Form, Input, Select, Button, Space } from 'antd';
import { CodeEditorModal } from '../../code-editor-modal';
import { CallableFunction, CallableEditorProps } from '../../../typings/callable';
import { JsonSchemaEditor } from '@flowgram.ai/form-materials';

const { Option } = Select;

export const CallableEditor: React.FC<CallableEditorProps> = ({
  value,
  onChange,
  onSave,
  onCancel,
  mode = 'create',
  systemFunctions = []
}) => {
  const [form] = Form.useForm();
  const [isCodeEditorVisible, setIsCodeEditorVisible] = useState(false);
  const [currentCallable, setCurrentCallable] = useState<CallableFunction | undefined>(value);
  const [codeValue, setCodeValue] = useState('');

  useEffect(() => {
    if (value) {
      form.setFieldsValue(value);
      setCurrentCallable(value);
      setCodeValue(value.code || '');
    }
  }, [value, form]);

  const handleValuesChange = (changedValues: any, allValues: any) => {
    const newCallable = { ...currentCallable, ...allValues };
    setCurrentCallable(newCallable as CallableFunction);
    onChange?.(newCallable as CallableFunction);
  };

  const handleSave = async () => {
    try {
      const values = await form.validateFields();
      const newCallable = { ...currentCallable, ...values };
      onSave?.(newCallable as CallableFunction);
    } catch (error) {
      console.error('Validation failed:', error);
    }
  };

  const handleCodeEdit = () => {
    setIsCodeEditorVisible(true);
  };

  const handleCodeChange = (value: string) => {
    setCodeValue(value);
    setCurrentCallable(prev => ({
      ...prev,
      code: value
    } as CallableFunction));
  };

  return (
    <Modal
      title={mode === 'create' ? 'Create Callable Function' : 'Edit Callable Function'}
      open={true}
      onOk={handleSave}
      onCancel={onCancel}
      width={800}
    >
      <Form
        form={form}
        layout="vertical"
        onValuesChange={handleValuesChange}
        initialValues={value}
      >
        <Form.Item
          name="name"
          label="Function Name"
          rules={[{ required: true, message: 'Please input function name!' }]}
        >
          <Input placeholder="Enter function name" />
        </Form.Item>

        <Form.Item
          name="desc"
          label="Description"
          rules={[{ required: true, message: 'Please input function description!' }]}
        >
          <Input.TextArea placeholder="Enter function description" />
        </Form.Item>

        <Form.Item
          name="type"
          label="Function Type"
          rules={[{ required: true, message: 'Please select function type!' }]}
        >
          <Select>
            <Option value="system">System Function</Option>
            <Option value="custom">Custom Function</Option>
          </Select>
        </Form.Item>

        {form.getFieldValue('type') === 'system' && (
          <Form.Item
            name="sysId"
            label="System Function ID"
            rules={[{ required: true, message: 'Please select system function!' }]}
          >
            <Select>
              {systemFunctions.map(func => (
                <Option key={func.sysId} value={func.sysId}>
                  {func.name}
                </Option>
              ))}
            </Select>
          </Form.Item>
        )}

        <Form.Item
          name="params"
          label="Parameters Schema"
          rules={[{ required: true, message: 'Please define parameters schema!' }]}
        >
          <JsonSchemaEditor />
        </Form.Item>

        <Form.Item
          name="returns"
          label="Return Type Schema"
          rules={[{ required: true, message: 'Please define return type schema!' }]}
        >
          <JsonSchemaEditor />
        </Form.Item>

        {form.getFieldValue('type') === 'custom' && (
          <Form.Item label="Implementation">
            <Space>
              <Button onClick={handleCodeEdit}>
                {currentCallable?.code ? 'Edit Code' : 'Add Code'}
              </Button>
              {currentCallable?.code && (
                <pre style={{ marginTop: 8, padding: 8, background: '#f5f5f5' }}>
                  {currentCallable.code}
                </pre>
              )}
            </Space>
          </Form.Item>
        )}
      </Form>

      <CodeEditorModal
        value={codeValue}
        onChange={handleCodeChange}
        language="typescript"
        visible={isCodeEditorVisible}
        onVisibleChange={setIsCodeEditorVisible}
        handleOk={() => setIsCodeEditorVisible(false)}
        handleCancel={() => setIsCodeEditorVisible(false)}
      />
    </Modal>
  );
}; 