/**
 * Platform Configuration
 * Manages platform-specific behavior for desktop vs web deployment
 */

export type PlatformType = 'desktop' | 'web';

export interface PlatformConfig {
  type: PlatformType;
  features: {
    ipcAvailable: boolean;
    fileSystemAccess: boolean;
    nativeDialogs: boolean;
    fullFilePaths: boolean;
  };
}

/**
 * Safe environment variable access
 */
function getEnvVar(key: string, defaultValue: string = 'desktop'): string {
  try {
    return (typeof process !== 'undefined' && process.env && process.env[key]) || defaultValue;
  } catch {
    return defaultValue;
  }
}

/**
 * Global platform configuration
 * Default to desktop mode with full IPC capabilities
 */
export const PLATFORM_CONFIG: PlatformConfig = {
  type: getEnvVar('REACT_APP_PLATFORM') as PlatformType,
  features: {
    ipcAvailable: getEnvVar('REACT_APP_PLATFORM') === 'desktop',
    fileSystemAccess: getEnvVar('REACT_APP_PLATFORM') === 'desktop',
    nativeDialogs: getEnvVar('REACT_APP_PLATFORM') === 'desktop',
    fullFilePaths: getEnvVar('REACT_APP_PLATFORM') === 'desktop',
  },
};

/**
 * Platform detection utilities
 */
export const isDesktopPlatform = () => PLATFORM_CONFIG.type === 'desktop';
export const isWebPlatform = () => PLATFORM_CONFIG.type === 'web';
export const hasIPCSupport = () => PLATFORM_CONFIG.features.ipcAvailable;
export const hasFileSystemAccess = () => PLATFORM_CONFIG.features.fileSystemAccess;
export const hasNativeDialogs = () => PLATFORM_CONFIG.features.nativeDialogs;
export const hasFullFilePaths = () => PLATFORM_CONFIG.features.fullFilePaths;

/**
 * Runtime platform detection (fallback)
 */
export const detectPlatform = (): PlatformType => {
  // Check if we're in a desktop environment with IPC
  if (typeof window !== 'undefined') {
    // Check for window.ipc (Qt WebChannel) as indicator of desktop mode
    try {
      // Primary check: window.ipc from Qt WebChannel
      if ((window as any).ipc) {
        return 'desktop';
      }
      // Secondary check: webchannel-ready event listener exists
      if ((window as any).__WEBCHANNEL_READY__) {
        return 'desktop';
      }
      return 'web';
    } catch (error) {
      console.debug('[Platform] IPC check failed:', error);
      return 'web';
    }
  }
  return 'web';
};

/**
 * Initialize platform configuration
 * Call this early in app initialization
 */
export const initializePlatform = () => {
  const detectedPlatform = detectPlatform();
  
  // Override config if detection differs from environment
  if (detectedPlatform !== PLATFORM_CONFIG.type) {
    console.info(`[Platform] Auto-correcting platform: configured as ${PLATFORM_CONFIG.type}, detected as ${detectedPlatform}. This is normal during development.`);
    
    // Update features based on detected platform
    const isDesktop = detectedPlatform === 'desktop';
    PLATFORM_CONFIG.type = detectedPlatform;
    PLATFORM_CONFIG.features.ipcAvailable = isDesktop;
    PLATFORM_CONFIG.features.fileSystemAccess = isDesktop;
    PLATFORM_CONFIG.features.nativeDialogs = isDesktop;
    PLATFORM_CONFIG.features.fullFilePaths = isDesktop;
  }
  
  console.log(`Platform initialized: ${PLATFORM_CONFIG.type}`, PLATFORM_CONFIG.features);
};
