/**
 * CN Commerce Operations - Product, Warehouse, LabelFormat
 *
 * CRUD operations for eCommerce entities using existing legacy record pattern.
 */

const { saveLegacy, removeLegacy, queryLegacy } = require('../compat/cn-legacy');

function parseInput(input) {
  if (typeof input === 'string') {
    try { return JSON.parse(input); } catch { return {}; }
  }
  return input || {};
}

async function queryProducts(prisma, identity, input) {
  const selector = parseInput(input);
  return queryLegacy(prisma, identity, 'product', selector);
}

async function saveProducts(prisma, identity, input) {
  const items = (input || []).map(item => ({
    ...item,
    id: item.id || item.pid || item.sku,
  }));
  return saveLegacy(prisma, identity, 'product', items);
}

async function removeProducts(prisma, identity, input) {
  return removeLegacy(prisma, identity, 'product', input);
}

async function queryWarehouses(prisma, identity, input) {
  const selector = parseInput(input);
  return queryLegacy(prisma, identity, 'warehouse', selector);
}

async function saveWarehouses(prisma, identity, input, updateOnly = false) {
  const results = [];
  for (const item of input || []) {
    try {
      const owner = identity.sub;
      const externalId = String(item.id || item.code || '');
      if (!externalId) { results.push({ id: null, success: false, error: 'Missing warehouse id/code' }); continue; }
      const data = { ...item, owner, id: externalId };
      const existing = await prisma.legacyRecord.findFirst({ where: { owner, kind: 'warehouse', externalId } });
      if (updateOnly && !existing) { results.push({ id: externalId, success: false, error: 'Not found' }); continue; }
      const row = existing
        ? await prisma.legacyRecord.update({ where: { id: existing.id }, data: { data: item } })
        : await prisma.legacyRecord.create({ data: { owner, kind: 'warehouse', externalId, data: item } });
      results.push({ id: row.externalId, success: true });
    } catch (e) { results.push({ id: item?.id || null, success: false, error: e.message }); }
  }
  return JSON.stringify(results);
}

async function removeWarehouses(prisma, identity, input) {
  return removeLegacy(prisma, identity, 'warehouse', input);
}

async function queryLabelFormats(prisma, identity, input) {
  const selector = parseInput(input);
  return queryLegacy(prisma, identity, 'label_format', selector);
}

async function saveLabelFormats(prisma, identity, input, updateOnly = false) {
  const results = [];
  for (const item of input || []) {
    try {
      const owner = identity.sub;
      const externalId = String(item.id || item.name || '');
      if (!externalId) { results.push({ id: null, success: false, error: 'Missing label format id/name' }); continue; }
      const existing = await prisma.legacyRecord.findFirst({ where: { owner, kind: 'label_format', externalId } });
      if (updateOnly && !existing) { results.push({ id: externalId, success: false, error: 'Not found' }); continue; }
      const row = existing
        ? await prisma.legacyRecord.update({ where: { id: existing.id }, data: { data: item } })
        : await prisma.legacyRecord.create({ data: { owner, kind: 'label_format', externalId, data: item } });
      results.push({ id: row.externalId, success: true });
    } catch (e) { results.push({ id: item?.id || null, success: false, error: e.message }); }
  }
  return JSON.stringify(results);
}

async function removeLabelFormats(prisma, identity, input) {
  return removeLegacy(prisma, identity, 'label_format', input);
}

module.exports = {
  queryProducts, saveProducts, removeProducts,
  queryWarehouses, saveWarehouses, removeWarehouses,
  queryLabelFormats, saveLabelFormats, removeLabelFormats,
};
