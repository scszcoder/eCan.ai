/**
 * WhatsApp Baileys Bridge
 * Exposes a local REST API so the Python eCan.ai backend can send/receive
 * WhatsApp messages via the Baileys library (no Meta developer account needed).
 *
 * Endpoints:
 *   GET  /status          — connection status + phone number
 *   GET  /qr              — current QR code as base64 PNG (while unpaired)
 *   POST /send            — send a text message  { jid, text }
 *   POST /send-media      — send image/video     { jid, url, caption, mimetype }
 *   GET  /health          — liveness probe
 *
 * Inbound messages are forwarded to the Python webhook URL configured in the
 * WEBHOOK_URL environment variable (default: http://127.0.0.1:5100/channel/whatsapp).
 *
 * Environment variables:
 *   PORT         — port to listen on (default: 3210)
 *   WEBHOOK_URL  — Python inbound webhook URL
 *   SESSION_DIR  — directory to persist auth state (default: ./wa_session)
 *   LOG_LEVEL    — pino log level (default: info)
 */

'use strict';

const { default: makeWASocket, useMultiFileAuthState, DisconnectReason, fetchLatestBaileysVersion } = require('@whiskeysockets/baileys');
const express = require('express');
const axios = require('axios');
const QRCode = require('qrcode');
const pino = require('pino');
const path = require('path');
const fs = require('fs');

// ─── Config ──────────────────────────────────────────────────────────────────

const PORT = parseInt(process.env.PORT || '3210', 10);
const WEBHOOK_URL = process.env.WEBHOOK_URL || 'http://127.0.0.1:5100/channel/whatsapp';
const SESSION_DIR = process.env.SESSION_DIR || path.join(__dirname, 'wa_session');
const LOG_LEVEL = process.env.LOG_LEVEL || 'info';

if (!fs.existsSync(SESSION_DIR)) fs.mkdirSync(SESSION_DIR, { recursive: true });

const logger = pino({ level: LOG_LEVEL }).child({ name: 'wa-bridge' });

// ─── State ────────────────────────────────────────────────────────────────────

let sock = null;
let qrBase64 = null;       // current QR image (null when paired)
let connectionStatus = 'disconnected'; // disconnected | connecting | connected | error
let phoneNumber = null;
let reconnectTimeout = null;

// ─── Socket factory ───────────────────────────────────────────────────────────

async function connectToWhatsApp() {
  const { state, saveCreds } = await useMultiFileAuthState(SESSION_DIR);
  const { version } = await fetchLatestBaileysVersion();
  logger.info({ version }, 'Baileys version');

  sock = makeWASocket({
    version,
    auth: state,
    logger: pino({ level: 'silent' }),   // suppress noisy baileys logs
    printQRInTerminal: false,
    browser: ['eCan.ai', 'Chrome', '120.0'],
  });

  connectionStatus = 'connecting';

  sock.ev.on('creds.update', saveCreds);

  sock.ev.on('connection.update', async (update) => {
    const { connection, lastDisconnect, qr } = update;

    if (qr) {
      try {
        qrBase64 = await QRCode.toDataURL(qr);
        logger.info('QR code generated — scan with WhatsApp');
      } catch (err) {
        logger.error({ err }, 'QR encode failed');
      }
    }

    if (connection === 'close') {
      qrBase64 = null;
      const code = lastDisconnect?.error?.output?.statusCode;
      const isLoggedOut = code === DisconnectReason.loggedOut;
      logger.warn({ code, isLoggedOut }, 'Connection closed');

      if (isLoggedOut) {
        connectionStatus = 'disconnected';
        phoneNumber = null;
        // Wipe session so fresh QR is generated on next connect
        fs.rmSync(SESSION_DIR, { recursive: true, force: true });
        fs.mkdirSync(SESSION_DIR, { recursive: true });
      } else {
        connectionStatus = 'reconnecting';
      }

      // Reconnect after a short delay (unless deliberately stopped)
      if (!isLoggedOut) {
        reconnectTimeout = setTimeout(() => {
          logger.info('Reconnecting…');
          connectToWhatsApp().catch((e) => logger.error({ e }, 'Reconnect failed'));
        }, 5000);
      }
    }

    if (connection === 'open') {
      qrBase64 = null;
      connectionStatus = 'connected';
      phoneNumber = sock.user?.id?.split(':')[0] || null;
      logger.info({ phoneNumber }, 'WhatsApp connected');
    }
  });

  sock.ev.on('messages.upsert', async ({ messages, type }) => {
    if (type !== 'notify') return;
    for (const msg of messages) {
      if (msg.key.fromMe) continue;   // ignore own messages
      await forwardToWebhook(msg);
    }
  });
}

