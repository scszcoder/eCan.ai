/**
 * Read-only view of the skill's TASK variables — the `{{var}}` placeholders in
 * its prompts, which are filled per-task rather than here.
 *
 * This tab exists because the variable icon is where people look for them, and
 * the neighbouring tabs are about something else entirely: Flowgram's global
 * scope describes node-to-node data TYPES and cannot hold a value. Sending
 * someone there to find a prompt variable wastes their time, so the panel now
 * shows the real list and says where it is edited.
 *
 * Source of truth stays elsewhere:
 *   declare  -> Skills page > Metadata > Required Inputs (need_inputs)
 *   fill in  -> Tasks page > the task's 任务变量 section (metadata.task_vars)
 */

import { useMemo } from 'react';
import { useClientContext } from '@flowgram.ai/free-layout-editor';
import { Typography, Tag, Tooltip } from '@douyinfe/semi-ui';

import { useSkillInfoStore } from '../../../stores/skill-info-store';
import { usePromptStore } from '../../../../../stores/promptStore';
import { collectPromptVars, makePromptResolver } from '../../../utils/prompt-vars';

const { Text } = Typography;

interface DeclaredVar {
  name: string;
  required?: boolean;
  description?: string;
  default?: any;
}

export function TaskVariablesPanel() {
  const skillInfo = useSkillInfoStore((s) => s.skillInfo);
  const prompts = usePromptStore((s) => s.prompts);
  const ctx = useClientContext();

  const declared: DeclaredVar[] = useMemo(() => {
    const list = (skillInfo as any)?.need_inputs;
    return Array.isArray(list) ? list : [];
  }, [skillInfo]);

  // Variables already present in the prompts but not declared yet. They are
  // added by the scan on the next save; showing them avoids the "I typed a
  // variable and nothing happened" gap between editing and saving.
  const pending: string[] = useMemo(() => {
    try {
      const doc: any = ctx?.document?.toJSON?.();
      const found = collectPromptVars(doc?.nodes, makePromptResolver(prompts as any));
      const known = new Set(declared.map((d) => String(d?.name || '')));
      return found.filter((name) => !known.has(name));
    } catch {
      return [];
    }
  }, [ctx, prompts, declared]);

  const hint = 'Declared in Skills > Metadata > Required Inputs. Values are entered per task (任务变量).';

  return (
    <div style={{ padding: '8px 4px', fontSize: 12 }}>
      <Text type="secondary" style={{ fontSize: 11, display: 'block', marginBottom: 8 }}>
        {hint}
      </Text>

      {declared.length === 0 && pending.length === 0 && (
        <Text type="secondary" style={{ fontSize: 11 }}>
          No task variables. Add a {'{{variable}}'} to a prompt and save — it is declared automatically.
        </Text>
      )}

      {declared.map((v) => (
        <div
          key={v.name}
          style={{ display: 'flex', alignItems: 'center', gap: 6, padding: '4px 0', flexWrap: 'wrap' }}
        >
          <Tooltip content={v.description || v.name}>
            <Text strong style={{ fontSize: 12 }}>{`{{${v.name}}}`}</Text>
          </Tooltip>
          {v.required ? <Tag size="small" color="red">required</Tag> : <Tag size="small" color="grey">optional</Tag>}
          {v.default !== undefined && v.default !== null && String(v.default) !== '' && (
            <Text type="secondary" style={{ fontSize: 11 }}>{`default: ${String(v.default)}`}</Text>
          )}
        </div>
      ))}

      {pending.length > 0 && (
        <div style={{ marginTop: 8, paddingTop: 6, borderTop: '1px solid rgba(255,255,255,0.12)' }}>
          <Text type="secondary" style={{ fontSize: 11, display: 'block', marginBottom: 4 }}>
            Found in prompts, declared on next save:
          </Text>
          {pending.map((name) => (
            <div key={name} style={{ padding: '2px 0' }}>
              <Text type="secondary" style={{ fontSize: 12 }}>{`{{${name}}}`}</Text>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
