/**
 * Copyright (c) 2025 Bytedance Ltd. and/or its affiliates
 * SPDX-License-Identifier: MIT
 */

import React, { useState, useEffect, useMemo } from 'react';
import { Select, Button, Space, Tooltip, Dropdown, Modal } from '@douyinfe/semi-ui';
import { IconPlus, IconEdit, IconBox, IconSetting, IconMinusCircle } from '@douyinfe/semi-icons';
import { CallableFunction } from '../../typings/callable';
import { systemFunctions, customFunctions } from './test-data';
import { CallableEditor } from './callable-editor';
import { CallableSelectorWrapper } from './styles';
import { createIPCAPI } from '../../../../services/ipc/api';

// 配置是否使用远程搜索
const USE_REMOTE_SEARCH = true;

interface CallableSelectorProps {
  value?: CallableFunction;
  onChange?: (value: CallableFunction) => void;
  onEdit?: (value: CallableFunction) => void;
  onAdd?: () => void;
  systemFunctions?: CallableFunction[];
}

export const CallableSelector: React.FC<CallableSelectorProps> = ({
  value,
  onChange,
  onEdit,
  onAdd,
  systemFunctions: propSystemFunctions = systemFunctions
}) => {
  const [searchText, setSearchText] = useState('');
  const [editorVisible, setEditorVisible] = useState(false);
  const [editingFunction, setEditingFunction] = useState<CallableFunction | null>(null);
  const [selectedValue, setSelectedValue] = useState<string | undefined>(value?.name);
  const [isLoading, setIsLoading] = useState(false);
  const [remoteFunctions, setRemoteFunctions] = useState<CallableFunction[]>([]);
  const [deleteConfirmVisible, setDeleteConfirmVisible] = useState(false);
  const [functionToDelete, setFunctionToDelete] = useState<CallableFunction | null>(null);

  const ipcAPI = createIPCAPI();

  // 添加刷新函数列表的函数
  const refreshFunctions = async () => {
    if (!USE_REMOTE_SEARCH) return;
    
    setIsLoading(true);
    try {
      const response = await ipcAPI.getCallables<{ data: CallableFunction[] }>({
        text: searchText || undefined
      });
      
      if (response.success && response.data?.data) {
        setRemoteFunctions(response.data.data);
      }
    } catch (error) {
      console.error('Error refreshing functions:', error);
    } finally {
      setIsLoading(false);
    }
  };

  // 组件挂载时刷新函数列表
  useEffect(() => {
    refreshFunctions();
  }, []);

  useEffect(() => {
    setSelectedValue(value?.name);
  }, [value]);

  // 修改远程搜索的 useEffect
  useEffect(() => {
    const debounceTimer = setTimeout(refreshFunctions, 300);
    return () => clearTimeout(debounceTimer);
  }, [searchText]);

  // 使用 useMemo 优化本地过滤函数列表的性能
  const localFilteredFunctions = useMemo(() => {
    if (!searchText) {
      return [...propSystemFunctions, ...customFunctions];
    }

    const searchLower = searchText.toLowerCase();
    return [...propSystemFunctions, ...customFunctions].filter(func => {
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
  }, [searchText, propSystemFunctions]);

  const handleSelect = (selectedValue: string | number | any[] | Record<string, any> | undefined) => {
    if (typeof selectedValue !== 'string') return;
    
    console.log('Selected value:', selectedValue);
    const functions = USE_REMOTE_SEARCH ? remoteFunctions : localFilteredFunctions;
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
    if (value) {
      setEditingFunction(value);
      setEditorVisible(true);
    }
  };

  const handleAdd = () => {
    const newFunction: CallableFunction = {
      name: '',
      desc: '',
      params: {
        type: 'object',
        properties: {}
      },
      returns: {
        type: 'object',
        properties: {}
      },
      type: 'custom'
    };
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

    // 更新函数列表
    await refreshFunctions();
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

    try {
      const response = await ipcAPI.manageCallable({
        action: 'delete',
        data: functionToDelete
      });

      if (response.success) {
        // 刷新函数列表
        await refreshFunctions();
        // 如果删除的是当前选中的函数，清空选择
        if (value?.name === functionToDelete.name) {
          if (onChange) {
            onChange(null as any);
          }
        }
      }
    } catch (error) {
      console.error('Error deleting function:', error);
    } finally {
      setDeleteConfirmVisible(false);
      setFunctionToDelete(null);
    }
  };

  const renderOption = (func: CallableFunction) => (
    <Tooltip content={func.desc} position="right">
      <div style={{ 
        display: 'flex', 
        alignItems: 'center', 
        gap: '8px',
        padding: '4px 0',
        width: '100%'
      }}>
        <span style={{ 
          display: 'flex', 
          alignItems: 'center', 
          justifyContent: 'center',
          width: '16px',
          height: '16px',
          color: 'var(--semi-color-text-2)'
        }}>
          {func.type === 'system' ? <IconBox /> : <IconEdit />}
        </span>
        <span style={{ 
          color: 'var(--semi-color-text-0)',
          flex: 1
        }}>{func.name}</span>
        {func.type === 'custom' && (
          <Button
            type="tertiary"
            theme="borderless"
            icon={<IconMinusCircle size="small" />}
            size="small"
            onClick={(e) => {
              e.stopPropagation();
              handleDelete(func);
            }}
            style={{ 
              padding: '2px',
              color: 'var(--semi-color-text-2)'
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
      disabled: !selectedValue
    },
    {
      key: 'add',
      text: 'Add',
      icon: <IconPlus />,
      onClick: handleAdd
    }
  ];

  // 确保函数列表始终是数组
  const functions = USE_REMOTE_SEARCH ? remoteFunctions : localFilteredFunctions;
  const optionList = Array.isArray(functions) ? functions : [];

  return (
    <CallableSelectorWrapper>
      <div className="selector-container">
        <Select
          style={{ width: '100%' }}
          value={value?.name || selectedValue}
          onChange={handleSelect}
          onSearch={setSearchText}
          showClear
          filter
          loading={isLoading}
          placeholder="Select a function"
          optionList={optionList.map(func => ({
            value: func.name,
            label: renderOption(func)
          }))}
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