import React, { useState, useEffect } from 'react';
import { Modal, Form, Input, Select, Button, Typography, message } from 'antd';
import { CodeOutlined } from '@ant-design/icons';
import { CallableFunction } from '../../../typings/callable';
import { CallableEditorWrapper } from './styles';
import { CodeEditor as CodeEditorModal } from '../../code-editor';

const { Option } = Select;
const { Title } = Typography;

interface CallableEditorProps {
  value?: CallableFunction;
  onSave: (func: CallableFunction) => void;
  onCancel: () => void;
  mode: 'create' | 'edit';
  systemFunctions: CallableFunction[];
  visible: boolean;
}

export const CallableEditor: React.FC<CallableEditorProps> = ({
  value,
  onSave,
  onCancel,
  mode,
  systemFunctions,
  visible
}) => {
  const [form] = Form.useForm();
  const [isCodeEditorVisible, setIsCodeEditorVisible] = useState(false);
  const [functionType, setFunctionType] = useState<'system' | 'custom'>(value?.type || 'custom');
  const [codeValue, setCodeValue] = useState(value?.code || '');
  const [tempCodeValue, setTempCodeValue] = useState('');
  const [language, setLanguage] = useState<'javascript' | 'python'>('python');
  const [isSubmitting, setIsSubmitting] = useState(false);

  useEffect(() => {
    if (value) {
      form.setFieldsValue(value);
      setFunctionType(value.type);
      setCodeValue(value.code || '');
      setTempCodeValue(value.code || '');
      setLanguage('python');
    }
  }, [value, form]);

  const handleSave = async () => {
    try {
      setIsSubmitting(true);
      const values = await form.validateFields();
      
      // Validate code for custom functions
      if (functionType === 'custom' && !codeValue) {
        message.error('Please implement the function code');
        return;
      }

      onSave({
        ...values,
        type: functionType,
        code: codeValue,
        params: { type: 'object', properties: {} },
        returns: { type: 'object', properties: {} }
      });
    } catch (error) {
      console.error('Form validation failed:', error);
      // Form validation errors will be shown automatically by antd
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleTypeChange = (type: 'system' | 'custom') => {
    setFunctionType(type);
    if (type === 'system') {
      form.setFieldsValue({
        name: '',
        desc: '',
        params: { type: 'object', properties: {} },
        returns: { type: 'object', properties: {} }
      });
      setCodeValue('');
    }
  };

  const handleCodeEdit = () => {
    if (functionType === 'custom') {
      if (!codeValue) {
        const functionName = form.getFieldValue('name') || 'my_function';
        const description = form.getFieldValue('desc') || 'Process the input parameters and return the result.';
        const defaultCode = `def ${functionName}(params):
    """
    ${description}
    
    Args:
        params (dict): A dictionary containing the input parameters.
            The structure of params is defined by the Parameters Schema.
    
    Returns:
        dict: The result object, structure defined by the Return Type Schema.
    """
    # TODO: Implement your function logic here
    
    # Example: Access parameters from the params dictionary
    # param1 = params.get('param1')
    # param2 = params.get('param2')
    
    # Example: Return a result
    return {
        # Add your return values here
    }`;
        setCodeValue(defaultCode);
        setTempCodeValue(defaultCode);
      } else {
        setTempCodeValue(codeValue);
      }
      setLanguage('python');
      setIsCodeEditorVisible(true);
    }
  };

  const handleCodeChange = (code: string) => {
    setTempCodeValue(code);
  };

  const handleCodeSave = () => {
    setCodeValue(tempCodeValue);
    
    // Parse function name and description from code
    const functionNameMatch = tempCodeValue.match(/def\s+([a-zA-Z_][a-zA-Z0-9_]*)\s*\(/);
    const docStringMatch = tempCodeValue.match(/"""(.*?)"""/s);
    
    if (functionNameMatch) {
      const newFunctionName = functionNameMatch[1];
      form.setFieldValue('name', newFunctionName);
    }
    
    if (docStringMatch) {
      const docString = docStringMatch[1].trim();
      // Extract the first line of docstring as description
      const description = docString.split('\n')[0].trim();
      form.setFieldValue('desc', description);
    }
    
    setIsCodeEditorVisible(false);
  };

  const handleCodeCancel = () => {
    setTempCodeValue(codeValue);
    setIsCodeEditorVisible(false);
  };

  return (
    <Modal
      title={mode === 'create' ? 'Create Callable Function' : 'Edit Callable Function'}
      open={visible}
      onOk={handleSave}
      onCancel={onCancel}
      width={800}
      confirmLoading={isSubmitting}
    >
      <CallableEditorWrapper>
        <Form
          form={form}
          layout="vertical"
          initialValues={value}
          disabled={mode === 'edit' && functionType === 'system'}
        >
          <Form.Item
            name="type"
            label="Function Type"
            rules={[{ required: true, message: 'Please select a function type' }]}
          >
            <Select onChange={handleTypeChange} disabled={mode === 'edit'}>
              <Option value="system">System Function</Option>
              <Option value="custom">Custom Function</Option>
            </Select>
          </Form.Item>

          {functionType === 'system' && (
            <Form.Item
              name="name"
              label="Function Name"
              rules={[{ required: true, message: 'Please select a system function' }]}
            >
              <Select>
                {systemFunctions.map(func => (
                  <Option key={func.sysId} value={func.name}>
                    {func.name}
                  </Option>
                ))}
              </Select>
            </Form.Item>
          )}

          {functionType === 'custom' && (
            <>
              <Form.Item
                name="name"
                label="Function Name"
                rules={[
                  { required: true, message: 'Please enter a function name' },
                  { pattern: /^[a-zA-Z_][a-zA-Z0-9_]*$/, message: 'Invalid function name format' }
                ]}
              >
                <Input />
              </Form.Item>

              <Form.Item
                name="desc"
                label="Description"
                rules={[{ required: true, message: 'Please enter a description' }]}
              >
                <Input.TextArea rows={2} />
              </Form.Item>
            </>
          )}

          <div style={{ marginTop: 16, display: 'flex', alignItems: 'center', gap: 8 }}>
            <Title level={5} style={{ color: '#fff', margin: 0 }}>Implementation Code</Title>
            {functionType === 'custom' && (
              <Button
                type="link"
                icon={<CodeOutlined />}
                onClick={handleCodeEdit}
              >
                Edit Code
              </Button>
            )}
          </div>
          <div className="code-preview">
            <CodeEditorModal
              value={codeValue || '// No implementation code yet'}
              onChange={() => {}}
              language="python"
              visible={true}
              handleOk={() => {}}
              handleCancel={() => {}}
              onVisibleChange={() => {}}
              mode="preview"
              height="200px"
              className="code-preview-editor"
            />
          </div>
        </Form>

        <CodeEditorModal
          value={tempCodeValue}
          onChange={handleCodeChange}
          language="python"
          visible={isCodeEditorVisible}
          handleOk={handleCodeSave}
          handleCancel={handleCodeCancel}
          onVisibleChange={setIsCodeEditorVisible}
          options={{ readOnly: functionType === 'system' }}
        />
      </CallableEditorWrapper>
    </Modal>
  );
}; 