/**
 * GraphQL Resolvers
 */

function generateId(prefix) {
  return `${prefix}_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
}

function parseJson(value) {
  if (!value) return null;
  if (typeof value === 'object') return value;
  try { return JSON.parse(value); } catch { return value; }
}

const resolvers = {
  Query: {
    getAgents: async (_, { owner }, { dataSources, identity }) => {
      const [rows] = await dataSources.mysql.pool().execute(
        'SELECT * FROM agents WHERE owner = ? AND deleted_at IS NULL ORDER BY created_at DESC',
        [owner || identity.sub]
      );
      return rows;
    },

    queryAgents: async (_, { input }, { dataSources }) => {
      const params = typeof input === 'string' ? JSON.parse(input) : (input || {});
      let sql = 'SELECT * FROM agents WHERE deleted_at IS NULL';
      const values = [];
      if (params.name) { sql += ' AND name LIKE ?'; values.push(`%${params.name}%`); }
      if (params.status) { sql += ' AND status = ?'; values.push(params.status); }
      if (params.owner) { sql += ' AND owner = ?'; values.push(params.owner); }
      sql += ' ORDER BY created_at DESC LIMIT 100';
      const [rows] = await dataSources.mysql.pool().execute(sql, values);
      return rows;
    },

    getAgentSkills: async (_, { owner }, { dataSources, identity }) => {
      const [rows] = await dataSources.mysql.pool().execute(
        'SELECT * FROM agent_skills WHERE owner = ? AND deleted_at IS NULL ORDER BY created_at DESC',
        [owner || identity.sub]
      );
      return rows.map(r => ({ ...r, id: r.id, askid: r.id }));
    },

    queryAgentSkills: async (_, { input }, { dataSources }) => {
      const params = typeof input === 'string' ? JSON.parse(input) : (input || {});
      let sql = 'SELECT * FROM agent_skills WHERE deleted_at IS NULL';
      const values = [];
      if (params.name) { sql += ' AND name LIKE ?'; values.push(`%${params.name}%`); }
      if (params.owner) { sql += ' AND owner = ?'; values.push(params.owner); }
      if (params.public !== undefined) { sql += ' AND public = ?'; values.push(params.public); }
      sql += ' ORDER BY created_at DESC LIMIT 100';
      const [rows] = await dataSources.mysql.pool().execute(sql, values);
      return rows.map(r => ({ ...r, id: r.id, askid: r.id }));
    },

    getAgentTasks: async (_, { owner }, { dataSources, identity }) => {
      const [rows] = await dataSources.mysql.pool().execute(
        'SELECT * FROM agent_tasks WHERE owner = ? ORDER BY created_at DESC',
        [owner || identity.sub]
      );
      return rows;
    },

    queryAgentTasks: async (_, { input }, { dataSources }) => {
      const params = typeof input === 'string' ? JSON.parse(input) : (input || {});
      let sql = 'SELECT * FROM agent_tasks WHERE 1=1';
      const values = [];
      if (params.status) { sql += ' AND status = ?'; values.push(params.status); }
      if (params.owner) { sql += ' AND owner = ?'; values.push(params.owner); }
      sql += ' ORDER BY created_at DESC LIMIT 100';
      const [rows] = await dataSources.mysql.pool().execute(sql, values);
      return rows;
    },

    getVehicles: async (_, { owner }, { dataSources, identity }) => {
      const [rows] = await dataSources.mysql.pool().execute(
        'SELECT * FROM agent_vehicles WHERE owner = ? ORDER BY created_at DESC',
        [owner || identity.sub]
      );
      return rows;
    },

    queryVehicles: async (_, { input }, { dataSources }) => {
      const params = typeof input === 'string' ? JSON.parse(input) : (input || {});
      let sql = 'SELECT * FROM agent_vehicles WHERE 1=1';
      const values = [];
      if (params.status) { sql += ' AND status = ?'; values.push(params.status); }
      sql += ' ORDER BY created_at DESC LIMIT 100';
      const [rows] = await dataSources.mysql.pool().execute(sql, values);
      return rows;
    },

    getOrgs: async (_, { owner }, { dataSources }) => {
      const [rows] = await dataSources.mysql.pool().execute(
        'SELECT * FROM agent_orgs WHERE 1=1 ORDER BY sort_order, created_at', []
      );
      return rows;
    },

    getSettings: async (_, { key }, { dataSources }) => {
      const [rows] = await dataSources.mysql.pool().execute(
        'SELECT value FROM settings WHERE `key` = ?', [key]
      );
      return rows[0]?.value || '{}';
    },

    getStory: async (_, { id }, { dataSources }) => {
      const [rows] = await dataSources.mysql.pool().execute(
        'SELECT * FROM stories WHERE id = ?', [id]
      );
      return rows[0] || null;
    },

    listStories: async (_, { input }, { dataSources }) => {
      const params = typeof input === 'string' ? JSON.parse(input) : (input || {});
      let sql = 'SELECT * FROM stories WHERE 1=1';
      const values = [];
      if (params.owner) { sql += ' AND owner = ?'; values.push(params.owner); }
      if (params.status) { sql += ' AND status = ?'; values.push(params.status); }
      sql += ' ORDER BY updated_at DESC LIMIT 100';
      const [rows] = await dataSources.mysql.pool().execute(sql, values);
      return rows;
    },
  },

  Mutation: {
    addAgents: async (_, { input }, { dataSources, identity }) => {
      const results = [];
      for (const agent of input) {
        try {
          const id = agent.id || generateId('agent');
          const now = new Date().toISOString();
          const owner = agent.owner || identity.sub;
          await dataSources.mysql.pool().execute(
            `INSERT INTO agents (id, name, owner, description, gender, title, status, extra_data, created_at, updated_at)
             VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`,
            [id, agent.name, owner, agent.description || null, agent.gender || 'male',
             agent.title ? JSON.stringify(agent.title) : null, agent.status || 'active',
             agent.extra_data ? JSON.stringify(agent.extra_data) : null, now, now]
          );
          results.push({ id, success: true });
        } catch (error) {
          results.push({ id: agent.id, success: false, error: error.message });
        }
      }
      return results;
    },

    updateAgents: async (_, { input }, { dataSources }) => {
      const results = [];
      for (const agent of input) {
        try {
          const updates = [], values = [];
          if (agent.name !== undefined) { updates.push('name = ?'); values.push(agent.name); }
          if (agent.description !== undefined) { updates.push('description = ?'); values.push(agent.description); }
          if (agent.status !== undefined) { updates.push('status = ?'); values.push(agent.status); }
          if (agent.extra_data !== undefined) { updates.push('extra_data = ?'); values.push(JSON.stringify(agent.extra_data)); }
          updates.push('updated_at = ?'); values.push(new Date().toISOString());
          values.push(agent.id);
          await dataSources.mysql.pool().execute(
            `UPDATE agents SET ${updates.join(', ')} WHERE id = ?`, values
          );
          results.push({ id: agent.id, success: true });
        } catch (error) {
          results.push({ id: agent.id, success: false, error: error.message });
        }
      }
      return results;
    },

    removeAgents: async (_, { input }, { dataSources }) => {
      const results = [];
      for (const item of input) {
        try {
          await dataSources.mysql.pool().execute(
            'UPDATE agents SET deleted_at = ? WHERE id = ?',
            [new Date().toISOString(), item.id]
          );
          results.push({ id: item.id, success: true });
        } catch (error) {
          results.push({ id: item.id, success: false, error: error.message });
        }
      }
      return results;
    },

    addAgentSkills: async (_, { input }, { dataSources, identity }) => {
      const results = [];
      for (const skill of input) {
        try {
          const id = skill.askid || skill.id || generateId('skill');
          const now = new Date().toISOString();
          const owner = skill.owner || identity.sub;
          await dataSources.mysql.pool().execute(
            `INSERT INTO agent_skills (id, name, owner, description, version, config, tags, source, price, public, created_at, updated_at)
             VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`,
            [id, skill.name, owner, skill.description || null, skill.version || '1.0.0',
             skill.config ? JSON.stringify(skill.config) : null,
             skill.tags ? JSON.stringify(skill.tags) : null,
             skill.source || 'ui', skill.price || 0, skill.public || false, now, now]
          );
          results.push({ id, askid: id, success: true });
        } catch (error) {
          results.push({ askid: skill.askid, success: false, error: error.message });
        }
      }
      return results;
    },

    updateAgentSkills: async (_, { input }, { dataSources }) => {
      const results = [];
      for (const skill of input) {
        try {
          const updates = [], values = [];
          if (skill.name !== undefined) { updates.push('name = ?'); values.push(skill.name); }
          if (skill.description !== undefined) { updates.push('description = ?'); values.push(skill.description); }
          if (skill.config !== undefined) { updates.push('config = ?'); values.push(JSON.stringify(skill.config)); }
          if (skill.tags !== undefined) { updates.push('tags = ?'); values.push(JSON.stringify(skill.tags)); }
          if (skill.public !== undefined) { updates.push('public = ?'); values.push(skill.public); }
          updates.push('updated_at = ?'); values.push(new Date().toISOString());
          values.push(skill.askid || skill.id);
          await dataSources.mysql.pool().execute(
            `UPDATE agent_skills SET ${updates.join(', ')} WHERE id = ?`, values
          );
          results.push({ id: skill.id, askid: skill.askid, success: true });
        } catch (error) {
          results.push({ askid: skill.askid, success: false, error: error.message });
        }
      }
      return results;
    },

    removeAgentSkills: async (_, { input }, { dataSources }) => {
      const results = [];
      for (const item of input) {
        try {
          await dataSources.mysql.pool().execute(
            'UPDATE agent_skills SET deleted_at = ? WHERE id = ?',
            [new Date().toISOString(), item.id]
          );
          results.push({ id: item.id, success: true });
        } catch (error) {
          results.push({ id: item.id, success: false, error: error.message });
        }
      }
      return results;
    },

    addAgentTasks: async (_, { input }, { dataSources, identity }) => {
      const results = [];
      for (const task of input) {
        try {
          const id = task.ataskid || task.id || generateId('task');
          const now = new Date().toISOString();
          const owner = task.owner || identity.sub;
          await dataSources.mysql.pool().execute(
            `INSERT INTO agent_tasks (id, name, owner, description, org_id, priority, status, task_type, objectives, schedule, trigger, created_at, updated_at)
             VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`,
            [id, task.name, owner, task.description || null, task.org_id || null,
             task.priority || 'medium', task.status || 'pending', task.task_type || null,
             task.objectives ? JSON.stringify(task.objectives) : null,
             task.schedule ? JSON.stringify(task.schedule) : null,
             task.trigger || null, now, now]
          );
          results.push({ id, success: true });
        } catch (error) {
          results.push({ id: task.id, success: false, error: error.message });
        }
      }
      return results;
    },

    updateAgentTasks: async (_, { input }, { dataSources }) => {
      const results = [];
      for (const task of input) {
        try {
          const updates = [], values = [];
          if (task.name !== undefined) { updates.push('name = ?'); values.push(task.name); }
          if (task.status !== undefined) { updates.push('status = ?'); values.push(task.status); }
          if (task.priority !== undefined) { updates.push('priority = ?'); values.push(task.priority); }
          if (task.objectives !== undefined) { updates.push('objectives = ?'); values.push(JSON.stringify(task.objectives)); }
          if (task.schedule !== undefined) { updates.push('schedule = ?'); values.push(JSON.stringify(task.schedule)); }
          if (task.progress !== undefined) { updates.push('progress = ?'); values.push(task.progress); }
          updates.push('updated_at = ?'); values.push(new Date().toISOString());
          values.push(task.ataskid || task.id);
          await dataSources.mysql.pool().execute(
            `UPDATE agent_tasks SET ${updates.join(', ')} WHERE id = ?`, values
          );
          results.push({ id: task.id, success: true });
        } catch (error) {
          results.push({ id: task.id, success: false, error: error.message });
        }
      }
      return results;
    },

    removeAgentTasks: async (_, { input }, { dataSources }) => {
      const results = [];
      for (const item of input) {
        try {
          await dataSources.mysql.pool().execute('DELETE FROM agent_tasks WHERE id = ?', [item.id]);
          results.push({ id: item.id, success: true });
        } catch (error) {
          results.push({ id: item.id, success: false, error: error.message });
        }
      }
      return results;
    },

    addVehicles: async (_, { input }, { dataSources, identity }) => {
      const results = [];
      for (const vehicle of input) {
        try {
          const id = vehicle.id || generateId('vehicle');
          const now = new Date().toISOString();
          const owner = vehicle.owner || identity.sub;
          await dataSources.mysql.pool().execute(
            `INSERT INTO agent_vehicles (id, name, owner, vehicle_type, platform, ip_address, capabilities, status, created_at, updated_at)
             VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`,
            [id, vehicle.name, owner, vehicle.vehicle_type || 'desktop',
             vehicle.platform || null, vehicle.ip_address || null,
             vehicle.capabilities ? JSON.stringify(vehicle.capabilities) : null,
             'offline', now, now]
          );
          results.push({ id, success: true });
        } catch (error) {
          results.push({ id: vehicle.id, success: false, error: error.message });
        }
      }
      return results;
    },

    updateVehicles: async (_, { input }, { dataSources }) => {
      const results = [];
      for (const vehicle of input) {
        try {
          const updates = [], values = [];
          if (vehicle.name !== undefined) { updates.push('name = ?'); values.push(vehicle.name); }
          if (vehicle.status !== undefined) { updates.push('status = ?'); values.push(vehicle.status); }
          if (vehicle.capabilities !== undefined) { updates.push('capabilities = ?'); values.push(JSON.stringify(vehicle.capabilities)); }
          updates.push('updated_at = ?'); values.push(new Date().toISOString());
          values.push(vehicle.id);
          await dataSources.mysql.pool().execute(
            `UPDATE agent_vehicles SET ${updates.join(', ')} WHERE id = ?`, values
          );
          results.push({ id: vehicle.id, success: true });
        } catch (error) {
          results.push({ id: vehicle.id, success: false, error: error.message });
        }
      }
      return results;
    },

    removeVehicles: async (_, { input }, { dataSources }) => {
      const results = [];
      for (const item of input) {
        try {
          await dataSources.mysql.pool().execute('DELETE FROM agent_vehicles WHERE id = ?', [item.id]);
          results.push({ id: item.id, success: true });
        } catch (error) {
          results.push({ id: item.id, success: false, error: error.message });
        }
      }
      return results;
    },

    updateSettings: async (_, { key, value }, { dataSources }) => {
      const val = typeof value === 'string' ? value : JSON.stringify(value);
      const now = new Date().toISOString();
      await dataSources.mysql.pool().execute(
        `INSERT INTO settings (\`key\`, value, updated_at) VALUES (?, ?, ?)
         ON DUPLICATE KEY UPDATE value = ?, updated_at = ?`,
        [key, val, now, val, now]
      );
      return val;
    },

    reqRAGStore: async (_, { input }) => {
      const params = typeof input === 'string' ? JSON.parse(input) : input;
      return JSON.stringify({ success: true, chunks: params.length || 0 });
    },

    runSkill: async (_, { input }) => {
      const params = typeof input === 'string' ? JSON.parse(input) : input;
      const runId = generateId('run');
      return { success: true, run_id: runId };
    },
  },

  Subscription: {
    onAgentUpdated: { subscribe: async () => ({ id: 1 }) },
    onAgentSkillUpdated: { subscribe: async () => ({ id: 1 }) },
    onTaskStatusChanged: { subscribe: async () => ({ id: 1 }) },
    onVehicleStatusChanged: { subscribe: async () => ({ id: 1 }) },
  },

  Agent: {
    title: (p) => parseJson(p.title),
    capabilities: (p) => parseJson(p.capabilities),
    extra_data: (p) => parseJson(p.extra_data),
  },
  AgentSkill: {
    config: (p) => parseJson(p.config),
    tags: (p) => parseJson(p.tags),
  },
  AgentTask: {
    objectives: (p) => parseJson(p.objectives),
    schedule: (p) => parseJson(p.schedule),
    result: (p) => parseJson(p.result),
  },
  Vehicle: {
    capabilities: (p) => parseJson(p.capabilities),
  },
};

module.exports = resolvers;
