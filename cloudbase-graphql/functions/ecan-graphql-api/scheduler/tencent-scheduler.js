const crypto = require('node:crypto');
const http = require('node:http');
const https = require('node:https');

function requestJson(url, options) {
  return new Promise((resolve, reject) => {
    const target = new URL(url);
    const transport = target.protocol === 'https:' ? https : http;
    const request = transport.request(target, {
      method: options.method,
      headers: options.headers,
    }, (response) => {
      let raw = '';
      response.setEncoding('utf8');
      response.on('data', (chunk) => { raw += chunk; });
      response.on('end', () => {
        resolve({
          ok: response.statusCode >= 200 && response.statusCode < 300,
          status: response.statusCode,
          async json() { return raw ? JSON.parse(raw) : {}; },
        });
      });
    });
    request.setTimeout(15000, () => request.destroy(new Error('Worker Launcher request timed out')));
    request.on('error', reject);
    request.end(options.body);
  });
}

function toScfCron(expression) {
  const value = String(expression || '').trim();
  const cron = value.match(/^cron\((.+)\)$/i);
  if (cron) {
    const fields = cron[1].trim().split(/\s+/);
    if (fields.length !== 6) throw new Error(`Unsupported scheduler cron: ${expression}`);
    return `0 ${fields.join(' ')}`;
  }
  const rate = value.match(/^rate\((\d+)\s+(minute|minutes|hour|hours|day|days)\)$/i);
  if (!rate) throw new Error(`Unsupported schedule expression: ${expression}`);
  const count = Number(rate[1]); const unit = rate[2].toLowerCase();
  if (unit.startsWith('minute') && count <= 59) return `0 */${count} * * * * *`;
  if (unit.startsWith('hour') && count <= 23) return `0 0 */${count} * * * *`;
  if (unit.startsWith('day') && count <= 31) return `0 0 0 */${count} * * *`;
  throw new Error(`Schedule interval is outside SCF cron limits: ${expression}`);
}

function scheduleExpression(schedule) {
  if (typeof schedule === 'string') return schedule;
  const type = String(schedule?.repeat_type || schedule?.repeatType || '').toLowerCase();
  const count = Number(schedule?.repeat_number || schedule?.repeatNumber || 1);
  if (type === 'by minutes') return `rate(${count} minutes)`;
  if (type === 'by hours') return `rate(${count} hours)`;
  if (type === 'by days') return `rate(${count} days)`;
  if (!type || type === 'none') return null;
  throw new Error(`Unsupported CN repeat type: ${type}`);
}

function triggerName(taskId) { return `ecan-task-${String(taskId).replace(/[^A-Za-z0-9_-]/g, '-').slice(0, 48)}`; }

function createScfClient(env = process.env) {
  const tencentcloud = require('tencentcloud-sdk-nodejs');
  return new tencentcloud.scf.v20180416.Client({
    credential: { secretId: env.TENCENTCLOUD_SECRETID || env.ECAN_TENCENT_SECRET_ID, secretKey: env.TENCENTCLOUD_SECRETKEY || env.ECAN_TENCENT_SECRET_KEY, token: env.TENCENTCLOUD_SESSIONTOKEN },
    region: env.TENCENT_REGION || env.TCB_REGION || 'ap-guangzhou',
    profile: { httpProfile: { endpoint: 'scf.tencentcloudapi.com' } },
  });
}

class TencentScheduler {
  constructor({ env = process.env, scfClient, fetchImpl = requestJson } = {}) { this.env = env; this.scf = scfClient || null; this.fetch = fetchImpl; }
  getScf() { if (!this.scf) this.scf = createScfClient(this.env); return this.scf; }
  async syncTask({ taskId, owner, taskType, triggerType, schedule, parameters }) {
    const shouldSchedule = String(taskType || '').toLowerCase() === 'cloud' && String(triggerType || '').toLowerCase() === 'schedule';
    const expression = shouldSchedule ? scheduleExpression(schedule) : null;
    if (!expression) return this.deleteTask(taskId);
    const functionName = this.env.TENCENT_SCHEDULER_FUNCTION;
    if (!functionName) throw new Error('TENCENT_SCHEDULER_FUNCTION is required');
    const params = { FunctionName: functionName, Namespace: this.env.TENCENT_SCF_NAMESPACE || 'default', TriggerName: triggerName(taskId), Type: 'timer', TriggerDesc: toScfCron(expression), Enable: 'OPEN', CustomArgument: JSON.stringify({ action: 'run_cloud_task', owner_id: owner, task_id: String(taskId), options: parameters || {} }) };
    const scf = this.getScf();
    try { await scf.UpdateTrigger(params); } catch (error) { if (!/notfound|resourcenotfound/i.test(error?.code || error?.Code || '')) throw error; await scf.CreateTrigger(params); }
  }
  async deleteTask(taskId) {
    if (!this.env.TENCENT_SCHEDULER_FUNCTION) return;
    try { await this.getScf().DeleteTrigger({ FunctionName: this.env.TENCENT_SCHEDULER_FUNCTION, Namespace: this.env.TENCENT_SCF_NAMESPACE || 'default', TriggerName: triggerName(taskId), Type: 'timer' }); }
    catch (error) { if (!/notfound|resourcenotfound/i.test(error?.code || error?.Code || '')) throw error; }
  }
  async launch({ owner, taskId, agentId, options = {} }) {
    const body = JSON.stringify({ owner_id: owner, task_id: String(taskId), schedule: 'now', meta_data: { ...options, agent_id: agentId || null }, environment: [
      { name: 'ECAN_CLOUD_PROVIDER', value: 'tencent' }, { name: 'ECAN_WORKER_MODE', value: 'single' }, { name: 'ECAN_TASK_ID', value: String(taskId) }, { name: 'ECAN_TASK_OWNER', value: owner }, { name: 'ECAN_TASK_PARAMS', value: JSON.stringify(options) },
    ] });
    if (Buffer.byteLength(body) > 65536) throw new Error('Worker launch payload exceeds 64 KiB');
    const timestamp = Math.floor(Date.now()/1000).toString(); const secret = this.env.TENCENT_WORKER_LAUNCH_SECRET; const url = this.env.TENCENT_WORKER_LAUNCH_URL;
    if (!url || !secret) throw new Error('Tencent Worker Launcher is not configured');
    const signature = crypto.createHmac('sha256', secret).update(`${timestamp}.${body}`).digest('hex');
    const response = await this.fetch(url, { method:'POST', headers:{'Content-Type':'application/json','X-ECAN-Timestamp':timestamp,'X-ECAN-Signature':signature}, body });
    const data = await response.json().catch(()=>({})); if (!response.ok) throw new Error(data.error || `Worker Launcher HTTP ${response.status}`); return data.run_id;
  }
}

module.exports = { TencentScheduler, requestJson, scheduleExpression, toScfCron, triggerName };
