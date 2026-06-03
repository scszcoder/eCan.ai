/**
 * Structured form editors for Skill metadata fields.
 * Replaces raw JSON TextArea inputs with interactive form controls.
 */

import React, { useState, useMemo } from 'react';
import { Input, Button, Tag, Space, Select, Tooltip, Typography } from 'antd';
import { PlusOutlined, DeleteOutlined } from '@ant-design/icons';
import { useTranslation } from 'react-i18next';

const { TextArea } = Input;
const { Text } = Typography;

// ============================================================================
// StringArrayInput: Interactive tag-style editor for string arrays
// (used for: tags, examples, objectives, limitations, apps.name)
// ============================================================================
interface StringArrayInputProps {
    value: string; // JSON string: string[]
    onChange: (value: string) => void; // emits JSON string
    placeholder?: string;
    label?: string;
}

export const StringArrayInput: React.FC<StringArrayInputProps> = ({
    value,
    onChange,
    placeholder = 'Type and press Enter',
    label,
}) => {
    const [inputValue, setInputValue] = useState('');

    const items = useMemo(() => {
        if (!value || value.trim() === '') return [];
        try {
            const parsed = JSON.parse(value);
            return Array.isArray(parsed) ? parsed.filter((v: any) => typeof v === 'string') : [];
        } catch {
            return [];
        }
    }, [value]);

    const add = () => {
        const trimmed = inputValue.trim();
        if (!trimmed) return;
        const newItems = [...items, trimmed];
        onChange(JSON.stringify(newItems));
        setInputValue('');
    };

    const remove = (item: string) => {
        const newItems = items.filter((t: string) => t !== item);
        onChange(JSON.stringify(newItems));
    };

    return (
        <div>
            {label && (
                <Text type="secondary" style={{ fontSize: 12, marginBottom: 6, display: 'block' }}>
                    {label}
                </Text>
            )}
            <Space wrap size={4} style={{ marginBottom: 8 }}>
                {items.map((item: string, idx: number) => (
                    <Tag
                        key={`${item}-${idx}`}
                        closable
                        onClose={() => remove(item)}
                        style={{ marginBottom: 4 }}
                    >
                        {item}
                    </Tag>
                ))}
            </Space>
            <Input
                value={inputValue}
                onChange={(e) => setInputValue(e.target.value)}
                onPressEnter={add}
                placeholder={placeholder}
                suffix={
                    <Button type="text" size="small" onClick={add} disabled={!inputValue.trim()} style={{ padding: '0 4px' }}>
                        <PlusOutlined />
                    </Button>
                }
                style={{ borderRadius: 6 }}
            />
        </div>
    );
};

// ============================================================================
// NeedInputsEditor: Structured editor for SkillNeedInput[] objects
// (name, type, description, required, default)
// ============================================================================
interface NeedInputItem {
    name: string;
    type?: string;
    description?: string;
    required?: boolean;
    default?: any;
}

interface NeedInputsEditorProps {
    value: string; // JSON string: NeedInputItem[]
    onChange: (value: string) => void;
}

