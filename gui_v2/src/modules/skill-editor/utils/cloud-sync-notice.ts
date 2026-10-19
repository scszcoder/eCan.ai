import i18n from 'i18next';
import { Toast } from '@douyinfe/semi-ui';
import { IPCAPI } from '../../../services/ipc/api';

/**
 * After a skill save / Save As / create: ask the backend whether the cloud
 * took it (skill_cloud_sync_status waits up to ~20 s) and warn the author if
 * not -- subscribers would otherwise keep the old version without anyone
 * knowing. Silent when the cloud accepted it or the save is unknown.
 */
export async function warnIfSkillCloudSyncFailed(skillId: string | undefined | null): Promise<void> {
  if (!skillId) return;
  try {
    const resp = await IPCAPI.getInstance().getSkillCloudSyncStatus<any>(String(skillId));
    const cloud = resp?.success ? resp.data : null;
    if (!cloud || cloud.ok) return;
    const why = Object.values(cloud.errors || {}).join('; ');
    const content = why
      ? i18n.t('save.cloudSyncFailed', { ns: 'skillEditor', error: why })
      : i18n.t('save.cloudSyncPending', { ns: 'skillEditor' });
    Toast.warning({ content, duration: 10 });
  } catch (e) {
    console.warn('[SKILL_IO] cloud sync status check failed', e);
  }
}
