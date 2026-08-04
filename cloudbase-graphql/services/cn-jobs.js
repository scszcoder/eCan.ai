const { saveLegacy } = require('../compat/cn-legacy');

async function dequeueTasks(prisma, identity, input) {
  const vehicleIds = (input || []).flatMap((item) => String(item.vehicles || '').split(',')).map((id) => id.trim()).filter(Boolean);
  const rows = await prisma.agentTaskRel.findMany({ where: { vehicleId: { in: vehicleIds }, status: { in: ['assigned', 'pending'] }, agent: { owner: identity.sub } }, include: { task: true }, take: 100 });
  return JSON.stringify(rows.map((row) => ({ relation_id: row.id, vehicle_id: row.vehicleId, task: row.task })));
}

async function reportVehicles(prisma, identity, input) {
  const results = [];
  for (const item of input || []) {
    if (item.owner && item.owner !== identity.sub) { results.push({ id: item.vid, success: false, error: 'Cross-owner access is forbidden' }); continue; }
    const id = item.vid ? String(item.vid) : undefined;
    const data = { owner: identity.sub, name: item.vname, status: item.status || 'online', ipAddress: item.ip, lastHeartbeat: item.lastseen ? new Date(item.lastseen) : new Date(), capabilities: { functions: item.functions, bids: item.bids }, extraMetadata: { hardware: item.hardware, software: item.software } };
    try { const existing = id ? await prisma.vehicle.findFirst({ where: { id, owner: identity.sub }, select: { id: true } }) : null; const row = existing ? await prisma.vehicle.update({ where: { id }, data }) : await prisma.vehicle.create({ data: { ...data, ...(id ? { id } : {}) } }); results.push({ id: row.id, success: true }); }
    catch (error) { results.push({ id: id || null, success: false, error: error.message }); }
  }
  return JSON.stringify(results);
}

async function requestExternalSkill(prisma, identity, input) {
  const records = (input || []).map((item) => ({ ...item, id: `${item.skid}:${item.requester_mid}:${Date.now()}`, owner: identity.sub, status: 'pending' }));
  return saveLegacy(prisma, identity, 'skill_run', records);
}

async function reportExternalSkill(prisma, identity, input) {
  const records = (input || []).map((item) => ({ ...item, id: item.run_id, owner: identity.sub }));
  return saveLegacy(prisma, identity, 'skill_run', records);
}

async function requestTraining(prisma, identity, input) {
  const jobs = [];
  for (const skill of input || []) { const row = await prisma.longLlmTask.create({ data: { owner: identity.sub, workType: 'skill-training', taskId: String(skill.skid), status: 'pending', input: skill } }); jobs.push({ id: row.id, skid: skill.skid, status: row.status }); }
  return JSON.stringify(jobs);
}

async function requestPuzzle(prisma, identity, input) {
  const puzzle = input?.[0]; if (!puzzle) throw new Error('Puzzle input required');
  await saveLegacy(prisma, identity, 'puzzle', [{ ...puzzle, id: puzzle.pzid, owner: identity.sub, status: 'pending' }]);
  return puzzle;
}

async function confirmPuzzle(prisma, identity, input) {
  const result = input?.[0]; if (!result) throw new Error('Puzzle result required');
  await saveLegacy(prisma, identity, 'puzzle', [{ ...result, id: result.pzid, owner: identity.sub, status: 'complete' }]);
  return result;
}

module.exports = { confirmPuzzle, dequeueTasks, reportExternalSkill, reportVehicles, requestExternalSkill, requestPuzzle, requestTraining };
