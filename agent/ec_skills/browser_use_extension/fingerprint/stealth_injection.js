// stealth_injection.js
// Injected early via CDP Page.addScriptToEvaluateOnNewDocument
// Contains placeholders that will be replaced server-side:
//   __CANVAS_SEED__            -> string seed (e.g. "winc_seed_001")
//   __WEBGL_VENDOR__           -> vendor string (e.g. "Intel Inc.")
//   __WEBGL_RENDERER__         -> renderer string (e.g. "Intel(R) UHD Graphics")
//   __PLATFORM__               -> platform (e.g. "Win32")
//   __LANGUAGES__              -> JS array literal of languages (e.g. ["en-US","en"])
//   __DISPLAY_LANGUAGE__       -> primary display language (e.g. "en-US")
//   __DO_NOT_TRACK__           -> "1", "0", or "" (empty = browser default)
//   __NOISE_WEBGL_IMAGE__      -> "true" or "false"
//   __NOISE_CLIENT_RECTS__     -> "true" or "false"
//   __NOISE_SPEECH_VOICES__    -> "true" or "false"
//   __NOISE_MEDIA_DEVICES__    -> "true" or "false"
//   __FONT_PROTECTION__        -> "true" or "false"
//   __CUSTOM_FONTS__           -> JS array literal of font names (e.g. ["Arial","Helvetica"])
//   __PORT_SCAN_PROTECTION__   -> "true" or "false"
//   __PORT_SCAN_ALLOWED__      -> JS array literal of allowed ports (e.g. [80,443])
//   __WEBGPU_MODE__            -> "based_on_webgl", "real", or "disabled"
//   __HARDWARE_CONCURRENCY__   -> number (e.g. 8) or 0 for browser default
//   __DEVICE_MEMORY__          -> number (e.g. 8) or 0 for browser default
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
  const DISPLAY_LANGUAGE = "__DISPLAY_LANGUAGE__";
  const DO_NOT_TRACK = "__DO_NOT_TRACK__";
  const NOISE_WEBGL_IMAGE = "__NOISE_WEBGL_IMAGE__" === "true";
  const NOISE_CLIENT_RECTS = "__NOISE_CLIENT_RECTS__" === "true";
  const NOISE_SPEECH_VOICES = "__NOISE_SPEECH_VOICES__" === "true";
  const NOISE_MEDIA_DEVICES = "__NOISE_MEDIA_DEVICES__" === "true";
  const FONT_PROTECTION = "__FONT_PROTECTION__" === "true";
  const PORT_SCAN_PROTECTION = "__PORT_SCAN_PROTECTION__" === "true";
  const WEBGPU_MODE = "__WEBGPU_MODE__";

  // Numeric placeholders — 0 means "use browser default"
  let HARDWARE_CONCURRENCY = 0;
  try { HARDWARE_CONCURRENCY = parseInt("__HARDWARE_CONCURRENCY__", 10) || 0; } catch(e) {}
  let DEVICE_MEMORY = 0;
  try { DEVICE_MEMORY = parseInt("__DEVICE_MEMORY__", 10) || 0; } catch(e) {}

  // LANGUAGES is expected to be an array literal after replacement, e.g. ["en-US","en"]
  let LANGUAGES = [];
  try {
    LANGUAGES = __LANGUAGES__;
  } catch (e) {
    try { LANGUAGES = JSON.parse("__LANGUAGES__"); } catch (ee) { LANGUAGES = ["en-US","en"]; }
  }

  // CUSTOM_FONTS: array of font family names to expose
  let CUSTOM_FONTS = [];
  try {
    CUSTOM_FONTS = __CUSTOM_FONTS__;
  } catch (e) {
    try { CUSTOM_FONTS = JSON.parse("__CUSTOM_FONTS__"); } catch (ee) { CUSTOM_FONTS = []; }
  }

  // PORT_SCAN_ALLOWED: array of port numbers that are allowed
  let PORT_SCAN_ALLOWED = [];
  try {
    PORT_SCAN_ALLOWED = __PORT_SCAN_ALLOWED__;
  } catch (e) {
    try { PORT_SCAN_ALLOWED = JSON.parse("__PORT_SCAN_ALLOWED__"); } catch (ee) { PORT_SCAN_ALLOWED = [80, 443]; }
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
  if (HARDWARE_CONCURRENCY > 0) {
    try {
      Object.defineProperty(navigator, 'hardwareConcurrency', {
        get: () => HARDWARE_CONCURRENCY,
        configurable: true
      });
    } catch (e) {}
  }
  if (DEVICE_MEMORY > 0) {
    try {
      Object.defineProperty(navigator, 'deviceMemory', {
        get: () => DEVICE_MEMORY,
        configurable: true
      });
    } catch (e) {}
  }

  // ---- Display language override ----
  try {
    if (DISPLAY_LANGUAGE && DISPLAY_LANGUAGE !== '__DISPLAY_LANGUAGE__') {
      Object.defineProperty(navigator, 'language', {
        get: () => DISPLAY_LANGUAGE,
        configurable: true
      });
    }
  } catch (e) {}

  // ---- Do Not Track ----
  try {
    if (DO_NOT_TRACK === '1' || DO_NOT_TRACK === '0') {
      Object.defineProperty(navigator, 'doNotTrack', {
        get: () => DO_NOT_TRACK,
        configurable: true
      });
    }
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

  // ---- WebGL Image noise (readPixels) ----
  if (NOISE_WEBGL_IMAGE) {
    (function patchWebGLImage() {
      try {
        const rand = seeded;
        function noiseReadPixels(orig) {
          return function (x, y, w, h, format, type, pixels) {
            orig.apply(this, arguments);
            try {
              if (pixels && pixels.length) {
                for (let i = 0; i < pixels.length; i += 4) {
                  const jitter = Math.floor((rand() - 0.5) * 4);
                  pixels[i] = (pixels[i] + jitter) & 0xff;
                  pixels[i+1] = (pixels[i+1] + jitter) & 0xff;
                  pixels[i+2] = (pixels[i+2] + jitter) & 0xff;
                }
              }
            } catch (e) {}
          };
        }
        if (typeof WebGLRenderingContext !== 'undefined') {
          const origRP = WebGLRenderingContext.prototype.readPixels;
          WebGLRenderingContext.prototype.readPixels = noiseReadPixels(origRP);
        }
        if (typeof WebGL2RenderingContext !== 'undefined') {
          const origRP2 = WebGL2RenderingContext.prototype.readPixels;
          WebGL2RenderingContext.prototype.readPixels = noiseReadPixels(origRP2);
        }
      } catch (e) {}
    })();
  }

  // ---- ClientRects noise ----
  if (NOISE_CLIENT_RECTS) {
    (function patchClientRects() {
      try {
        const rand = seeded;
        const shift = () => (rand() - 0.5) * 0.25; // tiny sub-pixel offset

        function noiseDOMRect(rect) {
          const s = shift();
          return new DOMRect(rect.x + s, rect.y + s, rect.width + s, rect.height + s);
        }

        const origGetBCR = Element.prototype.getBoundingClientRect;
        Element.prototype.getBoundingClientRect = function () {
          return noiseDOMRect(origGetBCR.call(this));
        };

        const origGetCR = Element.prototype.getClientRects;
        Element.prototype.getClientRects = function () {
          const rects = origGetCR.call(this);
          const result = [];
          for (let i = 0; i < rects.length; i++) {
            result.push(noiseDOMRect(rects[i]));
          }
          // mimic DOMRectList
          result.item = function (idx) { return this[idx] || null; };
          return result;
        };

        // Range methods too
        if (typeof Range !== 'undefined') {
          const origRangeBCR = Range.prototype.getBoundingClientRect;
          Range.prototype.getBoundingClientRect = function () {
            return noiseDOMRect(origRangeBCR.call(this));
          };
          const origRangeCR = Range.prototype.getClientRects;
          Range.prototype.getClientRects = function () {
            const rects = origRangeCR.call(this);
            const result = [];
            for (let i = 0; i < rects.length; i++) {
              result.push(noiseDOMRect(rects[i]));
            }
            result.item = function (idx) { return this[idx] || null; };
            return result;
          };
        }
      } catch (e) {}
    })();
  }

  // ---- SpeechVoices spoofing ----
  if (NOISE_SPEECH_VOICES) {
    (function patchSpeechVoices() {
      try {
        if (typeof speechSynthesis === 'undefined') return;
        const origGetVoices = speechSynthesis.getVoices;
        const cachedVoices = null;
        speechSynthesis.getVoices = function () {
          const voices = origGetVoices.call(this);
          if (!voices || !voices.length) return voices;
          // Return a deterministic subset based on seed to create a unique but stable fingerprint
          const rand = xfnv1a(CANVAS_SEED + '_voices');
          const count = Math.max(3, Math.floor(rand() * voices.length * 0.7) + 3);
          // Stable shuffle using seed
          const indices = [];
          for (let i = 0; i < voices.length; i++) indices.push(i);
          for (let i = indices.length - 1; i > 0; i--) {
            const j = Math.floor(rand() * (i + 1));
            const tmp = indices[i]; indices[i] = indices[j]; indices[j] = tmp;
          }
          const result = [];
          for (let i = 0; i < Math.min(count, indices.length); i++) {
            result.push(voices[indices[i]]);
          }
          return result;
        };
      } catch (e) {}
    })();
  }

  // ---- Media device spoofing ----
  if (NOISE_MEDIA_DEVICES) {
    (function patchMediaDevices() {
      try {
        if (!navigator.mediaDevices || !navigator.mediaDevices.enumerateDevices) return;
        const origEnumerate = navigator.mediaDevices.enumerateDevices;
        navigator.mediaDevices.enumerateDevices = function () {
          return origEnumerate.call(this).then(function (devices) {
            // Generate deterministic fake device IDs using seed
            const rand = xfnv1a(CANVAS_SEED + '_media');
            return devices.map(function (device) {
              // Build a deterministic fake deviceId
              let fakeId = '';
              for (let i = 0; i < 32; i++) {
                fakeId += Math.floor(rand() * 16).toString(16);
              }
              return {
                deviceId: fakeId,
                kind: device.kind,
                label: '', // hide real labels for privacy
                groupId: fakeId.substring(0, 16),
                toJSON: function () {
                  return { deviceId: this.deviceId, kind: this.kind, label: this.label, groupId: this.groupId };
                }
              };
            });
          });
        };
      } catch (e) {}
    })();
  }

  // ---- Font detection protection ----
  if (FONT_PROTECTION) {
    (function patchFonts() {
      try {
        // Font fingerprinting works by measuring offsetWidth/offsetHeight of text in various fonts.
        // We add slight noise to offset measurements to prevent exact font enumeration.
        const rand = seeded;

        // If custom fonts list is provided, restrict document.fonts.check()
        if (CUSTOM_FONTS.length > 0 && document.fonts && document.fonts.check) {
          const origCheck = document.fonts.check.bind(document.fonts);
          document.fonts.check = function (font, text) {
            // Extract font family from the CSS font shorthand
            const match = font.match(/(?:['"]([^'"]+)['"]|(\S+))$/);
            const family = match ? (match[1] || match[2]) : '';
            if (family && CUSTOM_FONTS.indexOf(family) === -1) {
              return false; // pretend font is not available
            }
            return origCheck(font, text);
          };
        }

        // Add noise to offsetWidth/offsetHeight to foil measurement-based detection
        const origOffsetWidth = Object.getOwnPropertyDescriptor(HTMLElement.prototype, 'offsetWidth');
        const origOffsetHeight = Object.getOwnPropertyDescriptor(HTMLElement.prototype, 'offsetHeight');
        if (origOffsetWidth && origOffsetWidth.get) {
          Object.defineProperty(HTMLElement.prototype, 'offsetWidth', {
            get: function () {
              const w = origOffsetWidth.get.call(this);
              return w + Math.floor((rand() - 0.5) * 2);
            },
            configurable: true
          });
        }
        if (origOffsetHeight && origOffsetHeight.get) {
          Object.defineProperty(HTMLElement.prototype, 'offsetHeight', {
            get: function () {
              const h = origOffsetHeight.get.call(this);
              return h + Math.floor((rand() - 0.5) * 2);
            },
            configurable: true
          });
        }
      } catch (e) {}
    })();
  }

  // ---- Port scan protection ----
  if (PORT_SCAN_PROTECTION) {
    (function patchPortScan() {
      try {
        // Common ports used by port-scanning scripts to detect local services
        const BLOCKED_PORTS = new Set([
          3389, 5900, 5800, 8080, 8443, 9222, 9229, 6379, 5432, 3306,
          27017, 1433, 11211, 6380, 4444, 9515, 7070, 5555, 8888
        ]);
        // Allow user-specified ports
        const ALLOWED = new Set(PORT_SCAN_ALLOWED || [80, 443]);

        function extractPort(url) {
          try {
            const u = new URL(url, location.href);
            const p = parseInt(u.port, 10);
            if (p) return p;
            return u.protocol === 'https:' ? 443 : 80;
          } catch (e) { return 0; }
        }

        function isBlockedPort(port) {
          if (!port || port === 80 || port === 443) return false;
          if (ALLOWED.has(port)) return false;
          if (BLOCKED_PORTS.has(port)) return true;
          // Block connections to localhost on non-standard ports
          return false;
        }

        // Patch WebSocket
        const OrigWebSocket = window.WebSocket;
        window.WebSocket = function (url, protocols) {
          const port = extractPort(url);
          if (isBlockedPort(port)) {
            throw new DOMException('WebSocket connection blocked by port scan protection', 'SecurityError');
          }
          return new OrigWebSocket(url, protocols);
        };
        window.WebSocket.prototype = OrigWebSocket.prototype;
        window.WebSocket.CONNECTING = OrigWebSocket.CONNECTING;
        window.WebSocket.OPEN = OrigWebSocket.OPEN;
        window.WebSocket.CLOSING = OrigWebSocket.CLOSING;
        window.WebSocket.CLOSED = OrigWebSocket.CLOSED;

        // Patch fetch for localhost port scanning
        const origFetch = window.fetch;
        window.fetch = function (input, init) {
          try {
            const url = typeof input === 'string' ? input : (input && input.url ? input.url : '');
            const port = extractPort(url);
            if (isBlockedPort(port)) {
              return Promise.reject(new TypeError('Failed to fetch (port blocked)'));
            }
          } catch (e) {}
          return origFetch.apply(this, arguments);
        };

        // Patch XMLHttpRequest.open
        const origXHROpen = XMLHttpRequest.prototype.open;
        XMLHttpRequest.prototype.open = function (method, url) {
          try {
            const port = extractPort(url);
            if (isBlockedPort(port)) {
              throw new DOMException('XHR blocked by port scan protection', 'SecurityError');
            }
          } catch (e) {
            if (e instanceof DOMException) throw e;
          }
          return origXHROpen.apply(this, arguments);
        };
      } catch (e) {}
    })();
  }

  // ---- WebGPU spoofing ----
  if (WEBGPU_MODE && WEBGPU_MODE !== 'real' && WEBGPU_MODE !== '__WEBGPU_MODE__') {
    (function patchWebGPU() {
      try {
        if (!navigator.gpu) return;

        if (WEBGPU_MODE === 'disabled') {
          // Completely hide WebGPU
          try {
            Object.defineProperty(navigator, 'gpu', {
              get: () => undefined,
              configurable: true
            });
          } catch (e) {
            try { delete navigator.gpu; } catch (ee) {}
          }
          return;
        }

        if (WEBGPU_MODE === 'based_on_webgl') {
          // Override requestAdapter to return spoofed GPU info matching WebGL config
          const origRequestAdapter = navigator.gpu.requestAdapter;
          navigator.gpu.requestAdapter = function () {
            return origRequestAdapter.apply(this, arguments).then(function (adapter) {
              if (!adapter) return adapter;
              // Wrap adapter.requestAdapterInfo to return spoofed data
              const origReqInfo = adapter.requestAdapterInfo;
              if (origReqInfo) {
                adapter.requestAdapterInfo = function () {
                  return origReqInfo.apply(this, arguments).then(function (info) {
                    // Override with WebGL vendor/renderer info
                    try {
                      Object.defineProperty(info, 'vendor', { get: () => WEBGL_VENDOR, configurable: true });
                      Object.defineProperty(info, 'architecture', { get: () => '', configurable: true });
                      Object.defineProperty(info, 'description', { get: () => WEBGL_RENDERER, configurable: true });
                    } catch (e) {}
                    return info;
                  });
                };
              }
              // Also try the info property (newer API)
              try {
                const origInfo = Object.getOwnPropertyDescriptor(Object.getPrototypeOf(adapter), 'info');
                if (origInfo && origInfo.get) {
                  Object.defineProperty(adapter, 'info', {
                    get: function () {
                      const info = origInfo.get.call(this);
                      try {
                        return {
                          vendor: WEBGL_VENDOR,
                          architecture: info ? info.architecture : '',
                          device: info ? info.device : '',
                          description: WEBGL_RENDERER,
                        };
                      } catch (e) { return info; }
                    },
                    configurable: true
                  });
                }
              } catch (e) {}
              return adapter;
            });
          };
        }
      } catch (e) {}
    })();
  }

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
})();
