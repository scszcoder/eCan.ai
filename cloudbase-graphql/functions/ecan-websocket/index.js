// CloudFunction entry point - dispatches HTTP / WebSocket requests.
//
// When TCB routes an HTTP request through `/ws/push` or `/ws/status`, the
// event has `httpMethod` and no `action`. We map the path to the right
// handler in websocket.js. When TCB delivers a WebSocket lifecycle event
// (action: Connect / Disconnect / Message), we forward to the WS handler.

const path = require('path');

// Load the shared implementation. In the deployed package, websocket.js
// sits next to this file; locally it lives two levels up (see project root).
let handler;
try {
  handler = require(path.join(__dirname, 'websocket.js'));
} catch (e) {
  // Fallback for local dev where the package root is the project root.
  handler = require(path.join(__dirname, '..', '..', 'websocket.js'));
}

async function dispatch(event, context) {
  try {
    // WebSocket lifecycle events have `action`.
    if (event && (event.action === 'Connect' || event.action === 'Disconnect' || event.action === 'Message')) {
      return await handler.main(event, context);
    }

    // HTTP events: route by path.
    const rawPath = event.path || event.rawPath || '';
    const cleanPath = rawPath.split('?')[0].replace(/^\//, '');
    const lower = cleanPath.toLowerCase();

    if (lower.startsWith('ws/push') || lower === 'ws/push') {
      return await handler.push(event, context);
    }
    if (lower.startsWith('ws/status') || lower === 'ws/status') {
      return await handler.status(event, context);
    }

    // Default: respond with a simple health check so curl GETs don't 404.
    return {
      statusCode: 200,
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        success: true,
        service: 'ecan-websocket',
        message: 'Use POST /ws/push or GET /ws/status',
      }),
    };
  } catch (err) {
    // Make sure the function never throws — TCB / SCF expects a statusCode.
    console.error('dispatch error:', err && err.stack || err);
    return {
      statusCode: 500,
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        success: false,
        error: err.message || 'internal error',
      }),
    };
  }
}

exports.main = dispatch;
exports.push = (event, context) => handler.push(event, context);
exports.status = (event, context) => handler.status(event, context);