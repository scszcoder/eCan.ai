/**
 * 腾讯云 TCB Database REST API
 *
 * 使用 TCB 原生能力:
 * - 认证: TCB Auth (Bearer Token) - 云函数自动验证
 * - 数据库: TCB Database (原生集合权限控制)
 *
 * 对应 AWS: Lambda + AppSync + DynamoDB
 */

const cloudbase = require('@cloudbase/node-sdk');

const app = cloudbase.init({
  env: cloudbase.SyunWing,
});

function generateId(prefix) {
  return `${prefix}_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
}

function parseJson(value) {
  if (!value) return null;
  if (typeof value === 'object') return value;
  try { return JSON.parse(value); } catch { return value; }
}

exports.main = async (event, context) => {
  const uid = context.uid || 'anonymous';
  const db = app.database();
  const { httpMethod, path, body: rawBody } = event;
  const body = rawBody ? JSON.parse(rawBody) : {};

  try {
    // RESTful 路由
    const segments = (path || '').split('/').filter(Boolean);
    const collection = segments[0] || body.collection;
    const id = segments[1] || body.id;
    const action = body.action;

    if (!collection) {
      return { statusCode: 400, body: JSON.stringify({ error: 'collection is required' }) };
    }

    const col = db.collection(collection);

    // 统一响应格式
    const ok = (data) => ({ code: 0, data, requestId: context.request_id });
    const fail = (msg, code = 1) => ({ code, error: msg, requestId: context.request_id });

    // RESTful 操作
    switch (httpMethod) {
      case 'GET':
        if (id) {
          // 获取单条
          const doc = await col.doc(id).get();
          return ok(doc.data || null);
        }
        // 列表 - TCB 自动按权限过滤
        const list = await col.get();
        return ok(list.data);

      case 'POST':
        if (action === 'batch') {
          // 批量添加
          const input = body.input || [];
          const results = [];
          for (const item of input) {
            const docId = item.id || generateId(collection);
            await col.add({ ...item, _id: docId, owner: uid, created_at: new Date().toISOString() });
            results.push({ id: docId, success: true });
          }
          return ok(results);
        }
        // 单条添加
        const newId = body.id || generateId(collection);
        await col.add({ ...body, _id: newId, owner: uid, created_at: new Date().toISOString() });
        return ok({ id: newId, success: true });

      case 'PUT':
        if (!id) return fail('id is required for update');
        const updates = { ...body };
        delete updates._id;
        delete updates.id;
        delete updates.collection;
        delete updates.action;
        updates.updated_at = new Date().toISOString();
        await col.doc(id).update(updates);
        return ok({ id, success: true });

      case 'DELETE':
        if (!id) return fail('id is required for delete');
        await col.doc(id).remove();
        return ok({ id, success: true });

      case 'PATCH':
        if (!id) return fail('id is required for patch');
        const patchData = { ...body };
        delete patchData._id;
        delete patchData.id;
        delete patchData.collection;
        delete patchData.action;
        patchData.updated_at = new Date().toISOString();
        await col.doc(id).update(patchData);
        return ok({ id, success: true });

      default:
        // GraphQL 风格查询
        if (body.query) {
          return handleGraphQL(body, db, uid, context.request_id);
        }
        return fail('Unsupported method: ' + httpMethod);
    }
  } catch (error) {
    console.error('Error:', error);
    return { statusCode: 500, body: JSON.stringify({ code: 1, error: error.message }) };
  }
};

// GraphQL 风格处理
async function handleGraphQL(body, db, uid, requestId) {
  const { query, variables = {} } = body;
  const col = db.collection(variables.collection || 'agents');

  try {
    // 简单 GraphQL 解析
    if (query.includes('query')) {
      // 查询
      const list = await col.get();
      return { code: 0, data: list.data, requestId };
    } else if (query.includes('mutation')) {
      // 变更
      if (query.includes('addAgents') || query.includes('add')) {
        const input = variables.input || [{}];
        const results = [];
        for (const item of input) {
          const id = item.id || generateId('agent');
          await col.add({ ...item, _id: id, owner: uid });
          results.push({ id, success: true });
        }
        return { code: 0, data: results, requestId };
      }
      if (query.includes('updateAgents') || query.includes('update')) {
        const input = variables.input || [];
        const results = [];
        for (const item of input) {
          await col.doc(item.id).update(item);
          results.push({ id: item.id, success: true });
        }
        return { code: 0, data: results, requestId };
      }
    }
    return { code: 1, error: 'Unknown query', requestId };
  } catch (error) {
    return { code: 1, error: error.message, requestId };
  }
}
