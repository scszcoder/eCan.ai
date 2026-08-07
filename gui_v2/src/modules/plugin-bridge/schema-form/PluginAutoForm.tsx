/**
 * PluginAutoForm — minimal JSON-Schema → Ant Design form renderer.
 *
 * Scope (Phase 2): cover the schema shapes used by feige_chat and the
 * shapes documented in HOOK_BUNDLES.md authoring guide. Specifically:
 *   - type: object             (top-level container)
 *   - type: string             (text, optional enum)
 *   - type: integer / number   (with minimum/maximum)
 *   - type: boolean            (switch)
 *   - type: object with additionalProperties: {type: string}
 *                              (rendered as a key/value editor)
 *
 * What this does NOT do (intentionally — swap to @rjsf if you need them):
 *   - nested object children, arrays of objects, $ref, oneOf/anyOf,
 *     custom widgets, validation messages other than "required".
 *
 * Lives in modules/plugin-bridge so both the Plugins page and the
 * skill-editor's per-node hookBundles UI can import the same component.
 */

import React, { useCallback, useMemo } from 'react';
import { Form, Input, InputNumber, Switch, Select, Button, Space, Tooltip, Typography } from 'antd';
import { DeleteOutlined, PlusOutlined, InfoCircleOutlined } from '@ant-design/icons';

const { Text } = Typography;

// JSON-Schema shape we actually consume — keeping this loose because plugin
// authors will write whatever they want and we just degrade gracefully.
export interface JsonSchema {
  type?: string;
  title?: string;
  description?: string;
  default?: unknown;
  minimum?: number;
  maximum?: number;
  enum?: unknown[];
  required?: string[];
  properties?: Record<string, JsonSchema>;
  additionalProperties?: boolean | JsonSchema;
}

export interface PluginAutoFormProps {
  schema: JsonSchema | null | undefined;
  /** Current values; uses schema defaults when a key is missing. */
  value: Record<string, unknown> | null | undefined;
  /** Called on every edit with the merged record. */
  onChange: (next: Record<string, unknown>) => void;
  /** Hide the actual edit controls; useful for "read-only" preview mode. */
  disabled?: boolean;
}

/** Resolve the value for a key, falling back to schema default, falling back to undefined. */
function resolveValue(
  key: string,
  schema: JsonSchema | undefined,
  value: Record<string, unknown> | null | undefined
): unknown {
  if (value && Object.prototype.hasOwnProperty.call(value, key)) {
    return value[key];
  }
  return schema?.default;
}

function isObjectOfStrings(schema: JsonSchema): boolean {
  return (
    schema.type === 'object' &&
    typeof schema.additionalProperties === 'object' &&
    (schema.additionalProperties as JsonSchema)?.type === 'string'
  );
}

const FieldLabel: React.FC<{ title: string; description?: string; required?: boolean }> = ({
  title,
  description,
  required,
}) => (
  <Space size={4}>
    <Text>{title}</Text>
    {required ? <Text type="danger">*</Text> : null}
    {description ? (
      <Tooltip title={description}>
        <InfoCircleOutlined style={{ color: 'var(--ant-color-text-quaternary)' }} />
      </Tooltip>
    ) : null}
  </Space>
);

const StringField: React.FC<{
  schema: JsonSchema;
  value: unknown;
  onChange: (v: string) => void;
  disabled?: boolean;
}> = ({ schema, value, onChange, disabled }) => {
  const str = typeof value === 'string' ? value : '';
  if (Array.isArray(schema.enum) && schema.enum.length > 0) {
    return (
      <Select
        disabled={disabled}
        value={str}
        onChange={(v) => onChange(String(v ?? ''))}
        options={schema.enum.map((e) => ({ label: String(e), value: String(e) }))}
        style={{ width: '100%' }}
      />
    );
  }
  return (
    <Input
      disabled={disabled}
      value={str}
      onChange={(e) => onChange(e.target.value)}
    />
  );
};

const NumberField: React.FC<{
  schema: JsonSchema;
  value: unknown;
  onChange: (v: number | null) => void;
  disabled?: boolean;
}> = ({ schema, value, onChange, disabled }) => {
  const isInt = schema.type === 'integer';
  return (
    <InputNumber
      disabled={disabled}
      value={typeof value === 'number' ? value : (value == null ? null : Number(value))}
      onChange={(v) => onChange(v == null ? null : (isInt ? Math.trunc(Number(v)) : Number(v)))}
      min={schema.minimum}
      max={schema.maximum}
      step={isInt ? 1 : 0.01}
      style={{ width: '100%' }}
    />
  );
};

const BooleanField: React.FC<{
  value: unknown;
  onChange: (v: boolean) => void;
  disabled?: boolean;
}> = ({ value, onChange, disabled }) => (
  <Switch disabled={disabled} checked={!!value} onChange={(v) => onChange(!!v)} />
);

