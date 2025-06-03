import React, { useState } from 'react';
import { Input, Button, Select, Space } from 'antd';
import { EditOutlined, PlusOutlined } from '@ant-design/icons';
import { CallableFunction, CallableSelectorProps } from '../../../typings/callable';
import { CallableEditor } from './callable-editor';
import { CallableSelectorWrapper } from './styles';

const { Option } = Select;

export const CallableSelector: React.FC<CallableSelectorProps> = ({
  value,
  onChange,
  onEdit,
  onAdd,
  systemFunctions = []
}) => {
  const [searchText, setSearchText] = useState('');
  const [isEditorVisible, setIsEditorVisible] = useState(false);
  const [editingCallable, setEditingCallable] = useState<CallableFunction | undefined>();

  // 过滤系统函数
  const filteredFunctions = systemFunctions.filter(func => 
    func.name.toLowerCase().includes(searchText.toLowerCase()) ||
    func.desc.toLowerCase().includes(searchText.toLowerCase())
  );

  const handleSelect = (funcName: string) => {
    onChange?.(funcName);
  };

  const handleEdit = (func: CallableFunction) => {
    setEditingCallable(func);
    setIsEditorVisible(true);
  };

  const handleAdd = () => {
    setEditingCallable(undefined);
    setIsEditorVisible(true);
  };

  const handleEditorSave = (func: CallableFunction) => {
    onEdit?.(func);
    setIsEditorVisible(false);
  };

  const handleEditorCancel = () => {
    setIsEditorVisible(false);
  };

  return (
    <CallableSelectorWrapper>
      <div className="callable-selector">
        <Select
          value={value}
          onChange={handleSelect}
          showSearch
          placeholder="Select or search a function"
          onSearch={setSearchText}
          filterOption={false}
          notFoundContent={null}
          optionLabelProp="label"
          style={{ width: '100%' }}
          dropdownMatchSelectWidth={false}
          dropdownStyle={{ minWidth: '200px' }}
        >
          {filteredFunctions.map(func => (
            <Option 
              key={func.name} 
              value={func.name}
              label={func.name}
            >
              <div className="function-option">
                <div className="function-name">{func.name}</div>
                <div className="function-desc">{func.desc}</div>
              </div>
            </Option>
          ))}
        </Select>
        <Button
          icon={<EditOutlined />}
          onClick={() => value && handleEdit(systemFunctions.find(f => f.name === value)!)}
          disabled={!value}
        />
        <Button
          icon={<PlusOutlined />}
          onClick={handleAdd}
        />
      </div>

      {isEditorVisible && (
        <CallableEditor
          value={editingCallable}
          onSave={handleEditorSave}
          onCancel={handleEditorCancel}
          mode={editingCallable ? 'edit' : 'create'}
          systemFunctions={systemFunctions}
        />
      )}
    </CallableSelectorWrapper>
  );
}; 