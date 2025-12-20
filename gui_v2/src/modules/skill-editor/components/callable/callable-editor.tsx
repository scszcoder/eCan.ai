/**
 * Copyright (c) 2025 Bytedance Ltd. and/or its affiliates
 * SPDX-License-Identifier: MIT
 */

import React, { useState, useEffect, useRef } from 'react';
import { Modal, Form, Input, Select, Button, Typography, message, Space, Card } from 'antd';
import { CodeOutlined, PlusOutlined, DeleteOutlined } from '@ant-design/icons';
import type { editor } from 'monaco-editor';
import { CallableFunction } from '../../typings/callable';
import { CallableEditorWrapper } from './styles';
import { useCodeEditor } from '../code-editor';
import { APIResponse, IPCAPI } from '../../../../services/ipc/api';
import { App } from 'antd';
import { logger } from '../../../../utils/logger';

const { Option } = Select;
const { Title } = Typography;

// Constants
const MODAL_WIDTH = 800;
const CODE_EDITOR_HEIGHT = '200px';
const DEFAULT_LANGUAGE = 'python';

// Types
type FunctionType = 'system' | 'custom';
type EditorMode = 'create' | 'edit';

interface CallableEditorProps {
  value?: CallableFunction;
  onSave: (func: CallableFunction) => void;
  onCancel: () => void;
  mode: EditorMode;
  systemFunctions: CallableFunction[];
  visible: boolean;
  userId?: string;
}

interface FormValues {
  name: string;
  desc: string;
  type: FunctionType;
  code?: string;
  params?: { type: string; properties: Record<string, any> };
  returns?: { type: string; properties: Record<string, any> };
}

