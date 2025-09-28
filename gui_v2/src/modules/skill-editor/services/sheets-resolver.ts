export interface ValidationIssue {
  level: 'error' | 'warning';
  message: string;
  sheetId?: string;
  nodeId?: string;
}

export interface SheetNode {
  id: string;
  type: string;
  data?: any;
}

export interface SheetDoc {
  nodes: SheetNode[];
  edges: any[];
  meta?: any;
}

export interface SheetEntry {
  id: string;
  name: string;
  document: SheetDoc;
}

export interface SheetsBundleLike {
  version?: number;
  mainSheetId: string;
  activeSheetId?: string | null;
  openTabs?: string[];
  sheets: SheetEntry[];
}

export interface ValidationResult {
  ok: boolean;
  errors: ValidationIssue[];
  warnings: ValidationIssue[];
  callGraph: Record<string, string[]>; // sheetId -> called sheetIds
}

/**
 * Validate a multi-sheet bundle for cross-sheet references.
 * - Ensures sheet-call nodes target an existing sheet
 * - Ensures target sheet exposes interface via sheet-inputs/sheet-outputs nodes (if present)
 * - Optionally detects simple call cycles
 */
export function validateBundle(bundle: SheetsBundleLike): ValidationResult {
  // Temporarily bypass validation when disabled via flag
  try {
    const { isValidationDisabled } = require('./validation-config');
    if (typeof isValidationDisabled === 'function' && isValidationDisabled()) {
      return { ok: true, errors: [], warnings: [], callGraph: {} };
    }
  } catch {
    // ignore missing module in unusual build environments
  }
  const errors: ValidationIssue[] = [];
  const warnings: ValidationIssue[] = [];

  if (!bundle || typeof bundle !== 'object' || !Array.isArray(bundle.sheets)) {
    return { ok: false, errors: [{ level: 'error', message: 'Invalid bundle format' }], warnings, callGraph: {} };
  }

  const sheetById = new Map<string, SheetEntry>();
  for (const s of bundle.sheets) {
    if (!s?.id) {
      errors.push({ level: 'error', message: 'Sheet missing id' });
      continue;
    }
    sheetById.set(s.id, s);
  }
  if (!sheetById.has(bundle.mainSheetId)) {
    errors.push({ level: 'error', message: `mainSheetId '${bundle.mainSheetId}' not found` });
  }

  const callGraph: Record<string, string[]> = {};

  // Helper: get interface of a sheet (input/output names) if declared via special nodes
  function getSheetInterface(sheet: SheetEntry): { inputs: string[]; outputs: string[] } {
    const doc = sheet.document || { nodes: [], edges: [] };
    const inputsNode = doc.nodes.find((n) => n.type === 'sheet-inputs');
    const outputsNode = doc.nodes.find((n) => n.type === 'sheet-outputs');
    const inputs = Array.isArray(inputsNode?.data?.inputs) ? inputsNode!.data.inputs.map((x: any) => String(x?.name || '')) : [];
    const outputs = Array.isArray(outputsNode?.data?.outputs) ? outputsNode!.data.outputs.map((x: any) => String(x?.name || '')) : [];
    return { inputs, outputs };
  }

  for (const sheet of bundle.sheets) {
    const doc = sheet.document || { nodes: [], edges: [] };
    for (const node of doc.nodes || []) {
      if (node.type !== 'sheet-call') continue;
      const targetSheetId = node?.data?.targetSheetId;
      if (!targetSheetId || !sheetById.has(targetSheetId)) {
        errors.push({ level: 'error', message: `sheet-call targets unknown sheet '${targetSheetId}'`, sheetId: sheet.id, nodeId: node.id });
        continue;
      }
      callGraph[sheet.id] ||= [];
      if (!callGraph[sheet.id].includes(targetSheetId)) callGraph[sheet.id].push(targetSheetId);

      // Validate interface mapping if target declares interface
      const target = sheetById.get(targetSheetId)!;
      const iface = getSheetInterface(target);
      const inputMapping = node?.data?.inputMapping || {};
      const outputMapping = node?.data?.outputMapping || {};

      for (const inputName of iface.inputs) {
        if (!(inputName in inputMapping)) {
          warnings.push({ level: 'warning', message: `Input '${inputName}' not mapped for call to '${targetSheetId}'`, sheetId: sheet.id, nodeId: node.id });
        }
      }
      for (const outputName of iface.outputs) {
        if (!(outputName in outputMapping)) {
          warnings.push({ level: 'warning', message: `Output '${outputName}' not mapped for call to '${targetSheetId}'`, sheetId: sheet.id, nodeId: node.id });
        }
      }
    }
  }

  // Detect simple cycles in call graph using DFS
  const visited = new Set<string>();
  const stack = new Set<string>();
  let hasCycle = false;
  function dfs(u: string) {
    if (stack.has(u)) {
      hasCycle = true;
      return;
    }
    if (visited.has(u)) return;
    visited.add(u);
    stack.add(u);
    for (const v of callGraph[u] || []) dfs(v);
    stack.delete(u);
  }
  Object.keys(callGraph).forEach(dfs);
  if (hasCycle) {
    warnings.push({ level: 'warning', message: 'Detected cycle in sheet-call graph. Ensure runtime can handle recursion/cycles.' });
  }

  return { ok: errors.length === 0, errors, warnings, callGraph };
}
