/**
 * History Button Component
 * Opens the skill version history modal
 */

import React, { useState, useRef } from 'react';
import { useTranslation } from 'react-i18next';
import { Tooltip, IconButton, Toast } from '@douyinfe/semi-ui';
import { IconHistoryColored } from '../tools/colored-icons';
import { HistoryModal } from './HistoryModal';
import { useSkillHistoryStore } from '../../stores/skill-history-store';
import { useSkillInfoStore } from '../../stores/skill-info-store';
import { useSheetsStore } from '../../stores/sheets-store';
import { SkillHistoryRecord } from '../../types/skill-history';
import { useClientContext } from '@flowgram.ai/free-layout-editor';
import { looksLikeBundle, normalizeBundle } from '../../utils/bundle-utils';

interface HistoryButtonProps {
  disabled?: boolean;
}

export const HistoryButton: React.FC<HistoryButtonProps> = ({ disabled }) => {
  const { t } = useTranslation('skillEditor');
  const [visible, setVisible] = useState(false);

  const skillInfo = useSkillInfoStore((state) => state.skillInfo);
  const skillId = (skillInfo as any)?.skillId || (skillInfo as any)?.id;

  const { fetchHistoryList, restoreFromHistory } = useSkillHistoryStore();

  // Capture editor document reference at mount time (safe, inside render)
  const { document: workflowDocument } = useClientContext();
  const documentRef = useRef(workflowDocument);
  documentRef.current = workflowDocument;

  const handleOpen = async () => {
    if (skillId) {
      await fetchHistoryList(skillId);
    }
    setVisible(true);
  };

  const handleClose = () => {
    setVisible(false);
  };

  /** Safe JSON parse — handles string, dict, or already-parsed values */
  const safeParse = (val: unknown, fallback = {}): Record<string, unknown> => {
    if (!val) return fallback as Record<string, unknown>;
    if (typeof val === 'object') return val as Record<string, unknown>;
    if (typeof val === 'string') {
      try { return JSON.parse(val); } catch { return fallback as Record<string, unknown>; }
    }
    return fallback as Record<string, unknown>;
  };

  const handleRestore = async (record: SkillHistoryRecord) => {
    console.log('[HistoryButton] Restore requested for version:', record.version, record.version_number);
    try {
      const result = await restoreFromHistory(record.id);

      if (!result || !result.success) {
        console.error('[HistoryButton] Restore API failed:', result);
        Toast.error({ content: t('history.restoreFailed') });
        return;
      }

      const skillData = result.skill_data;
      if (!skillData) {
        console.error('[HistoryButton] No skill_data in restore result:', result);
        Toast.error({ content: t('history.restoreFailed') });
        return;
      }

      // Parse diagram: might be a JSON string, a dict, or the whole skill_data IS the diagram
      const rawDiagram = skillData.diagram || skillData.workFlow || skillData;
      const diagram = safeParse(rawDiagram);
      const nodes = Array.isArray(diagram.nodes) ? diagram.nodes : [];
      const edges = Array.isArray(diagram.edges) ? diagram.edges : [];

      // Also parse config (might be a JSON string)
      const config = safeParse(skillData.config);

      console.log('[HistoryButton] Restoring diagram with nodes:', nodes.length, 'edges:', edges.length);

      // Apply restored data to the editor in the next tick
      setTimeout(() => {
        const doc = documentRef.current;
        const workflow = {
          nodes,
          edges,
          ...(diagram && typeof diagram === 'object' ? diagram : {}),
        };

        if (doc) {
          doc.clear();
          doc.fromJSON(workflow);
          doc.fitView && doc.fitView();
        }

        // Update skillInfo store with restored metadata
        useSkillInfoStore.getState().setSkillInfo({
          ...(skillInfo || {}),
          skillId: skillData.id || skillId,
          skillName: skillData.name || skillData.skillName || skillInfo?.skillName || '',
          version: skillData.version || skillInfo?.version || '1.0.0',
          description: skillData.description || '',
          lastModified: new Date().toISOString(),
          workFlow: workflow,
          schemaVersion: skillData.schemaVersion || (skillInfo as any)?.schemaVersion,
          config: config || skillInfo?.config,
        } as any);

        // Mark as unsaved so user knows to save
        useSkillInfoStore.getState().setHasUnsavedChanges(true);

        // Only load multi-sheet bundle when skill_data actually has bundle shape.
        // skill_files is a directory snapshot (path -> file content), NOT a SheetsBundle — never pass it to loadBundle.
        const rawBundle = skillData.bundle != null ? safeParse(skillData.bundle) : null;
        if (rawBundle && looksLikeBundle(rawBundle)) {
          const normalized = normalizeBundle(rawBundle);
          if (normalized) {
            useSheetsStore.getState().loadBundle(normalized);
          }
        }

        console.log('[HistoryButton] Editor refreshed. Nodes:', nodes.length);
      }, 0);

      Toast.success({ content: t('history.restoreSuccess', { version: record.version_number }) });
      setVisible(false);
    } catch (e) {
      console.error('[HistoryButton] Restore error:', e);
      Toast.error({ content: t('history.restoreFailed') });
    }
  };

  // Don't show badge if no skill is loaded
  if (!skillId) {
    return (
      <Tooltip content={t('toolbar.history') || 'Version History'}>
        <IconButton
          type="tertiary"
          theme="borderless"
          icon={<IconHistoryColored size={18} />}
          disabled={true}
        />
      </Tooltip>
    );
  }

  return (
    <>
      <Tooltip content={t('toolbar.history') || 'Version History'}>
        <IconButton
          type="tertiary"
          theme="borderless"
          icon={<IconHistoryColored size={18} />}
          disabled={disabled}
          onClick={handleOpen}
        />
      </Tooltip>

      <HistoryModal
        visible={visible}
        onClose={handleClose}
        onRestore={handleRestore}
      />
    </>
  );
};
