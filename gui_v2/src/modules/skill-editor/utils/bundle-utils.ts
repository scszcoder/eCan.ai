/**
 * Bundle Utilities
 * Common functions for handling skill bundle format conversion
 */

import type { Sheet } from '../stores/sheets-store';

export interface SheetsBundle {
  mainSheetId: string;
  sheets: Sheet[];
  openTabs?: string[];
  activeSheetId?: string | null;
}

/**
 * Normalize bundle format: convert legacy object-based sheets to array format
 * Legacy format: { sheets: { main: {...}, sheet2: {...} }, order: [...] }
 * New format: { sheets: [{id: 'main', ...}, {id: 'sheet2', ...}], mainSheetId: '...' }
 */
export function normalizeBundle(raw: any): SheetsBundle | null {
  if (!raw || typeof raw !== 'object') return null;
  
  const now = Date.now();
  
  // Already in array format
  if (Array.isArray(raw.sheets)) {
    // Ensure all sheets have required fields
    const sheets = raw.sheets.map((s: any) => ({
      ...s,
      createdAt: s.createdAt ?? now,
      lastOpenedAt: s.lastOpenedAt ?? now,
    }));
    return { ...raw, sheets } as SheetsBundle;
  }
  
  // Legacy object format: convert to array
  if (raw.sheets && typeof raw.sheets === 'object') {
    const order = Array.isArray(raw.order) ? raw.order : Object.keys(raw.sheets);
    const sheetsArray = order
      .filter((id: string) => raw.sheets[id])
      .map((id: string) => ({
        ...raw.sheets[id],
        id,
        createdAt: raw.sheets[id].createdAt ?? now,
        lastOpenedAt: raw.sheets[id].lastOpenedAt ?? now,
      }));
    
    if (sheetsArray.length === 0) return null;
    
    return {
      mainSheetId: order[0] || 'main',
      sheets: sheetsArray as Sheet[],
      openTabs: raw.openTabs || order,
      activeSheetId: raw.activeSheetId || order[0],
    };
  }
  
  return null;
}

/**
 * Check if raw object looks like a bundle (either format)
 */
export function looksLikeBundle(raw: any): boolean {
  if (!raw || typeof raw !== 'object') return false;
  // New format: has mainSheetId and sheets array
  if ('mainSheetId' in raw && Array.isArray(raw.sheets)) return true;
  // Legacy format: has sheets object and order array
  if (raw.sheets && typeof raw.sheets === 'object' && !Array.isArray(raw.sheets) && Array.isArray(raw.order)) return true;
  return false;
}

/**
 * Try to load bundle from sibling file paths
 * @param basePath - Base path without extension (e.g., '/path/to/skill_skill')
 * @param readFile - Function to read file content
 * @returns Normalized bundle or null
 */
export async function tryLoadSiblingBundle(
  basePath: string,
  readFile: (path: string) => Promise<{ success: boolean; data?: { content: string } }>
): Promise<SheetsBundle | null> {
  const candidates = [`${basePath}_bundle.json`, `${basePath}-bundle.json`];
  
  for (const bundlePath of candidates) {
    try {
      console.log('[BundleUtils] Trying bundle path:', bundlePath);
      const resp = await readFile(bundlePath);
      if (resp.success && resp.data) {
        const maybeBundle = JSON.parse(resp.data.content);
        if (looksLikeBundle(maybeBundle)) {
          const normalizedBundle = normalizeBundle(maybeBundle);
          if (normalizedBundle) {
            console.log('[BundleUtils] Loaded bundle with', normalizedBundle.sheets.length, 'sheets');
            return normalizedBundle;
          }
        }
      }
    } catch (e) {
      // Bundle file doesn't exist or failed to parse, continue
    }
  }
  
  return null;
}
