import React, { useMemo, useState } from 'react';
import { Typography, Tooltip, Input } from '@douyinfe/semi-ui';
import { useSkillInfoStore } from '../../stores/skill-info-store';

/**
 * Inline skill name display/editor to place on the main tools bar.
 * - Shows current `skillInfo.skillName`
 * - Double-click to edit, Enter/Escape to confirm/cancel
 */
export const SkillNameBadge: React.FC = () => {
  const skillInfo = useSkillInfoStore((s) => s.skillInfo);
  const setSkillInfo = useSkillInfoStore((s) => s.setSkillInfo);
  const setHasUnsavedChanges = useSkillInfoStore((s) => s.setHasUnsavedChanges);

  const value = skillInfo?.skillName || 'Untitled';
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(value);

  const display = useMemo(() => (value?.trim().length ? value : 'Untitled'), [value]);

  const commit = (next: string) => {
    const trimmed = next.trim();
    if (!skillInfo) return setEditing(false);
    if (!trimmed || trimmed === value) {
      setEditing(false);
      setDraft(value);
      return;
    }
    setSkillInfo({ ...skillInfo, skillName: trimmed });
    setHasUnsavedChanges(true);
    setEditing(false);
  };

  return (
    <div style={{ display: 'inline-flex', alignItems: 'center', margin: '0 8px' }}>
      {editing ? (
        <Input
          autoFocus
          size="small"
          value={draft}
          onChange={(v) => setDraft(v)}
          onEnterPress={() => commit(draft)}
          onBlur={() => commit(draft)}
          onKeyDown={(e) => {
            if (e.key === 'Escape') {
              setEditing(false);
              setDraft(value);
            }
          }}
          style={{ width: 220 }}
        />
      ) : (
        <Tooltip content="Double-click to rename skill">
          <Typography.Text
            strong
            onDoubleClick={() => {
              setDraft(value);
              setEditing(true);
            }}
            style={{ cursor: 'text', userSelect: 'none' }}
          >
            {display}
          </Typography.Text>
        </Tooltip>
      )}
    </div>
  );
};