// ─── Webhook forwarding ───────────────────────────────────────────────────────

async function forwardToWebhook(msg) {
  const jid = msg.key.remoteJid || '';
  const senderId = msg.key.participant || jid.split('@')[0];
  const content = msg.message;
  const text =
    content?.conversation ||
    content?.extendedTextMessage?.text ||
    content?.imageMessage?.caption ||
    content?.videoMessage?.caption ||
    '';

  const payload = {
    jid,
    sender_id: senderId,
    sender_name: msg.pushName || '',
    text,
    message_type: content?.imageMessage ? 'image' : content?.videoMessage ? 'video' : 'text',
    timestamp: Number(msg.messageTimestamp) || Date.now() / 1000,
    raw_message_id: msg.key.id,
  };

  try {
    await axios.post(WEBHOOK_URL, payload, { timeout: 10000 });
    logger.debug({ jid, text: text.slice(0, 60) }, 'Forwarded inbound message');
  } catch (err) {
    logger.warn({ err: err.message }, 'Failed to forward inbound message to webhook');
  }
}

// ─── Express API ──────────────────────────────────────────────────────────────

const app = express();
app.use(express.json());

app.get('/health', (_req, res) => res.json({ ok: true }));

// Root: browser-friendly QR viewer (auto-refreshes every 4 s until paired)
app.get('/', (_req, res) => {
  res.setHeader('Content-Type', 'text/html');
  res.send(`<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <title>WhatsApp Baileys Bridge</title>
  <style>
    body { font-family: sans-serif; display: flex; flex-direction: column; align-items: center;
           justify-content: center; min-height: 100vh; margin: 0; background: #f0f2f5; }
    .card { background: #fff; border-radius: 12px; padding: 32px; box-shadow: 0 2px 12px #0001;
            text-align: center; max-width: 360px; width: 90%; }
    h2 { margin: 0 0 8px; }
    p  { color: #666; font-size: 14px; }
    #status-badge { display: inline-block; padding: 4px 12px; border-radius: 99px;
                    font-size: 13px; font-weight: 600; margin-bottom: 16px; }
    .connected    { background: #d1fae5; color: #065f46; }
    .connecting   { background: #dbeafe; color: #1e40af; }
    .disconnected { background: #fee2e2; color: #991b1b; }
    img { width: 240px; height: 240px; border: 1px solid #e5e7eb; border-radius: 8px; }
    #msg { font-size: 13px; color: #6b7280; margin-top: 12px; }
  </style>
</head>
<body>
  <div class="card">
    <h2>WhatsApp Bridge</h2>
    <div id="status-badge" class="connecting">checking…</div>
    <div id="qr-container"></div>
    <p id="msg">Loading…</p>
  </div>
  <script>
    async function refresh() {
      try {
        const st = await fetch('/status').then(r => r.json());
        const badge = document.getElementById('status-badge');
        badge.textContent = st.status + (st.phone_number ? ' · ' + st.phone_number : '');
        badge.className = '';
        if (st.status === 'connected') {
          badge.classList.add('connected');
          document.getElementById('qr-container').innerHTML = '';
          document.getElementById('msg').textContent = 'Paired successfully! Ready to receive messages.';
          return;
        }
        badge.classList.add(st.status === 'connecting' ? 'connecting' : 'disconnected');

        const qr = await fetch('/qr');
        if (qr.status === 204) {
          document.getElementById('qr-container').innerHTML = '';
          document.getElementById('msg').textContent = 'Connected — no QR needed.';
        } else {
          const data = await qr.json();
          if (data.qr_base64) {
            document.getElementById('qr-container').innerHTML =
              '<img src="data:image/png;base64,' + data.qr_base64 + '" alt="QR Code" />';
            document.getElementById('msg').textContent =
              'Scan with WhatsApp → Linked Devices → Link a Device';
          } else {
            document.getElementById('qr-container').innerHTML = '';
            document.getElementById('msg').textContent = 'Waiting for QR code from WhatsApp…';
          }
        }
      } catch (e) {
        document.getElementById('status-badge').textContent = 'unreachable';
        document.getElementById('status-badge').className = 'disconnected';
        document.getElementById('msg').textContent = 'Bridge not reachable: ' + e.message;
      }
    }
    refresh();
    setInterval(refresh, 4000);
  </script>
</body>
</html>`);
});