/** Key/value editor for object-of-strings (e.g. quick_replies). */
const StringMapField: React.FC<{
  value: unknown;
  onChange: (v: Record<string, string>) => void;
  disabled?: boolean;
}> = ({ value, onChange, disabled }) => {
  const entries = useMemo(() => {
    const obj = (value && typeof value === 'object' && !Array.isArray(value)) ? value as Record<string, unknown> : {};
    return Object.entries(obj).map(([k, v]) => [k, typeof v === 'string' ? v : String(v ?? '')] as [string, string]);
  }, [value]);

  const setEntries = useCallback(
    (next: Array<[string, string]>) => {
      const out: Record<string, string> = {};
      for (const [k, v] of next) {
        if (k.length > 0) out[k] = v;
      }
      onChange(out);
    },
    [onChange]
  );

  return (
    <Space direction="vertical" style={{ width: '100%' }} size={4}>
      {entries.map(([k, v], i) => (
        <Space.Compact key={i} style={{ width: '100%' }}>
          <Input
            placeholder="key"
            value={k}
            disabled={disabled}
            onChange={(e) => {
              const next = [...entries];
              next[i] = [e.target.value, v];
              setEntries(next);
            }}
            style={{ width: '40%' }}
          />
          <Input
            placeholder="value"
            value={v}
            disabled={disabled}
            onChange={(e) => {
              const next = [...entries];
              next[i] = [k, e.target.value];
              setEntries(next);
            }}
            style={{ width: '55%' }}
          />
          <Button
            danger
            disabled={disabled}
            icon={<DeleteOutlined />}
            onClick={() => {
              const next = [...entries];
              next.splice(i, 1);
              setEntries(next);
            }}
          />
        </Space.Compact>
      ))}
      <Button
        size="small"
        icon={<PlusOutlined />}
        disabled={disabled}
        onClick={() => setEntries([...entries, ['', '']])}
      >
        Add entry
      </Button>
    </Space>
  );
};

/** Render a single property; switches widget based on schema.type. */
const PropertyField: React.FC<{
  name: string;
  schema: JsonSchema;
  required: boolean;
  value: unknown;
  onChange: (v: unknown) => void;
  disabled?: boolean;
}> = ({ name, schema, required, value, onChange, disabled }) => {
  let widget: React.ReactNode = null;

  if (schema.type === 'object' && isObjectOfStrings(schema)) {
    widget = (
      <StringMapField
        value={value}
        onChange={(v) => onChange(v)}
        disabled={disabled}
      />
    );
  } else if (schema.type === 'string') {
    widget = (
      <StringField schema={schema} value={value} disabled={disabled} onChange={(v) => onChange(v)} />
    );
  } else if (schema.type === 'integer' || schema.type === 'number') {
    widget = (
      <NumberField schema={schema} value={value} disabled={disabled} onChange={(v) => onChange(v)} />
    );
  } else if (schema.type === 'boolean') {
    widget = (
      <BooleanField value={value} disabled={disabled} onChange={(v) => onChange(v)} />
    );
  } else {
    // Unsupported type — show as monospace JSON so user can still see/edit raw.
    widget = (
      <Input.TextArea
        disabled={disabled}
        value={value == null ? '' : JSON.stringify(value, null, 2)}
        onChange={(e) => {
          try {
            onChange(JSON.parse(e.target.value));
          } catch {
            onChange(e.target.value); // keep as string while typing
          }
        }}
        autoSize={{ minRows: 2, maxRows: 6 }}
        style={{ fontFamily: 'monospace', fontSize: 12 }}
      />
    );
  }

  return (
    <Form.Item
      label={
        <FieldLabel
          title={schema.title || name}
          description={schema.description}
          required={required}
        />
      }
      style={{ marginBottom: 12 }}
    >
      {widget}
    </Form.Item>
  );
};

const EMPTY_OBJECT: Record<string, unknown> = {};

/** Top-level form: schema must be (or coerce to) type: object. */
export const PluginAutoForm: React.FC<PluginAutoFormProps> = ({
  schema,
  value,
  onChange,
  disabled,
}) => {
  if (!schema || schema.type !== 'object' || !schema.properties) {
    return (
      <Text type="secondary">
        This plugin does not declare a <code>config_schema</code>. Use the JSON config field on the
        node, or ask the plugin author to add a schema.
      </Text>
    );
  }
  const required = new Set(schema.required || []);
  const properties = schema.properties;
  const currentValue = value || EMPTY_OBJECT;

  const updateField = (key: string, next: unknown) => {
    const merged = { ...currentValue, [key]: next };
    onChange(merged);
  };

  return (
    <Form layout="vertical" disabled={disabled}>
      {Object.entries(properties).map(([key, propSchema]) => (
        <PropertyField
          key={key}
          name={key}
          schema={propSchema}
          required={required.has(key)}
          value={resolveValue(key, propSchema, currentValue)}
          onChange={(v) => updateField(key, v)}
          disabled={disabled}
        />
      ))}
    </Form>
  );
};

export default PluginAutoForm;
