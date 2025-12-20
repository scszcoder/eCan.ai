/**
 * Video Format Support Detection
 * 
 * Detects browser support for video formats once on page load
 */

let videoSupportChecked = false;

export interface VideoFormatSupport {
  webm: string;
  mp4: string;
}

let cachedSupport: VideoFormatSupport | null = null;

/**
 * Check and log video format support
 */
export function checkVideoSupport(): VideoFormatSupport {
  if (cachedSupport) {
    return cachedSupport;
  }

  const video = document.createElement('video');
  const webmSupport = video.canPlayType('video/webm; codecs="vp8, vorbis"');
  const mp4Support = video.canPlayType('video/mp4; codecs="avc1.42E01E, mp4a.40.2"');
  
  cachedSupport = {
    webm: webmSupport || 'not supported',
    mp4: mp4Support || 'not supported'
  };

  if (!videoSupportChecked) {
    console.log('[VideoSupport] Browser video format support:', cachedSupport);
    videoSupportChecked = true;
  }

  return cachedSupport;
}

/**
 * Initialize video support check on page load
 */
export function initVideoSupport(): void {
  if (typeof window !== 'undefined' && !videoSupportChecked) {
    checkVideoSupport();
  }
}

// Auto-initialize when module is imported
if (typeof window !== 'undefined') {
  console.log('[VideoSupport] Module loaded, readyState:', document.readyState);
  
  // Run check after DOM is ready
  if (document.readyState === 'loading') {
    console.log('[VideoSupport] Waiting for DOMContentLoaded...');
    document.addEventListener('DOMContentLoaded', () => {
      console.log('[VideoSupport] DOMContentLoaded fired, running check...');
      initVideoSupport();
    });
  } else {
    console.log('[VideoSupport] DOM already ready, running check immediately...');
    initVideoSupport();
  }
} else {
  console.log('[VideoSupport] Window not available (SSR?)');
}
