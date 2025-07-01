export interface Agent {
  id: string;
  name: string;
  description: string;
  departmentId: string;
}

const agents: Agent[] = [
  { id: 'a1', name: '小明', description: '负责招聘', departmentId: 'hr' },
  { id: 'a2', name: '小红', description: '负责员工关系', departmentId: 'hr' },
  { id: 'a3', name: '小刚', description: '负责IT支持', departmentId: 'it' },
  { id: 'a4', name: '小美', description: '负责财务报表', departmentId: 'finance' },
  { id: 'a5', name: '小强', description: '负责销售策略', departmentId: 'sales' },
  // 可继续添加
];

export default agents; 