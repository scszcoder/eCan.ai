import { loader } from '@monaco-editor/react';

// Configure Monaco Editor to use local files
// This MUST run before any Monaco Editor component mounts

/**
 * Monaco Editor Configuration - Always use local files
 * 
 * Both development and production use local files served by:
 * - Development: Vite dev server from public/monaco-editor
 * - Production: Python backend from dist/monaco-editor
 */

// Track current Monaco source for debugging
let currentMonacoSource: {
  type: 'local';
  url: string;
  timestamp: number;
} | null = null;

/**
 * Determine the base path based on environment
 */
const getMonacoBasePath = () => {
  if (typeof window === 'undefined') return './monaco-editor/vs';
  
  const isFileProtocol = window.location.protocol === 'file:';
  const isProduction = import.meta.env.PROD;
  
  if (isFileProtocol || isProduction) {
    // Production: use relative path for local files
    return './monaco-editor/vs';
  } else {
    // Development: use absolute path for local files (will be replaced by CDN if needed)
    return '/monaco-editor/vs';
  }
};

// Monaco initialization promise - components should await this before using Monaco
export let monacoReady: Promise<void>;

// In development, use local files served by Vite dev server
if (import.meta.env.DEV && typeof window !== 'undefined') {
  // Development: use local files from public directory
  const localPath = '/monaco-editor/vs';
  
  console.log(`%c[Monaco Editor] � Development Mode`, 'color: #3b82f6; font-weight: bold');
  console.log(`%c[Monaco Editor] Source: Local Files (Vite Dev Server)`, 'color: #10b981');
  console.log(`%c[Monaco Editor] Path: ${localPath}`, 'color: #6b7280');
  
  loader.config({
    paths: {
      vs: localPath
    }
  });
  
  // Configure worker URL for local files
  (window as any).MonacoEnvironment = {
    getWorkerUrl: function (_moduleId: string, _label: string) {
      return `${localPath}/base/worker/workerMain.js`;
    }
  };
  
  currentMonacoSource = { type: 'local', url: localPath, timestamp: Date.now() };
  monacoReady = Promise.resolve();
  
  console.log(`%c[Monaco Editor] ✅ Configuration Complete`, 'color: #10b981; font-weight: bold');
} else {
  // Production: use local files
  loader.config({
    paths: {
      vs: getMonacoBasePath()
    }
  });
  monacoReady = Promise.resolve();
}

// Configure Monaco worker paths for production only (dev is handled in findWorkingCDN)
if (typeof window !== 'undefined' && import.meta.env.PROD) {
  (window as any).MonacoEnvironment = {
    getWorkerUrl: function (_moduleId: string, _label: string) {
      // Always use relative path so it resolves correctly under any base path
      // (e.g., /app/gui-v2/monaco-editor/... instead of /monaco-editor/...)
      return './monaco-editor/vs/base/worker/workerMain.js';
    }
  };
}

export const setMonacoLanguage = (language: 'en' | 'zh-cn') => {
  loader.config({
    'vs/nls': {
      availableLanguages: {
        '*': language
      }
    }
  });
};

/**
 * Get current Monaco Editor source information
 * Usage in browser console: window.getMonacoSource()
 */
export const getMonacoSource = () => {
  if (!currentMonacoSource) {
    console.log(`%c[Monaco Info] ℹ️  Source not yet determined`, 'color: #f59e0b');
    return null;
  }
  
  const { type, url, timestamp } = currentMonacoSource;
  const age = Date.now() - timestamp;
  const ageSeconds = Math.floor(age / 1000);
  const env = import.meta.env.PROD ? 'Production' : 'Development';
  
  console.log(`%c
╔════════════════════════════════════════════════════════════════╗
║  Monaco Editor - Current Source Information                    ║
╠════════════════════════════════════════════════════════════════╣
║  Environment: ${env.padEnd(49)} ║
║  Source Type: ${type.toUpperCase().padEnd(48)} ║
║  URL: ${url.substring(0, 52).padEnd(52)} ║
║  Status: ACTIVE ✅                                             ║
║  Loaded: ${ageSeconds}s ago                                           ║
║  Timestamp: ${new Date(timestamp).toLocaleString().padEnd(42)} ║
╠════════════════════════════════════════════════════════════════╣
║  Note: Always uses local files (no CDN)                        ║
║  Dev:  Served by Vite from public/monaco-editor               ║
║  Prod: Served by Python backend from dist/monaco-editor       ║
╚════════════════════════════════════════════════════════════════╝
  `, 'color: #10b981; font-family: monospace');
  
  return currentMonacoSource;
};

// Expose to window for easy console access
if (typeof window !== 'undefined') {
  (window as any).getMonacoSource = getMonacoSource;
  console.log(`%c[Monaco Info] 💡 Tip: Type 'window.getMonacoSource()' in console to check current source`, 'color: #3b82f6; font-style: italic');
}
