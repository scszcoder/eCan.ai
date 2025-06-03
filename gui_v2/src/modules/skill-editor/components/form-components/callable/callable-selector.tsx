import React, { useState, useEffect, useMemo } from 'react';
import { Select, Button, Space, Tooltip } from '@douyinfe/semi-ui';
import { IconPlus, IconEdit, IconServer, IconCode } from '@douyinfe/semi-icons';
import { CallableFunction } from '../../../typings/callable';
import { systemFunctions, customFunctions } from './test-data';
import { CallableEditor } from './callable-editor';
import { CallableSelectorWrapper } from './styles';

interface CallableSelectorProps {
  value?: CallableFunction;
  onChange?: (value: CallableFunction) => void;
}

export const CallableSelector: React.FC<CallableSelectorProps> = ({
  value,
  onChange
}) => {
  const [searchText, setSearchText] = useState('');
  const [editorVisible, setEditorVisible] = useState(false);
  const [editingFunction, setEditingFunction] = useState<CallableFunction | null>(null);
  const [selectedValue, setSelectedValue] = useState<string | undefined>(value?.name);

  useEffect(() => {
    setSelectedValue(value?.name);
  }, [value]);

  // 使用 useMemo 优化过滤函数列表的性能
  const filteredFunctions = useMemo(() => {
    if (!searchText) {
      return [...systemFunctions, ...customFunctions];
    }

    const searchLower = searchText.toLowerCase();
    return [...systemFunctions, ...customFunctions].filter(func => {
      // 检查函数名
      if (func.name.toLowerCase().includes(searchLower)) {
        return true;
      }
      // 检查函数描述
      if (func.desc.toLowerCase().includes(searchLower)) {
        return true;
      }
      // 检查参数名称
      if (func.params.properties) {
        const paramNames = Object.keys(func.params.properties);
        if (paramNames.some(name => name.toLowerCase().includes(searchLower))) {
          return true;
        }
      }
      // 检查返回值类型
      if (func.returns.type && func.returns.type.toLowerCase().includes(searchLower)) {
        return true;
      }
      return false;
    });
  }, [searchText]);

  const handleSelect = (selectedValue: any) => {
    console.log('Selected value:', selectedValue);
    const selectedFunction = filteredFunctions.find(func => func.name === selectedValue);
    console.log('Found function:', selectedFunction);
    if (selectedFunction && onChange) {
      setSelectedValue(selectedValue);
      onChange(selectedFunction);
    }
  };

  const handleEdit = () => {
    if (value) {
      setEditingFunction(value);
      setEditorVisible(true);
    }
  };

  const handleAdd = () => {
    const newFunction: CallableFunction = {
      name: 'newFunction',
      desc: 'New function',
      params: {
        type: 'object',
        properties: {},
        required: []
      },
      returns: {
        type: 'object',
        properties: {}
      },
      type: 'custom',
      code: 'function newFunction(params) {\n  // Implement your logic here\n  return {};\n}'
    };
    setEditingFunction(newFunction);
    setEditorVisible(true);
  };

  const handleEditorSave = (updatedFunction: CallableFunction) => {
    if (onChange) {
      onChange(updatedFunction);
    }
    setEditorVisible(false);
    setEditingFunction(null);
  };

  const handleEditorCancel = () => {
    setEditorVisible(false);
    setEditingFunction(null);
  };

  const renderOption = (func: CallableFunction) => (
    <Tooltip content={func.desc} position="right">
      <div className="function-option">
        <span className="function-icon">
          {func.type === 'system' ? <IconServer /> : <IconCode />}
        </span>
        <span className="function-name">{func.name}</span>
      </div>
    </Tooltip>
  );

  return (
    <CallableSelectorWrapper>
      <Space vertical style={{ width: '100%' }}>
        <Select
          style={{ width: '100%' }}
          value={selectedValue}
          onChange={handleSelect}
          onSearch={setSearchText}
          showClear
          filter
          placeholder="Select a function"
          optionList={filteredFunctions.map(func => ({
            value: func.name,
            label: renderOption(func)
          }))}
        />
        <Space>
          <Button
            icon={<IconEdit />}
            onClick={handleEdit}
            disabled={!selectedValue}
          >
            Edit
          </Button>
          <Button
            icon={<IconPlus />}
            onClick={handleAdd}
          >
            Add
          </Button>
        </Space>
      </Space>

      {editorVisible && editingFunction && (
        <CallableEditor
          visible={editorVisible}
          value={editingFunction}
          onSave={handleEditorSave}
          onCancel={handleEditorCancel}
          mode={editingFunction.type === 'system' ? 'edit' : 'edit'}
          systemFunctions={systemFunctions}
        />
      )}
    </CallableSelectorWrapper>
  );
}; 