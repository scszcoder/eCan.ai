import React, { useState, useEffect } from 'react';
import { Modal, Form, Input, Select, Button, Typography } from 'antd';
import { CodeOutlined } from '@ant-design/icons';
import { CallableFunction } from '../../../typings/callable';
import { CallableEditorWrapper } from './styles';
import { CodeEditorModal } from '../../code-editor-modal';
import { FormItem } from '../../../form-components/form-item';
import { JsonSchemaEditor } from '@flowgram.ai/form-materials';
import { Editor } from '@monaco-editor/react';

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

  useEffect(() => {
    if (value) {
      form.setFieldsValue(value);
      setFunctionType(value.type);
      setCodeValue(value.code || '');
    }
  }, [value, form]);

  const handleSave = () => {
    form.validateFields().then(values => {
      onSave({
        ...values,
        type: functionType,
        code: codeValue
      });
    });
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
      setIsCodeEditorVisible(true);
    }
  };

  const handleCodeSave = (code: string) => {
    setCodeValue(code);
    setIsCodeEditorVisible(false);
  };

  return (
    <Modal
      title={mode === 'create' ? 'Create Callable Function' : 'Edit Callable Function'}
      open={visible}
      onOk={handleSave}
      onCancel={onCancel}
      width={800}
    >
      <CallableEditorWrapper>
        <Form
          form={form}
          layout="vertical"
          initialValues={value}
          disabled={functionType === 'system'}
        >
          <Form.Item
            name="type"
            label="Function Type"
            rules={[{ required: true }]}
          >
            <Select onChange={handleTypeChange}>
              <Option value="system">System Function</Option>
              <Option value="custom">Custom Function</Option>
            </Select>
          </Form.Item>

          {functionType === 'system' && (
            <Form.Item
              name="sysId"
              label="System Function"
              rules={[{ required: true }]}
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
            name="name"
            label="Function Name"
            rules={[{ required: true }]}
          >
            <Input />
          </Form.Item>

          <Form.Item
            name="desc"
            label="Description"
            rules={[{ required: true }]}
          >
            <Input.TextArea rows={2} />
          </Form.Item>

          <Title level={5} style={{ color: '#fff', marginTop: 24 }}>Parameters Schema</Title>
          <Form.Item
            name="params"
            rules={[{ required: true }]}
          >
            <JsonSchemaEditor
              value={form.getFieldValue('params')}
              onChange={(value) => form.setFieldValue('params', value)}
            />
          </Form.Item>

          <Title level={5} style={{ color: '#fff', marginTop: 24 }}>Return Type Schema</Title>
          <Form.Item
            name="returns"
            rules={[{ required: true }]}
          >
            <JsonSchemaEditor
              value={form.getFieldValue('returns')}
              onChange={(value) => form.setFieldValue('returns', value)}
            />
          </Form.Item>

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
            <Editor
              height="200px"
              defaultLanguage="javascript"
              value={codeValue || '// No implementation code yet'}
              theme="vs-dark"
              options={{
                readOnly: true,
                minimap: { enabled: false },
                scrollBeyondLastLine: false,
                automaticLayout: true,
                wordWrap: 'on',
                lineNumbers: 'off',
                folding: false,
                glyphMargin: false,
                lineDecorationsWidth: 0,
                lineNumbersMinChars: 0,
                renderLineHighlight: 'none',
                overviewRulerBorder: false,
                hideCursorInOverviewRuler: true,
                overviewRulerLanes: 0,
                scrollbar: {
                  vertical: 'hidden',
                  horizontal: 'hidden'
                }
              }}
            />
          </div>
        </Form>

        <CodeEditorModal
          value={codeValue}
          onChange={handleCodeSave}
          language="javascript"
          visible={isCodeEditorVisible}
          handleOk={() => setIsCodeEditorVisible(false)}
          handleCancel={() => setIsCodeEditorVisible(false)}
          onVisibleChange={setIsCodeEditorVisible}
          options={{ readOnly: functionType === 'system' }}
        />
      </CallableEditorWrapper>
    </Modal>
  );
}; 