export const NeedInputsEditor: React.FC<NeedInputsEditorProps> = ({ value, onChange }) => {
    const { t } = useTranslation();
    const [newName, setNewName] = useState('');
    const [newType, setNewType] = useState('string');
    const [newRequired, setNewRequired] = useState(false);
    const [newDesc, setNewDesc] = useState('');

    const items: NeedInputItem[] = useMemo(() => {
        if (!value || value.trim() === '') return [];
        try {
            const parsed = JSON.parse(value);
            return Array.isArray(parsed) ? parsed : [];
        } catch {
            return [];
        }
    }, [value]);

    const add = () => {
        if (!newName.trim()) return;
        const newItem: NeedInputItem = {
            name: newName.trim(),
            type: newType,
            required: newRequired,
        };
        if (newDesc.trim()) newItem.description = newDesc.trim();
        const newItems = [...items, newItem];
        onChange(JSON.stringify(newItems));
        setNewName('');
        setNewType('string');
        setNewRequired(false);
        setNewDesc('');
    };

    const remove = (idx: number) => {
        const newItems = items.filter((_: any, i: number) => i !== idx);
        onChange(JSON.stringify(newItems));
    };

    const update = (idx: number, key: keyof NeedInputItem, val: any) => {
        const newItems = items.map((item, i) => i === idx ? { ...item, [key]: val } : item);
        onChange(JSON.stringify(newItems));
    };

    const TYPE_OPTIONS = [
        { value: 'string', label: 'String' },
        { value: 'number', label: 'Number' },
        { value: 'boolean', label: 'Boolean' },
        { value: 'object', label: 'Object' },
        { value: 'array', label: 'Array' },
        { value: 'file', label: 'File' },
    ];

    return (
        <div>
            {items.length > 0 && (
                <Space direction="vertical" size={8} style={{ marginBottom: 12, width: '100%' }}>
                    {items.map((item, idx) => (
                        <div key={idx} style={{
                            display: 'flex',
                            alignItems: 'flex-start',
                            gap: 8,
                            padding: '8px 10px',
                            background: 'rgba(255,255,255,0.04)',
                            borderRadius: 8,
                            border: '1px solid rgba(255,255,255,0.08)',
                        }}>
                            <div style={{ flex: 1, minWidth: 0 }}>
                                <Space size={6} wrap>
                                    <Input
                                        size="small"
                                        value={item.name}
                                        onChange={(e) => update(idx, 'name', e.target.value)}
                                        placeholder="Parameter name"
                                        style={{ width: 140, borderRadius: 4 }}
                                    />
                                    <Select
                                        size="small"
                                        value={item.type || 'string'}
                                        onChange={(val) => update(idx, 'type', val)}
                                        options={TYPE_OPTIONS}
                                        style={{ width: 100 }}
                                    />
                                    <Tooltip title={item.required ? 'Required' : 'Optional'}>
                                        <Button
                                            size="small"
                                            type={item.required ? 'primary' : 'default'}
                                            onClick={() => update(idx, 'required', !item.required)}
                                            style={{ fontSize: 11, padding: '0 6px', height: 24 }}
                                        >
                                            {item.required ? t('common.required', 'Required') : t('common.optional', 'Optional')}
                                        </Button>
                                    </Tooltip>
                                </Space>
                                {item.description && (
                                    <Text type="secondary" style={{ fontSize: 11, marginTop: 4, display: 'block' }}>
                                        {item.description}
                                    </Text>
                                )}
                            </div>
                            <Button
                                size="small"
                                type="text"
                                danger
                                icon={<DeleteOutlined />}
                                onClick={() => remove(idx)}
                                style={{ marginTop: 2 }}
                            />
                        </div>
                    ))}
                </Space>
            )}

            {/* Add new input row */}
            <div style={{
                display: 'flex',
                alignItems: 'flex-start',
                gap: 8,
                padding: '8px 10px',
                background: 'rgba(24,144,255,0.06)',
                borderRadius: 8,
                border: '1px dashed rgba(24,144,255,0.3)',
            }}>
                <Space size={6} wrap style={{ flex: 1 }}>
                    <Input
                        size="small"
                        value={newName}
                        onChange={(e) => setNewName(e.target.value)}
                        onPressEnter={add}
                        placeholder={t('pages.skills.needInputs.namePlaceholder', 'Parameter name')}
                        style={{ width: 140, borderRadius: 4 }}
                    />
                    <Select
                        size="small"
                        value={newType}
                        onChange={setNewType}
                        options={TYPE_OPTIONS}
                        style={{ width: 100 }}
                    />
                    <Button
                        size="small"
                        type={newRequired ? 'primary' : 'default'}
                        onClick={() => setNewRequired(!newRequired)}
                        style={{ fontSize: 11, padding: '0 6px', height: 24 }}
                    >
                        {newRequired ? t('common.required', 'Required') : t('common.optional', 'Optional')}
                    </Button>
                    <Input
                        size="small"
                        value={newDesc}
                        onChange={(e) => setNewDesc(e.target.value)}
                        placeholder={t('pages.skills.needInputs.descPlaceholder', 'Description (optional)')}
                        style={{ width: 200, borderRadius: 4 }}
                    />
                </Space>
                <Button
                    size="small"
                    type="primary"
                    icon={<PlusOutlined />}
                    onClick={add}
                    disabled={!newName.trim()}
                    style={{ marginTop: 1 }}
                >
                    {t('common.add', 'Add')}
                </Button>
            </div>
        </div>
    );
};

// ============================================================================
// ModeSelector: Multi-select for inputModes / outputModes
// ============================================================================
interface ModeSelectorProps {
    value: string; // JSON string: string[]
    onChange: (value: string) => void;
    availableModes?: { value: string; label: string }[];
}

const DEFAULT_MODES = [
    { value: 'text', label: 'Text' },
    { value: 'file', label: 'File' },
    { value: 'image', label: 'Image' },
    { value: 'audio', label: 'Audio' },
    { value: 'video', label: 'Video' },
    { value: 'url', label: 'URL' },
    { value: 'code', label: 'Code' },
    { value: 'json', label: 'JSON' },
    { value: 'table', label: 'Table' },
    { value: 'command', label: 'Command' },
    { value: 'event', label: 'Event' },
];

export const ModeSelector: React.FC<ModeSelectorProps> = ({
    value,
    onChange,
    availableModes = DEFAULT_MODES,
}) => {
    const selected: string[] = useMemo(() => {
        if (!value || value.trim() === '') return [];
        try {
            const parsed = JSON.parse(value);
            return Array.isArray(parsed) ? parsed : [];
        } catch {
            return [];
        }
    }, [value]);

    const toggle = (mode: string) => {
        const next = selected.includes(mode)
            ? selected.filter((m) => m !== mode)
            : [...selected, mode];
        onChange(JSON.stringify(next));
    };

    return (
        <Space wrap size={4}>
            {availableModes.map((mode) => (
                <Button
                    key={mode.value}
                    size="small"
                    type={selected.includes(mode.value) ? 'primary' : 'default'}
                    onClick={() => toggle(mode.value)}
                    style={{
                        borderRadius: 6,
                        fontSize: 12,
                        height: 28,
                        padding: '0 10px',
                    }}
                >
                    {mode.label}
                </Button>
            ))}
        </Space>
    );
};

// ============================================================================
// JSONFallbackEditor: Fallback textarea for raw JSON editing
// ============================================================================
interface JSONFallbackEditorProps {
    value: string;
    onChange: (value: string) => void;
    rows?: number;
    placeholder?: string;
    error?: string;
}

export const JSONFallbackEditor: React.FC<JSONFallbackEditorProps> = ({
    value,
    onChange,
    rows = 4,
    placeholder = '{"key": "value"}',
    error,
}) => (
    <div>
        <TextArea
            value={value}
            onChange={(e) => onChange(e.target.value)}
            rows={rows}
            placeholder={placeholder}
            style={{
                fontFamily: 'monospace',
                fontSize: 13,
                lineHeight: 1.6,
                borderColor: error ? '#ff4d4f' : undefined,
            }}
        />
        {error && (
            <Text type="danger" style={{ fontSize: 12, marginTop: 4, display: 'block' }}>
                {error}
            </Text>
        )}
    </div>
);
