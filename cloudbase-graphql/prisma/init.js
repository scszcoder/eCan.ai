/**
 * 数据库初始化脚本
 * 
 * 用于创建数据库表结构和基础数据
 * 
 * 使用方式：
 *   node prisma/init.js
 */

const { PrismaClient } = require('@prisma/client');

async function upsertOrg(data) {
  return prisma.org.upsert({
    where: { id: data.id },
    create: data,
    update: data,
  });
}

async function upsertSetting(key, value) {
  return prisma.setting.upsert({
    where: { owner_key: { owner: '__global__', key } },
    create: { key, value, owner: '__global__' },
    update: { value },
  });
}

async function main() {
  console.log('🚀 开始初始化数据库...\n');

  const prisma = new PrismaClient();

  try {
    // ============ 1. 创建基础组织结构（幂等） ============
    console.log('📁 创建组织结构...');

    await upsertOrg({
      id: 'org-root',
      name: 'eCan.ai 总部',
      description: 'eCan.ai 人工智能平台总部',
      orgType: 'root',
      level: 0,
      sortOrder: 0,
      status: 'active',
    });
    await upsertOrg({
      id: 'org-tech',
      name: '技术部',
      description: '负责技术研发',
      orgType: 'department',
      parentId: 'org-root',
      level: 1,
      sortOrder: 1,
      status: 'active',
    });
    await upsertOrg({
      id: 'org-ops',
      name: '运维部',
      description: '负责系统运维',
      orgType: 'department',
      parentId: 'org-root',
      level: 1,
      sortOrder: 2,
      status: 'active',
    });
    console.log('  ✓ 组织结构创建完成（幂等）\n');

    // ============ 2. 创建基础设置（幂等） ============
    console.log('⚙️  创建系统设置...');

    await upsertSetting('system.app_name', { value: 'eCan.ai', description: '应用名称' });
    await upsertSetting('system.version', { value: '1.0.0', description: '系统版本' });
    await upsertSetting('system.timezone', { value: 'Asia/Shanghai', description: '系统时区' });
    await upsertSetting('agent.default_status', { value: 'active', description: 'Agent 默认状态' });
    await upsertSetting('task.default_priority', { value: 'normal', description: '任务默认优先级' });
    console.log('  ✓ 系统设置创建完成（幂等）\n');

    // ============ 3. 创建示例 Agent（幂等） ============
    console.log('🤖 创建示例 Agent...');

    await prisma.agent.upsert({
      where: { id: 'agent-demo' },
      create: {
        id: 'agent-demo',
        owner: 'system',
        name: '演示助手',
        description: '这是一个演示用的 AI 助手',
        status: 'active',
        gender: 'unknown',
        capabilities: {
          chat: true,
          reasoning: true,
          toolUse: false,
        },
        personalities: ['helpful', 'friendly'],
        title: {
          zh: '演示助手',
          en: 'Demo Assistant',
        },
      },
      update: {},
    });
    console.log('  ✓ 示例 Agent 创建完成（幂等）\n');

    // ============ 4. 创建示例 Skill（幂等） ============
    console.log('🎯 创建示例 Skill...');

    await prisma.agentSkill.upsert({
      where: { id: 'skill-demo' },
      create: {
        id: 'skill-demo',
        owner: 'system',
        name: '基础对话',
        description: '提供基础的对话能力',
        category: 'core',
        tags: ['chat', 'conversation'],
        capabilities: ['text_response', 'emotion_recognition'],
        limitations: ['不支持多模态'],
        inputModes: ['text', 'voice'],
        outputModes: ['text', 'voice'],
        isPublic: true,
        status: 'active',
      },
      update: {},
    });
    console.log('  ✓ 示例 Skill 创建完成（幂等）\n');

    // ============ 5. 创建 Agent-Skill 关联（幂等） ============
    console.log('🔗 创建关联关系...');

    await prisma.agentSkillRel.upsert({
      where: { agentId_skillId: { agentId: 'agent-demo', skillId: 'skill-demo' } },
      create: {
        agentId: 'agent-demo',
        skillId: 'skill-demo',
        proficiencyLevel: 80,
        experiencePoints: 1000,
        usageCount: 50,
        successRate: 0.95,
        status: 'active',
        isFavorite: true,
        priority: 1,
      },
      update: {},
    });
    console.log('  ✓ Agent-Skill 关联创建完成（幂等）\n');

    console.log('✅ 数据库初始化完成！\n');
    console.log('📊 当前数据统计：');
    
    const counts = await Promise.all([
      prisma.agent.count(),
      prisma.agentSkill.count(),
      prisma.agentTask.count(),
      prisma.vehicle.count(),
      prisma.org.count(),
      prisma.prompt.count(),
      prisma.avatar.count(),
      prisma.agentKnowledge.count(),
      prisma.agentTool.count(),
      prisma.setting.count(),
    ]);
    
    console.log(`  - Agents: ${counts[0]}`);
    console.log(`  - Skills: ${counts[1]}`);
    console.log(`  - Tasks: ${counts[2]}`);
    console.log(`  - Vehicles: ${counts[3]}`);
    console.log(`  - Orgs: ${counts[4]}`);
    console.log(`  - Prompts: ${counts[5]}`);
    console.log(`  - Avatars: ${counts[6]}`);
    console.log(`  - Knowledges: ${counts[7]}`);
    console.log(`  - Tools: ${counts[8]}`);
    console.log(`  - Settings: ${counts[9]}\n`);

  } catch (error) {
    console.error('❌ 初始化失败:', error.message);
    throw error;
  } finally {
    await prisma.$disconnect();
  }
}

main()
  .then(() => {
    console.log('🎉 所有操作完成！');
    process.exit(0);
  })
  .catch((error) => {
    console.error('💥 发生错误:', error);
    process.exit(1);
  });
