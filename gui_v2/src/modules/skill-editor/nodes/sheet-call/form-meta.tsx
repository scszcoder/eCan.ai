import React, { useMemo } from 'react';
import { FormMeta, FormRenderProps, useClientContext } from '@flowgram.ai/free-layout-editor';
import { Select, Input, Typography, Button, Radio, Space } from '@douyinfe/semi-ui';
import { FlowNodeJSON } from '../../typings';
import { useSheetsStore } from '../../stores/sheets-store';
import { FormHeader, FormContent } from '../../form-components';

type MappingValue = { kind: 'const'; value: any } | { kind: 'local-port'; nodeId: string; port: string };

const MappingRow: React.FC<{
  label: string;
  value?: MappingValue;
  onChange: (v: MappingValue) => void;
  nodeOptions?: Array<{ label: string; value: string }>;
}> = ({ label, value, onChange }) => {
  const kind = value?.kind || 'const';
  const [constText, setConstText] = React.useState(
    value && value.kind === 'const' ? JSON.stringify(value.value, null, 2) : ''
  );
  const [nodeId, setNodeId] = React.useState(value && value.kind === 'local-port' ? value.nodeId : '');
  const [port, setPort] = React.useState(value && value.kind === 'local-port' ? value.port : '');

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
      <Typography.Text strong>{label}</Typography.Text>
      <Radio.Group
        type="button"
        value={kind}
        onChange={(k) => {
          const nextKind = (k as any).target ? (k as any).target.value : k;
          if (nextKind === 'const') {
            onChange({ kind: 'const', value: constText ? JSON.parseSafe(constText) : undefined } as any);
          } else {
            onChange({ kind: 'local-port', nodeId, port } as any);
          }
        }}
      >
        <Radio value="const">Constant</Radio>
        <Radio value="local-port">Local Port</Radio>
      </Radio.Group>
      {kind === 'const' ? (
        <Input
          type="textarea"
          placeholder="JSON value"
          value={constText}
          onChange={(v) => setConstText(v)}
          onBlur={() => {
            try {
              const parsed = constText ? JSON.parse(constText) : undefined;
              onChange({ kind: 'const', value: parsed } as any);
            } catch {}
          }}
          style={{ fontFamily: 'monospace', height: 88 }}
        />
      ) : (
        <Space>
          <Select
            placeholder="nodeId"
            value={nodeId}
            onChange={(v) => { setNodeId(v as string); onChange({ kind: 'local-port', nodeId: v as string, port } as any); }}
            style={{ minWidth: 160 }}
            optionList={(MappingRow as any).nodeOptions || []}
          />
          <Input placeholder="port" value={port} onChange={setPort} onBlur={() => onChange({ kind: 'local-port', nodeId, port } as any)} />
        </Space>
      )}
    </div>
  );
};

// JSON.parseSafe helper
(JSON as any).parseSafe = (s: string) => {
  try {
    return JSON.parse(s);
  } catch {
    return s;
  }
};

