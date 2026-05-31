/**
 * Debug utilities for investigating the FlowGram plugin API
 * These functions help us understand what's available in the plugin context
 */

/**
 * Safely inspect an object and return its structure
 */
export function inspectObject(obj: any, maxDepth = 2, currentDepth = 0): any {
  if (currentDepth >= maxDepth) return '[Max Depth Reached]';
  if (obj === null) return null;
  if (obj === undefined) return undefined;
  
  const type = typeof obj;
  
  if (type === 'function') {
    return `[Function: ${obj.name || 'anonymous'}]`;
  }
  
  if (type !== 'object') {
    return obj;
  }
  
  if (Array.isArray(obj)) {
    return `[Array(${obj.length})]`;
  }
  
  const result: any = {};
  const keys = Object.keys(obj).slice(0, 20); // Limit to first 20 keys
  
  for (const key of keys) {
    try {
      result[key] = inspectObject(obj[key], maxDepth, currentDepth + 1);
    } catch (e) {
      result[key] = '[Error accessing property]';
    }
  }
  
  if (Object.keys(obj).length > 20) {
    result['...'] = `[${Object.keys(obj).length - 20} more properties]`;
  }
  
  return result;
}

/**
 * Get all methods from an object (including prototype chain)
 */
export function getMethods(obj: any): string[] {
  if (!obj) return [];
  
  const methods = new Set<string>();
  let current = obj;
  
  // Walk up the prototype chain
  while (current && current !== Object.prototype) {
    Object.getOwnPropertyNames(current).forEach(name => {
      if (typeof obj[name] === 'function' && name !== 'constructor') {
        methods.add(name);
      }
    });
    current = Object.getPrototypeOf(current);
  }
  
  return Array.from(methods).sort();
}

/**
 * Get all properties from an object (excluding methods)
 */
export function getProperties(obj: any): string[] {
  if (!obj) return [];
  
  return Object.keys(obj).filter(key => {
    try {
      return typeof obj[key] !== 'function';
    } catch {
      return false;
    }
  }).sort();
}

/**
 * Create a detailed report of an object
 */
export function createObjectReport(obj: any, name: string = 'Object'): string {
  const lines: string[] = [];
  
  lines.push(`=== ${name} Report ===`);
  lines.push(`Type: ${typeof obj}`);
  lines.push(`Constructor: ${obj?.constructor?.name || 'Unknown'}`);
  lines.push('');
  
  const methods = getMethods(obj);
  if (methods.length > 0) {
    lines.push(`Methods (${methods.length}):`);
    methods.forEach(m => lines.push(`  - ${m}()`));
    lines.push('');
  }
  
  const properties = getProperties(obj);
  if (properties.length > 0) {
    lines.push(`Properties (${properties.length}):`);
    properties.slice(0, 20).forEach(p => {
      try {
        const value = obj[p];
        const valueStr = typeof value === 'object' 
          ? `[${value?.constructor?.name || 'Object'}]`
          : String(value).slice(0, 50);
        lines.push(`  - ${p}: ${valueStr}`);
      } catch {
        lines.push(`  - ${p}: [Error accessing]`);
      }
    });
    if (properties.length > 20) {
      lines.push(`  ... ${properties.length - 20} more properties`);
    }
  }
  
  return lines.join('\n');
}

/**
 * Log a detailed inspection of a line object
 */
export function inspectLine(line: any): void {
  console.group('🔍 Line Inspection');
  
  console.log('Basic Info:', {
    id: line?.id,
    type: line?.constructor?.name,
  });
  
  console.log('From:', inspectObject(line?.from, 1));
  console.log('To:', inspectObject(line?.to, 1));
  console.log('Data:', inspectObject(line?.data, 2));
  
  const methods = getMethods(line);
  if (methods.length > 0) {
    console.log('Available Methods:', methods);
  }
  
  const properties = getProperties(line);
  if (properties.length > 0) {
    console.log('Available Properties:', properties);
  }
  
  console.groupEnd();
}

/**
 * Log a detailed inspection of the plugin context
 */
export function inspectContext(ctx: any): void {
  console.group('🔍 Plugin Context Inspection');
  
  console.log('Context Type:', ctx?.constructor?.name);
  
  // Try to find common services
  const serviceNames = [
    'document',
    'linesManager', 
    'WorkflowLinesManager',
    'playground',
    'commandService',
    'entityManager',
  ];
  
  console.log('Services:');
  serviceNames.forEach(name => {
    try {
      const service = ctx?.[name] || ctx?.get?.(name);
      if (service) {
        console.log(`  ✅ ${name}:`, service.constructor?.name);
        console.log(`     Methods:`, getMethods(service).slice(0, 10));
      } else {
        console.log(`  ❌ ${name}: Not found`);
      }
    } catch (e) {
      console.log(`  ⚠️ ${name}: Error accessing`);
    }
  });
  
  // List all available keys
  const allKeys = Object.keys(ctx || {});
  if (allKeys.length > 0) {
    console.log('All Context Keys:', allKeys);
  }
  
  console.groupEnd();
}

/**
 * Create a visual representation of a line path
 */
export function visualizePath(from: any, to: any, waypoints?: any[]): string {
  const points = [
    from,
    ...(waypoints || []),
    to,
  ].filter(Boolean);
  
  if (points.length < 2) return 'Invalid path';
  
  const lines: string[] = [];
  lines.push('Path Visualization:');
  
  for (let i = 0; i < points.length - 1; i++) {
    const p1 = points[i];
    const p2 = points[i + 1];
    const dx = p2.x - p1.x;
    const dy = p2.y - p1.y;
    const distance = Math.sqrt(dx * dx + dy * dy).toFixed(1);
    const direction = Math.abs(dx) > Math.abs(dy) ? 'horizontal' : 'vertical';
    
    lines.push(`  ${i + 1}. (${p1.x}, ${p1.y}) → (${p2.x}, ${p2.y}) [${direction}, ${distance}px]`);
  }
  
  return lines.join('\n');
}
