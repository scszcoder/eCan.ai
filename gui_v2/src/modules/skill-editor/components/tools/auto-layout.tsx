/**
 * Auto-layout toolbar button for the skill editor.
 *
 * Uses flowgram's built-in dagre layout engine (same technology as n8n, Dify, Coze) with
 * carefully tuned parameters for maximum readability:
 *   - Left-to-right direction (standard for workflow editors)
 *   - Wider node & rank separation to prevent crowding
 *   - Greedy acyclicer to cleanly handle loops/cycles
 *   - Smooth animation so users can follow the transition
 *
 * Key API:
 *   tools.autoLayout(LayoutOptions) – passes options straight through to
 *   AutoLayoutService.layout() → dagre algorithm → node position animation.
 *   No custom algorithm needed; dagre handles crossing minimisation.
 */

import { useCallback, useState } from 'react';
import { useTranslation } from 'react-i18next';

import { usePlayground, usePlaygroundTools } from '@flowgram.ai/free-layout-editor';
import { IconButton, Toast, Tooltip } from '@douyinfe/semi-ui';

import { IconAutoLayoutColored } from './colored-icons';

/**
 * Dagre layout configuration.
 * Defaults from flowgram: nodesep=100, ranksep=100.
 * We increase spacing and enable cycle handling for better readability.
 */
const LAYOUT_CONFIG = {
  /** Left-to-right: matches natural reading direction of workflows. */
  rankdir: 'LR' as const,
  /** Vertical gap (px) between nodes in the same column – bigger = less crowded. */
  nodesep: 60,
  /** Horizontal gap (px) between adjacent columns. */
  ranksep: 200,
  /** Margin around the whole graph. */
  marginx: 60,
  marginy: 60,
  /**
   * Greedy acyclicer: reverses the minimum-weight set of back-edges so that
   * cyclical flows (loops, retries) are laid out cleanly instead of overlapping.
   */
  acyclicer: 'greedy' as const,
  /**
   * network-simplex: the gold-standard dagre ranker – minimises total edge
   * length while balancing crossing minimisation. Used by n8n, Dify, etc.
   */
  ranker: 'network-simplex' as const,
};

export const AutoLayout = () => {
  const { t } = useTranslation('skillEditor');
  const tools = usePlaygroundTools();
  const playground = usePlayground();
  const [loading, setLoading] = useState(false);

  const handleAutoLayout = useCallback(async () => {
    if (loading) return;
    setLoading(true);
    try {
      await tools.autoLayout({
        layoutConfig: LAYOUT_CONFIG,
        /** Smooth animation so users can watch nodes settle into place. */
        enableAnimation: true,
        animationDuration: 380,
        /** fitView is handled by autoLayout internally; keep it enabled. */
        disableFitView: false,
      });
      Toast.success({ content: t('toolbar.layoutOptimized') });
    } catch (err) {
      console.error('[SkillEditor] Auto layout failed:', err);
      Toast.error({ content: t('toolbar.layoutOptimizeFailed') });
    } finally {
      setLoading(false);
    }
  }, [loading, t, tools]);

  return (
    <Tooltip content={t('toolbar.autoLayout')}>
      <IconButton
        disabled={playground.config.readonly || loading}
        type="tertiary"
        theme="borderless"
        onClick={handleAutoLayout}
        icon={<IconAutoLayoutColored size={18} />}
      />
    </Tooltip>
  );
};
