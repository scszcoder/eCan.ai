import React, { useState, useMemo } from 'react';
import { Modal, Input, Typography, Toast, Spin, Checkbox } from '@douyinfe/semi-ui';
import { useTranslation } from 'react-i18next';
import { usePromptStore } from '../../../../stores/promptStore';
import { useUserStore } from '../../../../stores/userStore';
import type { Prompt, PromptSection } from '../../../../pages/Prompts/types';
import { useClientContext, WorkflowDocument, useService } from '@flowgram.ai/free-layout-editor';

const { Text, Title } = Typography;

/** Describes one inline prompt found on a node */
export interface InlinePromptEntry {
  nodeId: string;
  nodeName: string;
  nodeType: string; // 'llm' | 'browser-automation'
  field: 'systemPrompt' | 'prompt';
  fieldLabel: string;
  content: string; // the raw inline prompt text
}

/**
 * Scan the current document JSON and return all inline prompt entries.
 * A prompt is considered "inline" when the corresponding promptSelection or
 * per-field promptId/systemPromptId is 'inline' / 'in-line' / absent.
 */
export function collectInlinePrompts(docJson: any): InlinePromptEntry[] {
  const entries: InlinePromptEntry[] = [];
  const nodes = docJson?.nodes || [];

  const PROMPT_NODE_TYPES = ['llm', 'browser-automation'];

  const processNodes = (nodeList: any[]) => {
    for (const node of nodeList) {
      const type = node?.type || node?.data?.type || '';
      if (!PROMPT_NODE_TYPES.includes(type)) {
        // recurse into subcanvas if present
        if (node?.data?.subcanvas?.nodes) {
          processNodes(node.data.subcanvas.nodes);
        }
        continue;
      }

      const iv = node?.data?.inputsValues || {};
      const nodeName = node?.data?.title || node?.data?.name || node?.id || 'Unnamed';

      // The top-level promptSelection field. 'inline' means inline mode.
      const promptSelection = iv.promptSelection?.content ?? 'inline';

      // Check systemPrompt
      const sysId = iv.systemPromptId?.content ?? 'in-line';
      const sysText = iv.systemPrompt?.content ?? '';
      // Inline if: top-level is inline AND per-field is 'in-line' (or absent)
      if (
        (promptSelection === 'inline') &&
        (sysId === 'in-line' || sysId === 'inline' || !sysId) &&
        typeof sysText === 'string' && sysText.trim().length > 0
      ) {
        entries.push({
          nodeId: node.id,
          nodeName,
          nodeType: type,
          field: 'systemPrompt',
          fieldLabel: 'System Prompt',
          content: sysText,
        });
      }

      // Check user prompt
      const promptId = iv.promptId?.content ?? 'in-line';
      const promptText = iv.prompt?.content ?? '';
      if (
        (promptSelection === 'inline') &&
        (promptId === 'in-line' || promptId === 'inline' || !promptId) &&
        typeof promptText === 'string' && promptText.trim().length > 0
      ) {
        entries.push({
          nodeId: node.id,
          nodeName,
          nodeType: type,
          field: 'prompt',
          fieldLabel: 'User Prompt',
          content: promptText,
        });
      }

      // recurse into subcanvas
      if (node?.data?.subcanvas?.nodes) {
        processNodes(node.data.subcanvas.nodes);
      }
    }
  };

  processNodes(nodes);
  return entries;
}

/** Build a Prompt object from raw text, using a single "custom" section. */
function buildPromptFromText(
  title: string,
  text: string,
  owner: string,
  promptType: 'systemPrompt' | 'prompt',
): Prompt {
  const id = `pr-${Date.now()}-${Math.floor(Math.random() * 100000)}`;
  const sectionType = promptType === 'systemPrompt' ? 'role' : 'instructions';
  const section: PromptSection = {
    id: `sec-${Date.now()}`,
    type: sectionType,
    items: [text],
  };

  return {
    id,
    title,
    topic: title,
    usageCount: 0,
    sections: promptType === 'systemPrompt' ? [section] : [],
    userSections: promptType === 'prompt' ? [section] : [],
    humanInputs: [],
    source: 'my_prompts',
    owner,
  };
}

interface SavePromptsModalProps {
  visible: boolean;
  onClose: () => void;
}

