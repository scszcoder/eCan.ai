// stealth_injection.js

// Hide navigator.webdriver
Object.defineProperty(navigator, 'webdriver', {
  get: () => false,
});

// Mock plugins
Object.defineProperty(navigator, 'plugins', {
  get: () => [1, 2, 3, 4, 5],
});

// Mock languages
Object.defineProperty(navigator, 'languages', {
  get: () => ['en-US', 'en'],
});

// Spoof WebGL vendor
const getParameter = WebGLRenderingContext.prototype.getParameter;
WebGLRenderingContext.prototype.getParameter = function (param) {
  if (param === 37445) return 'Intel Inc.'; // UNMASKED_VENDOR_WEBGL
  if (param === 37446) return 'Intel Iris OpenGL Engine'; // UNMASKED_RENDERER_WEBGL
  return getParameter.call(this, param);
};

// Canvas fingerprint spoofing
const toDataURL = HTMLCanvasElement.prototype.toDataURL;
HTMLCanvasElement.prototype.toDataURL = function () {
  return "data:image/png;base64,fakebase64string";
};

// Audio fingerprint spoofing
const originalGetFloatFrequencyData = AnalyserNode.prototype.getFloatFrequencyData;
AnalyserNode.prototype.getFloatFrequencyData = function (array) {
  const spoofed = new Float32Array(array.length).map(() => Math.random() * 100 - 50);
  array.set(spoofed);
};

// Spoof permissions query
const originalQuery = window.navigator.permissions.query;
window.navigator.permissions.query = parameters =>
  parameters.name === 'notifications'
    ? Promise.resolve({ state: Notification.permission })
    : originalQuery(parameters);
