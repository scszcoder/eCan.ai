import React, { useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Typography, Tooltip, Input } from '@douyinfe/semi-ui';
import { IconEdit } from '@douyinfe/semi-icons';
import styled from 'styled-components';
import { useSkillInfoStore } from '../../stores/skill-info-store';

const SkillNameContainer = styled.div`
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 6px 12px;
  margin: 0 8px;
  background: linear-gradient(135deg, rgba(99, 102, 241, 0.08) 0%, rgba(139, 92, 246, 0.08) 100%);
  border: none;
  border-radius: 8px;
  transition: all 0.3s ease;
  
  &:hover {
    background: linear-gradient(135deg, rgba(99, 102, 241, 0.12) 0%, rgba(139, 92, 246, 0.12) 100%);
    box-shadow: 0 2px 8px rgba(99, 102, 241, 0.15);
  }
`;

const SkillNameText = styled(Typography.Text)`
  cursor: text;
  user-select: none;
  font-weight: 600;
  font-size: 14px;
  color: #4338ca;
  letter-spacing: 0.3px;
  transition: color 0.2s ease;
  max-width: 200px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  display: inline-block;
  
  &:hover {
    color: #5b21b6;
  }
`;

const EditIconWrapper = styled.div`
  display: inline-flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  padding: 4px;
  border-radius: 4px;
  transition: all 0.2s ease;
  
  &:hover {
    background: rgba(99, 102, 241, 0.15);
  }
  
  &:active {
    transform: scale(0.95);
  }
`;

const EditIcon = styled(IconEdit)`
  color: rgba(99, 102, 241, 0.6);
  font-size: 14px;
  transition: all 0.2s ease;
  
  ${EditIconWrapper}:hover & {
    color: rgba(99, 102, 241, 1);
  }
`;

const StyledTooltip = styled(Tooltip)`
  .semi-portal-inner {
    .semi-tooltip-wrapper {
      .semi-tooltip {
        background: linear-gradient(135deg, #4338ca 0%, #5b21b6 100%);
        border: none;
        border-radius: 6px;
        padding: 6px 12px;
        font-size: 13px;
        font-weight: 500;
        letter-spacing: 0.2px;
        box-shadow: 0 4px 12px rgba(67, 56, 202, 0.25),
                    0 2px 6px rgba(0, 0, 0, 0.1);
        
        .semi-tooltip-content {
          color: #ffffff;
          text-shadow: 0 1px 2px rgba(0, 0, 0, 0.1);
        }
        
        .semi-tooltip-arrow {
          &::before {
            background: linear-gradient(135deg, #4338ca 0%, #5b21b6 100%);
            border: none;
          }
        }
      }
    }
  }
`;

const StyledInput = styled(Input)`
  .semi-input {
    border: none;
    border-radius: 6px;
    font-weight: 600;
    font-size: 14px;
    color: #4338ca;
    background: rgba(255, 255, 255, 0.95);
    padding: 4px 8px;
    transition: all 0.2s ease;
    box-shadow: none;
    
    &:hover {
      background: #ffffff;
      box-shadow: 0 0 0 1px rgba(99, 102, 241, 0.1);
    }
    
    &:focus {
      background: #ffffff;
      box-shadow: 0 0 0 1px rgba(99, 102, 241, 0.2), 0 1px 4px rgba(99, 102, 241, 0.08);
    }
  }
`;

/**
 * Inline skill name display/editor to place on the main tools bar.
 * - Shows current `skillInfo.skillName`
 * - Double-click to edit, Enter/Escape to confirm/cancel
 * - Beautiful gradient background with hover effects
 */
export const SkillName: React.FC = () => {
  const { t } = useTranslation('skillEditor');
  const skillInfo = useSkillInfoStore((state) => state.skillInfo);
  const setSkillInfo = useSkillInfoStore((state) => state.setSkillInfo);
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

    // Trigger immediate save when skill name changes
    // This ensures the rename is persisted to file, DB, and cloud
    setTimeout(async () => {
      try {
        const { useSheetsStore } = await import('../../stores/sheets-store');
        const ipcApi = (await import('../../../../services/ipc/api')).IPCAPI.getInstance();
        const sheetsStore = useSheetsStore.getState();
        const { skillInfo: latestSkillInfo, currentFilePath } = useSkillInfoStore.getState();

        // Get latest skillInfo from store (not from closure which has stale value)
        const skillInfoToSave = latestSkillInfo;
        const currentPath = currentFilePath;

        const sheetsData = {
          sheets: sheetsStore.sheets,
          order: sheetsStore.order,
          openTabs: sheetsStore.openTabs,
          activeSheetId: sheetsStore.activeSheetId,
        };

        console.log('[SkillName] Saving with skillName:', skillInfoToSave?.skillName, '->', trimmed, 'path:', currentPath);

        // Call backend directly - bypasses auto-save enabled check
        const response = await ipcApi.saveEditorCache({
          cacheData: {
            skillInfo: { ...skillInfoToSave, skillName: trimmed, lastModified: new Date().toISOString() },
            sheets: sheetsData,
            currentFilePath: currentPath,
          },
        });

        if (response.success) {
          const data = response.data as any;
          if (data?.renamed && data?.newFilePath) {
            useSkillInfoStore.getState().setCurrentFilePath(data.newFilePath);
          }
          console.log('[SkillName] Skill name saved:', value, '->', trimmed);
        } else {
          console.error('[SkillName] Save failed:', response.error);
        }
      } catch (err) {
        console.error('[SkillName] Failed to save after rename:', err);
      }
    }, 100);
  };

  const startEditing = () => {
    setDraft(value);
    setEditing(true);
  };

  return (
    <SkillNameContainer>
      {editing ? (
        <StyledInput
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
          style={{ width: 200 }}
          placeholder={t('skillName.placeholder')}
        />
      ) : (
        <>
          <StyledTooltip content={value} position="bottom">
            <SkillNameText onDoubleClick={startEditing}>
              {display}
            </SkillNameText>
          </StyledTooltip>
          <StyledTooltip content={t('skillName.clickToEdit')} position="bottom">
            <EditIconWrapper onClick={startEditing}>
              <EditIcon />
            </EditIconWrapper>
          </StyledTooltip>
        </>
      )}
    </SkillNameContainer>
  );
};

// Export alias for backward compatibility
export const SkillNameBadge = SkillName;