const generateDefaultCode = (functionName: string, description: string): string => {
  return `def ${functionName}(params):
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
};

/**
 * CallableEditor component for creating and editing callable functions
 */
export const CallableEditor: React.FC<CallableEditorProps> = ({
  value,
  onSave,
  onCancel,
  mode,
  systemFunctions,
  visible,
  userId
}) => {
  const [form] = Form.useForm<FormValues>();
  const [functionType, setFunctionType] = useState<FunctionType>(value?.type || 'custom');
  const [codeValue, setCodeValue] = useState(value?.code || '');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const previewEditorRef = useRef<editor.IStandaloneCodeEditor | null>(null);
  const { message: messageApi } = App.useApp();

  // Initialize form values when value prop changes
  useEffect(() => {
    if (value) {
      form.setFieldsValue(value);
      setFunctionType(value.type);
      setCodeValue(value.code || '');
    }
  }, [value, form]);

  // Generate and set default code when function type changes to custom
  useEffect(() => {
    if (functionType === 'custom' && !codeValue) {
      const functionName = form.getFieldValue('name') || 'my_function';
      const description = form.getFieldValue('desc') || 'Process the input parameters and return the result.';
      const defaultCode = generateDefaultCode(functionName, description);
      setCodeValue(defaultCode);
    }
  }, [functionType, codeValue, form]);

  const handleSave = async () => {
    try {
      setIsSubmitting(true);
      const formValues = form.getFieldsValue();
      
      // Ensure params and returns exist
      const formParams = Array.isArray(formValues.params) ? formValues.params : [];
      const formReturns = Array.isArray(formValues.returns) ? formValues.returns : [];

      // Assemble parameters
      const requestParams = {
        action: mode === 'edit' ? 'update' : 'add',
        data: {
          id: mode === 'edit' ? value?.id : undefined,
          name: formValues.name,
          desc: formValues.desc,
          params: formParams.map((param: any) => ({
            name: param.name,
            type: param.type,
            desc: param.desc,
            required: param.required
          })),
          returns: formReturns.map((ret: any) => ({
            name: ret.name,
            type: ret.type,
            desc: ret.desc
          })),
          type: formValues.type,
          code: codeValue
        }
      };

      // Call API and handle response
      const ipcAPI = IPCAPI.getInstance();
      const response: APIResponse<any> = await ipcAPI.manageCallable<any>(requestParams);
      logger.debug('Manage callable response:', response);

      // Handle response
      if (response.success && response.data) {
        const result = response.data;
        
        // Check if add operation returned a new ID
        if (mode !== 'edit' && !result.data.id) {
          throw new Error('Function ID not returned from server');
        }

        // Update form data, ensure ID is included
        const updatedFunction = {
          ...result.data,
          id: result.data.id || value?.id
        };

        messageApi.success(mode === 'edit' ? 'Updated successfully' : 'Added successfully');
        onSave(updatedFunction);
      } else {
        const errorMsg = response.error?.message || 'Operation failed';
        messageApi.error(errorMsg);
        logger.error('Manage callable failed:', response.error);
      }
    } catch (error) {
      const errorMessage = error instanceof Error ? error.message : 'Unknown error occurred';
      messageApi.error(`Operation failed: ${errorMessage}`);
      logger.error('Save callable error:', {
        message: errorMessage,
        error: error instanceof Error ? {
          name: error.name,
          message: error.message,
          stack: error.stack
        } : error
      });
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleTypeChange = (type: FunctionType) => {
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
        const defaultCode = generateDefaultCode(functionName, description);
        setCodeValue(defaultCode);
      }
      openEditor(codeValue);
    }
  };

  const handleCodeSave = (content: string) => {
    // ParseFunction名和Description
    const functionNameMatch = content.match(/def\s+(\w+)/);
    const docstringMatch = content.match(/"""(.*?)"""/s);
    
    if (functionNameMatch) {
      form.setFieldValue('name', functionNameMatch[1]);
    }
    if (docstringMatch) {
      form.setFieldValue('desc', docstringMatch[1].trim());
    }

    // UpdateCodeValue
    setCodeValue(content);
    
    // 强制Update预览Edit器
    if (previewEditorRef.current) {
      previewEditorRef.current.setValue(content);
      previewEditorRef.current.layout();
    }

    return true;
  };

  // 预览Edit器MountCallback
  const handlePreviewEditorDidMount = (editor: editor.IStandaloneCodeEditor) => {
    previewEditorRef.current = editor;
    // Settings初始Value
    editor.setValue(codeValue);
    editor.layout();
  };

  // ListenCodeValue变化
  useEffect(() => {
    if (previewEditorRef.current) {
      previewEditorRef.current.setValue(codeValue);
      previewEditorRef.current.layout();
    }
  }, [codeValue]);

  // CodeEdit器Configuration
  const { openEditor, closeEditor, editor } = useCodeEditor({
    initialContent: codeValue,
    language: DEFAULT_LANGUAGE,
    onSave: handleCodeSave,
    mode: 'edit',
    height: 'calc(100vh - 200px)',
    options: {
      readOnly: false,
      minimap: { enabled: false },
      scrollBeyondLastLine: false,
      lineNumbers: 'on',
      folding: true,
      automaticLayout: true,
      tabSize: 4,
      wordWrap: 'on',
      suggestOnTriggerCharacters: false,
      quickSuggestions: false,
      parameterHints: { enabled: false },
      snippetSuggestions: 'none',
      wordBasedSuggestions: 'off',
      theme: 'vs-dark'
    }
  });

  // 预览Edit器Configuration
  const { editor: previewEditor } = useCodeEditor({
    initialContent: codeValue || '// No implementation code yet',
    language: DEFAULT_LANGUAGE,
    mode: 'preview',
    height: CODE_EDITOR_HEIGHT,
    className: 'code-preview-editor',
    visible: true,
    options: {
      readOnly: true,
      lineNumbers: 'off',
      minimap: { enabled: false },
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
      },
      wordWrap: 'on',
      automaticLayout: true,
      contextmenu: false,
      quickSuggestions: false,
      suggestOnTriggerCharacters: false,
      parameterHints: { enabled: false },
      snippetSuggestions: 'none',
      wordBasedSuggestions: 'off',
      theme: 'vs-dark'
    },
    onEditorDidMount: handlePreviewEditorDidMount
  });

  const renderFunctionTypeFields = () => {
    if (functionType === 'system') {
      return (
        <Form.Item
          name="name"
          label="Function Name"
          rules={[{ required: true, message: 'Please select a function' }]}
        >
          <Select
            showSearch
            placeholder="Select a system function"
            optionFilterProp="children"
            filterOption={(input, option) =>
              (option?.children as unknown as string)
                .toLowerCase()
                .includes(input.toLowerCase())
            }
          >
            {systemFunctions.map((func) => (
              <Option key={func.name} value={func.name}>
                {func.name}
              </Option>
            ))}
          </Select>
        </Form.Item>
      );
    }

    return (
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
          label="Description"
          name="desc"
          rules={[{ required: false, message: 'Please enter description' }]}
        >
          <Input.TextArea
            rows={2}
            style={{
              resize: 'vertical',
              minHeight: '60px'
            }}
            placeholder="Enter function description"
          />
        </Form.Item>
      </>
    );
  };

  return (
    <Modal
      title={mode === 'create' ? 'Create Callable Function' : 'Edit Callable Function'}
      open={visible}
      onOk={handleSave}
      onCancel={onCancel}
      width={MODAL_WIDTH}
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

          {renderFunctionTypeFields()}

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
          <div className="code-preview" style={{ marginTop: 8, border: '1px solid var(--semi-color-border)', borderRadius: '4px', overflow: 'hidden' }}>
            {previewEditor}
          </div>
        </Form>
      </CallableEditorWrapper>
      {editor}
    </Modal>
  );
}; 