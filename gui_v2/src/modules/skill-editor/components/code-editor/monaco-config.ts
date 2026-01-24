import { loader } from '@monaco-editor/react';

// Configure Monaco Editor to use local files
// This MUST run before any Monaco Editor component mounts

/**
 * CDN Fallback Configuration for Development Environment
 * 
 * Priority Order:
 * 1. Local files (fastest, offline-capable)
 * 2. jsDelivr CDN (国际主流 CDN，优先)
 * 3. Cloudflare CDN (国内备选)
 * 4. unpkg CDN (最后备选)
 */
const MONACO_VERSION = '0.52.2';

const CDN_SOURCES = {
  local: '/monaco-editor/vs',
  jsdelivr: `https://cdn.jsdelivr.net/npm/monaco-editor@${MONACO_VERSION}/min/vs`,
  cloudflare: `https://cdnjs.cloudflare.com/ajax/libs/monaco-editor/${MONACO_VERSION}/min/vs`,
  unpkg: `https://unpkg.com/monaco-editor@${MONACO_VERSION}/min/vs`
};

// Track current Monaco source for debugging
let currentMonacoSource: {
  type: 'local' | 'jsdelivr' | 'cloudflare' | 'unpkg';
  url: string;
  timestamp: number;
} | null = null;

/**
 * Test if a CDN source is accessible
 */
async function testCDNSource(cdnUrl: string): Promise<boolean> {
  try {
    const testUrl = `${cdnUrl}/loader.js`;
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 3000); // 3s timeout
    
    const response = await fetch(testUrl, {
      method: 'HEAD',
      signal: controller.signal,
      cache: 'no-cache'
    });
    
    clearTimeout(timeoutId);
    return response.ok;
  } catch (error) {
    console.warn(`[Monaco CDN] Failed to access: ${cdnUrl}`, error);
    return false;
  }
}

/**
 * Try CDN sources in order until one works
 */
async function findWorkingCDN(): Promise<string> {
  const isDev = import.meta.env.DEV;
  
  if (!isDev) {
    // Production always uses local files
    const source = 'local';
    const url = CDN_SOURCES.local;
    currentMonacoSource = { type: source, url, timestamp: Date.now() };
    console.log(`%c[Monaco Editor] 📦 Production Mode`, 'color: #10b981; font-weight: bold');
    console.log(`%c[Monaco Editor] Source: Local Files`, 'color: #10b981');
    console.log(`%c[Monaco Editor] Path: ${url}`, 'color: #6b7280');
    return url;
  }
  
  console.log(`%c[Monaco Editor] 🔍 Development Mode - Testing CDN Sources...`, 'color: #3b82f6; font-weight: bold');
  
  // Development: skip local (not served by Vite), use CDN fallbacks (international first, domestic as backup)
  const sources: Array<keyof typeof CDN_SOURCES> = ['jsdelivr', 'cloudflare', 'unpkg'];
  
  for (const source of sources) {
    const url = CDN_SOURCES[source];
    console.log(`%c[Monaco CDN] Testing: ${source}`, 'color: #f59e0b', url);
    
    const startTime = Date.now();
    const isAccessible = await testCDNSource(url);
    const duration = Date.now() - startTime;
    
    if (isAccessible) {
      currentMonacoSource = { type: source, url, timestamp: Date.now() };
      
      // Success log with emoji and color
      console.log(`%c[Monaco CDN] ✅ SUCCESS - Using: ${source}`, 'color: #10b981; font-weight: bold');
      console.log(`%c[Monaco CDN] URL: ${url}`, 'color: #6b7280');
      console.log(`%c[Monaco CDN] Response Time: ${duration}ms`, 'color: #6b7280');
      console.log(`%c[Monaco CDN] Timestamp: ${new Date().toLocaleString()}`, 'color: #6b7280');
      
      // Show summary box
      console.log(`%c
╔════════════════════════════════════════════════════════════════╗
║  Monaco Editor Source Information                              ║
╠════════════════════════════════════════════════════════════════╣
║  Source Type: ${source.toUpperCase().padEnd(48)} ║
║  URL: ${url.substring(0, 52).padEnd(52)} ║
║  Status: ACTIVE ✅                                             ║
╚════════════════════════════════════════════════════════════════╝
      `, 'color: #10b981; font-family: monospace');
      
      return url;
    } else {
      console.log(`%c[Monaco CDN] ❌ FAILED - ${source} (${duration}ms)`, 'color: #ef4444');
    }
  }
  
  // Fallback to local if all CDNs fail
  const fallbackSource = 'local';
  const fallbackUrl = CDN_SOURCES.local;
  currentMonacoSource = { type: fallbackSource, url: fallbackUrl, timestamp: Date.now() };
  
  console.warn(`%c[Monaco CDN] ⚠️  WARNING - All CDN sources failed!`, 'color: #f59e0b; font-weight: bold');
  console.warn(`%c[Monaco CDN] Falling back to local files: ${fallbackUrl}`, 'color: #f59e0b');
  
  return fallbackUrl;
}

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

