import React, { useMemo, useCallback } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import OrgDoor from '../components/OrgDoor';
import { DisplayNode } from '../../Orgs/types';
import { seededOrgNameKey } from '../../Orgs/defaultOrgNames';

/**
 * 组织门Render的Custom Hook
 * 负责Process门的Click和Render逻辑
 */
export function useOrgDoorRenderer(levelDoors: DisplayNode[], actualOrgId?: string) {
  const navigate = useNavigate();
  const location = useLocation();
  const { t } = useTranslation();

  // Process门ClickEvent
  const handleDoorClick = useCallback(
    (door: DisplayNode) => {
      if (door.type === 'unassigned_agents') {
        const currentPath = location.pathname;
        navigate(`${currentPath}/organization/unassigned`);
        return;
      }

      // 构建正确的嵌套Path：When前Path + /organization/:orgId
      const currentPath = location.pathname.replace(/\/$/, ''); // Remove末尾斜杠
      const newPath = `${currentPath}/organization/${door.id}`;
      
      console.log('[OrgNavigator] Navigating from:', currentPath, 'to:', newPath);
      console.log('[OrgNavigator] Current actualOrgId:', actualOrgId, 'Target door.id:', door.id);
      
      navigate(newPath);
    },
    [navigate, location.pathname, actualOrgId]
  );

  // Render门Component
  const doorComponents = useMemo(() => {
    return levelDoors.map((door) => {
      let displayName = door.name;

      if (displayName.startsWith('pages.')) {
        displayName = t(displayName) || displayName;
      } else {
        // The seeded departments are stored in the DB with English names, so a
        // CN build showed "Sales" beside otherwise-Chinese UI. Translated by
        // the template's stable id; a customer's own org — or one they renamed
        // — has no key and keeps the name they gave it.
        const seededKey = seededOrgNameKey(door.id, door.name);
        if (seededKey) {
          const translated = t(seededKey);
          // i18next echoes the key back when it is missing.
          if (translated && translated !== seededKey) {
            displayName = translated;
          }
        }
      }

      if (door.type === 'org_with_agents' && typeof door.agentCount === 'number') {
        displayName = `${displayName} (${door.agentCount})`;
      }

      if (door.type === 'org_with_children' && typeof door.agentCount === 'number') {
        displayName = `${displayName} (${door.agentCount})`;
      }

      if (door.type === 'unassigned_agents') {
        displayName = `${displayName} (${door.agentCount || 0})`;
      }

      return (
        <div
          key={`${door.id}`}
          onClick={() => handleDoorClick(door)}
          style={{ position: 'relative', zIndex: 5, pointerEvents: 'auto' }}
        >
          <OrgDoor name={displayName} />
        </div>
      );
    });
  }, [levelDoors, t, handleDoorClick]);

  return {
    doorComponents,
    handleDoorClick,
  };
}
