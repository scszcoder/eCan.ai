import { hasIPCSupport, hasFullFilePaths } from '../../../config/platform';
import '../../../services/ipc/file-api';
import type { SheetsBundle } from '../utils/bundle-utils';
import { sanitizeNodeApiKeys } from '../utils/sanitize-utils';
// Re-export SheetsBundle for backward compatibility
export type { SheetsBundle };

// Save bundle to a specific file path (IPC) or download with a specific name (web)
export async function saveSheetsBundleToPath(
  targetPathOrName: string,
  bundle: SheetsBundle
): Promise<{ success: true; filePath?: string; mode: 'ipc' | 'download' }>{
  // Clone and sanitize bundle
  const sanitizedBundle = JSON.parse(JSON.stringify(bundle));
  if (sanitizedBundle.sheets) {
    sanitizedBundle.sheets.forEach((sheet: any) => {
      if (sheet.document?.nodes) {
        sanitizeNodeApiKeys(sheet.document.nodes);
      }
    });
  }
  const jsonString = JSON.stringify(sanitizedBundle, null, 2);
  // Try IPC write first; if anything fails, fall back to download method
  try {
    const { IPCAPI } = await import('../../../services/ipc/api');
    const ipcApi = IPCAPI.getInstance();
    const writeResponse = await ipcApi.writeSkillFile(targetPathOrName, jsonString);
    if (!writeResponse.success) {
      throw new Error(writeResponse.error || 'Failed to write bundle');
    }
    return { success: true, filePath: targetPathOrName, mode: 'ipc' };
  } catch (e) {
    // Fall through to browser download
    console.warn('[sheets-persistence] IPC write failed, falling back to download:', e);
  }
  // Browser/Web fallback: force a download using the provided name
  const blob = new Blob([jsonString], { type: 'application/json' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.style.display = 'none';
  a.href = url;
  // Strip directories if any; browsers only use file name
  const name = targetPathOrName.split(/[/\\]/).pop() || 'skill-bundle.json';
  a.download = name;
  document.body.appendChild(a);
  a.click();
  setTimeout(() => {
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  }, 100);
  return { success: true, mode: 'download' };
}

export async function saveSheetsBundle(bundle: SheetsBundle, suggestedName?: string) {
  // Clone and sanitize bundle
  const sanitizedBundle = JSON.parse(JSON.stringify(bundle));
  if (sanitizedBundle.sheets) {
    sanitizedBundle.sheets.forEach((sheet: any) => {
      if (sheet.document?.nodes) {
        sanitizeNodeApiKeys(sheet.document.nodes);
      }
    });
  }
  const jsonString = JSON.stringify(sanitizedBundle, null, 2);
  const fileName = (suggestedName || 'skill-multisheet') + '.json';

  if (hasIPCSupport() && hasFullFilePaths()) {
    const { IPCAPI } = await import('../../../services/ipc/api');
    const ipcApi = IPCAPI.getInstance();

    const dialogResponse = await ipcApi.showSaveDialog(fileName, [
      { name: 'Skill Bundle', extensions: ['json'] },
      { name: 'All Files', extensions: ['*'] },
    ]);
    if (!dialogResponse.success || !dialogResponse.data || dialogResponse.data.cancelled) {
      return { cancelled: true };
    }
    const filePath = dialogResponse.data.filePath;
    const writeResponse = await ipcApi.writeSkillFile(filePath, jsonString);
    if (!writeResponse.success) {
      throw new Error(writeResponse.error || 'Failed to write bundle');
    }
    return { success: true, filePath };
  }

  // Browser fallback
  const blob = new Blob([jsonString], { type: 'application/json' });
  try {
    const handle = await (window as any).showSaveFilePicker({
      suggestedName: fileName,
      types: [{ description: 'JSON Files', accept: { 'application/json': ['.json'] } }],
    });
    const writable = await handle.createWritable();
    await writable.write(blob);
    await writable.close();
    return { success: true };
  } catch {
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.style.display = 'none';
    a.href = url;
    a.download = fileName;
    document.body.appendChild(a);
    a.click();
    setTimeout(() => {
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
    }, 100);
    return { success: true };
  }
}

export async function loadSheetsBundle(): Promise<SheetsBundle | { cancelled: true }> {
  if (hasIPCSupport() && hasFullFilePaths()) {
    const { IPCAPI } = await import('../../../services/ipc/api');
    const ipcApi = IPCAPI.getInstance();
    const dialogResponse = await ipcApi.showOpenDialog([
      { name: 'Skill Bundle', extensions: ['json'] },
      { name: 'All Files', extensions: ['*'] },
    ]);
    if (!dialogResponse.success || !dialogResponse.data || dialogResponse.data.cancelled) {
      return { cancelled: true } as any;
    }
    const filePath = dialogResponse.data.filePaths?.[0];
    if (!filePath) return { cancelled: true } as any;
    const read = await ipcApi.readSkillFile(filePath);
    if (!read.success || !read.data) throw new Error(read.error || 'Failed to read bundle');
    const bundle = JSON.parse(read.data.content);
    return bundle as SheetsBundle;
  }

  return new Promise((resolve) => {
    const input = document.createElement('input');
    input.type = 'file';
    input.accept = '.json,application/json';
    input.onchange = () => {
      const file = input.files?.[0];
      if (!file) return resolve({ cancelled: true } as any);
      const reader = new FileReader();
      reader.onload = () => {
        try {
          const bundle = JSON.parse(reader.result as string) as SheetsBundle;
          resolve(bundle);
        } catch (e) {
          console.error('Failed to parse bundle', e);
          resolve({ cancelled: true } as any);
        }
      };
      reader.readAsText(file);
    };
    input.click();
  });
}