const SheetCallForm: React.FC<FormRenderProps<FlowNodeJSON>> = ({ form }) => {
  // Compatibility setter: prefer setFieldValue; fallback to setValue if provided by form API
  const setField = React.useCallback((name: string, value: any) => {
    const anyForm: any = form as any;
    if (anyForm && typeof anyForm.setFieldValue === 'function') {
      anyForm.setFieldValue(name, value);
    } else if (anyForm && typeof anyForm.setValue === 'function') {
      anyForm.setValue(name, value);
    } else {
      // last-resort: try assign into values object (won't trigger form updates but avoids crash)
      try {
        const parts = name.split('.');
        let cur: any = anyForm?.values || {};
        for (let i = 0; i < parts.length - 1; i++) {
          const k = parts[i];
          cur[k] = cur[k] || {};
          cur = cur[k];
        }
        cur[parts[parts.length - 1]] = value;
      } catch {}
      console.warn('[SheetCallForm] Form API does not expose setFieldValue/setValue, updated values shallowly.');
    }
  }, [form]);
  const sheets = useSheetsStore((s) => s.sheets);
  const ctx = useClientContext();
  const sheetOptions = useMemo(
    () => Object.values(sheets).map((s) => ({ label: `${s.name} (${s.id})`, value: s.id })),
    [sheets]
  );

  const data = form.values.data || {};
  const openSheet = useSheetsStore((s) => s.openSheet);

  const target = data.targetSheetId ? sheets[data.targetSheetId] : null;
  const doc = target?.document || { nodes: [] };
  const inputsNode = doc.nodes?.find((n: any) => n.type === 'sheet-inputs');
  const outputsNode = doc.nodes?.find((n: any) => n.type === 'sheet-outputs');
  const exposedInputs: string[] = (inputsNode?.data?.interface?.inputs || []).map((x: any) => x.name).filter(Boolean);
  const exposedOutputs: string[] = (outputsNode?.data?.interface?.outputs || []).map((x: any) => x.name).filter(Boolean);

  // Build node dropdown from current active document
  let nodeOptions: Array<{ label: string; value: string }> = [];
  try {
    const currentDoc = ctx?.document?.toJSON();
    if (currentDoc?.nodes) {
      nodeOptions = currentDoc.nodes.map((n: any) => ({ label: `${n.data?.title || n.type} (${n.id})`, value: n.id }));
    }
  } catch {}

  // Compute warnings for missing mappings
  const missingInputs = exposedInputs.filter((name) => !(data.inputMapping || {})[name]);
  const missingOutputs = exposedOutputs.filter((name) => !(data.outputMapping || {})[name]);

  // Update title badge dynamically based on warnings (simple in-canvas indicator)
  React.useEffect(() => {
    const hasWarn = missingInputs.length > 0 || missingOutputs.length > 0;
    const title: string = data.title || data.callName || 'SheetCall';
    const badge = ' ⚠';
    const hasBadge = title.endsWith(badge);
    if (hasWarn && !hasBadge) {
      setField('data.title', `${title}${badge}`);
    } else if (!hasWarn && hasBadge) {
      setField('data.title', title.slice(0, -badge.length));
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [JSON.stringify(missingInputs), JSON.stringify(missingOutputs)]);

  return (
    <>
      <FormHeader />
      <FormContent>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
          <Typography.Text strong>Sheet Call</Typography.Text>
      <Input
        value={data.callName || ''}
        onChange={(v) => setField('data.callName', v)}
        placeholder="Call name"
      />
      <Select
        value={data.targetSheetId || ''}
        placeholder="Select target sheet"
        optionList={sheetOptions}
        onChange={(v) => {
          const id = v as string;
          setField('data.targetSheetId', id);
          try {
            const sheet = sheets[id];
            if (sheet) {
              // Store name for backend compatibility (flowgram2langgraph reads target_sheet/targetSheet)
              setField('data.target_sheet', sheet.name);
              setField('data.targetSheet', sheet.name);
            }
          } catch {}
        }}
      />
      {data.targetSheetId ? (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
          {(missingInputs.length > 0 || missingOutputs.length > 0) && (
            <Typography.Text type="danger">
              Missing mappings: {missingInputs.length > 0 ? `inputs(${missingInputs.join(', ')})` : ''}
              {missingInputs.length > 0 && missingOutputs.length > 0 ? ' • ' : ''}
              {missingOutputs.length > 0 ? `outputs(${missingOutputs.join(', ')})` : ''}
            </Typography.Text>
          )}
          <Typography.Text strong>Input Mapping</Typography.Text>
          {exposedInputs.length === 0 && (
            <Typography.Text type="tertiary">Target sheet has no declared inputs (add a sheet-inputs node).</Typography.Text>
          )}
          {exposedInputs.map((name) => (
            <MappingRow
              key={name}
              label={name}
              value={(data.inputMapping || {})[name] as any}
              onChange={(v) => setField(`data.inputMapping.${name}`, v)}
              nodeOptions={nodeOptions}
            />
          ))}
          <Typography.Text strong>Output Mapping</Typography.Text>
          {exposedOutputs.length === 0 && (
            <Typography.Text type="tertiary">Target sheet has no declared outputs (add a sheet-outputs node).</Typography.Text>
          )}
          {exposedOutputs.map((name) => (
            <MappingRow
              key={name}
              label={name}
              value={(data.outputMapping || {})[name] as any}
              onChange={(v) => setField(`data.outputMapping.${name}`, v)}
              nodeOptions={nodeOptions}
            />
          ))}
        </div>
      ) : null}

      <div style={{ display: 'flex', gap: 8, marginTop: 8 }}>
        <Button disabled={!data.targetSheetId} onClick={() => data.targetSheetId && openSheet(data.targetSheetId)}>Jump to target sheet</Button>
      </div>
        </div>
      </FormContent>
    </>
  );
};

export const formMeta: FormMeta<FlowNodeJSON> = {
  render: (props) => <SheetCallForm {...props} />,
};