app.get('/status', (_req, res) => {
  res.json({ status: connectionStatus, phone_number: phoneNumber });
});

app.get('/qr', (_req, res) => {
  if (!qrBase64) {
    return res.status(204).json({ message: 'No QR available (already connected or not started)' });
  }
  // Strip the data-URL prefix so the client gets raw base64
  const base64 = qrBase64.replace(/^data:image\/png;base64,/, '');
  res.json({ qr_base64: base64 });
});

app.post('/send', async (req, res) => {
  const { jid, text } = req.body || {};
  if (!jid || !text) return res.status(400).json({ error: 'jid and text are required' });
  if (connectionStatus !== 'connected') return res.status(503).json({ error: 'Not connected to WhatsApp' });

  try {
    // Step 1: Resolve canonical JID
    let resolvedJid = jid;
    try {
      const [info] = await sock.onWhatsApp(jid);
      if (info?.exists) {
        resolvedJid = info.jid;
        logger.info({ jid, resolvedJid }, 'JID resolved');
      } else {
        logger.warn({ jid }, 'Number not found on WhatsApp — sending anyway');
      }
    } catch (lookupErr) {
      logger.warn({ jid, err: lookupErr.message }, 'onWhatsApp lookup failed — sending anyway');
    }

    // Step 2: Force pre-key fetch so the recipient can decrypt the message.
    // assertSessions downloads fresh pre-key bundles from WA servers, which
    // prevents the "Waiting for this message" error on the recipient's device.
    try {
      await sock.assertSessions([resolvedJid], true);
      logger.info({ resolvedJid }, 'Pre-key sessions asserted');
    } catch (sessErr) {
      logger.warn({ err: sessErr.message }, 'assertSessions failed — sending anyway');
    }

    const result = await sock.sendMessage(resolvedJid, { text });
    res.json({ success: true, message_id: result?.key?.id, resolved_jid: resolvedJid });
  } catch (err) {
    logger.error({ err }, 'Send message failed');
    res.status(500).json({ error: err.message });
  }
});

app.post('/send-media', async (req, res) => {
  const { jid, url, caption = '', mimetype = 'image/jpeg' } = req.body || {};
  if (!jid || !url) return res.status(400).json({ error: 'jid and url are required' });
  if (connectionStatus !== 'connected') return res.status(503).json({ error: 'Not connected' });

  const isVideo = mimetype.startsWith('video/');
  try {
    const result = await sock.sendMessage(jid, {
      [isVideo ? 'video' : 'image']: { url },
      caption,
      mimetype,
    });
    res.json({ success: true, message_id: result?.key?.id });
  } catch (err) {
    logger.error({ err }, 'Send media failed');
    res.status(500).json({ error: err.message });
  }
});

// ─── Start ────────────────────────────────────────────────────────────────────

app.listen(PORT, '127.0.0.1', () => {
  logger.info({ port: PORT, webhook: WEBHOOK_URL }, 'Baileys bridge listening');
  connectToWhatsApp().catch((e) => logger.error({ e }, 'Initial connect failed'));
});

// Graceful shutdown
process.on('SIGINT', () => {
  logger.info('Shutting down');
  clearTimeout(reconnectTimeout);
  process.exit(0);
});
