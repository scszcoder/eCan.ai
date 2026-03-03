/**
 * Platform Configuration
 * Manages platform-specific behavior for desktop vs web deployment
 * 
 * Architecture:
 * - Desktop: Runs on localhost (Qt WebEngine or browser), uses local GraphQL (/graphql)
 * - Web: Runs on cloud domain, uses AppSync (AWS GraphQL)
 */

export type PlatformType = 'desktop' | 'web';

/**
 * Platform detection utilities
 * All based on runtime detection for reliability
 */
export const isDesktopPlatform = () => detectPlatform() === 'desktop';
export const isWebPlatform = () => detectPlatform() === 'web';

/**
 * Feature detection based on platform
 * Desktop mode has full local file system access
 * Web mode is sandboxed
 */
export const hasIPCSupport = () => isDesktopPlatform();
export const hasFileSystemAccess = () => isDesktopPlatform();
export const hasNativeDialogs = () => isDesktopPlatform();
export const hasFullFilePaths = () => isDesktopPlatform();

/**
 * Runtime platform detection
 * 
 * Detection strategy:
 * 1. Check if running on localhost/127.0.0.1 → Desktop mode
 * 2. Otherwise → Web mode (cloud deployment)
 * 
 * This is reliable because:
 * - Desktop app always runs on localhost (Qt WebEngine serves local server)
 * - Web app always runs on cloud domain (e.g., app.ecan.ai)
 */
export const detectPlatform = (): PlatformType => {
  if (typeof window === 'undefined') {
    return 'web';
  }

  try {
    const protocol = window.location.protocol;
    const hostname = window.location.hostname;
    
    // Desktop mode: file:// protocol (production build opened directly)
    if (protocol === 'file:') {
      return 'desktop';
    }
    
    // Desktop mode: localhost or 127.0.0.1
    if (hostname === 'localhost' || hostname === '127.0.0.1' || hostname.startsWith('192.168.')) {
      return 'desktop';
    }
    
    // Web mode: any other domain
    return 'web';
  } catch (error) {
    console.debug('[Platform] Detection failed, defaulting to web:', error);
    return 'web';
  }
};

/**
 * Initialize platform configuration
 * Call this early in app initialization
 * 
 * Note: With pure runtime detection, this is now just a logging function
 */
export const initializePlatform = () => {
  const platform = detectPlatform();
  const features = {
    ipcAvailable: platform === 'desktop',
    fileSystemAccess: platform === 'desktop',
    nativeDialogs: platform === 'desktop',
    fullFilePaths: platform === 'desktop',
  };
  
  console.log(`[Platform] Detected: ${platform}`, {
    hostname: typeof window !== 'undefined' ? window.location.hostname : 'N/A',
    features
  });
};
