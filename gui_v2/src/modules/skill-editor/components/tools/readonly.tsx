import { useCallback, useEffect } from 'react';

import { usePlayground } from '@flowgram.ai/free-layout-editor';
import { IconButton, Tooltip, Toast } from '@douyinfe/semi-ui';
import { IconUnlock, IconLock } from '@douyinfe/semi-icons';
import { useSkillInfoStore } from '../../stores/skill-info-store';

/**
 * Mode toggle: development <-> released
 * - released => editor readonly, skillInfo.mode = 'released'
 * - development => editor editable, skillInfo.mode = 'development'
 */
export const Readonly = () => {
  const playground = usePlayground();
  const skillInfo = useSkillInfoStore((s) => s.skillInfo);
  const setSkillInfo = useSkillInfoStore((s) => s.setSkillInfo);

  // Sync playground readOnly from mode on render
  useEffect(() => {
    if (!skillInfo) return;
    const isReleased = skillInfo.mode === 'released';
    if (playground.config.readonly !== isReleased) {
      // Defer to next tick to avoid mid-render flips in dependent components
      setTimeout(() => {
        playground.config.readonly = isReleased;
      }, 0);
    }
  }, [skillInfo?.mode, playground]);

  const toggleMode = useCallback(() => {
    if (!skillInfo) return;
    const nextMode = skillInfo.mode === 'released' ? 'development' : 'released';
    // Update store
    setSkillInfo({ ...skillInfo, mode: nextMode });
    // Reflect in editor (defer)
    setTimeout(() => {
      playground.config.readonly = nextMode === 'released';
    }, 0);
    // Defer toast to avoid nested update warnings within UI updates
    setTimeout(() => {
      try { Toast.info({ content: nextMode === 'released' ? 'Switched to Released (read-only)' : 'Switched to Development (editable)' }); } catch {}
    }, 0);
  }, [skillInfo, setSkillInfo, playground]);

  const isReleased = skillInfo?.mode === 'released' || playground.config.readonly;

  return isReleased ? (
    <Tooltip content="Develop (switch to editable)">
      <IconButton
        theme="borderless"
        type="tertiary"
        icon={<IconLock size="default" />}
        onClick={toggleMode}
      />
    </Tooltip>
  ) : (
    <Tooltip content="Release (switch to read-only)">
      <IconButton
        theme="borderless"
        type="tertiary"
        icon={<IconUnlock size="default" />}
        onClick={toggleMode}
      />
    </Tooltip>
  );
};
