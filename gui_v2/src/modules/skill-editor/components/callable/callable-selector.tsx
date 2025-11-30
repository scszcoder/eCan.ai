/**
 * Copyright (c) 2025 Bytedance Ltd. and/or its affiliates
 * SPDX-License-Identifier: MIT
 */

import React, { useState, useEffect, useMemo } from 'react';
import { Select, Button, Tooltip, Dropdown, Modal } from '@douyinfe/semi-ui';
import { IconPlus, IconEdit, IconBox, IconSetting, IconMinusCircle } from '@douyinfe/semi-icons';
import { CallableFunction, createDefaultCallableFunction } from '../../typings/callable';
import { systemFunctions, customFunctions } from './test-data';
import { CallableEditor } from './callable-editor';
import { CallableSelectorWrapper } from './styles';

// Configuration是否使用RemoteSearch
const USE_REMOTE_SEARCH = false; // Set to false to use props

interface CallableSelectorProps {
  value?: CallableFunction;
  onChange?: (value: CallableFunction) => void;
  onAdd?: () => void;
  systemFunctions?: CallableFunction[];
  readonly?: boolean;
}

export const CallableSelector: React.FC<CallableSelectorProps> = ({
  value,
  onChange,
  onAdd,
  systemFunctions: propSystemFunctions = systemFunctions,
  readonly = false,
}) => {
  const [searchText, setSearchText] = useState('');
  const [editorVisible, setEditorVisible] = useState(false);
  const [editingFunction, setEditingFunction] = useState<CallableFunction | null>(null);
  const [selectedValue, setSelectedValue] = useState<string | undefined>(value?.name);
  const [deleteConfirmVisible, setDeleteConfirmVisible] = useState(false);
  const [functionToDelete, setFunctionToDelete] = useState<CallableFunction | null>(null);

  useEffect(() => {
    setSelectedValue(value?.name);
  }, [value]);

  // Create the "llm auto select" option
  const llmAutoSelectFunction: CallableFunction = {
    id: 'llm-auto-select',
    name: 'llm auto select',
    desc: 'Let the LLM automatically select the appropriate tool based on the context',
    params: { type: 'object', properties: {} },
    returns: { type: 'object', properties: {} },
    type: 'system',
    source: '',
  };

  // 使用 useMemo OptimizeLocalFilterFunctionList的Performance
  const localFilteredFunctions = useMemo(() => {
    const allFunctions = [llmAutoSelectFunction, ...propSystemFunctions, ...customFunctions];
    
    if (!searchText) {
      return allFunctions;
    }

    const searchLower = searchText.toLowerCase();
    return allFunctions.filter(func => {
      // CheckFunction名
      if (func.name.toLowerCase().includes(searchLower)) {
        return true;
      }
      // CheckFunctionDescription
      if (func.desc.toLowerCase().includes(searchLower)) {
        return true;
      }
      // CheckParameterName
      if (func.params.properties) {
        const paramNames = Object.keys(func.params.properties);
        if (paramNames.some(name => name.toLowerCase().includes(searchLower))) {
          return true;
        }
      }
      // CheckReturn valueType
      if (func.returns.type && func.returns.type.toLowerCase().includes(searchLower)) {
        return true;
      }
      return false;
    });
  }, [searchText, propSystemFunctions, llmAutoSelectFunction]);

  const handleSelect = (selectedValue: string | number | any[] | Record<string, any> | undefined) => {
    if (typeof selectedValue !== 'string') return;
    
    console.log('Selected value:', selectedValue);
    const functions = localFilteredFunctions;
    const selectedFunction = functions.find(func => func.name === selectedValue);
    console.log('Found function:', selectedFunction);
    if (selectedFunction) {
      setSelectedValue(selectedValue);
      if (onChange) {
        onChange(selectedFunction);
      }
    }
  };

  const handleEdit = () => {
    if (readonly) return;
    if (value) {
      setEditingFunction(value);
      setEditorVisible(true);
    }
  };

  const handleAdd = () => {
    if (readonly) return;
    const newFunction = createDefaultCallableFunction();
    setEditingFunction(newFunction);
    setEditorVisible(true);
    if (onAdd) {
      onAdd();
    }
  };

  const handleEditorSave = async (updatedFunction: CallableFunction) => {
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

  const handleDelete = async (func: CallableFunction) => {
    setFunctionToDelete(func);
    setDeleteConfirmVisible(true);
  };

  const handleDeleteConfirm = async () => {
    if (!functionToDelete) return;

    // This logic is for remote search, can be adjusted or removed
    setDeleteConfirmVisible(false);
    setFunctionToDelete(null);
  };

  const renderOption = (func: CallableFunction) => (
    <Tooltip content={func.desc} position="right">
      <div style={{ 
        display: 'flex', 
        alignItems: 'center', 
        gap: '8px',
        padding: '4px 0',
        width: '100%',
        minWidth: 0
      }}>
        <span style={{ 
          display: 'flex', 
          alignItems: 'center', 
          justifyContent: 'center',
          width: 16,
          height: 16,
          color: 'var(--semi-color-text-2)',
          flex: '0 0 auto'
        }}>
          {func.type === 'system' ? <IconBox /> : <IconEdit />}
        </span>
        <span style={{ 
          color: 'var(--semi-color-text-0)',
          flex: 1,
          minWidth: 0,
          overflow: 'hidden',
          textOverflow: 'ellipsis',
          whiteSpace: 'nowrap'
        }}>{func.name}</span>
        {func.type === 'custom' && (
          <Button
            type="tertiary"
            theme="borderless"
            icon={<IconMinusCircle size="small" />}
            size="small"
            onClick={e => {
              e.stopPropagation();
              handleDelete(func);
            }}
            style={{ 
              padding: 2,
              color: 'var(--semi-color-text-2)',
              flex: '0 0 auto'
            }}
          />
        )}
      </div>
    </Tooltip>
  );

  const dropdownItems = [
    {
      key: 'edit',
      text: 'Edit',
      icon: <IconEdit />,
      onClick: handleEdit,
      disabled: !selectedValue || readonly,
    },
    {
      key: 'add',
      text: 'Add',
      icon: <IconPlus />,
      onClick: handleAdd,
      disabled: readonly,
    }
  ];

  // 确保FunctionList始终是数组
  const functions = localFilteredFunctions;
  const optionList = Array.isArray(functions) ? functions : [];

  return (
    <CallableSelectorWrapper>
      <div className="selector-container" style={{ width: '100%', maxWidth: '100%' }}>
        <Select
          style={{ width: '100%' }}
          value={value?.name || selectedValue}
          onChange={handleSelect}
          onSearch={setSearchText}
          showClear
          filter
          placeholder="Select a function"
          optionList={optionList.map(func => ({
            value: func.name,
            label: renderOption(func)
          }))}
          disabled={readonly}
          dropdownMatchSelectWidth
          size="small"
        />
        <Dropdown
          trigger="click"
          position="bottomRight"
          render={
            <Dropdown.Menu>
              {dropdownItems.map(item => (
                <Dropdown.Item
                  key={item.key}
                  icon={item.icon}
                  onClick={item.onClick}
                  disabled={item.disabled}
                >
                  {item.text}
                </Dropdown.Item>
              ))}
            </Dropdown.Menu>
          }
        >
          <Button
            type="tertiary"
            theme="borderless"
            className="settings-button"
            icon={<IconSetting size="small" />}
            disabled={readonly}
          />
        </Dropdown>
      </div>

      {editorVisible && editingFunction && (
        <CallableEditor
          visible={editorVisible}
          value={editingFunction}
          onSave={handleEditorSave}
          onCancel={handleEditorCancel}
          mode={editingFunction.id ? 'edit' : 'create'}
          systemFunctions={propSystemFunctions}
        />
      )}

      <Modal
        title="Delete Function"
        visible={deleteConfirmVisible}
        onOk={handleDeleteConfirm}
        onCancel={() => {
          setDeleteConfirmVisible(false);
          setFunctionToDelete(null);
        }}
        okType="danger"
        okText="Delete"
        cancelText="Cancel"
      >
        {functionToDelete && (
          <div>
            <p>Are you sure you want to delete the following function?</p>
            <p><strong>Name:</strong> {functionToDelete.name}</p>
            <p><strong>Description:</strong> {functionToDelete.desc}</p>
          </div>
        )}
      </Modal>
    </CallableSelectorWrapper>
  );
};