export const SavePromptsModal: React.FC<SavePromptsModalProps> = ({ visible, onClose }) => {
  const { t } = useTranslation('skillEditor');
  const ctx = useClientContext();
  const workflowDocument = useService(WorkflowDocument);
  const username = useUserStore((s) => s.username || 'user');
  const promptSave = usePromptStore((s) => s.save);
  const promptFetch = usePromptStore((s) => s.fetch);

  // Collect inline prompts from current document
  const entries = useMemo(() => {
    if (!visible) return [];
    try {
      const docJson = ctx.document.toJSON();
      return collectInlinePrompts(docJson);
    } catch {
      return [];
    }
  }, [visible, ctx]);

  // Per-entry state: name input and enabled checkbox
  const [names, setNames] = useState<Record<string, string>>({});
  const [enabled, setEnabled] = useState<Record<string, boolean>>({});
  const [saving, setSaving] = useState(false);

  // Initialize defaults when entries change
  React.useEffect(() => {
    if (!visible) return;
    const newNames: Record<string, string> = {};
    const newEnabled: Record<string, boolean> = {};
    entries.forEach((e) => {
      const key = `${e.nodeId}_${e.field}`;
      newNames[key] = `${e.nodeName}_${e.field === 'systemPrompt' ? 'sys' : 'usr'}`;
      newEnabled[key] = true;
    });
    setNames(newNames);
    setEnabled(newEnabled);
  }, [entries, visible]);

  const handleSave = async () => {
    setSaving(true);
    let savedCount = 0;
    let failedCount = 0;

    try {
      for (const entry of entries) {
        const key = `${entry.nodeId}_${entry.field}`;
        if (!enabled[key]) continue;
        const name = (names[key] || '').trim();
        if (!name) continue;

        const promptObj = buildPromptFromText(
          name,
          entry.content,
          username,
          entry.field,
        );

        const saved = await promptSave(username, promptObj);
        if (saved) {
          savedCount++;
          // Update the live node to reference the saved prompt
          try {
            const liveNode = workflowDocument.getNode(entry.nodeId) as any;
            if (liveNode) {
              // Update via raw and json data paths
              const updatePaths = [liveNode.raw?.data?.inputsValues, liveNode.json?.data?.inputsValues].filter(Boolean);
              for (const iv of updatePaths) {
                // Set the per-field promptId/systemPromptId to the saved prompt's ID.
                // Leave promptSelection as 'inline' — the per-field selectors handle
                // individual prompt references independently.
                if (entry.field === 'systemPrompt') {
                  iv.systemPromptId = { type: 'constant', content: saved.id };
                } else {
                  iv.promptId = { type: 'constant', content: saved.id };
                }
              }
            }
          } catch (e) {
            console.warn('[SavePrompts] Failed to update live node:', entry.nodeId, e);
          }
        } else {
          failedCount++;
        }
      }

      // Refresh prompt store so selectors pick up new prompts
      await promptFetch(username, true);

      if (failedCount === 0 && savedCount > 0) {
        Toast.success({ content: t('sheetsMenu.savePromptsSaved', { count: savedCount }) });
      } else if (savedCount > 0 && failedCount > 0) {
        Toast.warning({ content: t('sheetsMenu.savePromptsPartialError', { saved: savedCount, failed: failedCount }) });
      } else if (savedCount === 0) {
        Toast.info({ content: t('sheetsMenu.savePromptsNone') });
      }
    } catch (e) {
      console.error('[SavePrompts] Error:', e);
      Toast.error({ content: t('sheetsMenu.savePromptsError') });
    } finally {
      setSaving(false);
      onClose();
    }
  };

  return (
    <Modal
      title={t('sheetsMenu.savePromptsTitle')}
      visible={visible}
      onCancel={onClose}
      onOk={handleSave}
      okText={saving ? t('sheetsMenu.savePromptsSaving') : 'Save'}
      cancelText="Cancel"
      okButtonProps={{ disabled: saving || entries.length === 0 }}
      width={640}
      maskClosable={false}
    >
      {saving && (
        <div style={{ textAlign: 'center', padding: 24 }}>
          <Spin size="large" />
          <div style={{ marginTop: 12 }}>{t('sheetsMenu.savePromptsSaving')}</div>
        </div>
      )}

      {!saving && entries.length === 0 && (
        <Text type="tertiary">{t('sheetsMenu.savePromptsNone')}</Text>
      )}

      {!saving && entries.length > 0 && (
        <div>
          <Text type="tertiary" size="small" style={{ display: 'block', marginBottom: 16 }}>
            {t('sheetsMenu.savePromptsDesc')}
          </Text>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
            {entries.map((entry) => {
              const key = `${entry.nodeId}_${entry.field}`;
              return (
                <div
                  key={key}
                  style={{
                    border: '1px solid #e8e8e8',
                    borderRadius: 8,
                    padding: 12,
                    background: enabled[key] ? '#fafafa' : '#f0f0f0',
                    opacity: enabled[key] ? 1 : 0.6,
                  }}
                >
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }}>
                    <Checkbox
                      checked={!!enabled[key]}
                      onChange={(e) =>
                        setEnabled((prev) => ({ ...prev, [key]: !!e.target.checked }))
                      }
                    />
                    <Title heading={6} style={{ margin: 0 }}>
                      {t('sheetsMenu.savePromptsNodeLabel', { name: entry.nodeName, type: entry.nodeType })}
                    </Title>
                    <Text type="tertiary" size="small">
                      — {entry.field === 'systemPrompt'
                        ? t('sheetsMenu.savePromptsSystemPrompt')
                        : t('sheetsMenu.savePromptsUserPrompt')}
                    </Text>
                  </div>
                  <Input
                    value={names[key] || ''}
                    onChange={(val) => setNames((prev) => ({ ...prev, [key]: val }))}
                    placeholder={t('sheetsMenu.savePromptsNamePlaceholder')}
                    disabled={!enabled[key]}
                    style={{ marginBottom: 8 }}
                  />
                  <div
                    style={{
                      maxHeight: 80,
                      overflow: 'auto',
                      background: '#fff',
                      border: '1px solid #e8e8e8',
                      borderRadius: 4,
                      padding: 8,
                      fontSize: 12,
                      fontFamily: 'monospace',
                      whiteSpace: 'pre-wrap',
                      color: '#666',
                    }}
                  >
                    {entry.content.length > 300
                      ? entry.content.slice(0, 300) + '…'
                      : entry.content}
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}
    </Modal>
  );
};