// In development, configure CDN before Monaco tries to load
if (import.meta.env.DEV && typeof window !== 'undefined') {
  // Development: find working CDN first, then configure
  monacoReady = findWorkingCDN().then(workingCDN => {
    console.log(`%c[Monaco CDN] 🔄 Configuring Monaco with: ${workingCDN}`, 'color: #3b82f6; font-weight: bold');
    
    loader.config({
      paths: {
        vs: workingCDN
      }
    });
    
    // Also update worker URL for CDN
    (window as any).MonacoEnvironment = {
      getWorkerUrl: function (_moduleId: string, _label: string) {
        return `${workingCDN}/base/worker/workerMain.js`;
      }
    };
    
    console.log(`%c[Monaco CDN] ✅ Configuration Complete`, 'color: #10b981; font-weight: bold');
  }).catch(error => {
    console.error(`%c[Monaco CDN] ❌ Error during CDN fallback:`, 'color: #ef4444; font-weight: bold', error);
    // Fallback to jsdelivr directly
    const fallbackUrl = CDN_SOURCES.jsdelivr;
    loader.config({ paths: { vs: fallbackUrl } });
  });
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
      const isFileProtocol = window.location.protocol === 'file:';
      
      if (isFileProtocol) {
        return './monaco-editor/vs/base/worker/workerMain.js';
      } else {
        return '/monaco-editor/vs/base/worker/workerMain.js';
      }
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
  
  console.log(`%c
╔════════════════════════════════════════════════════════════════╗
║  Monaco Editor - Current Source Information                    ║
╠════════════════════════════════════════════════════════════════╣
║  Source Type: ${type.toUpperCase().padEnd(48)} ║
║  URL: ${url.substring(0, 52).padEnd(52)} ║
║  Status: ACTIVE ✅                                             ║
║  Loaded: ${ageSeconds}s ago                                           ║
║  Timestamp: ${new Date(timestamp).toLocaleString().padEnd(42)} ║
╠════════════════════════════════════════════════════════════════╣
║  Available CDN Sources:                                        ║
║    1. Local:      /monaco-editor/vs                            ║
║    2. jsDelivr:   cdn.jsdelivr.net (International)             ║
║    3. Cloudflare: cdnjs.cloudflare.com (Domestic Backup)       ║
║    4. unpkg:      unpkg.com (Last Resort)                      ║
╚════════════════════════════════════════════════════════════════╝
  `, 'color: #10b981; font-family: monospace');
  
  return currentMonacoSource;
};

// Expose to window for easy console access
if (typeof window !== 'undefined') {
  (window as any).getMonacoSource = getMonacoSource;
  console.log(`%c[Monaco Info] 💡 Tip: Type 'window.getMonacoSource()' in console to check current source`, 'color: #3b82f6; font-style: italic');
}
