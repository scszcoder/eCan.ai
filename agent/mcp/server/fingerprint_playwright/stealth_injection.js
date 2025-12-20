// stealth_injection.js
// stealth/stealth_injection.js
// Injected early via Playwright's add_init_script()
// Contains placeholders that will be replaced server-side:
//   __CANVAS_SEED__      -> string seed (e.g. "winc_seed_001")
//   __WEBGL_VENDOR__     -> vendor string (e.g. "Intel Inc.")
//   __WEBGL_RENDERER__   -> renderer string (e.g. "Intel(R) UHD Graphics")
//   __PLATFORM__         -> platform (e.g. "Win32")
//   __LANGUAGES__        -> JS array literal of languages (e.g. ["en-US","en"])
//
// NOTE: Keep this file robust and non-destructive. It attempts to mimic native behavior
// while hiding common automation artifacts. No single patch is perfect; test and iterate.

(function () {
  'use strict';

  // small safe helpers
  const noop = () => {};
  const hasOwn = (o, k) => Object.prototype.hasOwnProperty.call(o, k);

  // ---- seeded pseudorandom for deterministic, per-profile noise ----
  // simple xorshift32-ish from seed string -> number
  function xfnv1a(str) {
    let h = 2166136261 >>> 0;
    for (let i = 0; i < str.length; i++) {
      h ^= str.charCodeAt(i);
      h += (h << 1) + (h << 4) + (h << 7) + (h << 8) + (h << 24);
      h = h >>> 0;
    }
    return function () {
      // Robert Jenkins' 32 bit integer hash
      h += 0x6D2B79F5;
      let t = Math.imul(h ^ (h >>> 15), 1 | h);
      t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
      return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
    };
  }

  // Replace placeholders (these will be replaced server-side with concrete values).
  // Example replacements expected:
  //   __CANVAS_SEED__  => "winc_seed_001"
  //   __WEBGL_VENDOR__ => "Intel Inc."
  //   __WEBGL_RENDERER__ => "Intel Iris OpenGL Engine"
  //   __PLATFORM__ => "Win32"
  //   __LANGUAGES__ => ["en-US","en"]
  const CANVAS_SEED = "__CANVAS_SEED__";
  const WEBGL_VENDOR = "__WEBGL_VENDOR__";
  const WEBGL_RENDERER = "__WEBGL_RENDERER__";
  const PLATFORM = "__PLATFORM__";
  // LANGUAGES is expected to be an array literal after replacement, e.g. ["en-US","en"]
  let LANGUAGES = [];
  try {
    // if replacement inserted an array literal, evaluate it safely:
    LANGUAGES = __LANGUAGES__;
  } catch (e) {
    // fallback
    try { LANGUAGES = JSON.parse("__LANGUAGES__"); } catch (ee) { LANGUAGES = ["en-US","en"]; }
  }

  const seeded = xfnv1a(String(CANVAS_SEED || "default_seed"));

  // ---- hide navigator.webdriver ----
  try {
    Object.defineProperty(navigator, 'webdriver', {
      get: () => false,
      configurable: true
    });
  } catch (e) {}

  // ---- patch navigator.languages ----
  try {
    if (Array.isArray(LANGUAGES) && LANGUAGES.length) {
      Object.defineProperty(navigator, 'languages', {
        get: () => LANGUAGES,
        configurable: true
      });
    }
  } catch (e) {}

  // ---- patch navigator.plugins & mimeTypes with minimal API ----
  (function patchPlugins() {
    try {
      const fakePlugins = [
        { name: 'Chrome PDF Plugin', filename: 'internal-pdf-viewer', description: '' },
        { name: 'Chrome PDF Viewer', filename: 'mhjfbmdgcfjbbpaeojofohoefgiehjai', description: '' }
      ];
      function makePluginArray(plugins) {
        const arr = plugins.map(p => {
          return {
            name: p.name,
            filename: p.filename,
            description: p.description,
            length: 0,
            item: function () { return undefined; }
          };
        });
        // minimal PluginArray shape
        Object.defineProperty(arr, 'namedItem', {
          value: function (name) {
            return arr.find(p => p.name === name) || null;
          }
        });
        return arr;
      }
      if (!navigator.plugins || !navigator.plugins.length) {
        const pa = makePluginArray(fakePlugins);
        try {
          Object.defineProperty(navigator, 'plugins', {
            get: () => pa,
            configurable: true
          });
        } catch (e) {
          // fallback: assign if allowed
          try { navigator.plugins = pa; } catch (ee) {}
        }
      }
    } catch (e) {}
  })();

  // ---- platform spoof ----
  try {
    if (PLATFORM && PLATFORM !== 'undefined') {
      Object.defineProperty(navigator, 'platform', {
        get: () => PLATFORM,
        configurable: true
      });
    }
  } catch (e) {}

  // ---- hardwareConcurrency & deviceMemory ----
  try {
    Object.defineProperty(navigator, 'hardwareConcurrency', {
      get: () => (navigator.hardwareConcurrency || 4),
      configurable: true
    });
  } catch (e) {}
  try {
    Object.defineProperty(navigator, 'deviceMemory', {
      get: () => (navigator.deviceMemory || 8),
      configurable: true
    });
  } catch (e) {}

  // ---- Permissions API patch for notifications/geolocation/persistent-storage ----
  try {
    const originalQuery = navigator.permissions && navigator.permissions.query;
    if (originalQuery) {
      const patchedQuery = function (params) {
        // mirror original for known names, otherwise fallback:
        if (!params || !params.name) return originalQuery.call(navigator.permissions, params);
        if (params.name === 'notifications') {
          // delegate to Notification.permission
          return Promise.resolve({ state: Notification.permission });
        }
        if (params.name === 'push') {
          return Promise.resolve({ state: 'denied' });
        }
        return originalQuery.call(navigator.permissions, params);
      };
      patchedQuery.toString = () => 'function query() { [native code] }';
      try { navigator.permissions.query = patchedQuery; } catch (e) {}
    }
  } catch (e) {}

  // ---- WebRTC prevention / override to avoid local IP leaks ----
  (function patchWebRTC() {
    try {
      // Keep original if exists
      const OrigRTCPeerConnection = window.RTCPeerConnection || window.webkitRTCPeerConnection || window.mozRTCPeerConnection;
      function FakeRTCPeerConnection() {
        console.warn('RTCPeerConnection blocked by stealth_injection.js');
        // Provide a minimal dummy object shape to avoid page errors
        return {
          createDataChannel: function () { return {}; },
          createOffer: function () { return Promise.resolve({ sdp: '', type: 'offer' }); },
          createAnswer: function () { return Promise.resolve({ sdp: '', type: 'answer' }); },
          setLocalDescription: function () { return Promise.resolve(); },
          setRemoteDescription: function () { return Promise.resolve(); },
          addIceCandidate: function () { return Promise.resolve(); },
          getSenders: () => []
        };
      }
      // Replace constructor
      try {
        Object.defineProperty(window, 'RTCPeerConnection', { get: () => FakeRTCPeerConnection, configurable: true });
        Object.defineProperty(window, 'webkitRTCPeerConnection', { get: () => FakeRTCPeerConnection, configurable: true });
        Object.defineProperty(window, 'mozRTCPeerConnection', { get: () => FakeRTCPeerConnection, configurable: true });
      } catch (e) {
        // fallback assign
        try { window.RTCPeerConnection = FakeRTCPeerConnection; } catch (ee) {}
      }
    } catch (e) {}
  })();

  // ---- Canvas poisoning: toDataURL / getImageData / toBlob ----
  (function patchCanvas() {
    try {
      const toDataURL = HTMLCanvasElement.prototype.toDataURL;
      const getContext = HTMLCanvasElement.prototype.getContext;
      const toBlob = HTMLCanvasElement.prototype.toBlob;
      const getImageData_backup = CanvasRenderingContext2D && CanvasRenderingContext2D.prototype.getImageData;

      const rand = seeded;
      function perturbImageData(data) {
        // data is ImageData.data (Uint8ClampedArray)
        // apply tiny per-pixel noise based on seed
        for (let i = 0; i < data.length; i += 4) {
          // only alter a little; keep alpha intact
          const jitter = Math.floor((rand() - 0.5) * 6); // -3..+2
          data[i] = (data[i] + jitter) & 0xff;
          data[i + 1] = (data[i + 1] + jitter) & 0xff;
          data[i + 2] = (data[i + 2] + jitter) & 0xff;
        }
      }

      // patch getContext('2d') -> wrap getImageData
      HTMLCanvasElement.prototype.getContext = function (type, opts) {
        const ctx = getContext.call(this, type, opts);
        if (!ctx) return ctx;
        try {
          if (type === '2d' && ctx && ctx.getImageData) {
            const originalGetImageData = ctx.getImageData;
            ctx.getImageData = function (sx, sy, sw, sh) {
              const img = originalGetImageData.apply(this, arguments);
              try {
                perturbImageData(img.data);
              } catch (e) {}
              return img;
            };
          }
        } catch (e) {}
        return ctx;
      };

      // patch toDataURL
      HTMLCanvasElement.prototype.toDataURL = function () {
        try {
          const ctx = this.getContext && this.getContext('2d');
          if (ctx && ctx.getImageData) {
            try {
              const w = this.width, h = this.height;
              if (w > 0 && h > 0) {
                const img = ctx.getImageData(0, 0, w, h);
                perturbImageData(img.data);
                // put back (best-effort)
                try { ctx.putImageData(img, 0, 0); } catch (e) {}
              }
            } catch (e) {}
          }
        } catch (e) {}
        // fallback to native
        try { return toDataURL.apply(this, arguments); } catch (e) { return ''; }
      };

      // patch toBlob similarly
      if (toBlob) {
        HTMLCanvasElement.prototype.toBlob = function (cb, type, quality) {
          try {
            // try perturb via getContext -> putImageData before blob
            const ctx = this.getContext && this.getContext('2d');
            if (ctx && ctx.getImageData) {
              try {
                const w = this.width, h = this.height;
                if (w > 0 && h > 0) {
                  const img = ctx.getImageData(0, 0, w, h);
                  perturbImageData(img.data);
                  try { ctx.putImageData(img, 0, 0); } catch (e) {}
                }
              } catch (e) {}
            }
          } catch (e) {}
          return toBlob.apply(this, arguments);
        };
      }
    } catch (e) {}
  })();

  // ---- WebGL vendor/renderer spoofing ----
  (function patchWebGL() {
    try {
      const proto = WebGLRenderingContext && WebGLRenderingContext.prototype;
      if (!proto) return;

      const origGetParameter = proto.getParameter;
      proto.getParameter = function (param) {
        // constants 37445, 37446 are UNMASKED_VENDOR_WEBGL and UNMASKED_RENDERER_WEBGL in many contexts
        try {
          if (param === 37445 && WEBGL_VENDOR) return WEBGL_VENDOR;
          if (param === 37446 && WEBGL_RENDERER) return WEBGL_RENDERER;
        } catch (e) {}
        return origGetParameter.call(this, param);
      };

      // mask getExtension to avoid exposing debug info
      const origGetExtension = proto.getExtension;
      proto.getExtension = function (name) {
        // hide certain debugging extensions if desired
        if (name && (name.indexOf('dbg') !== -1 || name.indexOf('debug') !== -1)) {
          return null;
        }
        return origGetExtension.call(this, name);
      };
    } catch (e) {}
  })();

  // ---- AudioContext fingerprint mitigation ----
  (function patchAudio() {
    try {
      const OrigAudioContext = window.AudioContext || window.webkitAudioContext;
      if (!OrigAudioContext) return;

      const origCreateAnalyser = OrigAudioContext.prototype.createAnalyser;
      OrigAudioContext.prototype.createAnalyser = function () {
        const analyser = origCreateAnalyser.apply(this, arguments);
        try {
          const origGetFloatFrequencyData = analyser.getFloatFrequencyData;
          analyser.getFloatFrequencyData = function (array) {
            // call original
            try { origGetFloatFrequencyData.apply(this, arguments); } catch (e) {}
            // then slightly alter the values to add noise
            try {
              for (let i = 0; i < array.length; i++) {
                array[i] = array[i] + (seeded() - 0.5) * 0.0001;
              }
            } catch (e) {}
            return array;
          };
        } catch (e) {}
        return analyser;
      };
    } catch (e) {}
  })();

  // ---- Function.prototype.toString trick ----
  // make patched functions appear native when toString() is called
  (function maskToString() {
    try {
      const nativeToString = Function.prototype.toString;
      const nativeApply = Function.prototype.apply;

      const patchedFns = new WeakMap();

      // helper to wrap a function and make its toString look native
      function wrap(fn, name) {
        if (typeof fn !== 'function') return fn;
        const wrapped = function () {
          return nativeApply.call(fn, this, arguments);
        };
        patchedFns.set(wrapped, name || fn.name || 'function');
        return wrapped;
      }

      // override Function.prototype.toString
      Function.prototype.toString = function () {
        if (patchedFns.has(this)) {
          const name = patchedFns.get(this);
          return `function ${name}() { [native code] }`;
        }
        return nativeToString.call(this);
      };

      // register specific patched functions above so they look native
      // we cannot easily reference internal patched functions from here, but we can wrap common overrides if needed.
      // (This area is left light-touch to avoid breaking.)
    } catch (e) {}
  })();

  // ---- minimal navigator.webdriver shim for chrome-specific detection ----
  (function extraAntiDetect() {
    try {
      // navigator.chrome.runtime may be probed
      if (!window.chrome) {
        try { window.chrome = {}; } catch (e) {}
      }
      if (!window.chrome.runtime) {
        try { window.chrome.runtime = {}; } catch (e) {}
      }
    } catch (e) {}
  })();

  // done
  // console.log('stealth_injection applied');
})();
