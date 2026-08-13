const assert = require('node:assert/strict');
const crypto = require('node:crypto');
const { launch, verifyRequest } = require('./core');

async function main() {
  const secret = 'secret'; const rawBody = JSON.stringify({ owner_id: 'u1', task_id: 't1', environment: [{ name: 'A', value: 'B' }] });
  const timestamp = Math.floor(Date.now()/1000).toString(); const signature = crypto.createHmac('sha256', secret).update(`${timestamp}.${rawBody}`).digest('hex');
  assert.ok(verifyRequest({rawBody,timestamp,signature,secret}));
  assert.throws(() => verifyRequest({rawBody,timestamp,signature:'00',secret}), /signature/);
  let completed;
  const store = { async authorize(){return true}, async claim(){return {claimed:true}}, async complete(...a){completed=a}, async fail(){throw new Error('unexpected')} };
  const jobs = { async create(namespace, job){ assert.equal(namespace,'workers'); assert.equal(job.spec.template.spec.containers[0].image,'approved/image:1'); assert.equal(job.spec.template.spec.containers[0].envFrom[0].secretRef.name,'worker-runtime'); return 'job-1'; } };
  const result = await launch({rawBody,headers:{timestamp,signature},config:{secret,image:'approved/image:1',namespace:'workers',serviceAccount:'worker',workerSecret:'worker-runtime',resources:{requests:{cpu:'1',memory:'1Gi'},limits:{cpu:'2',memory:'2Gi'}}},store,jobs});
  assert.equal(result.run_id,'job-1'); assert.equal(completed[2],'job-1');
  console.log('PASS worker launcher authentication, Job policy and persistence contract');
}
main().catch(e=>{console.error(e);process.exitCode=1});
