const crypto = require('node:crypto');

function verifyRequest({ rawBody, timestamp, signature, secret, now = Date.now(), maxSkewSeconds = 300 }) {
  if (!secret || !timestamp || !signature) throw new Error('Missing launcher authentication');
  const seconds = Number(timestamp);
  if (!Number.isFinite(seconds) || Math.abs(Math.floor(now / 1000) - seconds) > maxSkewSeconds) throw new Error('Expired launcher request');
  const expected = crypto.createHmac('sha256', secret).update(`${timestamp}.${rawBody}`).digest('hex');
  const a = Buffer.from(expected, 'hex');
  const b = Buffer.from(String(signature), 'hex');
  if (a.length !== b.length || !crypto.timingSafeEqual(a, b)) throw new Error('Invalid launcher signature');
  return crypto.createHash('sha256').update(`${timestamp}.${signature}`).digest('hex');
}

function validatePayload(payload) {
  if (!payload || !payload.owner_id || !payload.task_id) throw new Error('owner_id and task_id are required');
  const env = Array.isArray(payload.environment) ? payload.environment : [];
  if (env.length > 40) throw new Error('Too many environment variables');
  return { ...payload, owner_id: String(payload.owner_id), task_id: String(payload.task_id), environment: env };
}

function buildJob({ payload, image, namespace, serviceAccount, workerSecret, requestId, limits }) {
  const safeTask = payload.task_id.replace(/[^a-z0-9-]/gi, '-').toLowerCase().slice(0, 24);
  const name = `ecan-${safeTask}-${requestId.slice(0, 10)}`.replace(/-+/g, '-');
  return {
    apiVersion: 'batch/v1', kind: 'Job',
    metadata: { name, namespace, labels: { app: 'ecan-cloud-worker', 'ecan-task-id': safeTask } },
    spec: {
      backoffLimit: 0, ttlSecondsAfterFinished: 86400,
      template: {
        metadata: { labels: { app: 'ecan-cloud-worker', 'ecan-request-id': requestId.slice(0, 63) } },
        spec: {
          restartPolicy: 'Never', serviceAccountName: serviceAccount,
          containers: [{
            name: 'worker', image, imagePullPolicy: 'IfNotPresent',
            envFrom: workerSecret ? [{ secretRef: { name: workerSecret } }] : [],
            env: payload.environment.map((item) => ({ name: String(item.name || item.Name), value: String(item.value ?? item.Value ?? '') })),
            resources: { requests: limits.requests, limits: limits.limits },
          }],
        },
      },
    },
  };
}

async function launch({ rawBody, headers, config, store, jobs, now }) {
  const requestId = verifyRequest({ rawBody, timestamp: headers.timestamp, signature: headers.signature, secret: config.secret, now });
  const payload = validatePayload(JSON.parse(rawBody));
  if (!(await store.authorize(payload))) throw new Error('Task not found for authenticated owner');
  const claim = await store.claim(requestId, payload);
  if (!claim.claimed) {
    if (claim.runId) return { run_id: claim.runId, replay: true };
    throw new Error('Identical launch request is already in progress');
  }
  const job = buildJob({ payload, image: config.image, namespace: config.namespace, serviceAccount: config.serviceAccount, workerSecret: config.workerSecret, requestId, limits: config.resources });
  try {
    const runId = await jobs.create(config.namespace, job);
    await store.complete(requestId, payload, runId);
    return { run_id: runId, replay: false };
  } catch (error) {
    await store.fail(requestId, error.message);
    throw error;
  }
}

module.exports = { buildJob, launch, validatePayload, verifyRequest };
